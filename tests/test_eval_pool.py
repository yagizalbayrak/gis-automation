"""Scenario pool integrity + harness routing/classification (offline)."""
from __future__ import annotations

import pytest

from ageo.evals.harness import (
    COMPOSED_CLARIFICATION,
    COMPOSED_GEODETIC,
    COMPOSED_REFUSED,
    COMPOSED_SCHEMA,
    COMPOSED_UNKNOWN_TOOL,
    NEEDS_INPUT,
    NO_LLM,
    REGISTERED,
    EvalRunner,
    load_scenarios,
)

VALID_EXPECTS = {"registered", "needs_input", "composed", "gap", "clarification"}


def test_pool_integrity() -> None:
    scenarios = load_scenarios()
    assert len(scenarios) == 50
    ids = [s["id"] for s in scenarios]
    assert len(set(ids)) == 50
    for s in scenarios:
        assert s["expect"] in VALID_EXPECTS, s["id"]
        assert 2 <= s["difficulty"] <= 5, s["id"]  # no trivial scenarios
        assert s["prompt"].strip(), s["id"]
        assert s["lang"] in ("tr", "en"), s["id"]
        if s["expect"] == "gap":
            assert s["gaps"], f"{s['id']}: gap scenario must name missing capabilities"


def test_pool_difficulty_and_language_spread() -> None:
    scenarios = load_scenarios()
    hard = [s for s in scenarios if s["difficulty"] >= 4]
    turkish = [s for s in scenarios if s["lang"] == "tr"]
    assert len(hard) >= 20          # the pool must skew non-trivial
    assert 20 <= len(turkish) <= 40  # both languages well represented


def test_deterministic_routing_offline() -> None:
    """Registered/needs_input scenarios route WITHOUT any LLM."""
    runner = EvalRunner(use_llm=False)
    scenarios = {s["id"]: s for s in load_scenarios()}

    assert runner.run_scenario(scenarios["S01"]).outcome == REGISTERED
    assert runner.run_scenario(scenarios["S02"]).outcome == REGISTERED
    assert runner.run_scenario(scenarios["S04"]).outcome == NEEDS_INPUT
    # composed scenario without an LLM ends as unmatched_no_llm, honestly
    assert runner.run_scenario(scenarios["S05"]).outcome == NO_LLM


def test_composer_error_classification() -> None:
    classify = EvalRunner._classify_composer_error
    assert classify(
        "x.step1: unknown tool 'calculate_area'"
    ) == COMPOSED_UNKNOWN_TOOL
    assert classify(
        "requires a projected metric CRS but the chain proves geographic"
    ) == COMPOSED_GEODETIC
    assert classify("Composed plan does not fit the plan schema: ...") == COMPOSED_SCHEMA
    assert classify("plan has 40 steps; limit is 15") == COMPOSED_SCHEMA
    assert classify(
        "plan_refused: no tool exists for slope analysis"
    ) == COMPOSED_REFUSED


def test_empty_plan_is_an_honest_refusal_without_retry(crs_info) -> None:
    """An empty-steps plan carries the model's reason and must NOT be
    retried - the capability is missing, feedback cannot fix that."""
    from ageo.application.agents.composer import PlanComposer
    from ageo.application.rag.store import RecipeStore
    from ageo.application.tools.errors import ComposerError
    from ageo.application.tools.registry import registry

    class RefusingLlm:
        calls = 0

        def compose(
            self, text, tool_catalog, recipes, feedback, *, profile=None,
            clarification_answer=None,
        ):
            self.calls += 1
            return {
                "name": "cannot_do",
                "summary": "No tool exists for DEM slope analysis.",
                "steps": [],
                "outputs": {},
            }

    llm = RefusingLlm()
    composer = PlanComposer(llm, registry, crs_info, RecipeStore())
    with pytest.raises(ComposerError, match="plan_refused: No tool exists"):
        composer.compose("slope analysis please")
    assert llm.calls == 1  # refusal is terminal, not retried


def test_composer_clarification_is_classified_and_scenario_pool_expects_it() -> None:
    """The harness must classify a ComposerClarificationRequired as its own
    outcome, and the S26 degree/metre trap scenario must now expect it."""

    class ClarifyingLlm:
        def compose(
            self, text, tool_catalog, recipes, feedback, *, profile=None,
            clarification_answer=None,
        ) -> dict:
            return {
                "clarification": {
                    "reason": "0.001 degrees is not a fixed distance",
                    "question": {
                        "en": "Did you mean ~111 m?",
                        "tr": "111 m mi demek istediniz?",
                    },
                    "options": [
                        {"value": 111, "label": {"en": "111 m", "tr": "111 m"}, "recommended": True}
                    ],
                }
            }

    runner = EvalRunner(use_llm=True)
    runner.recording._inner = ClarifyingLlm()  # replace the real LiteLlmComposer
    outcome, _ = runner._route("0.001 derece tampon")
    assert outcome == COMPOSED_CLARIFICATION

    scenarios = {s["id"]: s for s in load_scenarios()}
    assert scenarios["S26"]["expect"] == "clarification"
