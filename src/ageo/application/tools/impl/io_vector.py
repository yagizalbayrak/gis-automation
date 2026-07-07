"""Vector I/O tools: load_vector, save_vector, detect_crs.

GeoPandas is used here as the tabular-geometry computation library (the
project's numpy, per the brief's technical foundation); all filesystem
and CRS-fact access still flows through ToolContext ports.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import geopandas as gpd
from pydantic import Field

from ageo.application.tools.contract import (
    CrsEffect,
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import EmptyLayerError, ToolExecutionError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import CrsRequirement, InputRequirement


class LoadVectorInput(StrictModel):
    path: str = Field(min_length=1)
    layer_name: str | None = None  # for multi-layer sources such as GeoPackage


class LoadVectorOutput(StrictModel):
    layer: LayerRef
    feature_count: int
    srid: str | None  # None => CRS missing; workflows must resolve before metric ops
    geometry_types: tuple[str, ...]


@registry.register
class LoadVector(Tool[LoadVectorInput, LoadVectorOutput]):
    Input = LoadVectorInput
    Output = LoadVectorOutput
    spec = ToolSpec(
        name="load_vector",
        summary="Load a vector dataset (Shapefile, GeoPackage, GeoJSON, DXF...) "
                "into the workspace. Reports CRS as found; never guesses.",
        crs_effect=CrsEffect.RUNTIME,
        failure_modes=("file_not_found", "unreadable_format", "empty_layer"),
    )

    def run(self, params: LoadVectorInput, ctx: ToolContext) -> LoadVectorOutput:
        source = Path(params.path)
        if not source.exists():
            raise ToolExecutionError(f"file_not_found: {source}")
        try:
            gdf = gpd.read_file(source, layer=params.layer_name)
        except Exception as exc:  # pyogrio raises driver-specific errors
            raise ToolExecutionError(f"unreadable_format: {source.name}: {exc}") from exc
        if gdf.empty:
            raise EmptyLayerError(f"empty_layer: {source.name}")

        ref = ctx.write(gdf, name=source.stem)
        crs = ctx.crs_of(ref)
        return LoadVectorOutput(
            layer=ref,
            feature_count=len(gdf),
            srid=crs.srid if crs else None,
            geometry_types=tuple(sorted(gdf.geometry.geom_type.dropna().unique())),
        )


class SaveVectorInput(StrictModel):
    layer: LayerRef
    path: str = Field(min_length=1)
    format: Literal["GPKG", "GeoJSON", "ESRI Shapefile", "DXF", "KML"] = "GPKG"


class SaveVectorOutput(StrictModel):
    path: str
    feature_count: int


@registry.register
class SaveVector(Tool[SaveVectorInput, SaveVectorOutput]):
    Input = SaveVectorInput
    Output = SaveVectorOutput
    spec = ToolSpec(
        name="save_vector",
        summary="Export a workspace layer to GeoPackage, GeoJSON, Shapefile, "
                "DXF or KML. Refuses to export layers without a defined CRS; "
                "KML additionally requires the layer already be in EPSG:4326 "
                "(GDAL would otherwise reproject silently, which this project "
                "never allows).",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.ANY_DEFINED)
        },
        crs_effect=CrsEffect.NONE,
        failure_modes=("write_failed", "kml_requires_wgs84"),
    )

    def run(self, params: SaveVectorInput, ctx: ToolContext) -> SaveVectorOutput:
        gdf = ctx.read(params.layer)
        if params.format == "KML" and gdf.crs.to_epsg() != 4326:
            raise ToolExecutionError(
                f"kml_requires_wgs84: layer is {gdf.crs}. KML only supports "
                f"EPSG:4326; insert an explicit 'reproject' step first "
                f"rather than relying on a silent GDAL reprojection."
            )
        target = Path(params.path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            gdf.to_file(target, driver=params.format)
        except Exception as exc:
            raise ToolExecutionError(f"write_failed: {target}: {exc}") from exc
        return SaveVectorOutput(path=str(target), feature_count=len(gdf))


class DetectCrsInput(StrictModel):
    layer: LayerRef


class DetectCrsOutput(StrictModel):
    defined: bool
    srid: str | None
    kind: str
    unit: str | None
    name: str | None


@registry.register
class DetectCrs(Tool[DetectCrsInput, DetectCrsOutput]):
    Input = DetectCrsInput
    Output = DetectCrsOutput
    spec = ToolSpec(
        name="detect_crs",
        summary="Report the CRS facts of a layer (authority, kind, unit). "
                "Works on layers with missing CRS - that is its point.",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.NONE)
        },
        crs_effect=CrsEffect.NONE,
    )

    def run(self, params: DetectCrsInput, ctx: ToolContext) -> DetectCrsOutput:
        crs = ctx.crs_of(params.layer)
        if crs is None:
            return DetectCrsOutput(
                defined=False, srid=None, kind="unknown", unit=None, name=None
            )
        return DetectCrsOutput(
            defined=True, srid=crs.srid, kind=crs.kind.value, unit=crs.unit,
            name=crs.name or None,
        )
