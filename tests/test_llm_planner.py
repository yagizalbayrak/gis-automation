"""LiteLLM planner adapter + HybridPlanner sanitization tests.

litellm.completion is always mocked: no test spends a token or touches
the network. What we test is the untrusted-data handling around the
model, which is where the safety actually lives.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ageo.application.agents.planner import HybridPlanner, PlannerDecision
from ageo.application.tools.errors import GatewayError
from ageo.infrastructure.llm import litellm_planner
from ageo.infrastructure.llm.litellm_planner import LiteLlmPlanner


def _completion_returning(content: str):
    def fake_completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    return fake_completion


@pytest.fixture
def catalog(workflows) -> list[dict]:
    return workflows.catalog()


def test_valid_json_response_is_parsed(monkeypatch, catalog) -> None:
    payload = {
        "workflow": "road_fetch_and_buffer",
        "params": {"place": "Kutahya", "street_name": "Ataturk", "buffer_m": 25.0},
        "confidence": 0.92,
        "explanation": "Road buffering request.",
    }
    monkeypatch.setattr(
        litellm_planner.litellm, "completion", _completion_returning(json.dumps(payload))
    )
    decision = LiteLlmPlanner(model="test/model").plan("buffer some roads", catalog)
    assert decision.workflow == "road_fetch_and_buffer"
    assert decision.params["buffer_m"] == 25.0
    assert decision.confidence == 0.92


def test_json_wrapped_in_prose_is_extracted(monkeypatch, catalog) -> None:
    content = 'Sure! Here is the plan:\n```json\n{"workflow": null, "params": {}, "confidence": 0.1, "explanation": "no match"}\n```'
    monkeypatch.setattr(
        litellm_planner.litellm, "completion", _completion_returning(content)
    )
    decision = LiteLlmPlanner(model="test/model").plan("gibberish", catalog)
    assert decision.workflow is None


def test_malformed_response_raises_gateway_error(monkeypatch, catalog) -> None:
    monkeypatch.setattr(
        litellm_planner.litellm, "completion", _completion_returning("I cannot help.")
    )
    with pytest.raises(GatewayError, match="malformed"):
        LiteLlmPlanner(model="test/model").plan("anything", catalog)


def test_out_of_range_confidence_is_clamped(monkeypatch, catalog) -> None:
    content = '{"workflow": null, "params": {}, "confidence": 7, "explanation": "x"}'
    monkeypatch.setattr(
        litellm_planner.litellm, "completion", _completion_returning(content)
    )
    assert LiteLlmPlanner(model="test/model").plan("x", catalog).confidence == 1.0


class StubLlm:
    def __init__(self, decision: PlannerDecision | None = None, error: Exception | None = None):
        self.decision = decision
        self.error = error
        self.calls = 0

    def plan(self, text, workflow_catalog):
        self.calls += 1
        if self.error:
            raise self.error
        return self.decision


def test_hybrid_falls_back_to_deterministic_when_llm_fails(workflows) -> None:
    llm = StubLlm(error=GatewayError("model down"))
    hybrid = HybridPlanner(workflows, llm=llm)
    decision = hybrid.plan("do something clever with my roads")
    assert llm.calls == 1
    assert decision.workflow is None  # deterministic result, not a crash


def test_hybrid_rejects_hallucinated_workflow(workflows) -> None:
    llm = StubLlm(decision=PlannerDecision(
        workflow="delete_all_data",  # not in the registry
        params={"x": 1},
        confidence=0.99,
        explanation="hallucination",
    ))
    hybrid = HybridPlanner(workflows, llm=llm)
    decision = hybrid.plan("unmatched text")
    assert decision.workflow is None  # fell back to deterministic


def test_hybrid_drops_unknown_params_and_recomputes_missing(workflows) -> None:
    llm = StubLlm(decision=PlannerDecision(
        workflow="road_fetch_and_buffer",
        params={"place": "Kutahya", "rm_rf": "/", "buffer_m": 25.0},
        missing_params=(),  # LLM claims nothing is missing - it is wrong
        confidence=0.8,
        explanation="llm",
    ))
    hybrid = HybridPlanner(workflows, llm=llm)
    decision = hybrid.plan("unmatched text so llm is consulted")
    assert decision.workflow == "road_fetch_and_buffer"
    assert "rm_rf" not in decision.params
    # registry, not the LLM, decides what is still required
    assert decision.missing_params == ("street_name",)
