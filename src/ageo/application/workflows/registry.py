"""Workflow registry: named, validated workflow records.

All validation logic lives in ageo.application.workflows.validation and
is shared with the plan composer - registered and composed workflows are
held to exactly the same structural and geodetic standard.
"""
from __future__ import annotations

from ageo.application.tools.errors import WorkflowRegistrationError
from ageo.application.tools.registry import ToolRegistry
from ageo.application.workflows.spec import WorkflowSpec
from ageo.application.workflows.validation import validate_workflow
from ageo.domain.ports.crs_info import CrsInfoPort


class WorkflowRegistry:
    def __init__(self, tools: ToolRegistry, crs_info: CrsInfoPort) -> None:
        self._tools = tools
        self._crs_info = crs_info
        self._workflows: dict[str, WorkflowSpec] = {}

    def register(self, spec: WorkflowSpec) -> WorkflowSpec:
        if spec.name in self._workflows:
            raise WorkflowRegistrationError(f"Duplicate workflow: {spec.name!r}")
        validate_workflow(spec, self._tools, self._crs_info)
        self._workflows[spec.name] = spec
        return spec

    def get(self, name: str) -> WorkflowSpec:
        if name not in self._workflows:
            raise KeyError(f"Unknown workflow: {name!r}")
        return self._workflows[name]

    def names(self) -> list[str]:
        return sorted(self._workflows)

    def catalog(self) -> list[dict]:
        """Planner-facing catalog of available workflows."""
        return [
            {
                "name": wf.name,
                "summary": wf.summary,
                "nl_patterns": list(wf.nl_patterns),
                "params": [p.model_dump() for p in wf.params],
            }
            for wf in self._workflows.values()
        ]
