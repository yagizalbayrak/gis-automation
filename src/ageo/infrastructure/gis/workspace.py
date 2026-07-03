"""In-memory session workspace implementing ToolContext.

Phase 1 adapter: layers live as GeoDataFrames in process memory. The
PostGIS-backed workspace (Phase 5) implements the same ToolContext port,
which is why no tool code will change when execution moves into the
database.
"""
from __future__ import annotations

from typing import Any

from ageo.application.tools.contract import LayerRef, OsmGateway, ToolContext
from ageo.application.tools.errors import UnknownLayerError
from ageo.domain.ports.crs_info import CrsInfoPort
from ageo.domain.value_objects.crs import CrsDescriptor


class InMemoryWorkspace(ToolContext):
    def __init__(self, crs_info: CrsInfoPort, osm: OsmGateway | None = None) -> None:
        self._crs_info = crs_info
        self.osm = osm
        self._layers: dict[str, Any] = {}
        self._counter = 0

    def read(self, ref: LayerRef) -> Any:
        if ref.layer_id not in self._layers:
            raise UnknownLayerError(f"No such layer in workspace: {ref.layer_id!r}")
        return self._layers[ref.layer_id]

    def write(self, data: Any, *, name: str) -> LayerRef:
        self._counter += 1
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        layer_id = f"{safe_name}_{self._counter:04d}"
        self._layers[layer_id] = data
        return LayerRef(layer_id=layer_id)

    def crs_of(self, ref: LayerRef) -> CrsDescriptor | None:
        gdf = self.read(ref)
        if gdf.crs is None:
            return None
        return self._crs_info.describe(gdf.crs)

    def layer_ids(self) -> list[str]:
        return sorted(self._layers)
