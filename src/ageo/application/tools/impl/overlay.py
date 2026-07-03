"""Overlay tools: clip, intersect, difference.

Cross-layer CRS equality cannot be expressed as a per-input declarative
requirement, so it is checked in-tool via _require_same_crs and declared
as the 'crs_mismatch' failure mode.
"""
from __future__ import annotations

from typing import Any

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
from ageo.domain.value_objects.requirements import (
    CrsRequirement,
    GeometryClass,
    InputRequirement,
)


def _require_same_crs(left: Any, right: Any, left_name: str, right_name: str) -> None:
    if left.crs != right.crs:
        raise ToolExecutionError(
            f"crs_mismatch: {left_name} is {left.crs} but {right_name} is "
            f"{right.crs}. Reproject one of them first."
        )


class ClipInput(StrictModel):
    layer: LayerRef
    mask: LayerRef


class ClipOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class Clip(Tool[ClipInput, ClipOutput]):
    Input = ClipInput
    Output = ClipOutput
    spec = ToolSpec(
        name="clip",
        summary="Clip a layer by a polygon mask. Both layers must share the "
                "same CRS; reproject one of them first if they differ.",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.ANY_DEFINED),
            "mask": InputRequirement(
                crs=CrsRequirement.ANY_DEFINED,
                geometry=frozenset({GeometryClass.POLYGON}),
            ),
        },
        failure_modes=("crs_mismatch",),
    )

    def run(self, params: ClipInput, ctx: ToolContext) -> ClipOutput:
        gdf = ctx.read(params.layer)
        mask = ctx.read(params.mask)
        _require_same_crs(gdf, mask, "layer", "mask")
        clipped = gdf.clip(mask)
        ref = ctx.write(clipped, name="clipped")
        return ClipOutput(layer=ref, feature_count=len(clipped))


class OverlayInput(StrictModel):
    layer: LayerRef
    other: LayerRef


class OverlayOutput(StrictModel):
    layer: LayerRef
    feature_count: int


_OVERLAY_REQUIREMENTS = {
    "layer": InputRequirement(crs=CrsRequirement.ANY_DEFINED),
    "other": InputRequirement(
        crs=CrsRequirement.ANY_DEFINED,
        geometry=frozenset({GeometryClass.POLYGON}),
    ),
}


def _run_overlay(params: OverlayInput, ctx: ToolContext, how: str) -> OverlayOutput:
    gdf = ctx.read(params.layer)
    other = ctx.read(params.other)
    _require_same_crs(gdf, other, "layer", "other")
    try:
        result = gpd.overlay(gdf, other, how=how, keep_geom_type=True)
    except Exception as exc:
        raise ToolExecutionError(f"overlay_failed: {how}: {exc}") from exc
    ref = ctx.write(result, name=how)
    return OverlayOutput(layer=ref, feature_count=len(result))


@registry.register
class Intersect(Tool[OverlayInput, OverlayOutput]):
    Input = OverlayInput
    Output = OverlayOutput
    spec = ToolSpec(
        name="intersect",
        summary="Geometric intersection of a layer with a polygon layer, "
                "keeping attributes from both. Layers must share a CRS.",
        input_requirements=_OVERLAY_REQUIREMENTS,
        failure_modes=("crs_mismatch", "overlay_failed"),
    )

    def run(self, params: OverlayInput, ctx: ToolContext) -> OverlayOutput:
        return _run_overlay(params, ctx, "intersection")


@registry.register
class Difference(Tool[OverlayInput, OverlayOutput]):
    Input = OverlayInput
    Output = OverlayOutput
    spec = ToolSpec(
        name="difference",
        summary="Subtract a polygon layer from a layer (erase). Layers must "
                "share a CRS.",
        input_requirements=_OVERLAY_REQUIREMENTS,
        failure_modes=("crs_mismatch", "overlay_failed"),
    )

    def run(self, params: OverlayInput, ctx: ToolContext) -> OverlayOutput:
        return _run_overlay(params, ctx, "difference")
