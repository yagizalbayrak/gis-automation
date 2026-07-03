"""Measurement tools for metric GeoDataFrames.

Area and length calculations are only meaningful in a projected metric CRS.
The tools declare that precondition and let the executor guard enforce it.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from ageo.application.tools.contract import (
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import EmptyLayerError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import (
    CrsRequirement,
    GeometryClass,
    InputRequirement,
)


class CalculateAreaInput(StrictModel):
    layer: LayerRef
    output_field: str = Field(
        default="area_m2",
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Attribute name that will receive each feature area",
    )
    unit: Literal["m2", "ha"] = Field(
        default="m2",
        description="Area unit for output_field and table values: m2 or hectares",
    )


class CalculateAreaOutput(StrictModel):
    layer: LayerRef
    feature_count: int
    total_area_m2: float
    table: tuple[dict[str, Any], ...]


class CalculateLengthInput(StrictModel):
    layer: LayerRef
    output_field: str = Field(
        default="length_m",
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        description="Attribute name that will receive each feature length",
    )
    unit: Literal["m", "km"] = Field(
        default="m",
        description="Length unit for output_field and table values: metres or kilometres",
    )


class CalculateLengthOutput(StrictModel):
    layer: LayerRef
    feature_count: int
    total_length_m: float
    table: tuple[dict[str, Any], ...]


@registry.register
class CalculateArea(Tool[CalculateAreaInput, CalculateAreaOutput]):
    Input = CalculateAreaInput
    Output = CalculateAreaOutput
    spec = ToolSpec(
        name="calculate_area",
        summary=(
            "Calculate per-feature polygon area in square metres or hectares "
            "and return a layer with an area attribute plus a compact result table."
        ),
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.PROJECTED_METRIC,
                geometry=frozenset({GeometryClass.POLYGON}),
                requires_valid_geometry=True,
            )
        },
        failure_modes=("empty_layer",),
    )

    def run(self, params: CalculateAreaInput, ctx: ToolContext) -> CalculateAreaOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: nothing to measure")

        measured = gdf.copy()
        area_m2 = measured.geometry.area.astype(float)
        values = area_m2 / 10_000.0 if params.unit == "ha" else area_m2
        measured[params.output_field] = values
        ref = ctx.write(measured, name="area_measured")
        table = tuple(
            {params.output_field: float(value)}
            for value in measured[params.output_field].tolist()
        )
        return CalculateAreaOutput(
            layer=ref,
            feature_count=len(measured),
            total_area_m2=float(area_m2.sum()),
            table=table,
        )


@registry.register
class CalculateLength(Tool[CalculateLengthInput, CalculateLengthOutput]):
    Input = CalculateLengthInput
    Output = CalculateLengthOutput
    spec = ToolSpec(
        name="calculate_length",
        summary=(
            "Calculate per-feature line length in metres or kilometres and "
            "return a layer with a length attribute plus a compact result table."
        ),
        input_requirements={
            "layer": InputRequirement(
                crs=CrsRequirement.PROJECTED_METRIC,
                geometry=frozenset({GeometryClass.LINE}),
                requires_valid_geometry=True,
            )
        },
        failure_modes=("empty_layer",),
    )

    def run(
        self, params: CalculateLengthInput, ctx: ToolContext
    ) -> CalculateLengthOutput:
        gdf = ctx.read(params.layer)
        if gdf.empty:
            raise EmptyLayerError("empty_layer: nothing to measure")

        measured = gdf.copy()
        length_m = measured.geometry.length.astype(float)
        values = length_m / 1_000.0 if params.unit == "km" else length_m
        measured[params.output_field] = values
        ref = ctx.write(measured, name="length_measured")
        table = tuple(
            {params.output_field: float(value)}
            for value in measured[params.output_field].tolist()
        )
        return CalculateLengthOutput(
            layer=ref,
            feature_count=len(measured),
            total_length_m=float(length_m.sum()),
            table=table,
        )
