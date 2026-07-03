"""Runtime LLM configuration: which model, which key, which endpoint.

Users configure this from the web UI (Settings panel); it persists to a
local JSON file with owner-only permissions. Adapters read the LIVE
configuration on every call, so saving new settings takes effect
immediately - no restart.

Resolution order for the effective configuration:
1. explicit constructor override (tests),
2. the saved settings file,
3. environment (AGEO_*_MODEL + provider env keys, for headless deployments).

The API key is never returned to clients in full - only a masked suffix.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from ageo.application.tools.errors import GatewayError

DEFAULT_SETTINGS_PATH = Path.home() / ".ageo" / "llm_settings.json"
_ENV_LOADED = False

# Provider presets surfaced in the UI. Model ids are LiteLLM identifiers.
PROVIDER_PRESETS: dict[str, dict] = {
    "gemini": {
        "label": "Google Gemini",
        "models": ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"],
        "key_hint": "Google AI Studio API key",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "models": [
            "anthropic/claude-haiku-4-5-20251001",
            "anthropic/claude-sonnet-5",
        ],
        "key_hint": "Anthropic API key",
    },
    "openai": {
        "label": "OpenAI",
        "models": ["gpt-4.1-mini", "gpt-4.1"],
        "key_hint": "OpenAI API key",
    },
    "custom": {
        "label": "Custom (any LiteLLM model id)",
        "models": [],
        "key_hint": "Provider API key",
    },
}


@dataclass(frozen=True)
class LlmConfig:
    provider: str            # gemini | anthropic | openai | custom
    model: str               # LiteLLM model id, e.g. "gemini/gemini-2.5-flash"
    api_key: str | None = None
    api_base: str | None = None

    def masked_key(self) -> str | None:
        if not self.api_key:
            return None
        return "••••" + self.api_key[-4:]

    def completion_kwargs(self) -> dict:
        """Per-call kwargs for litellm.completion. api_key=None lets litellm
        fall back to provider environment variables."""
        kwargs: dict = {"model": self.model}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        return kwargs


class LlmConfigStore:
    """Thread-safe, file-backed store for the active LLM configuration."""

    def __init__(
        self, path: Path | str | None = None, load_dotenv: bool | None = None
    ) -> None:
        self._path = Path(path) if path else DEFAULT_SETTINGS_PATH
        self._load_dotenv = (path is None) if load_dotenv is None else load_dotenv
        self._use_environment = path is None or self._load_dotenv
        self._lock = threading.Lock()

    def get(self) -> LlmConfig | None:
        with self._lock:
            if not self._path.exists():
                return None
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                return LlmConfig(
                    provider=str(payload.get("provider", "custom")),
                    model=str(payload["model"]),
                    api_key=payload.get("api_key") or None,
                    api_base=payload.get("api_base") or None,
                )
            except (json.JSONDecodeError, KeyError, OSError):
                return None

    def save(self, config: LlmConfig) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(asdict(config), indent=2), encoding="utf-8"
            )
            os.chmod(self._path, 0o600)  # owner-only: the file holds a secret

    def effective(self, env_model_var: str) -> LlmConfig:
        """The configuration adapters should use right now, or a clear error
        telling the user to open Settings."""
        saved = self.get()
        if saved is not None:
            return saved
        if self._load_dotenv:
            _load_project_env()
        env_model = os.environ.get(env_model_var) if self._use_environment else None
        if env_model:
            # key resolution deferred to litellm's provider env variables
            return LlmConfig(provider="custom", model=env_model)
        raise GatewayError(
            "llm_not_configured: no model/API key set. Open Settings in the "
            "web UI (or set the "
            f"{env_model_var} environment variable) to enable AI planning."
        )

    def is_configured(self, env_model_var: str) -> bool:
        try:
            self.effective(env_model_var)
            return True
        except GatewayError:
            return False


def _load_project_env() -> None:
    """Load simple KEY=VALUE pairs from the nearest project .env file.

    This intentionally does not override real shell environment variables.
    It is a small, dependency-free loader for local development credentials.
    """
    global _ENV_LOADED
    if os.environ.get("AGEO_DISABLE_DOTENV") == "1":
        return
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    for path in _candidate_env_paths():
        if path.exists():
            _apply_env_file(path)
            return


def _candidate_env_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    for base in (Path.cwd(), *_PROJECT_ROOTS):
        paths.extend(parent / ".env" for parent in (base, *base.parents))
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return tuple(deduped)


_PROJECT_ROOTS = (Path(__file__).resolve().parents[4],)


def _apply_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and value and key not in os.environ:
            os.environ[key] = value
