# Evaluation Findings - 50-Scenario Pool, Gemini 2.5 Flash

Runs: `run1.json` (full pool, 2026-07-03), `run2.json` (24 re-runs after
fixes). Harness: `uv run python -m ageo.evals`. Plans validated statically,
never executed - zero Overpass load, ~70 Flash calls total.

## Final scoreboard (best result per scenario)

| Outcome | Count | Meaning |
|---|---|---|
| registered / needs_input | 4 | deterministic layer, zero tokens |
| composed_ok | 27 | valid plan, passed structural + CRS validation |
| composed_refused | 19 | honest refusal naming the missing capability |
| unresolved failures | 0 | - |

**49/50 scenarios behave as intended** (S26 exceeded expectations: refused a
degree-based buffer with a correct geodetic explanation instead of guessing).

## Headline quality findings

1. **All 27 successful plans validated on the FIRST attempt.** The retry
   loop exists but was never needed - catalog + system prompt are
   well-calibrated for Gemini 2.5 Flash.
2. **Geodetic discipline held under adversarial prompts**: explicit
   "process in EPSG:4326" was disobeyed in favour of EPSG:5254 (S27); a
   foot-based CRS suggestion was ignored (S29); Erzurum correctly got UTM
   37N rather than a hardcoded TM30 (S28).
3. **Longest chain: 13 steps first-try** (S47 multi-ring impact zones).
4. **Refusals are precise**: every gap scenario's refusal names the exact
   missing capability, making the build list below machine-harvested.

## Fixes that came out of run 1

- `max_tokens` 2000 -> 8000 in the composer adapter: ALL 16 run-1
  "failures" were JSON truncation (Gemini 2.5 spends output budget on
  internal reasoning), not model or rate-limit problems.
- Empty-plan refusals are now first-class (`plan_refused: <reason>`), not
  schema errors; never retried; reason surfaced to the user.
- System prompt now forbids fake substitutes (run 1 produced an 800 m
  circular buffer posing as a "10-minute walk isochrone" and a
  fetch-only plan posing as slope analysis; run 2 refuses both).

## Tool build list (harvested from refusals, ordered by effort/value)

**Status (2026-07-07): Tier 1 is fully built.** All items below are
registered tools with offline unit + guard tests (see
`src/ageo/application/tools/impl/geometry_ops.py`, `spatial_analysis.py`,
`tessellation.py`, `aggregate.py`, `csv_import.py`, `io_vector.py`,
`packaging.py`). `grid_generation` produces a square grid only - S46's
"hex-grid" title is not literally satisfied. Live-LLM re-run of S43-S50
to flip the scoreboard below is still pending explicit user approval
(see HANDOFF.md "Next steps").

**Tier 1 - trivial GeoPandas/Shapely wrappers, high demand:**
- `calculate_area` (S33), `calculate_length` (S34) - also need scalar/table
  outputs, not just layers - DONE
- `centroid` (S43), `simplify_geometry` (S44, metric-CRS tolerance) - DONE
- `count_points_in_polygons` / group-aggregate (S35, S46) - DONE
- `nearest_neighbor_distance` via sjoin_nearest (S36) - DONE
- `merge_layers` (S48), `csv_to_point_layer` (S30, in the brief) - DONE
- DXF + KML drivers in `save_vector` (S49, S50 - both in the brief's
  output-format list) - DONE (KML additionally refuses non-EPSG:4326
  layers rather than let GDAL reproject silently)
- `voronoi` (S45, as `voronoi_polygons`), `grid_generation` (S46, square
  cells only) - DONE

**Tier 2 - new adapters/design work:**
- bulk `geocoding` (S42; Nominatim rate limits!)
- batch folder processing (S48; roadmap Phase 3)
- `degree_distance_clarification` HIL flow (S26)

**Tier 3 - new subsystems (roadmap Phase 5+):**
- routing engine (S37), isochrones (S38) - pgRouting/network model
- raster stack: DEM, slope, zonal statistics, density/heatmap
  (S39, S40, S41)

## Re-run protocol

After adding tools, re-run gap scenarios: they should flip from
`composed_refused` to `composed_ok` one by one - a living progress metric.
`uv run python -m ageo.evals --only S33 S34 S43 ...`
