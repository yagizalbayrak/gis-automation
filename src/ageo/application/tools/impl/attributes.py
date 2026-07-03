"""Attribute tools: filter_by_attribute.

Case-insensitive matching folds Turkish diacritics on both sides: real
OSM data carries names like "Atatürk Bulvarı" while users routinely type
"Ataturk Bulvari" - plain lowercasing cannot equate i/ı or u/ü. The
uppercase dotted İ is folded BEFORE lowercasing because Python's
str.lower() turns it into "i" + a combining dot that silently breaks
equality.
"""
from __future__ import annotations

from pydantic import Field, model_validator

_TR_FOLD = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


def _fold(text: str) -> str:
    return text.translate(_TR_FOLD).lower()

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


class FilterByAttributeInput(StrictModel):
    layer: LayerRef
    field: str = Field(min_length=1)
    equals: str | None = None
    contains: str | None = None  # case-insensitive substring match
    in_values: tuple[str, ...] | None = None  # exact membership, e.g. road classes
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _exactly_one_predicate(self) -> "FilterByAttributeInput":
        provided = [
            p for p in (self.equals, self.contains, self.in_values) if p is not None
        ]
        if len(provided) != 1:
            raise ValueError(
                "Provide exactly one of 'equals', 'contains' or 'in_values'."
            )
        return self


class FilterByAttributeOutput(StrictModel):
    layer: LayerRef
    matched_count: int


@registry.register
class FilterByAttribute(Tool[FilterByAttributeInput, FilterByAttributeOutput]):
    Input = FilterByAttributeInput
    Output = FilterByAttributeOutput
    spec = ToolSpec(
        name="filter_by_attribute",
        summary="Select features by attribute equality, substring match, or "
                "value-set membership (e.g. street names on the OSM 'name' "
                "field, or road classes via in_values on 'highway').",
        input_requirements={
            "layer": InputRequirement(crs=CrsRequirement.NONE)
        },
        failure_modes=("missing_field",),
    )

    def run(self, params: FilterByAttributeInput, ctx: ToolContext) -> FilterByAttributeOutput:
        gdf = ctx.read(params.layer)
        if params.field not in gdf.columns:
            raise ToolExecutionError(
                f"missing_field: {params.field!r} not in layer attributes "
                f"{sorted(c for c in gdf.columns if c != gdf.geometry.name)}"
            )
        column = gdf[params.field].astype("string")
        haystack = column if params.case_sensitive else column.map(
            lambda v: _fold(v) if isinstance(v, str) else v
        )
        if params.equals is not None:
            needle = params.equals if params.case_sensitive else _fold(params.equals)
            mask = haystack == needle
        elif params.in_values is not None:
            values = (
                set(params.in_values)
                if params.case_sensitive
                else {_fold(v) for v in params.in_values}
            )
            mask = haystack.isin(values)
        else:
            needle = params.contains if params.case_sensitive else _fold(params.contains)
            mask = haystack.str.contains(needle, na=False, regex=False)
        selected = gdf[mask.fillna(False)]
        ref = ctx.write(selected, name=f"filtered_{params.field}")
        return FilterByAttributeOutput(layer=ref, matched_count=len(selected))
