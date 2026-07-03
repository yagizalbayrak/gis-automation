"""CRS transformation. The ONLY tool allowed to change a layer's CRS.

Uses GeoPandas to_crs, which delegates to pyproj - no manual CRS string
manipulation, per the safety rules in the project brief.
"""
from __future__ import annotations

from pydantic import Field

from ageo.application.tools.contract import (
    CrsEffect,
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import ToolExecutionError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import CrsRequirement, InputRequirement


class ReprojectInput(StrictModel):
    layer: LayerRef
    target_srid: str = Field(pattern=r"^[A-Za-z]+:\d+$", description="e.g. 'EPSG:5254'")


class ReprojectOutput(StrictModel):
    layer: LayerRef
    srid: str
    feature_count: int


@registry.register
class Reproject(Tool[ReprojectInput, ReprojectOutput]):
    Input = ReprojectInput
    Output = ReprojectOutput
    spec = ToolSpec(
        name="reproject",
        summary="Transform a layer to a target CRS via pyproj. Source layer "
                "must have a defined CRS (assign/detect it first).",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.ANY_DEFINED)
        },
        crs_effect=CrsEffect.FROM_PARAM,
        crs_param="target_srid",
        failure_modes=("transform_failed",),
    )

    def run(self, params: ReprojectInput, ctx: ToolContext) -> ReprojectOutput:
        gdf = ctx.read(params.layer)
        try:
            transformed = gdf.to_crs(params.target_srid)
        except Exception as exc:
            raise ToolExecutionError(
                f"transform_failed: {params.target_srid}: {exc}"
            ) from exc
        ref = ctx.write(transformed, name=f"reprojected_{params.target_srid.replace(':', '_').lower()}")
        return ReprojectOutput(
            layer=ref, srid=params.target_srid, feature_count=len(transformed)
        )
