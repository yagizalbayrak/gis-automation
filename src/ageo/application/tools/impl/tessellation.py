"""Tessellation tools: voronoi_polygons, grid_generation.

Both derive new polygon geometry purely from planar coordinates, so - like
buffer/centroid/simplify_geometry - they require a projected metric CRS
rather than a distorted geographic-degree tessellation.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from pydantic import Field
from shapely import MultiPoint, voronoi_polygons
from shapely.geometry import box

from ageo.application.tools.contract import (
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import EmptyLayerError, ToolExecutionError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import (
    CrsRequirement,
    GeometryClass,
    InputRequirement,
)

_MAX_GRID_CELLS = 200_000


class VoronoiPolygonsInput(StrictModel):
    layer: LayerRef
    clip_to_extent: bool = Field(
        default=True,
        description="Clip voronoi cells to the input layer's bounding box",
    )


class VoronoiPolygonsOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class VoronoiPolygons(Tool[VoronoiPolygonsInput, VoronoiPolygonsOutput]):
    Input = VoronoiPolygonsInput
    Output = VoronoiPolygonsOutput
    spec = ToolSpec(
        name="voronoi_polygons",
        summary="Build a Voronoi tessellation from a point layer (each cell is "
                "the area closest to one input point). Input must be a "
                "projected metric CRS with at least 2 points.",
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.PROJECTED_METRIC,
                geometry=frozenset({GeometryClass.POINT}),
                requires_valid_geometry=True,
            )
        },
        failure_modes=("empty_layer", "insufficient_points"),
    )

    def run(
        self, params: VoronoiPolygonsInput, ctx: ToolContext
    ) -> VoronoiPolygonsOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: nothing to tessellate")
        if len(gdf) < 2:
            raise ToolExecutionError(
                "insufficient_points: voronoi tessellation requires at least "
                "2 points"
            )

        collection = voronoi_polygons(MultiPoint(list(gdf.geometry)))
        cells = gpd.GeoDataFrame(geometry=list(collection.geoms), crs=gdf.crs)

        if params.clip_to_extent:
            extent = gpd.GeoDataFrame(
                geometry=[box(*gdf.total_bounds)], crs=gdf.crs
            )
            cells = gpd.overlay(cells, extent, how="intersection")

        ref = ctx.write(cells, name="voronoi_cells")
        return VoronoiPolygonsOutput(layer=ref, feature_count=len(cells))


class GridGenerationInput(StrictModel):
    layer: LayerRef
    cell_size_m: float = Field(gt=0, description="Grid cell edge length in metres")
    clip_to_boundary: bool = Field(
        default=True,
        description="Clip the grid to the boundary layer instead of its "
                     "rectangular extent",
    )


class GridGenerationOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class GridGeneration(Tool[GridGenerationInput, GridGenerationOutput]):
    Input = GridGenerationInput
    Output = GridGenerationOutput
    spec = ToolSpec(
        name="grid_generation",
        summary="Generate a square grid covering a polygon boundary's extent, "
                "in a given cell size (metres); optionally clipped to the "
                "boundary shape. Input must be a projected metric CRS.",
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.PROJECTED_METRIC,
                geometry=frozenset({GeometryClass.POLYGON}),
                requires_valid_geometry=True,
            )
        },
        failure_modes=("empty_layer", "too_many_cells"),
    )

    def run(
        self, params: GridGenerationInput, ctx: ToolContext
    ) -> GridGenerationOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: nothing to grid")

        minx, miny, maxx, maxy = gdf.total_bounds
        size = params.cell_size_m
        n_cols = int(np.ceil((maxx - minx) / size)) or 1
        n_rows = int(np.ceil((maxy - miny) / size)) or 1
        if n_cols * n_rows > _MAX_GRID_CELLS:
            raise ToolExecutionError(
                f"too_many_cells: {n_cols * n_rows} cells requested (limit "
                f"{_MAX_GRID_CELLS}). Increase cell_size_m."
            )

        cells = [
            box(minx + col * size, miny + row * size,
                minx + (col + 1) * size, miny + (row + 1) * size)
            for col in range(n_cols)
            for row in range(n_rows)
        ]
        grid = gpd.GeoDataFrame(geometry=cells, crs=gdf.crs)

        if params.clip_to_boundary:
            boundary = gpd.GeoDataFrame(geometry=gdf.geometry.values, crs=gdf.crs)
            grid = gpd.overlay(grid, boundary, how="intersection")

        ref = ctx.write(grid, name="grid")
        return GridGenerationOutput(layer=ref, feature_count=len(grid))
