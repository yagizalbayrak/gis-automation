"""OSM data-fetch tools.

The tools own the contract; the network lives behind ctx.osm (an
OsmGateway implemented in infrastructure, faked in tests). Everything
OSM returns is EPSG:4326 by definition - the specs declare SETS_WGS84
so the workflow registry can reason about it symbolically.
"""
from __future__ import annotations

from pydantic import Field

from ageo.application.tools.contract import (
    CrsEffect,
    LayerRef,
    StrictModel,
    Tool,
    ToolContext,
    ToolSpec,
)
from ageo.application.tools.errors import EmptyLayerError, GatewayError
from ageo.application.tools.registry import registry
from ageo.domain.value_objects.requirements import (
    CrsRequirement,
    GeometryClass,
    InputRequirement,
)


def _require_gateway(ctx: ToolContext):
    if ctx.osm is None:
        raise GatewayError(
            "OSM gateway is not configured for this session; cannot fetch OSM data."
        )
    return ctx.osm


class FetchOsmBoundaryInput(StrictModel):
    place_name: str = Field(min_length=2, description="e.g. 'Kutahya, Turkey'")


class FetchOsmBoundaryOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class FetchOsmBoundary(Tool[FetchOsmBoundaryInput, FetchOsmBoundaryOutput]):
    Input = FetchOsmBoundaryInput
    Output = FetchOsmBoundaryOutput
    spec = ToolSpec(
        name="fetch_osm_boundary",
        summary="Fetch an administrative boundary polygon from OSM by place "
                "name. Result is EPSG:4326.",
        crs_effect=CrsEffect.SETS_WGS84,
        failure_modes=("gateway_unavailable", "place_not_found"),
    )

    def run(self, params: FetchOsmBoundaryInput, ctx: ToolContext) -> FetchOsmBoundaryOutput:
        gateway = _require_gateway(ctx)
        boundary = gateway.fetch_boundary(params.place_name)
        if boundary is None or boundary.empty:
            raise EmptyLayerError(f"place_not_found: {params.place_name!r}")
        ref = ctx.write(boundary, name=f"boundary_{params.place_name.lower()}")
        return FetchOsmBoundaryOutput(layer=ref, feature_count=len(boundary))


class FetchOsmFeaturesInput(StrictModel):
    boundary: LayerRef
    key: str = Field(min_length=1, description="OSM tag key, e.g. 'highway'")
    value: str | None = Field(
        default=None, description="OSM tag value filter; None fetches all values"
    )
    require_tags: tuple[str, ...] = Field(
        default=(),
        description="Only fetch features that also carry these tags (e.g. "
                    "['name'] for named roads) - keeps queries small",
    )


class FetchOsmFeaturesOutput(StrictModel):
    layer: LayerRef
    feature_count: int


@registry.register
class FetchOsmFeatures(Tool[FetchOsmFeaturesInput, FetchOsmFeaturesOutput]):
    Input = FetchOsmFeaturesInput
    Output = FetchOsmFeaturesOutput
    spec = ToolSpec(
        name="fetch_osm_features",
        summary="Fetch OSM features by tag (e.g. highway=*) inside a boundary "
                "polygon. Boundary must be geographic; result is EPSG:4326.",
        input_requirements={
            "boundary": InputRequirement(
                crs=CrsRequirement.GEOGRAPHIC,
                geometry=frozenset({GeometryClass.POLYGON}),
            )
        },
        crs_effect=CrsEffect.SETS_WGS84,
        failure_modes=("gateway_unavailable", "no_features_found"),
    )

    def run(self, params: FetchOsmFeaturesInput, ctx: ToolContext) -> FetchOsmFeaturesOutput:
        gateway = _require_gateway(ctx)
        boundary = ctx.read(params.boundary)
        features = gateway.fetch_features(
            boundary, params.key, params.value, params.require_tags
        )
        if features is None or features.empty:
            raise EmptyLayerError(
                f"no_features_found: {params.key}={params.value or '*'}"
            )
        ref = ctx.write(features, name=f"osm_{params.key}")
        return FetchOsmFeaturesOutput(layer=ref, feature_count=len(features))
