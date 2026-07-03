"""Scenario evaluation harness for the planner/composer ladder.

Feeds the scenario pool through EXACTLY the production routing logic
(DeterministicPlanner -> HybridPlanner LLM fallback -> PlanComposer) and
classifies each outcome so we can see, in aggregate:

- which requests the deterministic layer already handles,
- which the composer plans successfully (and with which tools),
- which fail because a TOOL IS MISSING (the build list for the registry),
- which fail validation (geodetic/structural) even after the retry,
- which the model cannot plan at all.

Plans are validated statically but NOT executed: evaluation costs LLM
calls only, never Overpass load. Run with:

    uv run python -m ageo.evals              # full pool, live LLM if configured
    uv run python -m ageo.evals --no-llm     # deterministic layer only
    uv run python -m ageo.evals --only S05 S28
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import ageo.application.tools.impl  # noqa: F401 - registers tools
from ageo.application.agents.composer import LlmComposerPort, PlanComposer, plan_preview
from ageo.application.agents.planner import DeterministicPlanner
from ageo.application.rag.store import RecipeStore
from ageo.application.tools.errors import ComposerError, GatewayError
from ageo.application.tools.registry import registry as tool_registry
from ageo.application.workflows.defs import register_bundled
from ageo.application.workflows.registry import WorkflowRegistry
from ageo.infrastructure.gis.crs_info import PyprojCrsInfo
from ageo.infrastructure.llm.config import LlmConfigStore

_UNKNOWN_TOOL = re.compile(r"unknown tool '([^']+)'")

# Outcome vocabulary (stable keys for aggregation)
REGISTERED = "registered"
NEEDS_INPUT = "needs_input"
COMPOSED_OK = "composed_ok"
COMPOSED_REFUSED = "composed_refused"  # empty plan + stated missing capability
COMPOSED_UNKNOWN_TOOL = "composed_error_unknown_tool"
COMPOSED_GEODETIC = "composed_error_geodetic"
COMPOSED_STRUCTURAL = "composed_error_structural"
COMPOSED_SCHEMA = "composed_error_schema"
LLM_MALFORMED = "llm_malformed_response"  # truncated/broken JSON from the model
LLM_UNAVAILABLE = "llm_unavailable"
NO_LLM = "unmatched_no_llm"

# expected route -> outcomes that confirm the expectation
_EXPECT_OK = {
    "registered": {REGISTERED},
    "needs_input": {NEEDS_INPUT},
    "composed": {COMPOSED_OK},
    # a gap scenario is "working as intended" when the system surfaces the
    # missing capability (explicit refusal or unknown-tool rejection). A
    # composed_ok on a gap scenario needs MANUAL review - it may be a fake
    # substitute (e.g. buffer posing as isochrone), so it does not count.
    "gap": {COMPOSED_REFUSED, COMPOSED_UNKNOWN_TOOL},
}


def load_scenarios() -> list[dict]:
    payload = json.loads(
        resources.files("ageo.evals").joinpath("scenarios.json").read_text("utf-8")
    )
    return payload["scenarios"]


class RecordingComposerLlm:
    """Wraps the real composer LLM and records every raw plan + feedback,
    so failed attempts remain analyzable after the run."""

    def __init__(self, inner: LlmComposerPort) -> None:
        self._inner = inner
        self.attempts: list[dict] = []

    def reset(self) -> None:
        self.attempts = []

    def compose(self, text, tool_catalog, recipes, feedback):
        payload = self._inner.compose(text, tool_catalog, recipes, feedback)
        self.attempts.append({"feedback_in": feedback, "plan_out": payload})
        return payload


@dataclass
class EvalResult:
    scenario_id: str
    outcome: str
    expected: str
    matches_expectation: bool
    detail: dict[str, Any] = field(default_factory=dict)


class EvalRunner:
    def __init__(self, use_llm: bool = True) -> None:
        self.crs_info = PyprojCrsInfo()
        self.workflows = WorkflowRegistry(tool_registry, self.crs_info)
        register_bundled(self.workflows)
        self.planner = DeterministicPlanner(self.workflows)

        self.recording: RecordingComposerLlm | None = None
        self.composer: PlanComposer | None = None
        if use_llm:
            from ageo.infrastructure.llm.litellm_composer import LiteLlmComposer

            self.recording = RecordingComposerLlm(LiteLlmComposer(LlmConfigStore()))
            self.composer = PlanComposer(
                self.recording, tool_registry, self.crs_info, RecipeStore()
            )

    def run_scenario(self, scenario: dict) -> EvalResult:
        outcome, detail = self._route(scenario["prompt"])
        expected = scenario["expect"]
        return EvalResult(
            scenario_id=scenario["id"],
            outcome=outcome,
            expected=expected,
            matches_expectation=outcome in _EXPECT_OK.get(expected, set()),
            detail=detail,
        )

    def _route(self, text: str) -> tuple[str, dict]:
        decision = self.planner.plan(text)
        if decision.workflow is not None:
            if decision.ready:
                return REGISTERED, {
                    "workflow": decision.workflow,
                    "params": decision.params,
                }
            return NEEDS_INPUT, {
                "workflow": decision.workflow,
                "params": decision.params,
                "missing_params": list(decision.missing_params),
            }

        if self.composer is None:
            return NO_LLM, {}

        self.recording.reset()
        started = time.monotonic()
        try:
            composed = self.composer.compose(text)
        except ComposerError as exc:
            return self._classify_composer_error(str(exc)), {
                "error": str(exc),
                "attempts": self.recording.attempts,
                "elapsed_s": round(time.monotonic() - started, 1),
            }
        except GatewayError as exc:
            outcome = (
                LLM_MALFORMED if "malformed" in str(exc) else LLM_UNAVAILABLE
            )
            return outcome, {"error": str(exc)}

        spec = composed.spec
        return COMPOSED_OK, {
            "plan_name": spec.name,
            "attempts": composed.attempts,
            "step_count": len(spec.steps),
            "tools_used": sorted({step.tool for step in spec.steps}),
            "plan": plan_preview(spec),
            "outputs": dict(spec.outputs),
            "retry_feedback": [a["feedback_in"] for a in self.recording.attempts if a["feedback_in"]],
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    @staticmethod
    def _classify_composer_error(message: str) -> str:
        if "plan_refused" in message:
            return COMPOSED_REFUSED
        if _UNKNOWN_TOOL.search(message):
            return COMPOSED_UNKNOWN_TOOL
        if "metric" in message or "geographic" in message:
            return COMPOSED_GEODETIC
        if "schema" in message or "no steps" in message or "limit" in message:
            return COMPOSED_SCHEMA
        return COMPOSED_STRUCTURAL


def missing_tools(results: list[EvalResult]) -> Counter:
    """Aggregate hallucinated/missing tool names across all failed attempts:
    this is the prioritized build list for the tool registry."""
    counter: Counter = Counter()
    for result in results:
        error = result.detail.get("error", "")
        counter.update(_UNKNOWN_TOOL.findall(error))
        for attempt_feedback in result.detail.get("retry_feedback", []):
            counter.update(_UNKNOWN_TOOL.findall(attempt_feedback or ""))
    return counter


def summarize(results: list[EvalResult]) -> str:
    lines: list[str] = ["", "=" * 64, "EVALUATION SUMMARY", "=" * 64]
    by_outcome = Counter(r.outcome for r in results)
    for outcome, count in by_outcome.most_common():
        lines.append(f"  {outcome:32s} {count}")
    matched = sum(1 for r in results if r.matches_expectation)
    lines.append(f"\n  expectation matches: {matched}/{len(results)}")

    mismatches = [r for r in results if not r.matches_expectation]
    if mismatches:
        lines.append("\n  MISMATCHES (expected -> got):")
        for r in mismatches:
            lines.append(f"    {r.scenario_id}: {r.expected} -> {r.outcome}")

    gaps = missing_tools(results)
    if gaps:
        lines.append("\n  MISSING/HALLUCINATED TOOLS (build-list candidates):")
        for name, count in gaps.most_common():
            lines.append(f"    {name:32s} requested {count}x")
    lines.append("=" * 64)
    return "\n".join(lines)


def run_pool(
    use_llm: bool = True,
    only: list[str] | None = None,
    limit: int | None = None,
    out_path: str | None = None,
) -> list[EvalResult]:
    scenarios = load_scenarios()
    if only:
        wanted = set(only)
        scenarios = [s for s in scenarios if s["id"] in wanted]
    if limit:
        scenarios = scenarios[:limit]

    runner = EvalRunner(use_llm=use_llm)
    results: list[EvalResult] = []
    for scenario in scenarios:
        result = runner.run_scenario(scenario)
        results.append(result)
        marker = "OK " if result.matches_expectation else "!! "
        print(f"{marker}{scenario['id']} [{result.outcome}] {scenario['title']}")

    print(summarize(results))

    if out_path:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(
            [
                {
                    "id": r.scenario_id,
                    "outcome": r.outcome,
                    "expected": r.expected,
                    "match": r.matches_expectation,
                    "detail": r.detail,
                }
                for r in results
            ],
            indent=2, ensure_ascii=False, default=str,
        ), encoding="utf-8")
        print(f"\nFull results written to {target}")
    return results
