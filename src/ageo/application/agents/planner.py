"""Planner: natural language -> workflow selection + parameter binding.

Cost-strategy implementation of the brief, section 6:

- DeterministicPlanner runs first: zero tokens, pure pattern matching
  against the nl_patterns of registered workflows plus regex parameter
  extraction. Deterministic input -> deterministic plan, cacheable.
- LlmPlannerPort is the seam for the single model call (LiteLLM adapter
  in infrastructure, later). It is consulted ONLY when the deterministic
  pass cannot decide - never per file, per layer or per geometry.
- The planner NEVER executes anything. Its output is a PlannerDecision
  that the runner validates again (parameter kinds, srid_metric contract)
  before the first step runs - LLM output is data, not code.
- Missing parameters are reported, not guessed: ambiguous requests become
  human-in-the-loop questions, per the geodetic safety rules.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import Field

from ageo.application.tools.contract import StrictModel
from ageo.application.workflows.registry import WorkflowRegistry
from ageo.application.workflows.spec import WorkflowParam, WorkflowSpec

# Turkish-aware folding so 'yolları' matches the pattern 'yollari'.
_TR_FOLD = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u",
})

_DISTANCE_M = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m|metre|meter|metres|meters)\b", re.IGNORECASE
)
_QUOTED = re.compile(r"\"([^\"]+)\"|'([^']{2,})'")
_PLACE_TR = re.compile(r"([A-Za-zÇĞİÖŞÜçğıöşü]+)'[dt][ae]ki")  # Kutahya'daki
_PLACE_EN = re.compile(r"\bin\s+([A-Z][A-Za-z]+)")
_FILE_PATH = re.compile(r"(\S+\.(?:shp|gpkg|geojson|json|csv|dxf|kml))", re.IGNORECASE)
_SRID = re.compile(r"\b(EPSG:\d{4,6})\b", re.IGNORECASE)


def _fold(text: str) -> str:
    return text.translate(_TR_FOLD).lower()


class PlannerDecision(StrictModel):
    """The planner's entire output: a workflow name and parameter bindings.

    No code, no tool calls - the runner re-validates everything. If
    missing_params is non-empty the request needs a human answer before
    execution can start.
    """

    workflow: str | None
    params: dict[str, Any] = Field(default_factory=dict)
    missing_params: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str

    @property
    def ready(self) -> bool:
        return self.workflow is not None and not self.missing_params


class LlmPlannerPort(Protocol):
    """Seam for the single LLM planning call (LiteLLM adapter, later).

    Receives the user text and the workflow catalog - never geometries,
    never file contents. Returns the same PlannerDecision shape, which
    the runner validates before anything executes.
    """

    def plan(self, text: str, workflow_catalog: list[dict]) -> PlannerDecision: ...


class DeterministicPlanner:
    def __init__(self, workflows: WorkflowRegistry) -> None:
        self._workflows = workflows

    def plan(self, text: str) -> PlannerDecision:
        spec, matched = self._select_workflow(text)
        if spec is None:
            return PlannerDecision(
                workflow=None,
                confidence=0.0,
                explanation="No registered workflow pattern matches the request.",
            )

        params = self._extract_params(spec, text)
        missing = tuple(
            p.name
            for p in spec.params
            if p.required and p.default is None and p.name not in params
        )
        confidence = min(1.0, len(matched) / max(1, len(spec.nl_patterns)) + 0.5)
        return PlannerDecision(
            workflow=spec.name,
            params=params,
            missing_params=missing,
            confidence=confidence,
            explanation=(
                f"Matched workflow '{spec.name}' via patterns {matched}; "
                f"extracted {sorted(params)}"
                + (f"; awaiting {list(missing)}" if missing else "")
            ),
        )

    def _select_workflow(self, text: str) -> tuple[WorkflowSpec | None, list[str]]:
        folded = _fold(text)
        best: tuple[WorkflowSpec | None, list[str]] = (None, [])
        for name in self._workflows.names():
            spec = self._workflows.get(name)
            matched = [p for p in spec.nl_patterns if _fold(p) in folded]
            if len(matched) > len(best[1]):
                best = (spec, matched)
        return best

    def _extract_params(self, spec: WorkflowSpec, text: str) -> dict[str, Any]:
        """Heuristic extraction for the common parameter shapes. Anything
        not confidently extracted is left missing - the planner asks, it
        does not guess."""
        extracted: dict[str, Any] = {}
        for param in spec.params:
            value = self._extract_one(param, text)
            if value is not None:
                extracted[param.name] = value
        return extracted

    def _extract_one(self, param: WorkflowParam, text: str) -> Any:
        if param.kind == "float":
            if match := _DISTANCE_M.search(_fold(text)):
                return float(match.group(1).replace(",", "."))
            return None
        if param.kind in ("srid", "srid_metric"):
            if match := _SRID.search(text):
                return match.group(1).upper()
            return None
        if param.kind == "string":
            if param.name in ("street_name", "name"):
                if match := _QUOTED.search(text):
                    return match.group(1) or match.group(2)
                return None
            if param.name == "place":
                if match := _PLACE_TR.search(text):
                    return match.group(1)
                if match := _PLACE_EN.search(text):
                    return match.group(1)
                return None
            if param.name in ("path", "output_dir"):
                if param.name == "path" and (match := _FILE_PATH.search(text)):
                    return match.group(1)
                return None
        return None


class HybridPlanner:
    """Deterministic first; one LLM call only when the deterministic pass
    cannot produce a ready decision AND an LLM port is configured.

    The LLM's answer is treated as untrusted data: unknown workflows fall
    back to the deterministic decision, unknown parameters are dropped,
    and missing_params is recomputed from the registry (the LLM has no
    authority over what is required). An LLM failure - network, quota,
    malformed output - silently degrades to the deterministic result: the
    workbench must keep working when the model does not."""

    def __init__(
        self,
        workflows: WorkflowRegistry,
        llm: LlmPlannerPort | None = None,
    ) -> None:
        self._deterministic = DeterministicPlanner(workflows)
        self._workflows = workflows
        self._llm = llm

    def plan(self, text: str) -> PlannerDecision:
        decision = self._deterministic.plan(text)
        if decision.ready or self._llm is None:
            return decision
        try:
            llm_decision = self._llm.plan(text, self._workflows.catalog())
        except Exception:
            return decision
        return self._sanitize(llm_decision, fallback=decision)

    def _sanitize(
        self, llm_decision: PlannerDecision, fallback: PlannerDecision
    ) -> PlannerDecision:
        name = llm_decision.workflow
        if name is None or name not in self._workflows.names():
            return fallback
        spec = self._workflows.get(name)
        known = {p.name for p in spec.params}
        params = {k: v for k, v in llm_decision.params.items() if k in known}
        missing = tuple(
            p.name
            for p in spec.params
            if p.required and p.default is None and p.name not in params
        )
        return PlannerDecision(
            workflow=name,
            params=params,
            missing_params=missing,
            confidence=llm_decision.confidence,
            explanation=llm_decision.explanation,
        )
