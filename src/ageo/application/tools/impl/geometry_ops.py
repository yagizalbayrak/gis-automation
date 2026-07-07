"""Single-layer geometry transforms: centroid, simplify_geometry.

Both are geometric measurements in the same sense as buffer/area/length -
their result depends on the planar metric of the CRS they run in - so they
require a projected metric CRS rather than silently computing a distorted
answer in geographic degrees.
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


class CentroidInput(StrictModel):
    layer: LayerRef


class CentroidOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class Centroid(Tool[CentroidInput, CentroidOutput]):
    Input = CentroidInput
    Output = CentroidOutput
    spec = ToolSpec(
        name="centroid",
        summary="Replace each feature's geometry with its centroid point, "
                "keeping all attributes. Input must be in a projected metric CRS.",
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.PROJECTED_METRIC,
                requires_valid_geometry=True,
            )
        },
        failure_modes=("empty_layer",),
    )

    def run(self, params: CentroidInput, ctx: ToolContext) -> CentroidOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: nothing to compute a centroid for")
        centroids = gdf.copy()
        centroids.geometry = gdf.geometry.centroid
        ref = ctx.write(centroids, name="centroid")
        return CentroidOutput(layer=ref, feature_count=len(centroids))


class SimplifyGeometryInput(StrictModel):
    layer: LayerRef
    tolerance_m: float = Field(gt=0, description="Simplification tolerance in metres")
    preserve_topology: bool = True


class SimplifyGeometryOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class SimplifyGeometry(Tool[SimplifyGeometryInput, SimplifyGeometryOutput]):
    Input = SimplifyGeometryInput
    Output = SimplifyGeometryOutput
    spec = ToolSpec(
        name="simplify_geometry",
        summary="Reduce vertex count of line/polygon geometries with a metric "
                "tolerance (Douglas-Peucker). Input must be a projected metric CRS.",
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.PROJECTED_METRIC,
                requires_valid_geometry=True,
            )
        },
        failure_modes=("empty_layer",),
    )

    def run(
        self, params: SimplifyGeometryInput, ctx: ToolContext
    ) -> SimplifyGeometryOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: nothing to simplify")
        simplified = gdf.copy()
        simplified.geometry = gdf.geometry.simplify(
            params.tolerance_m, preserve_topology=params.preserve_topology
        )
        ref = ctx.write(simplified, name="simplified")
        return SimplifyGeometryOutput(layer=ref, feature_count=len(simplified))
