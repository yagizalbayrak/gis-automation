"""Workflow validation: the deterministic Critic.

validate_workflow() proves, before any data exists, that a workflow spec -
whether bundled at startup or COMPOSED BY AN LLM at request time - is:

1. structurally sound (tools exist, bindings resolve, required inputs
   covered, forward-only step references),
2. CRS-COHERENT: simulating the symbolic CRS state of every layer through
   the chain, no tool can receive a layer violating its declared CRS
   requirement. A plan that pipes an EPSG:4326 OSM fetch straight into
   buffer_metric is rejected here with an actionable message.

This module is intentionally free of registry state so the plan composer
can call it on ephemeral specs. The same code path guards both worlds:
there is no weaker rulebook for generated plans.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from ageo.application.tools.contract import CrsEffect, Tool, layer_ref_kind
from ageo.application.tools.errors import WorkflowRegistrationError
from ageo.application.tools.registry import ToolRegistry
from ageo.application.workflows.spec import (
    WorkflowSpec,
    is_params_ref,
    is_steps_ref,
    parse_params_ref,
    parse_steps_ref,
)
from ageo.domain.ports.crs_info import CrsInfoPort
from ageo.domain.value_objects.crs import CrsKind
from ageo.domain.value_objects.requirements import CrsRequirement


class SymCrs(StrEnum):
    """Symbolic CRS state of a layer variable during static analysis."""

    GEOGRAPHIC = "geographic"
    METRIC = "metric"
    OTHER = "other"      # projected, non-metric units
    RUNTIME = "runtime"  # defined-but-unknown until execution (e.g. loaded file)


_KIND_TO_SYM = {
    CrsKind.GEOGRAPHIC: SymCrs.GEOGRAPHIC,
    CrsKind.PROJECTED_METRIC: SymCrs.METRIC,
    CrsKind.PROJECTED_OTHER: SymCrs.OTHER,
}


def validate_workflow(
    spec: WorkflowSpec, tools: ToolRegistry, crs_info: CrsInfoPort
) -> None:
    """Raise WorkflowRegistrationError if the spec is structurally or
    geodetically unsound."""
    _validate_structure(spec, tools)
    _validate_crs_coherence(spec, tools, crs_info)


# -- structural validation ---------------------------------------------------


def _validate_structure(spec: WorkflowSpec, tools: ToolRegistry) -> None:
    param_names = {p.name for p in spec.params}
    seen_steps: dict[str, Tool] = {}

    for step in spec.steps:
        if step.id in seen_steps:
            raise WorkflowRegistrationError(
                f"{spec.name}: duplicate step id {step.id!r}"
            )
        if step.tool not in tools:
            raise WorkflowRegistrationError(
                f"{spec.name}.{step.id}: unknown tool {step.tool!r}"
            )
        tool = tools.get(step.tool)

        unknown = set(step.params) - set(tool.Input.model_fields)
        if unknown:
            raise WorkflowRegistrationError(
                f"{spec.name}.{step.id}: unknown tool inputs {sorted(unknown)}"
            )
        required = {
            name
            for name, field in tool.Input.model_fields.items()
            if field.is_required()
        }
        missing = required - set(step.params)
        if missing:
            raise WorkflowRegistrationError(
                f"{spec.name}.{step.id}: missing required inputs {sorted(missing)}"
            )

        for key, value in step.params.items():
            _validate_binding(spec, step.id, key, value, param_names, seen_steps)

        seen_steps[step.id] = tool

    for out_name, ref in spec.outputs.items():
        if not is_steps_ref(ref):
            raise WorkflowRegistrationError(
                f"{spec.name}: output {out_name!r} must reference a step field"
            )
        step_id, field = parse_steps_ref(ref)
        if step_id not in seen_steps:
            raise WorkflowRegistrationError(
                f"{spec.name}: output {out_name!r} references unknown step {step_id!r}"
            )
        if field not in seen_steps[step_id].Output.model_fields:
            raise WorkflowRegistrationError(
                f"{spec.name}: output {out_name!r} references unknown field {field!r}"
            )


def _validate_binding(
    spec: WorkflowSpec,
    step_id: str,
    key: str,
    value: Any,
    param_names: set[str],
    seen_steps: dict[str, Tool],
) -> None:
    if isinstance(value, (list, tuple)):
        for element in value:
            _validate_binding(spec, step_id, key, element, param_names, seen_steps)
        return
    if is_params_ref(value):
        name = parse_params_ref(value)
        if name not in param_names:
            raise WorkflowRegistrationError(
                f"{spec.name}.{step_id}.{key}: unknown workflow param {name!r}"
            )
    elif is_steps_ref(value):
        ref_step, ref_field = parse_steps_ref(value)
        if ref_step not in seen_steps:
            raise WorkflowRegistrationError(
                f"{spec.name}.{step_id}.{key}: reference to undefined or "
                f"later step {ref_step!r} (steps are a forward-only chain)"
            )
        if ref_field not in seen_steps[ref_step].Output.model_fields:
            raise WorkflowRegistrationError(
                f"{spec.name}.{step_id}.{key}: step {ref_step!r} has no "
                f"output field {ref_field!r}"
            )


# -- geodetic (CRS) coherence -------------------------------------------------


def _validate_crs_coherence(
    spec: WorkflowSpec, tools: ToolRegistry, crs_info: CrsInfoPort
) -> None:
    states: dict[str, SymCrs] = {}  # "step_id.field" -> SymCrs

    for step in spec.steps:
        tool = tools.get(step.tool)

        input_states: dict[str, SymCrs] = {}
        for field_name, requirement in tool.spec.input_requirements.items():
            bound = step.params.get(field_name)
            bindings = bound if isinstance(bound, (list, tuple)) else (bound,)
            field_states = [_state_of_binding(b, states) for b in bindings]
            input_states[field_name] = field_states[0]
            for state in field_states:
                problem = _check_symbolic(requirement.crs, state)
                if problem is not None:
                    raise WorkflowRegistrationError(
                        f"{spec.name}.{step.id} ({step.tool}.{field_name}): {problem}"
                    )

        out_state = _output_state(spec, step, tool, input_states, crs_info)
        if out_state is not None:
            for out_field, field_info in tool.Output.model_fields.items():
                if layer_ref_kind(field_info.annotation) is not None:
                    states[f"{step.id}.{out_field}"] = out_state


def _state_of_binding(bound: Any, states: dict[str, SymCrs]) -> SymCrs:
    if is_steps_ref(bound):
        step_id, field = parse_steps_ref(bound)
        return states.get(f"{step_id}.{field}", SymCrs.RUNTIME)
    return SymCrs.RUNTIME  # externally supplied layer: guard checks at runtime


def _output_state(
    spec: WorkflowSpec,
    step: Any,
    tool: Tool,
    input_states: dict[str, SymCrs],
    crs_info: CrsInfoPort,
) -> SymCrs | None:
    effect = tool.spec.crs_effect
    if effect is CrsEffect.NONE:
        return None
    if effect is CrsEffect.SETS_WGS84:
        return SymCrs.GEOGRAPHIC
    if effect is CrsEffect.RUNTIME:
        return SymCrs.RUNTIME
    if effect is CrsEffect.PRESERVES:
        # single-input tools propagate; multi-input tools propagate the
        # first declared layer input (the primary layer by convention)
        return next(iter(input_states.values()), SymCrs.RUNTIME)
    if effect is CrsEffect.FROM_PARAM:
        bound = step.params.get(tool.spec.crs_param)
        if is_params_ref(bound):
            param = spec.param(parse_params_ref(bound))
            if param is not None and param.kind == "srid_metric":
                # runner enforces metric-ness before execution starts
                return SymCrs.METRIC
            return SymCrs.RUNTIME
        if isinstance(bound, str):
            descriptor = crs_info.describe(bound)
            return _KIND_TO_SYM.get(descriptor.kind, SymCrs.RUNTIME)
        return SymCrs.RUNTIME
    return SymCrs.RUNTIME


def _check_symbolic(requirement: CrsRequirement, state: SymCrs) -> str | None:
    if requirement is CrsRequirement.NONE or requirement is CrsRequirement.ANY_DEFINED:
        # ANY_DEFINED on a RUNTIME layer is deferred to the runtime guard.
        return None
    if requirement is CrsRequirement.PROJECTED_METRIC and state is not SymCrs.METRIC:
        return (
            f"requires a projected metric CRS but the chain proves the layer "
            f"would be '{state.value}' at this point. Insert a reproject step "
            f"to a metric CRS (e.g. EPSG:5254) before this tool."
        )
    if requirement is CrsRequirement.GEOGRAPHIC and state is not SymCrs.GEOGRAPHIC:
        return (
            f"requires a geographic CRS but the chain proves the layer would "
            f"be '{state.value}' at this point."
        )
    return None
