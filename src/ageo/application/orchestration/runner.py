"""Workflow runner: executes a registered workflow spec step by step.

Parameter validation happens BEFORE the first step runs - including the
geodetic 'srid_metric' contract, which refuses to start a workflow whose
target CRS is not projected and metric. Combined with the registry's
static coherence check, this closes the loop: chains are proven safe at
registration time and parameterizations are proven safe at start time.
"""
from __future__ import annotations

from typing import Any

from ageo.application.orchestration.executor import ToolExecutor
from ageo.application.orchestration.trace import TraceEvent, TracePhase, TraceSink
from ageo.application.tools.contract import StrictModel, ToolContext
from ageo.application.tools.errors import AgeoError, WorkflowParamError
from ageo.application.tools.registry import ToolRegistry
from ageo.application.workflows.registry import WorkflowRegistry
from ageo.application.workflows.spec import (
    WorkflowSpec,
    is_params_ref,
    is_steps_ref,
    parse_params_ref,
    parse_steps_ref,
)
from ageo.domain.ports.crs_info import CrsInfoPort

_PYTHON_KIND = {"string": str, "float": (int, float), "int": int, "bool": bool}


class WorkflowRunner:
    def __init__(
        self,
        workflows: WorkflowRegistry,
        tools: ToolRegistry,
        ctx: ToolContext,
        trace: TraceSink,
        crs_info: CrsInfoPort,
    ) -> None:
        self._workflows = workflows
        self._executor = ToolExecutor(tools, ctx, trace)
        self._trace = trace
        self._crs_info = crs_info

    def run(self, workflow_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.run_spec(self._workflows.get(workflow_name), params)

    def run_spec(self, spec: WorkflowSpec, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a spec directly - used for validated composed plans that
        are not registered. Same parameter contract, same guarded executor."""
        resolved_params = self._validate_params(spec, params)

        self._trace.emit(TraceEvent(
            phase=TracePhase.WORKFLOW_STARTED,
            subject=spec.name,
            detail={"params": {k: str(v) for k, v in resolved_params.items()}},
        ))

        step_outputs: dict[str, StrictModel] = {}
        try:
            for step in spec.steps:
                bound = {
                    key: self._resolve(value, resolved_params, step_outputs)
                    for key, value in step.params.items()
                }
                step_outputs[step.id] = self._executor.execute(
                    step.tool, bound, step_id=step.id
                )
        except AgeoError as exc:
            self._trace.emit(TraceEvent(
                phase=TracePhase.WORKFLOW_FAILED,
                subject=spec.name,
                detail={"error": str(exc)},
            ))
            raise

        outputs = {
            name: self._resolve(ref, resolved_params, step_outputs)
            for name, ref in spec.outputs.items()
        }
        self._trace.emit(TraceEvent(
            phase=TracePhase.WORKFLOW_FINISHED,
            subject=spec.name,
            detail={"outputs": {k: _brief(v) for k, v in outputs.items()}},
        ))
        return outputs

    def _validate_params(
        self, spec: WorkflowSpec, provided: dict[str, Any]
    ) -> dict[str, Any]:
        unknown = set(provided) - {p.name for p in spec.params}
        if unknown:
            raise WorkflowParamError(
                f"{spec.name}: unknown parameters {sorted(unknown)}"
            )
        resolved: dict[str, Any] = {}
        for param in spec.params:
            if param.name in provided:
                value = provided[param.name]
            elif param.default is not None or not param.required:
                value = param.default
            else:
                raise WorkflowParamError(
                    f"{spec.name}: missing required parameter {param.name!r}"
                )

            if value is not None:
                if param.kind in _PYTHON_KIND and not isinstance(
                    value, _PYTHON_KIND[param.kind]
                ):
                    raise WorkflowParamError(
                        f"{spec.name}.{param.name}: expected {param.kind}, "
                        f"got {type(value).__name__}"
                    )
                if param.kind in ("srid", "srid_metric"):
                    descriptor = self._crs_info.describe(value)
                    if param.kind == "srid_metric" and not descriptor.is_metric():
                        raise WorkflowParamError(
                            f"{spec.name}.{param.name}: {descriptor.srid} "
                            f"({descriptor.name or descriptor.kind.value}) is not "
                            f"a projected metric CRS; distance operations would "
                            f"be geodetically meaningless."
                        )
            resolved[param.name] = value
        return resolved

    def _resolve(
        self,
        value: Any,
        params: dict[str, Any],
        step_outputs: dict[str, StrictModel],
    ) -> Any:
        if isinstance(value, (list, tuple)):
            # collections resolve element-wise; tuple satisfies strict schemas
            return tuple(
                self._resolve(element, params, step_outputs) for element in value
            )
        if is_params_ref(value):
            return params[parse_params_ref(value)]
        if is_steps_ref(value):
            step_id, field = parse_steps_ref(value)
            return getattr(step_outputs[step_id], field)
        return value


def _brief(value: Any) -> Any:
    if isinstance(value, StrictModel):
        return value.model_dump(mode="json")
    return value
