"""Guarded tool executor.

The executor is the ONLY code path through which tools run. It enforces,
uniformly for every tool:

1. strict input validation against the tool's Pydantic schema,
2. the CRS guard (domain check_crs) on every declared layer input,
3. the geometry-class and geometry-validity guards,
4. strict output validation,
5. trace events around everything.

Tools therefore contain zero defensive code: "never buffer in EPSG:4326"
is a structural guarantee of this module, not a convention.
"""
from __future__ import annotations

from typing import Any

from ageo.application.orchestration.trace import TraceEvent, TracePhase, TraceSink
from ageo.application.tools.contract import LayerRef, StrictModel, ToolContext
from ageo.application.tools.errors import (
    CrsGuardViolation,
    GeometryGuardViolation,
    ToolExecutionError,
)
from ageo.application.tools.registry import ToolRegistry
from ageo.domain.value_objects.requirements import (
    GeometryClass,
    InputRequirement,
    check_crs,
)

_GEOMETRY_CLASS_BY_TYPE = {
    "Point": GeometryClass.POINT,
    "MultiPoint": GeometryClass.POINT,
    "LineString": GeometryClass.LINE,
    "MultiLineString": GeometryClass.LINE,
    "Polygon": GeometryClass.POLYGON,
    "MultiPolygon": GeometryClass.POLYGON,
}


class ToolExecutor:
    def __init__(
        self, registry: ToolRegistry, ctx: ToolContext, trace: TraceSink
    ) -> None:
        self._registry = registry
        self._ctx = ctx
        self._trace = trace

    def execute(
        self,
        tool_name: str,
        params: dict[str, Any] | StrictModel,
        step_id: str | None = None,
    ) -> StrictModel:
        tool = self._registry.get(tool_name)
        payload = params.model_dump() if isinstance(params, StrictModel) else params
        inp = tool.Input.model_validate(payload)

        self._emit(
            TracePhase.TOOL_STARTED, tool_name,
            {"params": _loggable(inp)}, step_id,
        )

        for field_name, requirement in tool.spec.input_requirements.items():
            value = getattr(inp, field_name)
            refs = value if isinstance(value, tuple) else (value,)
            for ref in refs:
                self._guard(tool_name, field_name, ref, requirement, step_id)

        try:
            out = tool.run(inp, self._ctx)
        except ToolExecutionError as exc:
            self._emit(
                TracePhase.TOOL_FAILED, tool_name, {"error": str(exc)}, step_id
            )
            raise
        out = tool.Output.model_validate(out.model_dump())
        self._emit(
            TracePhase.TOOL_FINISHED, tool_name, {"result": _loggable(out)}, step_id
        )
        return out

    def _guard(
        self,
        tool_name: str,
        field_name: str,
        ref: LayerRef,
        requirement: InputRequirement,
        step_id: str | None,
    ) -> None:
        crs = self._ctx.crs_of(ref)
        violation = check_crs(requirement.crs, crs)
        if violation is not None:
            self._emit(
                TracePhase.GUARD_FAILED,
                tool_name,
                {"input": field_name, "kind": "crs", "message": violation},
                step_id,
            )
            raise CrsGuardViolation(f"{tool_name}.{field_name}: {violation}")

        gdf = self._ctx.read(ref)
        geometry_violation = _check_geometry(gdf, requirement)
        if geometry_violation is not None:
            self._emit(
                TracePhase.GUARD_FAILED,
                tool_name,
                {"input": field_name, "kind": "geometry", "message": geometry_violation},
                step_id,
            )
            raise GeometryGuardViolation(
                f"{tool_name}.{field_name}: {geometry_violation}"
            )

        self._emit(
            TracePhase.GUARD_PASSED,
            tool_name,
            {"input": field_name, "crs": crs.srid if crs else None},
            step_id,
        )

    def _emit(
        self,
        phase: TracePhase,
        subject: str,
        detail: dict[str, Any],
        step_id: str | None = None,
    ) -> None:
        if step_id is not None:
            detail = {**detail, "step_id": step_id}
        self._trace.emit(TraceEvent(phase=phase, subject=subject, detail=detail))


def _check_geometry(gdf: Any, requirement: InputRequirement) -> str | None:
    present = {
        _GEOMETRY_CLASS_BY_TYPE.get(geom_type)
        for geom_type in gdf.geometry.geom_type.dropna().unique()
    }
    present.discard(None)
    disallowed = {gc for gc in present if not requirement.allows_geometry(gc)}
    if disallowed:
        allowed = sorted(gc.value for gc in requirement.geometry)
        found = sorted(gc.value for gc in disallowed)
        return f"Geometry classes {found} not allowed; tool accepts {allowed}."

    if requirement.requires_valid_geometry:
        invalid_count = int((~gdf.geometry.is_valid).sum())
        empty_count = int(gdf.geometry.is_empty.sum() + gdf.geometry.isna().sum())
        if invalid_count or empty_count:
            return (
                f"Layer contains {invalid_count} invalid and {empty_count} "
                f"empty/missing geometries. Run repair_geometry first."
            )
    return None


def _loggable(model: StrictModel) -> dict[str, Any]:
    """Compact, geometry-free representation for the trace."""
    return model.model_dump(mode="json")
