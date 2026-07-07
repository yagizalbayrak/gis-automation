// Tools whose output is CRS bookkeeping, a validation report, or a
// delivery export rather than a meaningful intermediate preview - ghosting
// them would be visual noise, not progress.
export const GHOST_SKIP_TOOLS = new Set([
  "reproject",
  "detect_crs",
  "validate_geometry",
  "save_vector",
  "package_outputs",
]);

export const GHOST_COLOR = "#5b7290";

export const NAMED_LAYER_COLORS: Record<string, string> = {
  all_roads: "#7c8899",
  selected_roads: "#35d5e8",
  buffered: "#ff9d3a",
  suitable_area: "#ff9d3a",
  schools: "#35d5e8",
  main_roads: "#7c8899",
};
export const FALLBACK_COLORS = ["#34d399", "#c084fc", "#fbbf24", "#fb7185"];

export function extractLayerIds(result: unknown): string[] {
  if (!result || typeof result !== "object") return [];
  const ids: string[] = [];
  for (const value of Object.values(result as Record<string, unknown>)) {
    if (isLayerRefShaped(value)) {
      ids.push(value.layer_id);
    } else if (Array.isArray(value)) {
      for (const item of value) {
        if (isLayerRefShaped(item)) ids.push(item.layer_id);
      }
    }
  }
  return ids;
}

function isLayerRefShaped(value: unknown): value is { layer_id: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).layer_id === "string"
  );
}

export function geometryTypesIn(fc: GeoJSON.FeatureCollection): Set<string> {
  const types = new Set<string>();
  for (const feature of fc.features) {
    if (feature.geometry) types.add(feature.geometry.type);
  }
  return types;
}

export function hasGeometry(types: Set<string>, base: "Polygon" | "LineString" | "Point"): boolean {
  return types.has(base) || types.has(`Multi${base}`);
}

export function extendBoundsWithFeatureCollection(
  bounds: maplibregl.LngLatBounds,
  fc: GeoJSON.FeatureCollection,
): void {
  for (const feature of fc.features) {
    walkCoordinates(feature.geometry, (lon, lat) => bounds.extend([lon, lat]));
  }
}

function walkCoordinates(
  geometry: GeoJSON.Geometry | null | undefined,
  visit: (lon: number, lat: number) => void,
): void {
  if (!geometry || geometry.type === "GeometryCollection") return;
  const walk = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === "number") {
      visit(node[0] as number, node[1] as number);
      return;
    }
    for (const child of node) walk(child);
  };
  walk((geometry as { coordinates?: unknown }).coordinates);
}
