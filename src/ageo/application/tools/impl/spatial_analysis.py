"""Two-layer spatial analysis: count_points_in_polygons, nearest_neighbor_distance.

Cross-layer CRS equality cannot be expressed as a per-input declarative
requirement (see overlay.py), so both tools check it themselves and
declare 'crs_mismatch' as a failure mode.
"""
from __future__ import annotations

import geopandas as gpd
from pydantic import Field

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


def _require_same_crs(left, right, left_name: str, right_name: str) -> None:
    if left.crs != right.crs:
        raise ToolExecutionError(
            f"crs_mismatch: {left_name} is {left.crs} but {right_name} is "
            f"{right.crs}. Reproject one of them first."
        )


class CountPointsInPolygonsInput(StrictModel):
    points: LayerRef
    polygons: LayerRef
    output_field: str = Field(
        default="point_count",
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Attribute name that will receive each polygon's point count",
    )


class CountPointsInPolygonsOutput(StrictModel):
    layer: LayerRef
    feature_count: int
    total_points_matched: int


@registry.register
class CountPointsInPolygons(
    Tool[CountPointsInPolygonsInput, CountPointsInPolygonsOutput]
):
    Input = CountPointsInPolygonsInput
    Output = CountPointsInPolygonsOutput
    spec = ToolSpec(
        name="count_points_in_polygons",
        summary="Count how many points fall within each polygon and attach the "
                "count as an attribute. Both layers must share the same CRS.",
        input_requirements={
            # 'polygons' declared first: it is the primary layer whose CRS
            # the output carries forward (PRESERVES propagates the first
            # declared input by convention - see workflows/validation.py).
            "polygons": InputRequirement(
                crs=CrsRequirement.ANY_DEFINED,
                geometry=frozenset({GeometryClass.POLYGON}),
            ),
            "points": InputRequirement(
                crs=CrsRequirement.ANY_DEFINED,
                geometry=frozenset({GeometryClass.POINT}),
            ),
        },
        failure_modes=("crs_mismatch",),
    )

    def run(
        self, params: CountPointsInPolygonsInput, ctx: ToolContext
    ) -> CountPointsInPolygonsOutput:
        points = ctx.read(params.points)
        polygons = ctx.read(params.polygons)
        _require_same_crs(points, polygons, "points", "polygons")

        result = polygons.copy()
        if points.empty or polygons.empty:
            result[params.output_field] = 0
            ref = ctx.write(result, name="point_counts")
            return CountPointsInPolygonsOutput(
                layer=ref, feature_count=len(result), total_points_matched=0
            )

        joined = gpd.sjoin(points, polygons, predicate="within", how="inner")
        counts = joined.groupby("index_right").size()
        result[params.output_field] = (
            result.index.map(counts).fillna(0).astype(int)
        )
        ref = ctx.write(result, name="point_counts")
        return CountPointsInPolygonsOutput(
            layer=ref,
            feature_count=len(result),
            total_points_matched=int(counts.sum()) if not counts.empty else 0,
        )


class NearestNeighborDistanceInput(StrictModel):
    layer: LayerRef
    other: LayerRef
    output_field: str = Field(
        default="nearest_distance_m",
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Attribute name that will receive the distance to the "
                     "nearest feature in 'other', in metres",
    )


class NearestNeighborDistanceOutput(StrictModel):
    layer: LayerRef
    feature_count: int
    min_distance_m: float
    max_distance_m: float
    mean_distance_m: float


@registry.register
class NearestNeighborDistance(
    Tool[NearestNeighborDistanceInput, NearestNeighborDistanceOutput]
):
    Input = NearestNeighborDistanceInput
    Output = NearestNeighborDistanceOutput
    spec = ToolSpec(
        name="nearest_neighbor_distance",
        summary="Attach the distance in metres to the nearest feature in "
                "'other' onto each feature of 'layer'. Both layers must "
                "already be in the same projected metric CRS.",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.PROJECTED_METRIC),
            "other": InputRequirement(crs=CrsRequirement.PROJECTED_METRIC),
        },
        failure_modes=("crs_mismatch", "empty_layer"),
    )

    def run(
        self, params: NearestNeighborDistanceInput, ctx: ToolContext
    ) -> NearestNeighborDistanceOutput:
        left = ctx.read(params.layer)
        right = ctx.read(params.other)
        _require_same_crs(left, right, "layer", "other")
        if left.empty or right.empty:
            raise EmptyLayerError(
                "empty_layer: both layer and other must have features"
            )

        joined = gpd.sjoin_nearest(left, right, distance_col=params.output_field)
        joined = joined[~joined.index.duplicated(keep="first")]
        joined = joined.drop(columns=["index_right"], errors="ignore")
        ref = ctx.write(joined, name="nearest_distance")
        values = joined[params.output_field]
        return NearestNeighborDistanceOutput(
            layer=ref,
            feature_count=len(joined),
            min_distance_m=float(values.min()),
            max_distance_m=float(values.max()),
            mean_distance_m=float(values.mean()),
        )
