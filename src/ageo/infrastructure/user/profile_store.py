"""Persisted user profile: role, GIS skill level, autonomy preference,
explanation depth, language.

Single-tenant, like LlmConfigStore: this is the owner's own workbench,
not a multi-user system, so there is one profile file, no per-user
keying. Users configure it from the web UI Settings panel; adapters read
the live profile on every call - saving takes effect immediately.

Unlike LlmConfigStore, a missing or unreadable profile file is not an
error: it just means "use safe defaults", so there is no env-var
fallback and no effective()/is_configured() pair - get_or_default() is
the only read method callers need. The file holds no secret, so unlike
llm_settings.json it is not chmod 600.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

from ageo.domain.value_objects.user_profile import (
    AutonomyPreference,
    CrsAwareness,
    ExplanationDepth,
    GisLevel,
    ProfileLanguage,
    UserProfile,
    UserRole,
)

DEFAULT_PROFILE_PATH = Path.home() / ".ageo" / "user_profile.json"


class UserProfileStore:
    """Thread-safe, file-backed store for the active user profile."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_PROFILE_PATH
        self._lock = threading.Lock()

    def get(self) -> UserProfile | None:
        with self._lock:
            if not self._path.exists():
                return None
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                return UserProfile(
                    role=UserRole(payload["role"]),
                    gis_level=GisLevel(payload["gis_level"]),
                    crs_awareness=CrsAwareness(payload["crs_awareness"]),
                    autonomy_preference=AutonomyPreference(
                        payload["autonomy_preference"]
                    ),
                    explanation_depth=ExplanationDepth(
                        payload["explanation_depth"]
                    ),
                    language=ProfileLanguage(payload["language"]),
                )
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                return None

    def get_or_default(self) -> UserProfile:
        return self.get() or UserProfile()

    def save(self, profile: UserProfile) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(asdict(profile), indent=2), encoding="utf-8"
            )
