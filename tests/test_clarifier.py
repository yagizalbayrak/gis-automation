"""Clarifier tests: the gating matrix that turns missing/defaulted
workflow params into structured questions or ledger assumptions, purely
by autonomy_preference - zero LLM tokens, all offline."""
from __future__ import annotations

import pytest

from ageo.application.agents.clarifier import build_questions
from ageo.application.workflows.defs import CRS_NORMALIZATION, ROAD_FETCH_AND_BUFFER
from ageo.domain.value_objects.user_profile import AutonomyPreference, UserProfile

_ALL_AUTONOMY = (
    AutonomyPreference.GUIDED,
    AutonomyPreference.AUTONOMOUS,
    AutonomyPreference.STRICT_CONFIRM,
)


def _profile(autonomy: AutonomyPreference) -> UserProfile:
    return UserProfile(autonomy_preference=autonomy)


@pytest.mark.parametrize("autonomy", _ALL_AUTONOMY)
def test_required_params_are_critical_blocking_questions_under_every_autonomy(
    autonomy,
) -> None:
    questions, assumptions = build_questions(
        ROAD_FETCH_AND_BUFFER, {}, _profile(autonomy)
    )
    required_questions = [q for q in questions if q.param != "target_srid"]
    assert [q.param for q in required_questions] == ["place", "street_name", "buffer_m"]
    for q in required_questions:
        assert q.question_type == "parameter"
        assert q.severity == "critical"
        assert q.blocking is True
        assert q.default_if_skipped is None
        assert q.options == ()
        assert q.question_id == f"q_param_{q.param}"
    assert not any(a.param in {"place", "street_name", "buffer_m"} for a in assumptions)


@pytest.mark.parametrize("autonomy", [AutonomyPreference.GUIDED, AutonomyPreference.AUTONOMOUS])
def test_spec_default_becomes_assumption_for_guided_and_autonomous(autonomy) -> None:
    provided = {"place": "Kutahya", "street_name": "Ataturk", "buffer_m": 25.0}
    questions, assumptions = build_questions(
        ROAD_FETCH_AND_BUFFER, provided, _profile(autonomy)
    )
    assert questions == []
    assert len(assumptions) == 1
    assumption = assumptions[0]
    assert assumption.param == "target_srid"
    assert assumption.value == "EPSG:5254"
    assert assumption.source == "spec_default"


def test_spec_default_becomes_risk_confirmation_for_strict_confirm() -> None:
    provided = {"place": "Kutahya", "street_name": "Ataturk", "buffer_m": 25.0}
    questions, assumptions = build_questions(
        ROAD_FETCH_AND_BUFFER, provided, _profile(AutonomyPreference.STRICT_CONFIRM)
    )
    assert assumptions == []
    assert len(questions) == 1
    question = questions[0]
    assert question.question_id == "q_confirm_target_srid"
    assert question.question_type == "risk_confirmation"
    assert question.severity == "material"  # srid_metric kind
    assert question.blocking is True
    assert question.default_if_skipped == "EPSG:5254"
    assert len(question.options) == 1
    assert question.options[0].value == "EPSG:5254"
    assert question.options[0].recommended is True


def test_non_srid_default_is_cosmetic_under_strict_confirm() -> None:
    provided = {
        "path": "/tmp/in.shp",
        "target_srid": "EPSG:5254",
        "output_dir": "/tmp/out",
    }
    questions, assumptions = build_questions(
        CRS_NORMALIZATION, provided, _profile(AutonomyPreference.STRICT_CONFIRM)
    )
    assert assumptions == []
    assert len(questions) == 1
    assert questions[0].param == "output_name"
    assert questions[0].severity == "cosmetic"


@pytest.mark.parametrize("autonomy", _ALL_AUTONOMY)
def test_user_supplied_value_suppresses_question_and_assumption(autonomy) -> None:
    provided = {
        "place": "Kutahya",
        "street_name": "Ataturk",
        "buffer_m": 25.0,
        "target_srid": "EPSG:5254",
    }
    questions, assumptions = build_questions(
        ROAD_FETCH_AND_BUFFER, provided, _profile(autonomy)
    )
    assert questions == []
    assert assumptions == []


def test_texts_carry_english_and_turkish() -> None:
    questions, assumptions = build_questions(
        ROAD_FETCH_AND_BUFFER, {}, _profile(AutonomyPreference.STRICT_CONFIRM)
    )
    for q in questions:
        assert q.text["en"]
        assert q.text["tr"]
        for option in q.options:
            assert option.label["en"]
            assert option.label["tr"]
    target_srid_question = next(q for q in questions if q.param == "target_srid")
    assert "TUREF/TM30" in target_srid_question.text["en"]

    _, assumptions = build_questions(
        ROAD_FETCH_AND_BUFFER,
        {"place": "Kutahya", "street_name": "Ataturk", "buffer_m": 25.0},
        _profile(AutonomyPreference.GUIDED),
    )
    for a in assumptions:
        assert a.text["en"]
        assert a.text["tr"]


def test_models_serialize_to_json() -> None:
    questions, _ = build_questions(
        ROAD_FETCH_AND_BUFFER, {}, _profile(AutonomyPreference.STRICT_CONFIRM)
    )
    for q in questions:
        dumped = q.model_dump(mode="json")
        assert "param" in dumped
        assert "text" in dumped

    _, assumptions = build_questions(
        ROAD_FETCH_AND_BUFFER,
        {"place": "Kutahya", "street_name": "Ataturk", "buffer_m": 25.0},
        _profile(AutonomyPreference.GUIDED),
    )
    for a in assumptions:
        dumped = a.model_dump(mode="json")
        assert "param" in dumped
        assert "text" in dumped
