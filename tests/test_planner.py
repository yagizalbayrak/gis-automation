"""Planner tests: deterministic selection/extraction, HIL missing params,
LLM fallback seam, and planner->runner integration."""
from __future__ import annotations

import pytest

from ageo.application.agents.planner import (
    DeterministicPlanner,
    HybridPlanner,
    PlannerDecision,
)


@pytest.fixture
def planner(workflows) -> DeterministicPlanner:
    return DeterministicPlanner(workflows)


def test_turkish_buffer_command_fully_extracted(planner) -> None:
    decision = planner.plan(
        'Kutahya\'daki "Ataturk Caddesi" icin 25 m buffer uygula'
    )
    assert decision.workflow == "road_fetch_and_buffer"
    assert decision.params["place"] == "Kutahya"
    assert decision.params["street_name"] == "Ataturk Caddesi"
    assert decision.params["buffer_m"] == 25.0
    assert decision.ready


def test_turkish_diacritics_fold_onto_patterns(planner) -> None:
    decision = planner.plan("Kütahya'daki tüm yolları haritaya çek")
    assert decision.workflow == "road_fetch_and_buffer"
    assert decision.params["place"] == "Kütahya"


def test_ambiguous_request_reports_missing_params_instead_of_guessing(planner) -> None:
    decision = planner.plan("Kutahya'daki tum yollari haritaya cek")
    assert decision.workflow == "road_fetch_and_buffer"
    assert set(decision.missing_params) == {"street_name", "buffer_m"}
    assert not decision.ready


def test_quality_check_with_path(planner) -> None:
    decision = planner.plan("please run a quality check on /data/parcels.shp")
    assert decision.workflow == "preflight_quality_check"
    assert decision.params["path"] == "/data/parcels.shp"
    assert decision.ready


def test_unmatched_request_yields_no_workflow(planner) -> None:
    decision = planner.plan("what is the meaning of life?")
    assert decision.workflow is None
    assert decision.confidence == 0.0


class FakeLlmPlanner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def plan(self, text: str, workflow_catalog: list[dict]) -> PlannerDecision:
        self.calls.append(text)
        assert any(w["name"] == "road_fetch_and_buffer" for w in workflow_catalog)
        return PlannerDecision(
            workflow="road_fetch_and_buffer",
            params={"place": "Kutahya"},
            missing_params=("street_name", "buffer_m"),
            confidence=0.9,
            explanation="llm fallback",
        )


def test_hybrid_planner_calls_llm_only_when_needed(workflows) -> None:
    llm = FakeLlmPlanner()
    hybrid = HybridPlanner(workflows, llm=llm)

    ready = hybrid.plan('Kutahya\'daki "Ataturk Caddesi" icin 25 m buffer uygula')
    assert ready.ready
    assert llm.calls == []  # deterministic path spent zero tokens

    fallback = hybrid.plan("do something clever with my roads")
    assert fallback.explanation == "llm fallback"
    assert len(llm.calls) == 1


def test_planner_decision_drives_runner_end_to_end(planner, runner, ctx) -> None:
    decision = planner.plan(
        'Kutahya\'daki "Ataturk" icin 25 m buffer uygula'
    )
    assert decision.ready
    outputs = runner.run(decision.workflow, decision.params)
    buffered = ctx.read(outputs["buffered"])
    assert len(buffered) == 1
    assert buffered.crs.to_epsg() == 4326
