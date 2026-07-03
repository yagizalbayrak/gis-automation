# Autonomous GIS Workbench (ageo)

Standalone, natural-language geospatial automation workbench. Few agents,
many tested tools, deterministic workflow registry, geodetic correctness
by construction. See [PROJECT_BRIEF_FABLE5.md](PROJECT_BRIEF_FABLE5.md)
for the full product brief.

## Phase 1 status - deterministic core

Implemented:

- **Domain layer** (`src/ageo/domain/`): pure-Python CRS/geometry invariants.
  `check_crs` is the geodetic gate: metric-CRS preconditions, undefined-CRS
  rejection.
- **Tool contract + registry** (`src/ageo/application/tools/`): strict
  Pydantic v2 I/O schemas, declarative CRS/geometry preconditions, opaque
  `LayerRef` handles (geometries never cross the tool boundary; collections
  via `tuple[LayerRef, ...]` get the same guards), import-time contract
  validation. 18 tools registered: load/save/detect_crs, reproject,
  buffer_metric, calculate_area/length, validate/repair_geometry, filter_by_attribute,
  fetch_osm_boundary/features, clip, intersect, difference, dissolve,
  spatial_join, package_outputs.
- **Guarded executor** (`src/ageo/application/orchestration/executor.py`):
  the only path through which tools run. Enforces CRS, geometry-class and
  validity guards uniformly; emits typed trace events for the audit trail.
- **Workflow registry** (`src/ageo/application/workflows/`): workflows are
  data (steps + `$params.x` / `$steps.id.field` bindings). Registration
  statically proves chains CRS-coherent - a workflow that buffers an
  EPSG:4326 layer cannot be registered.
- **Workflow runner**: validates parameters before step one, including the
  `srid_metric` contract (refuses non-metric target CRS at start time).
- **Infrastructure** (`src/ageo/infrastructure/gis/`): pyproj-backed CRS
  facts + location-aware metric CRS advisor (TUREF TM zones in Turkey, UTM
  elsewhere), in-memory workspace, Overpass/Nominatim OSM gateway.

- **Planner agents** (`src/ageo/application/agents/planner.py`):
  `DeterministicPlanner` matches natural language (Turkish-diacritics-aware)
  onto workflow `nl_patterns` and extracts parameters by regex - zero
  tokens. Missing parameters are reported for human-in-the-loop, never
  guessed. `HybridPlanner` consults the LLM port only when the
  deterministic pass cannot decide, treats the answer as untrusted data
  (hallucinated workflows rejected, unknown params dropped, missing_params
  recomputed from the registry) and silently degrades to the deterministic
  result if the model is unavailable.
- **LiteLLM adapter** (`src/ageo/infrastructure/llm/litellm_planner.py`):
  the system's only LLM call site. One completion per ambiguous request,
  small model by default (set `AGEO_PLANNER_MODEL` to enable/override),
  sees only the user text and the workflow catalog - never geometries.
- **Plan composer** (`src/ageo/application/agents/composer.py`): for
  requests no registered workflow covers (e.g. multi-criteria site search:
  "areas near a school and main roads"), a stronger model composes a NEW
  tool-chain plan - data, never code - grounded by RAG-lite recipes
  (`src/ageo/application/rag/`, bundled JSON, keyword-matched, lazy). The
  plan must pass the same validator bundled workflows pass (structure +
  static CRS coherence); a rejected plan gets one retry with the
  validator's error as feedback, then fails. Runtime guards still apply
  to every step. Enable with `AGEO_COMPOSER_MODEL`; `--demo` mode ships a
  scripted composer for the Kutahya rental scenario.
- **Reporter agent** (`src/ageo/application/agents/reporter.py`):
  deterministic, template-based process reports in English and Turkish
  (workflow, steps, CRS decisions, warnings, outputs, errors) built purely
  from the trace. Served at `GET /tasks/{id}/report?lang=en|tr` and shown
  in the UI with an EN/TR toggle.

- **LLM connection settings** (`src/ageo/infrastructure/llm/config.py` +
  Settings panel in the UI): choose a provider (Google Gemini default,
  Anthropic, OpenAI, or any custom LiteLLM model id), paste an API key,
  save, and run a one-click connection test. Settings persist to
  `~/.ageo/llm_settings.json` (owner-only permissions), keys are never
  echoed back (masked suffix only), and adapters read the live
  configuration on every call - no restart needed. Endpoints:
  `GET/PUT /settings/llm`, `POST /settings/llm/test`.
- **Web UI** (`src/ageo/interface/web/static/`): the operational workbench
  screen - left panel with the natural-language task box, "Understood"
  summary, live process trace (SSE), needs-input question forms and output
  list; right panel MapLibre map rendering output layers (roads, selections,
  buffers) with fit-to-results. Vanilla JS, no build toolchain.
- **Interface layer** (`src/ageo/interface/api/`): FastAPI app.
  `POST /tasks` runs planner -> guarded runner (with `needs_input` +
  `missing_params` for human-in-the-loop questions), `GET /tasks/{id}/trace`
  and `/events` (SSE) expose the full process log, `/layers/{name}` serves
  display-ready EPSG:4326 GeoJSON for the map panel (analysis CRS is
  preserved in the workspace), scalar/table outputs are returned under
  `results`, `/uploads` accepts files, `/catalog` lists workflows and tools.
  Each task gets an isolated workspace and trace.

Bundled workflows: `road_fetch_and_buffer` (the MVP scenario),
`preflight_quality_check`, `crs_normalization` (load -> reproject ->
delivery package with manifest).

## Development

```bash
uv sync                                             # install
uv run pytest                                       # 97 tests, all offline
uv run python -m ageo.interface.api.serve           # server on :8000, real OSM
uv run python -m ageo.interface.api.serve --demo    # offline synthetic Kutahya
```

LLM setup: paste your Google AI Studio key into `.env`:

```bash
GEMINI_API_KEY=your_key_here
AGEO_PLANNER_MODEL=gemini/gemini-2.5-flash
AGEO_COMPOSER_MODEL=gemini/gemini-2.5-flash
```

Saved UI settings in `~/.ageo/llm_settings.json` take precedence over `.env`.
If the UI has an old key saved, update it in Settings or remove that JSON file.

Open http://127.0.0.1:8000/ and try the example chips, e.g.:
`Kutahya'daki "Ataturk Caddesi" icin 25 m buffer uygula`
or the composed multi-criteria scenario:
`Kutahya Evliya Celebi Mahallesi'nde okula 500 m, ana yollara 250 m
mesafede kiralik ev icin uygun alanlari bul`

## Not yet built (by design order)

Vector-store RAG (pgvector) behind the RecipeStore interface, PostGIS
workspace, Docker packaging and sandbox, batch folder processing (Phase 3).
