"""Topology and geometry quality tools: validate_geometry, repair_geometry.

Both run in any CRS (including undefined) on purpose: quality checking
broken uploads is exactly when the CRS may still be unresolved.
"""
from __future__ import annotations

from ageo.application.tools.contract import (
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import CrsRequirement, InputRequirement

_NO_CRS_NEEDED = {"layer": InputRequirement(crs=CrsRequirement.NONE)}


class ValidateGeometryInput(StrictModel):
    layer: LayerRef


class ValidateGeometryOutput(StrictModel):
    feature_count: int
    invalid_count: int
    empty_count: int
    duplicate_count: int
    is_clean: bool


@registry.register
class ValidateGeometry(Tool[ValidateGeometryInput, ValidateGeometryOutput]):
    Input = ValidateGeometryInput
    Output = ValidateGeometryOutput
    spec = ToolSpec(
        name="validate_geometry",
        summary="Report invalid, empty and duplicate geometries (Shapely 2.x "
                "validity rules). Read-only; never mutates the layer.",
        input_requirements=_NO_CRS_NEEDED,
    )

    def run(self, params: ValidateGeometryInput, ctx: ToolContext) -> ValidateGeometryOutput:
        gdf = ctx.read(params.layer)
        geoms = gdf.geometry
        invalid = int((~geoms.is_valid).sum())
        empty = int(geoms.is_empty.sum() + geoms.isna().sum())
        duplicates = int(geoms.to_wkb().duplicated().sum())
        return ValidateGeometryOutput(
            feature_count=len(gdf),
            invalid_count=invalid,
            empty_count=empty,
            duplicate_count=duplicates,
            is_clean=(invalid == 0 and empty == 0 and duplicates == 0),
        )


class RepairGeometryInput(StrictModel):
    layer: LayerRef
    drop_duplicates: bool = True


class RepairGeometryOutput(StrictModel):
    layer: LayerRef
    repaired_count: int
    dropped_count: int
    feature_count: int


@registry.register
class RepairGeometry(Tool[RepairGeometryInput, RepairGeometryOutput]):
    Input = RepairGeometryInput
    Output = RepairGeometryOutput
    spec = ToolSpec(
        name="repair_geometry",
        summary="Repair invalid geometries with Shapely make_valid, drop empty "
                "or missing geometries, optionally drop exact duplicates.",
        input_requirements=_NO_CRS_NEEDED,
    )

    def run(self, params: RepairGeometryInput, ctx: ToolContext) -> RepairGeometryOutput:
        gdf = ctx.read(params.layer).copy()
        before = len(gdf)

        invalid_mask = ~gdf.geometry.is_valid
        repaired_count = int(invalid_mask.sum())
        if repaired_count:
            gdf.loc[invalid_mask, gdf.geometry.name] = gdf.geometry[invalid_mask].make_valid()

        keep = ~(gdf.geometry.is_empty | gdf.geometry.isna())
        gdf = gdf[keep]
        if params.drop_duplicates:
            gdf = gdf[~gdf.geometry.to_wkb().duplicated()]

        ref = ctx.write(gdf, name="repaired")
        return RepairGeometryOutput(
            layer=ref,
            repaired_count=repaired_count,
            dropped_count=before - len(gdf),
            feature_count=len(gdf),
        )
