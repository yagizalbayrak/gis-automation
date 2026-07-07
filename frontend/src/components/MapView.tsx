import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { getNamedLayer, getWorkspaceLayer } from "../lib/api";
import type { TaskStatus, TraceEvent } from "../lib/types";
import {
  extendBoundsWithFeatureCollection,
  extractLayerIds,
  FALLBACK_COLORS,
  GHOST_COLOR,
  GHOST_SKIP_TOOLS,
  geometryTypesIn,
  hasGeometry,
  NAMED_LAYER_COLORS,
} from "../lib/mapLayers";

const KUTAHYA: [number, number] = [29.98, 39.42];

interface MapViewProps {
  taskId: string | null;
  status: TaskStatus | undefined;
  trace: TraceEvent[];
  outputs: Record<string, string>;
}

export function MapView({ taskId, status, trace, outputs }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const ghostSourceIdsRef = useRef<Set<string>>(new Set());
  const ghostLayerIdsRef = useRef<string[]>([]);
  const finalSourceIdsRef = useRef<Set<string>>(new Set());
  const finalLayerIdsRef = useRef<string[]>([]);
  const generationRef = useRef(0);
  const processedTraceCountRef = useRef(0);
  const boundsRef = useRef(new maplibregl.LngLatBounds());
  const fallbackColorIndexRef = useRef(0);

  // Mount the map exactly once.
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "&copy; OpenStreetMap contributors",
          },
        },
        layers: [
          { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.9 } },
        ],
      },
      center: KUTAHYA,
      zoom: 11,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  const clearGhosts = () => {
    const map = mapRef.current;
    generationRef.current += 1;
    if (map) {
      for (const id of ghostLayerIdsRef.current) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      for (const id of ghostSourceIdsRef.current) {
        if (map.getSource(id)) map.removeSource(id);
      }
    }
    ghostLayerIdsRef.current = [];
    ghostSourceIdsRef.current = new Set();
  };

  const clearFinal = () => {
    const map = mapRef.current;
    if (map) {
      for (const id of finalLayerIdsRef.current) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      for (const id of finalSourceIdsRef.current) {
        if (map.getSource(id)) map.removeSource(id);
      }
    }
    finalLayerIdsRef.current = [];
    finalSourceIdsRef.current = new Set();
  };

  // A new task starts: wipe every trace of the previous run.
  useEffect(() => {
    clearGhosts();
    clearFinal();
    processedTraceCountRef.current = 0;
    boundsRef.current = new maplibregl.LngLatBounds();
    fallbackColorIndexRef.current = 0;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  // Progressive rendering: draw a fading-in "ghost" for every finished step.
  useEffect(() => {
    if (!taskId) return;
    const newEvents = trace.slice(processedTraceCountRef.current);
    processedTraceCountRef.current = trace.length;
    const generation = generationRef.current;

    for (const event of newEvents) {
      if (event.phase !== "tool_finished" || GHOST_SKIP_TOOLS.has(event.subject)) continue;
      const layerIds = extractLayerIds((event.detail as { result?: unknown })?.result);
      for (const layerId of layerIds) {
        void renderGhost(taskId, layerId, generation);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trace, taskId]);

  const renderGhost = async (taskId: string, layerId: string, generation: number) => {
    try {
      const layer = await getWorkspaceLayer(taskId, layerId);
      if (!layer || generation !== generationRef.current) return;
      addGhostLayer(layerId, layer.feature_collection);
    } catch {
      // Best-effort preview only; a failed fetch never blocks the run.
    }
  };

  const addGhostLayer = (layerId: string, fc: GeoJSON.FeatureCollection) => {
    const map = mapRef.current;
    if (!map || !fc.features.length) return;
    const sourceId = `ghost-${layerId}`;
    if (map.getSource(sourceId)) return;
    map.addSource(sourceId, { type: "geojson", data: fc });

    const types = geometryTypesIn(fc);
    const fades: { id: string; property: string; target: number }[] = [];

    if (hasGeometry(types, "Polygon")) {
      const id = `${sourceId}-fill`;
      map.addLayer({
        id,
        type: "fill",
        source: sourceId,
        paint: {
          "fill-color": GHOST_COLOR,
          "fill-opacity": 0,
          "fill-opacity-transition": { duration: 550, delay: 0 },
        },
        filter: ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false],
      });
      ghostLayerIdsRef.current.push(id);
      fades.push({ id, property: "fill-opacity", target: 0.22 });
    }
    if (hasGeometry(types, "LineString")) {
      const id = `${sourceId}-line`;
      map.addLayer({
        id,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": GHOST_COLOR,
          "line-width": 2.5,
          "line-opacity": 0,
          "line-opacity-transition": { duration: 550, delay: 0 },
        },
        filter: ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false],
      });
      ghostLayerIdsRef.current.push(id);
      fades.push({ id, property: "line-opacity", target: 0.6 });
    }
    if (hasGeometry(types, "Point")) {
      const id = `${sourceId}-circle`;
      map.addLayer({
        id,
        type: "circle",
        source: sourceId,
        paint: {
          "circle-color": GHOST_COLOR,
          "circle-radius": 4.5,
          "circle-opacity": 0,
          "circle-opacity-transition": { duration: 550, delay: 0 },
        },
        filter: ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false],
      });
      ghostLayerIdsRef.current.push(id);
      fades.push({ id, property: "circle-opacity", target: 0.6 });
    }
    ghostSourceIdsRef.current.add(sourceId);

    extendBoundsWithFeatureCollection(boundsRef.current, fc);
    if (!boundsRef.current.isEmpty()) {
      map.fitBounds(boundsRef.current, { padding: 72, maxZoom: 15, duration: 450 });
    }

    requestAnimationFrame(() => {
      for (const fade of fades) {
        if (map.getLayer(fade.id)) map.setPaintProperty(fade.id, fade.property, fade.target);
      }
    });
  };

  // Task finished: clear ghosts, and if it succeeded, draw the bold final
  // named outputs on top.
  useEffect(() => {
    if (!taskId || !status) return;
    if (status !== "running" && status !== "needs_input") {
      clearGhosts();
    }
    if (status === "succeeded") {
      void drawFinalOutputs(taskId, outputs);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, taskId, outputs]);

  const drawFinalOutputs = async (taskId: string, outputs: Record<string, string>) => {
    clearFinal();
    const map = mapRef.current;
    if (!map) return;
    const bounds = new maplibregl.LngLatBounds();

    for (const name of Object.keys(outputs)) {
      const layer = await getNamedLayer(taskId, name);
      if (!layer) continue;
      const color =
        NAMED_LAYER_COLORS[name] ||
        FALLBACK_COLORS[fallbackColorIndexRef.current++ % FALLBACK_COLORS.length];
      addFinalLayer(name, layer.feature_collection, color);
      extendBoundsWithFeatureCollection(bounds, layer.feature_collection);
    }
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 72, maxZoom: 15 });
  };

  const addFinalLayer = (name: string, fc: GeoJSON.FeatureCollection, color: string) => {
    const map = mapRef.current;
    if (!map) return;
    const sourceId = `out-${name}`;
    map.addSource(sourceId, { type: "geojson", data: fc });
    finalSourceIdsRef.current.add(sourceId);

    const types = geometryTypesIn(fc);
    if (hasGeometry(types, "Polygon")) {
      const fillId = `${sourceId}-fill`;
      map.addLayer({
        id: fillId,
        type: "fill",
        source: sourceId,
        paint: { "fill-color": color, "fill-opacity": 0.32 },
        filter: ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false],
      });
      finalLayerIdsRef.current.push(fillId);

      const outlineId = `${sourceId}-outline`;
      map.addLayer({
        id: outlineId,
        type: "line",
        source: sourceId,
        paint: { "line-color": color, "line-width": 1.75 },
        filter: ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false],
      });
      finalLayerIdsRef.current.push(outlineId);
    }
    if (hasGeometry(types, "LineString")) {
      const lineId = `${sourceId}-line`;
      map.addLayer({
        id: lineId,
        type: "line",
        source: sourceId,
        paint: { "line-color": color, "line-width": 3.25 },
        filter: ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false],
      });
      finalLayerIdsRef.current.push(lineId);
    }
    if (hasGeometry(types, "Point")) {
      const haloId = `${sourceId}-halo`;
      map.addLayer({
        id: haloId,
        type: "circle",
        source: sourceId,
        paint: { "circle-color": color, "circle-radius": 9, "circle-opacity": 0.25 },
        filter: ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false],
      });
      finalLayerIdsRef.current.push(haloId);

      const circleId = `${sourceId}-circle`;
      map.addLayer({
        id: circleId,
        type: "circle",
        source: sourceId,
        paint: {
          "circle-color": color,
          "circle-radius": 5,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#090b10",
        },
        filter: ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false],
      });
      finalLayerIdsRef.current.push(circleId);
    }
  };

  return (
    <div className="relative h-full w-full">
      {/* Inline position/inset: maplibre-gl.css sets .maplibregl-map's
          position to relative with equal specificity to Tailwind's
          .absolute utility, and whichever stylesheet loads later in the
          bundle wins the cascade - an inline style always wins instead. */}
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-bg/70 via-transparent to-transparent" />
    </div>
  );
}
