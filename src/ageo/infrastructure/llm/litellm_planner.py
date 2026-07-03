"""LiteLLM-backed implementation of LlmPlannerPort.

This is the system's ONLY LLM call site, and it embodies the cost
strategy from the brief:

- exactly one completion per ambiguous request (never per file/layer/geometry),
- a small model by default (workflow selection is classification, not
  reasoning) - override with AGEO_PLANNER_MODEL for harder planning,
- the model sees ONLY the user text and the workflow catalog: no
  geometries, no file contents, no credentials,
- the response is DATA: parsed, schema-validated, then sanitized by
  HybridPlanner against the registry and re-validated by the runner.
  Nothing the model says is ever executed directly.
"""
from __future__ import annotations

import json

import litellm

from ageo.application.agents.planner import PlannerDecision
from ageo.application.tools.errors import GatewayError
from ageo.infrastructure.llm.config import LlmConfig, LlmConfigStore

_ENV_MODEL_VAR = "AGEO_PLANNER_MODEL"

_SYSTEM_PROMPT = """\
You are the planning component of a deterministic GIS automation workbench.
Given a user request and a catalog of registered workflows, respond with a
single JSON object and NOTHING else:

{
  "workflow": "<workflow name from the catalog, or null if none fits>",
  "params": {"<param name>": <value>},
  "confidence": <0.0-1.0>,
  "explanation": "<one short sentence>"
}

Rules:
- Only use workflow names and parameter names that exist in the catalog.
- Only include parameters whose values are explicitly present in the request.
  NEVER invent values (especially distances, CRS codes, file paths or names);
  omit unknown parameters instead - the system will ask the user.
- Distances must be numbers in metres. CRS values look like "EPSG:5254".
- If the request does not match any workflow, set "workflow" to null.
"""


class LiteLlmPlanner:
    def __init__(
        self,
        config: LlmConfigStore | None = None,
        model: str | None = None,
        timeout_s: float = 30.0,
        max_tokens: int = 500,
    ) -> None:
        self._config = config
        self._model_override = model
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens

    def _effective(self) -> LlmConfig:
        if self._model_override:
            return LlmConfig(provider="custom", model=self._model_override)
        if self._config is not None:
            return self._config.effective(_ENV_MODEL_VAR)
        raise GatewayError("llm_not_configured: planner has no model configured")

    def plan(self, text: str, workflow_catalog: list[dict]) -> PlannerDecision:
        config = self._effective()
        try:
            response = litellm.completion(
                **config.completion_kwargs(),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Workflow catalog:\n{json.dumps(workflow_catalog, ensure_ascii=False)}\n\n"
                            f"User request:\n{text}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=self._max_tokens,
                timeout=self._timeout_s,
            )
        except Exception as exc:
            raise GatewayError(f"llm_planner_unavailable: {exc}") from exc

        content = response.choices[0].message.content or ""
        payload = _extract_json(content)
        return _to_decision(payload)


def _extract_json(content: str) -> dict:
    """Parse the first JSON object in the completion. Models occasionally
    wrap JSON in prose or code fences despite instructions."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end <= start:
        raise GatewayError(f"llm_planner_malformed_response: no JSON object in {content!r:.120}")
    try:
        payload = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GatewayError(f"llm_planner_malformed_response: {exc}") from exc
    if not isinstance(payload, dict):
        raise GatewayError("llm_planner_malformed_response: top-level JSON is not an object")
    return payload


def _to_decision(payload: dict) -> PlannerDecision:
    """Normalize loosely-typed model output into the strict decision schema.
    Anything that does not fit is dropped or clamped, never guessed."""
    workflow = payload.get("workflow")
    if not isinstance(workflow, str) or not workflow:
        workflow = None

    params = payload.get("params")
    if not isinstance(params, dict):
        params = {}
    params = {k: v for k, v in params.items() if isinstance(k, str)}

    confidence = payload.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    confidence = max(0.0, min(1.0, float(confidence)))

    explanation = payload.get("explanation", "")
    if not isinstance(explanation, str):
        explanation = ""

    return PlannerDecision(
        workflow=workflow,
        params=params,
        missing_params=(),  # authoritative recomputation happens in HybridPlanner
        confidence=confidence,
        explanation=explanation or "LLM planner decision.",
    )
