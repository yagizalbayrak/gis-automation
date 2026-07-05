"""LiteLLM-backed implementation of LlmComposerPort.

Composition is the one place the cost strategy allows a stronger model:
it runs only when no registered workflow matches (rare), and one good
plan replaces an entire manual GIS session. Configure with
AGEO_COMPOSER_MODEL; unset means composition is disabled entirely.
"""
from __future__ import annotations

import json

import litellm

from ageo.application.tools.errors import GatewayError
from ageo.domain.value_objects.user_profile import UserProfile
from ageo.infrastructure.llm.config import LlmConfig, LlmConfigStore

_ENV_MODEL_VAR = "AGEO_COMPOSER_MODEL"

_SYSTEM_PROMPT = """\
You compose executable GIS analysis plans for a deterministic automation
workbench. You receive a user request (Turkish or English), a catalog of
available tools with their exact input/output JSON schemas and CRS
requirements, and recipe guidance.

Respond with ONE JSON object and NOTHING else:

{
  "name": "<snake_case plan name>",
  "summary": "<one sentence describing the plan>",
  "steps": [
    {"id": "<snake_case id>", "tool": "<tool name from catalog>",
     "params": {"<input field>": <literal value or reference>}}
  ],
  "outputs": {"<output name>": "$steps.<step_id>.<output_field>"}
}

Hard rules:
- Only tools and input fields that exist in the catalog. Steps run in order.
- Reference earlier step outputs as "$steps.<step_id>.<field>". Use literal
  values everywhere else - no "$params" indirection, no placeholders.
- OSM fetch results are EPSG:4326. Distance operations (buffer_metric)
  REQUIRE a projected metric CRS: insert a reproject step with a literal
  target_srid (e.g. "EPSG:5254" for western Turkey) before them. The plan
  is statically checked and will be REJECTED if a layer can reach a metric
  operation in a geographic CRS.
- Layers combined by intersect/clip/spatial_join must be in the same CRS.
- Reproject final map outputs to "EPSG:4326" and list them under "outputs"
  with clear names.
- Distances: metres, numbers. Do not invent data paths; fetch from OSM.
- If the request needs a capability that does NOT exist in the catalog
  (e.g. routing, isochrones, raster/DEM analysis, geocoding, statistics),
  REFUSE: return "steps": [] and state in "summary" exactly which
  capability is missing. Do NOT substitute a different analysis (a
  circular buffer is NOT an isochrone; fetching data is NOT computing
  statistics) and do NOT return a partial preparation plan.
- If the request is genuinely AMBIGUOUS in a way you cannot safely resolve
  alone - for example, a distance given in DEGREES (e.g. "0.001 derece
  tampon"/"0.001 degree buffer"): a degree is not a fixed distance, but at
  a given latitude it corresponds to a rough metre value (0.001 deg is
  roughly 111 m at mid-latitudes) - do NOT silently guess and do NOT
  bluntly refuse. Instead return ONLY this JSON object:
  {
    "clarification": {
      "reason": "<short EN reason>",
      "question": {"en": "...", "tr": "..."},
      "options": [
        {"value": "<literal to feed back, e.g. a metre number>",
         "label": {"en": "...", "tr": "..."}, "recommended": true}
      ]
    }
  }
  This is DIFFERENT from the refusal shape ("steps": []): use clarification
  only when a single follow-up answer would let you produce a real plan,
  not when the capability itself is missing.
- If a "User clarification answer" section is present in the input, you
  MUST use it to produce a final plan (or an honest "steps": [] refusal if
  it turns out impossible) - do NOT emit another "clarification" object.
"""


class LiteLlmComposer:
    def __init__(
        self,
        config: LlmConfigStore | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
        # generous: reasoning models (Gemini 2.5) spend output budget on
        # internal thinking, and 2000 demonstrably truncated real plans
        max_tokens: int = 8000,
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
        raise GatewayError("llm_not_configured: composer has no model configured")

    def compose(
        self,
        text: str,
        tool_catalog: list[dict],
        recipes: list[str],
        feedback: str | None,
        *,
        profile: UserProfile | None = None,
        clarification_answer: str | None = None,
    ) -> dict:
        sections = [
            f"Tool catalog:\n{json.dumps(tool_catalog, ensure_ascii=False)}",
        ]
        if recipes:
            sections.append("Recipe guidance:\n" + "\n---\n".join(recipes))
        sections.append(f"User request:\n{text}")
        if profile is not None:
            sections.append(profile.to_prompt_line())
        if clarification_answer is not None:
            sections.append(f"User clarification answer: {clarification_answer}")
        if feedback:
            sections.append(
                "Your previous plan was REJECTED by the validator with this "
                f"error - fix it:\n{feedback}"
            )

        config = self._effective()
        try:
            response = litellm.completion(
                **config.completion_kwargs(),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": "\n\n".join(sections)},
                ],
                temperature=0.0,
                max_tokens=self._max_tokens,
                timeout=self._timeout_s,
            )
        except Exception as exc:
            raise GatewayError(f"llm_composer_unavailable: {exc}") from exc

        content = response.choices[0].message.content or ""
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end <= start:
            raise GatewayError("llm_composer_malformed_response: no JSON object")
        try:
            payload = json.loads(content[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GatewayError(f"llm_composer_malformed_response: {exc}") from exc
        if not isinstance(payload, dict):
            raise GatewayError("llm_composer_malformed_response: not an object")
        return payload
