"""Aggregation tools: dissolve, merge_layers."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
from pydantic import Field

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


class MergeLayersInput(StrictModel):
    layers: tuple[LayerRef, ...] = Field(min_length=2)


class MergeLayersOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class MergeLayers(Tool[MergeLayersInput, MergeLayersOutput]):
    Input = MergeLayersInput
    Output = MergeLayersOutput
    spec = ToolSpec(
        name="merge_layers",
        summary="Concatenate two or more layers into one (attribute union, "
                "missing fields become null). All layers must share the "
                "same CRS.",
        input_requirements={
            "layers": InputRequirement(crs=CrsRequirement.ANY_DEFINED)
        },
        failure_modes=("crs_mismatch",),
    )

    def run(self, params: MergeLayersInput, ctx: ToolContext) -> MergeLayersOutput:
        gdfs = [ctx.read(ref) for ref in params.layers]
        first_crs = gdfs[0].crs
        for position, gdf in enumerate(gdfs[1:], start=2):
            if gdf.crs != first_crs:
                raise ToolExecutionError(
                    f"crs_mismatch: layer 1 is {first_crs} but layer "
                    f"{position} is {gdf.crs}. Reproject to a common CRS first."
                )
        merged = gpd.GeoDataFrame(
            pd.concat(gdfs, ignore_index=True), crs=first_crs
        )
        ref = ctx.write(merged, name="merged")
        return MergeLayersOutput(layer=ref, feature_count=len(merged))
