"""PlanComposer: LLM-composed tool chains for requests no registered
workflow covers - held to the registered-workflow standard.

The escalation ladder for a natural-language request is now:

1. DeterministicPlanner: registered workflow, zero tokens.
2. HybridPlanner LLM fallback: registered workflow, one small-model call.
3. PlanComposer (this module): NO registered workflow fits, so a stronger
   model composes a NEW plan from the tool catalog, grounded by RAG-lite
   recipes.

The model emits DATA - a WorkflowSpec-shaped JSON plan with literal
values, never code. Before anything executes, the plan must pass
validate_workflow(): the same structural checks and the same static CRS
coherence proof that bundled workflows pass at startup. A rejected plan
gets ONE retry with the validator's error message as feedback (the
deterministic Critic talking to the generative Composer); a second
failure raises ComposerError. At runtime every step still goes through
the guarded executor - composed plans get no weaker rulebook anywhere.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from ageo.application.rag.store import RecipeStore
from ageo.application.tools.errors import ComposerError, WorkflowRegistrationError
from ageo.application.tools.registry import ToolRegistry
from ageo.application.workflows.spec import WorkflowSpec
from ageo.application.workflows.validation import validate_workflow
from ageo.domain.ports.crs_info import CrsInfoPort

MAX_STEPS = 15
_NAME_OK = re.compile(r"^[a-z][a-z0-9_]*$")


class LlmComposerPort(Protocol):
    """Seam for the composition model call (LiteLLM adapter in
    infrastructure, scripted fakes in tests/demo). Receives the user text,
    the tool catalog and recipe guidance; returns the parsed plan dict.
    `feedback` carries the validator's error message on the retry pass."""

    def compose(
        self,
        text: str,
        tool_catalog: list[dict],
        recipes: list[str],
        feedback: str | None,
    ) -> dict: ...


@dataclass(frozen=True)
class ComposedPlan:
    spec: WorkflowSpec
    attempts: int
    recipes_used: int


class PlanComposer:
    def __init__(
        self,
        llm: LlmComposerPort,
        tools: ToolRegistry,
        crs_info: CrsInfoPort,
        recipes: RecipeStore | None = None,
        max_attempts: int = 2,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._crs_info = crs_info
        self._recipes = recipes or RecipeStore()
        self._max_attempts = max_attempts

    def compose(self, text: str) -> ComposedPlan:
        recipe_texts = self._recipes.search(text, k=2)
        catalog = self._tools.catalog()
        feedback: str | None = None

        for attempt in range(1, self._max_attempts + 1):
            payload = self._llm.compose(text, catalog, recipe_texts, feedback)
            spec = self._parse(payload)
            try:
                validate_workflow(spec, self._tools, self._crs_info)
            except WorkflowRegistrationError as exc:
                feedback = str(exc)
                continue
            return ComposedPlan(
                spec=spec, attempts=attempt, recipes_used=len(recipe_texts)
            )

        raise ComposerError(
            f"Could not compose a valid plan after {self._max_attempts} attempts. "
            f"Last validation error: {feedback}"
        )

    def _parse(self, payload: dict) -> WorkflowSpec:
        """Normalize untrusted model output into a strict WorkflowSpec.
        Composed plans carry literal values only: no workflow params, no
        nl_patterns - anything else the model added is dropped."""
        if not isinstance(payload, dict):
            raise ComposerError("Composer returned a non-object plan.")

        steps = payload.get("steps")
        if isinstance(steps, list) and not steps:
            # An empty plan is the model REFUSING with a reason - a correct,
            # honest outcome for capabilities we do not have. Surface the
            # reason; retrying cannot help.
            reason = str(payload.get("summary", "")).strip() or "no reason given"
            raise ComposerError(f"plan_refused: {reason}")
        if not isinstance(steps, list):
            raise ComposerError("Composed plan has no steps.")
        if len(steps) > MAX_STEPS:
            raise ComposerError(
                f"Composed plan has {len(steps)} steps; limit is {MAX_STEPS}."
            )

        name = payload.get("name")
        if not isinstance(name, str) or not _NAME_OK.match(name):
            name = "composed_plan"

        outputs = payload.get("outputs")
        if not isinstance(outputs, dict):
            outputs = {}

        normalized = {
            "name": name,
            "summary": str(payload.get("summary", ""))[:300] or "Composed plan",
            "steps": [
                {
                    "id": str(step.get("id", f"step_{index}")),
                    "tool": str(step.get("tool", "")),
                    "params": step.get("params") if isinstance(step.get("params"), dict) else {},
                }
                for index, step in enumerate(steps, start=1)
            ],
            "outputs": {str(k): str(v) for k, v in outputs.items()},
        }
        try:
            # JSON-mode validation so arrays satisfy the strict tuple fields
            return WorkflowSpec.model_validate_json(json.dumps(normalized))
        except Exception as exc:
            raise ComposerError(f"Composed plan does not fit the plan schema: {exc}") from exc


def plan_preview(spec: WorkflowSpec) -> list[dict[str, Any]]:
    """Compact, JSON-safe rendering of a plan for API responses and the UI."""
    return [
        {"id": step.id, "tool": step.tool, "params": step.params}
        for step in spec.steps
    ]
