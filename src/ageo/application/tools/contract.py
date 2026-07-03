"""Tool contract: every deterministic tool implements this shape.

A tool is (spec, input schema, output schema, deterministic run function).
The executor - not the tool - is responsible for guards, tracing and
error wrapping, so tools stay small and unit-testable.

Design rules enforced here:
- Tool I/O crosses the boundary only as strict, frozen Pydantic models.
- Geometries never cross the boundary: layers travel as LayerRef handles
  into a session workspace. The LLM planner sees schemas and refs only.
- Tools must not call LLMs and must not do I/O except through ToolContext.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, ClassVar, Generic, Literal, Protocol, TypeVar, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

from ageo.domain.value_objects.crs import CrsDescriptor
from ageo.domain.value_objects.requirements import InputRequirement


class StrictModel(BaseModel):
    """Base for all tool I/O. Strict types, no silent coercion, immutable."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class LayerRef(StrictModel):
    """Opaque handle to a layer in the session workspace.

    Geometries never cross the tool boundary; only refs do. This keeps
    LLM context free of coordinate data and keeps batch runs cheap.
    """

    layer_id: str = Field(min_length=1)


class CrsEffect(StrEnum):
    """How a tool affects the CRS of the layers it produces.

    Interpreted symbolically by the workflow registry to prove chains
    CRS-coherent at registration time.
    """

    PRESERVES = "preserves"        # output CRS == input CRS (buffer, clip, filter)
    SETS_WGS84 = "sets_wgs84"      # output is EPSG:4326 (OSM fetches)
    FROM_PARAM = "from_param"      # output CRS taken from a parameter (reproject)
    RUNTIME = "runtime"            # CRS known only at runtime (load_vector)
    NONE = "none"                  # tool produces no layer output


class ToolSpec(StrictModel):
    """Registration-time metadata. This is what the planner catalog, the
    workflow registry and the trace panel see."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = "1.0.0"
    summary: str  # one line, shown in the planner catalog
    input_requirements: dict[str, InputRequirement] = Field(default_factory=dict)
    # ^ keyed by the LayerRef field name on the input schema, e.g. {"layer": ...}
    crs_effect: CrsEffect = CrsEffect.PRESERVES
    crs_param: str | None = None  # required when crs_effect is FROM_PARAM
    failure_modes: tuple[str, ...] = ()

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", arbitrary_types_allowed=True
    )


class OsmGateway(Protocol):
    """Gateway to OpenStreetMap data. Implemented in infrastructure
    (Overpass/Nominatim); faked in tests. Returns GeoDataFrames in EPSG:4326."""

    def fetch_boundary(self, place_name: str) -> Any: ...

    def fetch_features(
        self,
        boundary: Any,
        key: str,
        value: str | None,
        require_tags: tuple[str, ...] = (),
    ) -> Any: ...


class ToolContext(ABC):
    """Port bundle through which tools reach the workspace, CRS facts and
    external gateways. Implemented in infrastructure (in-memory GeoPandas
    workspace now, PostGIS later) - this seam is what lets execution move
    to the database in Phase 5 without touching tool code."""

    osm: OsmGateway | None = None

    @abstractmethod
    def read(self, ref: LayerRef) -> Any:
        """Return the layer as a GeoDataFrame. Raises UnknownLayerError."""

    @abstractmethod
    def write(self, data: Any, *, name: str) -> LayerRef:
        """Store a GeoDataFrame under a new ref."""

    @abstractmethod
    def crs_of(self, ref: LayerRef) -> CrsDescriptor | None:
        """CRS facts for a layer, or None if the layer has no CRS."""


def layer_ref_kind(annotation: Any) -> Literal["single", "collection"] | None:
    """Classify a schema field annotation as a layer input/output.

    'single' for LayerRef, 'collection' for tuple[LayerRef, ...] (used by
    tools such as package_outputs that consume many layers). Guards and
    the static workflow checker treat every element of a collection like
    a single ref - collections get no weaker guarantees.
    """
    if annotation is LayerRef:
        return "single"
    if get_origin(annotation) is tuple:
        args = get_args(annotation)
        if args and args[0] is LayerRef:
            return "collection"
    return None


TIn = TypeVar("TIn", bound=StrictModel)
TOut = TypeVar("TOut", bound=StrictModel)


class Tool(ABC, Generic[TIn, TOut]):
    """Base class for all deterministic tools."""

    spec: ClassVar[ToolSpec]
    Input: ClassVar[type[StrictModel]]
    Output: ClassVar[type[StrictModel]]

    @abstractmethod
    def run(self, params: TIn, ctx: ToolContext) -> TOut:
        """Deterministic execution. No LLM calls, no I/O outside ctx.
        Raises ToolExecutionError subclasses only."""
