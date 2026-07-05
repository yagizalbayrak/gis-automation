"""GET/PUT /settings/profile: defaults, roundtrip, full-replace semantics,
validation - all offline, no LLM involved."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ageo.interface.api.app import create_app
from conftest import FakeOsmGateway

_VALID_PAYLOAD = {
    "role": "urban_planner",
    "gis_level": "intermediate",
    "crs_awareness": "high",
    "autonomy_preference": "autonomous",
    "explanation_depth": "technical_audit",
    "language": "tr",
}


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = create_app(
        osm_gateway=FakeOsmGateway(),
        upload_dir=str(tmp_path / "uploads"),
        settings_path=str(tmp_path / "llm_settings.json"),
        profile_path=str(tmp_path / "user_profile.json"),
    )
    return TestClient(app)


def test_get_profile_returns_defaults_when_unset(client) -> None:
    response = client.get("/settings/profile").json()
    assert response == {
        "role": "non_technical_user",
        "gis_level": "beginner",
        "crs_awareness": "low",
        "autonomy_preference": "guided",
        "explanation_depth": "plain_language",
        "language": "en",
    }


def test_put_profile_roundtrip(client) -> None:
    updated = client.put("/settings/profile", json=_VALID_PAYLOAD).json()
    assert updated == _VALID_PAYLOAD
    assert client.get("/settings/profile").json() == _VALID_PAYLOAD


def test_put_profile_rejects_invalid_enum_value(client) -> None:
    payload = {**_VALID_PAYLOAD, "role": "wizard"}
    response = client.put("/settings/profile", json=payload)
    assert response.status_code == 422


def test_put_profile_rejects_missing_field(client) -> None:
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "language"}
    response = client.put("/settings/profile", json=payload)
    assert response.status_code == 422


def test_put_profile_rejects_unknown_field(client) -> None:
    payload = {**_VALID_PAYLOAD, "extra_field": "nope"}
    response = client.put("/settings/profile", json=payload)
    assert response.status_code == 422
