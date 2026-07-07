"""csv_to_point_layer: build a point layer from a CSV/TSV with x/y columns.

The source CRS of the coordinate columns is a required parameter, not a
guess - a CSV of decimal degrees and a CSV of projected metres look
identical on disk.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
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


class CsvToPointLayerInput(StrictModel):
    path: str = Field(min_length=1)
    x_field: str = Field(min_length=1, description="Column holding the x/longitude value")
    y_field: str = Field(min_length=1, description="Column holding the y/latitude value")
    srid: str = Field(
        default="EPSG:4326",
        pattern=r"^[A-Za-z]+:\d+$",
        description="CRS of the x/y coordinate columns, e.g. 'EPSG:4326'",
    )


class CsvToPointLayerOutput(StrictModel):
    layer: LayerRef
    feature_count: int
    srid: str


@registry.register
class CsvToPointLayer(Tool[CsvToPointLayerInput, CsvToPointLayerOutput]):
    Input = CsvToPointLayerInput
    Output = CsvToPointLayerOutput
    spec = ToolSpec(
        name="csv_to_point_layer",
        summary="Load a CSV/TSV file with x/y coordinate columns and build a "
                "point layer in the declared CRS.",
        crs_effect=CrsEffect.FROM_PARAM,
        crs_param="srid",
        failure_modes=(
            "file_not_found", "unreadable_format", "missing_field",
            "empty_layer", "invalid_coordinates",
        ),
    )

    def run(
        self, params: CsvToPointLayerInput, ctx: ToolContext
    ) -> CsvToPointLayerOutput:
        source = Path(params.path)
        if not source.exists():
            raise ToolExecutionError(f"file_not_found: {source}")
        try:
            df = pd.read_csv(source, sep=None, engine="python")
        except Exception as exc:
            raise ToolExecutionError(f"unreadable_format: {source.name}: {exc}") from exc

        missing = [f for f in (params.x_field, params.y_field) if f not in df.columns]
        if missing:
            raise ToolExecutionError(
                f"missing_field: {missing} not in CSV columns "
                f"{list(df.columns)}"
            )
        if df.empty:
            raise EmptyLayerError(f"empty_layer: {source.name}")

        try:
            xs = df[params.x_field].astype(float)
            ys = df[params.y_field].astype(float)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"invalid_coordinates: {exc}") from exc

        gdf = gpd.GeoDataFrame(
            df, geometry=gpd.points_from_xy(xs, ys), crs=params.srid
        )
        ref = ctx.write(gdf, name=source.stem)
        return CsvToPointLayerOutput(
            layer=ref, feature_count=len(gdf), srid=params.srid
        )
