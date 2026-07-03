"""Workflow records: declarative, deterministic tool chains.

A workflow is DATA - a named, validated sequence of (tool, bindings).
Bindings reference workflow parameters as "$params.<name>" and prior
step outputs as "$steps.<step_id>.<field>". No code, no LLM: the planner
only *selects* workflows and fills parameters.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ageo.application.tools.contract import StrictModel

PARAMS_PREFIX = "$params."
STEPS_PREFIX = "$steps."

ParamKind = Literal["string", "float", "int", "bool", "srid", "srid_metric"]


class WorkflowParam(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: ParamKind
    description: str = ""
    required: bool = True
    default: Any = None
    # kind "srid_metric" is a geodetic contract: the runner refuses to start
    # the workflow unless the supplied CRS is projected and metric, and the
    # static checker may treat layers reprojected to it as metric.


class WorkflowStep(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowSpec(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    summary: str
    nl_patterns: tuple[str, ...] = ()  # natural-language cues for the planner
    params: tuple[WorkflowParam, ...] = ()
    steps: tuple[WorkflowStep, ...]
    outputs: dict[str, str] = Field(default_factory=dict)  # name -> "$steps.x.field"

    def param(self, name: str) -> WorkflowParam | None:
        return next((p for p in self.params if p.name == name), None)


def is_params_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PARAMS_PREFIX)


def is_steps_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(STEPS_PREFIX)


def parse_steps_ref(value: str) -> tuple[str, str]:
    """'$steps.roads.layer' -> ('roads', 'layer')"""
    step_id, _, field = value.removeprefix(STEPS_PREFIX).partition(".")
    return step_id, field


def parse_params_ref(value: str) -> str:
    """'$params.place' -> 'place'"""
    return value.removeprefix(PARAMS_PREFIX)
