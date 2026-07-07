"""Spatial analysis tools for counts, distances and site suitability scoring.

Cross-layer CRS equality cannot be expressed as a per-input declarative
requirement (see overlay.py), so two-layer tools check it themselves and
declare 'crs_mismatch' as a failure mode.
"""
from __future__ import annotations

from typing import Literal

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


class ScoreCriterion(StrictModel):
    field: str = Field(
        min_length=1,
        description="Numeric attribute to normalize and include in the score",
    )
    direction: Literal["maximize", "minimize"] = Field(
        description="'maximize' rewards larger values; 'minimize' rewards smaller values"
    )
    weight: float = Field(gt=0.0, description="Relative criterion weight")
    min_value: float | None = Field(
        default=None,
        description="Optional lower normalization bound; defaults to field minimum",
    )
    max_value: float | None = Field(
        default=None,
        description="Optional upper normalization bound; defaults to field maximum",
    )


class ScoreCandidatesInput(StrictModel):
    layer: LayerRef
    criteria: tuple[ScoreCriterion, ...] = Field(
        min_length=1,
        description="Weighted numeric criteria used to rank candidate sites",
    )
    output_field: str = Field(
        default="suitability_score",
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    rank_field: str = Field(
        default="suitability_rank",
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    top_n: int | None = Field(
        default=None,
        ge=1,
        description="Optionally keep only the top N ranked candidates",
    )


class ScoreCandidatesOutput(StrictModel):
    layer: LayerRef
    feature_count: int
    best_score: float
    worst_score: float
    mean_score: float


@registry.register
class ScoreCandidates(Tool[ScoreCandidatesInput, ScoreCandidatesOutput]):
    Input = ScoreCandidatesInput
    Output = ScoreCandidatesOutput
    spec = ToolSpec(
        name="score_candidates",
        summary="Rank candidate sites with a weighted suitability score. "
                "Each numeric criterion is normalized to 0-100, either "
                "maximized (larger is better) or minimized (smaller is better).",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.ANY_DEFINED)
        },
        failure_modes=(
            "empty_layer", "missing_field", "non_numeric_field",
            "invalid_criteria",
        ),
    )

    def run(
        self, params: ScoreCandidatesInput, ctx: ToolContext
    ) -> ScoreCandidatesOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: layer must have candidate features")

        total_weight = sum(criterion.weight for criterion in params.criteria)
        if total_weight <= 0:
            raise ToolExecutionError("invalid_criteria: total weight must be positive")

        result = gdf.copy()
        score = pd.Series(0.0, index=result.index, dtype="float64")
        for criterion in params.criteria:
            if criterion.field not in result.columns:
                raise ToolExecutionError(
                    f"missing_field: {criterion.field!r} not in layer attributes"
                )
            values = pd.to_numeric(result[criterion.field], errors="coerce")
            if values.notna().sum() == 0:
                raise ToolExecutionError(
                    f"non_numeric_field: {criterion.field!r} has no numeric values"
                )

            min_value = (
                criterion.min_value
                if criterion.min_value is not None
                else float(values.min(skipna=True))
            )
            max_value = (
                criterion.max_value
                if criterion.max_value is not None
                else float(values.max(skipna=True))
            )
            if max_value < min_value:
                raise ToolExecutionError(
                    f"invalid_criteria: {criterion.field!r} max_value is below min_value"
                )
            if max_value == min_value:
                normalized = pd.Series(1.0, index=result.index, dtype="float64")
            elif criterion.direction == "maximize":
                normalized = (values - min_value) / (max_value - min_value)
            else:
                normalized = (max_value - values) / (max_value - min_value)

            normalized = normalized.clip(lower=0.0, upper=1.0).fillna(0.0)
            score += normalized * (criterion.weight / total_weight)

        result[params.output_field] = (score * 100.0).round(6)
        result = result.sort_values(
            params.output_field, ascending=False, kind="mergesort"
        )
        result[params.rank_field] = range(1, len(result) + 1)
        if params.top_n is not None:
            result = result.head(params.top_n)

        values = result[params.output_field]
        ref = ctx.write(result, name="scored_candidates")
        return ScoreCandidatesOutput(
            layer=ref,
            feature_count=len(result),
            best_score=float(values.max()),
            worst_score=float(values.min()),
            mean_score=float(values.mean()),
        )
