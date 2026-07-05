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

from ageo.application.agents.clarifier import PendingQuestion, QuestionOption
from ageo.application.rag.store import RecipeStore
from ageo.application.tools.errors import ComposerError, WorkflowRegistrationError
from ageo.application.tools.registry import ToolRegistry
from ageo.application.workflows.spec import WorkflowSpec
from ageo.application.workflows.validation import validate_workflow
from ageo.domain.ports.crs_info import CrsInfoPort
from ageo.domain.value_objects.user_profile import UserProfile

MAX_STEPS = 15
_NAME_OK = re.compile(r"^[a-z][a-z0-9_]*$")


class LlmComposerPort(Protocol):
    """Seam for the composition model call (LiteLLM adapter in
    infrastructure, scripted fakes in tests/demo). Receives the user text,
    the tool catalog and recipe guidance; returns the parsed plan dict.
    `feedback` carries the validator's error message on the retry pass.
    `clarification_answer` carries the user's answer to a prior
    ComposerClarificationRequired, when one was asked."""

    def compose(
        self,
        text: str,
        tool_catalog: list[dict],
        recipes: list[str],
        feedback: str | None,
        *,
        profile: UserProfile | None = None,
        clarification_answer: str | None = None,
    ) -> dict: ...


@dataclass(frozen=True)
class ComposedPlan:
    spec: WorkflowSpec
    attempts: int
    recipes_used: int


class ComposerClarificationRequired(Exception):
    """The composer needs a human answer before it can produce a plan or an
    honest refusal - a genuine third outcome, not a failure. Deliberately
    NOT an AgeoError subclass: existing `except AgeoError` call sites
    (TaskManager, the eval harness) must never silently swallow it."""

    def __init__(self, question: PendingQuestion) -> None:
        self.question = question
        super().__init__(question.reason)


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

    def compose(
        self,
        text: str,
        *,
        profile: UserProfile | None = None,
        clarification_answer: str | None = None,
    ) -> ComposedPlan:
        recipe_texts = self._recipes.search(text, k=2)
        catalog = self._tools.catalog()
        feedback: str | None = None
        # Whether the CALLER already supplied an answer to a prior
        # clarification - not whether one was raised on a previous retry
        # attempt within this same invocation. Caps clarification at one
        # round per task: a second ask despite an answer becomes an honest
        # refusal instead of looping forever.
        answer_supplied = clarification_answer is not None

        for attempt in range(1, self._max_attempts + 1):
            payload = self._llm.compose(
                text,
                catalog,
                recipe_texts,
                feedback,
                profile=profile,
                clarification_answer=clarification_answer,
            )
            clarification = self._parse_clarification(payload)
            if clarification is not None:
                if answer_supplied:
                    raise ComposerError(f"plan_refused: {clarification.reason}")
                raise ComposerClarificationRequired(clarification)

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

    def _parse_clarification(self, payload: dict) -> PendingQuestion | None:
        """Detect and defensively sanitize the clarification wire shape.
        Must run BEFORE _parse()'s empty-steps refusal check: a
        clarification payload has no "steps" key at all. Untrusted model
        output - never raise a raw KeyError/TypeError, never leave en/tr
        text empty, mirroring _to_decision() in litellm_planner.py."""
        if not isinstance(payload, dict):
            return None
        raw = payload.get("clarification")
        if not isinstance(raw, dict):
            return None

        reason = str(raw.get("reason", "")).strip() or "the request is ambiguous"

        raw_question = raw.get("question")
        if not isinstance(raw_question, dict):
            raw_question = {}
        text = {
            "en": str(raw_question.get("en", "")).strip()
            or "Please clarify your request.",
            "tr": str(raw_question.get("tr", "")).strip()
            or "Lutfen isteginizi netlestirin.",
        }

        raw_options = raw.get("options")
        if not isinstance(raw_options, list):
            raw_options = []
        options: list[QuestionOption] = []
        for raw_option in raw_options:
            if not isinstance(raw_option, dict) or "value" not in raw_option:
                continue
            raw_label = raw_option.get("label")
            if not isinstance(raw_label, dict):
                raw_label = {}
            label = {
                "en": str(raw_label.get("en", "")).strip() or str(raw_option["value"]),
                "tr": str(raw_label.get("tr", "")).strip() or str(raw_option["value"]),
            }
            recommended = raw_option.get("recommended")
            if not isinstance(recommended, bool):
                recommended = False
            options.append(
                QuestionOption(
                    value=raw_option["value"], label=label, recommended=recommended
                )
            )

        return PendingQuestion(
            question_id="q_composer_clarification",
            question_type="clarification",
            severity="material",
            param="clarification_answer",
            kind="string",
            reason=reason,
            text=text,
            options=tuple(options),
            blocking=True,
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
