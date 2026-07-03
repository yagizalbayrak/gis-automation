"""Aggregation tools: dissolve."""
from __future__ import annotations

from ageo.application.tools.contract import (
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import ToolExecutionError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import CrsRequirement, InputRequirement


class DissolveInput(StrictModel):
    layer: LayerRef
    by: str | None = None  # None dissolves everything into one feature


class DissolveOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class Dissolve(Tool[DissolveInput, DissolveOutput]):
    Input = DissolveInput
    Output = DissolveOutput
    spec = ToolSpec(
        name="dissolve",
        summary="Merge features into single geometries, optionally grouped "
                "by an attribute field.",
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.NONE, requires_valid_geometry=True
            )
        },
        failure_modes=("missing_field",),
    )

    def run(self, params: DissolveInput, ctx: ToolContext) -> DissolveOutput:
        gdf = ctx.read(params.layer)
        if params.by is not None and params.by not in gdf.columns:
            raise ToolExecutionError(
                f"missing_field: {params.by!r} not in layer attributes"
            )
        dissolved = gdf.dissolve(by=params.by)
        if params.by is not None:
            dissolved = dissolved.reset_index()
        ref = ctx.write(dissolved, name="dissolved")
        return DissolveOutput(layer=ref, feature_count=len(dissolved))
