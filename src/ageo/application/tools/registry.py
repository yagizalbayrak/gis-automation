"""Tool registry: single source of truth for what the system can do.

Validation happens at REGISTRATION time (import time), not execution
time: a malformed tool fails the test suite and app startup, never a
user's workflow.
"""
from __future__ import annotations

from ageo.application.tools.contract import CrsEffect, Tool, layer_ref_kind
from ageo.application.tools.errors import ToolRegistrationError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool_cls: type[Tool]) -> type[Tool]:
        """Class decorator: @registry.register above each tool."""
        spec = tool_cls.spec
        if spec.name in self._tools:
            raise ToolRegistrationError(f"Duplicate tool name: {spec.name!r}")

        layer_in_fields = _layer_ref_fields(tool_cls.Input)
        missing = set(spec.input_requirements) - layer_in_fields
        if missing:
            raise ToolRegistrationError(
                f"{spec.name}: input_requirements reference non-LayerRef "
                f"fields {sorted(missing)}"
            )
        undeclared = layer_in_fields - set(spec.input_requirements)
        if undeclared:
            raise ToolRegistrationError(
                f"{spec.name}: LayerRef inputs {sorted(undeclared)} have no "
                f"declared InputRequirement. Every layer input must state its "
                f"CRS and geometry preconditions explicitly."
            )
        if spec.crs_effect is CrsEffect.FROM_PARAM:
            if not spec.crs_param or spec.crs_param not in tool_cls.Input.model_fields:
                raise ToolRegistrationError(
                    f"{spec.name}: crs_effect FROM_PARAM requires crs_param to "
                    f"name an existing input field."
                )
        if spec.crs_effect is CrsEffect.NONE and _layer_ref_fields(tool_cls.Output):
            raise ToolRegistrationError(
                f"{spec.name}: declares crs_effect NONE but outputs a LayerRef."
            )

        self._tools[spec.name] = tool_cls()
        return tool_cls

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name!r}")
        return self._tools[name]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def catalog(self) -> list[dict]:
        """Planner-facing catalog: name, summary, JSON Schemas, requirements.
        This - not the tool code - is the LLM's entire view of the system."""
        return [
            {
                "name": tool.spec.name,
                "summary": tool.spec.summary,
                "input_schema": tool.Input.model_json_schema(),
                "output_schema": tool.Output.model_json_schema(),
                "crs_requirements": {
                    field: req.crs.value
                    for field, req in tool.spec.input_requirements.items()
                },
                "failure_modes": list(tool.spec.failure_modes),
            }
            for tool in self._tools.values()
        ]


def _layer_ref_fields(model: type) -> set[str]:
    return {
        name
        for name, field in model.model_fields.items()
        if layer_ref_kind(field.annotation) is not None
    }


# Module-level default registry. Tool implementations register themselves
# against this instance at import time (see ageo.application.tools.impl).
registry = ToolRegistry()
