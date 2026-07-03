"""Spatial join."""
from __future__ import annotations

from typing import Literal

import geopandas as gpd

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


class SpatialJoinInput(StrictModel):
    layer: LayerRef   # left: features to enrich
    other: LayerRef   # right: attribute source
    predicate: Literal["intersects", "within", "contains"] = "intersects"
    how: Literal["inner", "left"] = "inner"


class SpatialJoinOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class SpatialJoin(Tool[SpatialJoinInput, SpatialJoinOutput]):
    Input = SpatialJoinInput
    Output = SpatialJoinOutput
    spec = ToolSpec(
        name="spatial_join",
        summary="Join attributes from one layer onto another by spatial "
                "predicate (intersects/within/contains). Same CRS required.",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.ANY_DEFINED),
            "other": InputRequirement(crs=CrsRequirement.ANY_DEFINED),
        },
        failure_modes=("crs_mismatch",),
    )

    def run(self, params: SpatialJoinInput, ctx: ToolContext) -> SpatialJoinOutput:
        left = ctx.read(params.layer)
        right = ctx.read(params.other)
        if left.crs != right.crs:
            raise ToolExecutionError(
                f"crs_mismatch: layer is {left.crs} but other is {right.crs}. "
                f"Reproject one of them first."
            )
        joined = gpd.sjoin(left, right, predicate=params.predicate, how=params.how)
        joined = joined.drop(columns=["index_right"], errors="ignore")
        ref = ctx.write(joined, name=f"joined_{params.predicate}")
        return SpatialJoinOutput(layer=ref, feature_count=len(joined))
