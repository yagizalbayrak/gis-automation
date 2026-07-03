"""buffer_metric: distance buffering, metres only.

The geodetic poster child of the guard architecture: this tool contains
no CRS check at all. Its spec declares PROJECTED_METRIC and the executor
guard makes buffering in EPSG:4326 structurally impossible.
"""
from __future__ import annotations

from pydantic import Field

from ageo.application.tools.contract import (
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import EmptyLayerError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import CrsRequirement, InputRequirement


class BufferMetricInput(StrictModel):
    layer: LayerRef
    distance_m: float = Field(gt=0, le=100_000, description="Buffer distance in metres")


class BufferMetricOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class BufferMetric(Tool[BufferMetricInput, BufferMetricOutput]):
    Input = BufferMetricInput
    Output = BufferMetricOutput
    spec = ToolSpec(
        name="buffer_metric",
        summary="Buffer features by a distance in metres. Input MUST already "
                "be in a projected metric CRS; reproject first.",
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.PROJECTED_METRIC,
                requires_valid_geometry=True,
            )
        },
        failure_modes=("empty_layer",),
    )

    def run(self, params: BufferMetricInput, ctx: ToolContext) -> BufferMetricOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: nothing to buffer")
        buffered = gdf.copy()
        buffered.geometry = gdf.geometry.buffer(params.distance_m)
        ref = ctx.write(buffered, name=f"buffer_{params.distance_m:g}m")
        return BufferMetricOutput(layer=ref, feature_count=len(buffered))
