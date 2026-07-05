"""LLM settings: config store persistence, masked keys, API endpoints and
the connection-test endpoint (litellm mocked - no tokens, no network)."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ageo.application.tools.errors import GatewayError
from ageo.infrastructure.llm import config as llm_config
from ageo.infrastructure.llm.config import LlmConfig, LlmConfigStore
from ageo.interface.api.app import create_app
from conftest import FakeOsmGateway


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(
        osm_gateway=FakeOsmGateway(),
        upload_dir=str(tmp_path / "uploads"),
        settings_path=str(tmp_path / "llm_settings.json"),
        profile_path=str(tmp_path / "user_profile.json"),
    )
    return TestClient(app)


def test_config_store_roundtrip_and_permissions(tmp_path) -> None:
    path = tmp_path / "llm.json"
    store = LlmConfigStore(path)
    assert store.get() is None
    with pytest.raises(GatewayError, match="Settings"):
        store.effective("AGEO_COMPOSER_MODEL")

    store.save(LlmConfig(
        provider="gemini", model="gemini/gemini-2.5-flash", api_key="secret-abcd"
    ))
    loaded = store.get()
    assert loaded.model == "gemini/gemini-2.5-flash"
    assert loaded.masked_key() == "••••abcd"
    assert oct(path.stat().st_mode)[-3:] == "600"
    assert store.effective("AGEO_COMPOSER_MODEL").api_key == "secret-abcd"


def test_project_env_file_supplies_llm_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGEO_DISABLE_DOTENV", raising=False)
    monkeypatch.delenv("AGEO_COMPOSER_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm_config, "_ENV_LOADED", False)
    (tmp_path / ".env").write_text(
        "\n".join([
            "GEMINI_API_KEY=AIza-test-env-key",
            "AGEO_COMPOSER_MODEL=gemini/gemini-2.5-flash",
        ]),
        encoding="utf-8",
    )

    effective = LlmConfigStore(
        tmp_path / "missing.json", load_dotenv=True
    ).effective(
        "AGEO_COMPOSER_MODEL"
    )

    assert effective.model == "gemini/gemini-2.5-flash"
    assert effective.api_key is None  # LiteLLM reads provider env keys directly.
    assert os.environ["GEMINI_API_KEY"] == "AIza-test-env-key"


def test_settings_endpoints_never_echo_the_key(client) -> None:
    initial = client.get("/settings/llm").json()
    assert initial["configured"] is False
    assert "gemini" in initial["providers"]

    saved = client.put("/settings/llm", json={
        "provider": "gemini",
        "model": "gemini/gemini-2.5-flash",
        "api_key": "AIza-test-key-1234",
    }).json()
    assert saved["configured"] is True
    assert saved["model"] == "gemini/gemini-2.5-flash"
    assert saved["api_key_masked"] == "••••1234"
    assert "AIza-test-key-1234" not in str(saved)


def test_partial_update_keeps_saved_key(client) -> None:
    client.put("/settings/llm", json={
        "provider": "gemini",
        "model": "gemini/gemini-2.5-flash",
        "api_key": "AIza-test-key-1234",
    })
    # switch model without re-sending the key
    updated = client.put("/settings/llm", json={
        "provider": "gemini",
        "model": "gemini/gemini-2.5-pro",
    }).json()
    assert updated["model"] == "gemini/gemini-2.5-pro"
    assert updated["api_key_masked"] == "••••1234"


def test_connection_test_unconfigured(client) -> None:
    result = client.post("/settings/llm/test").json()
    assert result["ok"] is False
    assert "Save settings" in result["message"]


def test_connection_test_success_and_failure(client, monkeypatch) -> None:
    client.put("/settings/llm", json={
        "provider": "gemini",
        "model": "gemini/gemini-2.5-flash",
        "api_key": "AIza-test-key-1234",
    })

    import litellm

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)
    result = client.post("/settings/llm/test").json()
    assert result["ok"] is True
    assert result["model"] == "gemini/gemini-2.5-flash"
    assert captured["api_key"] == "AIza-test-key-1234"  # saved key is used

    def broken_completion(**kwargs):
        raise RuntimeError("401 API key not valid. Please pass a valid API key.")

    monkeypatch.setattr(litellm, "completion", broken_completion)
    result = client.post("/settings/llm/test").json()
    assert result["ok"] is False
    assert "API key not valid" in result["message"]

    def gemini_style_error(**kwargs):
        # real provider errors bury the actionable reason inside a JSON blob
        raise RuntimeError(
            'litellm.AuthenticationError: GeminiException - {\n  "error": {\n'
            '    "code": 400,\n    "message": "API key expired. Please renew '
            'the API key.",\n    "status": "INVALID_ARGUMENT"\n  }\n}'
        )

    monkeypatch.setattr(litellm, "completion", gemini_style_error)
    result = client.post("/settings/llm/test").json()
    assert result["ok"] is False
    assert "API key expired" in result["message"]  # reason surfaced, not truncated


def test_composed_request_without_llm_guides_to_settings(client) -> None:
    response = client.post("/tasks?wait=true", json={
        "text": "find suitable areas near schools in Kutahya for a new clinic"
    }).json()
    assert response["status"] == "unmatched"
    assert "Settings" in response["error"]
