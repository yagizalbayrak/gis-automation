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
  validation. 27 tools registered: load/save (+DXF/KML)/detect_crs, reproject,
  buffer_metric, calculate_area/length, centroid, simplify_geometry,
  validate/repair_geometry, filter_by_attribute, fetch_osm_boundary/features,
  clip, intersect, difference, dissolve, merge_layers, spatial_join,
  count_points_in_polygons, nearest_neighbor_distance, score_candidates,
  voronoi_polygons, grid_generation, csv_to_point_layer, package_outputs (+DXF/KML).
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
  elsewhere), in-memory workspace, Overpass/Nominatim OSM gateway with
  real node/way/relation geometry parsing.

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

- **User profile** (`src/ageo/domain/value_objects/user_profile.py` +
  `src/ageo/infrastructure/user/profile_store.py`): role, GIS skill level,
  CRS awareness, autonomy preference and explanation depth, persisted to
  `~/.ageo/user_profile.json`. Injected as a compact one-line string into
  the planner's and composer's LLM prompts, and drives the report's
  `depth` (plain/steps/audit) when not explicitly requested. Endpoints:
  `GET/PUT /settings/profile`. No Settings UI tab yet (API-only).

- **Clarification Engine** (`src/ageo/application/agents/clarifier.py`,
  `src/ageo/application/agents/composer.py`): missing workflow parameters
  become structured questions with severity, Turkish+English text,
  options and defaults - rendered as a rich form in the UI. The profile's
  autonomy preference gates behavior: `strict_confirm` asks the user to
  confirm every spec default (prefilled, one click); `guided`/`autonomous`
  apply defaults silently but record each one in an **Assumption Ledger**
  shown in the response, a UI card and the report at every depth - a
  silent default is never invisible. Required parameters without defaults
  are always asked: autonomy never invents values. The LLM plan composer
  can also raise a structured clarification for genuinely ambiguous novel
  requests (e.g. a buffer distance given in degrees instead of metres)
  instead of only producing a plan or an honest refusal - **this is where
  `guided` and `autonomous` first actually diverge**: both surface the
  question, but `autonomous` auto-resolves when the composer supplies a
  recommended option (ledgered, never invented). Live-verified against
  the real configured Gemini 2.5 Flash key: the degree/metre trap
  scenario correctly produces a clarification with a recommended
  metric-distance option and clean EN+TR text (see HANDOFF.md).

- **LLM connection settings** (`src/ageo/infrastructure/llm/config.py` +
  Settings panel in the UI): choose a provider (Google Gemini default,
  Anthropic, OpenAI, or any custom LiteLLM model id), paste an API key,
  save, and run a one-click connection test. Settings persist to
  `~/.ageo/llm_settings.json` (owner-only permissions), keys are never
  echoed back (masked suffix only), and adapters read the live
  configuration on every call - no restart needed. Endpoints:
  `GET/PUT /settings/llm`, `POST /settings/llm/test`.
- **Web UI** (`frontend/`, React + Vite + TypeScript + Tailwind v4 -
  builds into `src/ageo/interface/web/dist`, which `app.py` serves): a
  floating glass control panel over a full-bleed MapLibre map - the
  natural-language task box, "Understood" summary, live process trace
  (SSE, each event labelled with its workflow step id) with a pulsing
  status chip while running, needs-input question forms, composed-plan
  preview, assumptions ledger, outputs list and an EN/TR report toggle.
  **Progressive rendering**: as each workflow step finishes, its output
  layer fades in on the map as a pale "ghost" preview (fetched from
  `/workspace/{layer_id}`) with the view progressively extending to cover
  it, so steps become visible as they run instead of only at the end;
  ghosts clear once the bold final outputs are drawn. `npm run build`
  required once per checkout (see AGENTS.md section 4); `npm run dev`
  for HMR iteration against a running backend.
- **Interface layer** (`src/ageo/interface/api/`): FastAPI app.
  `POST /tasks` runs planner -> guarded runner (with `needs_input` +
  `missing_params`/structured `questions` for human-in-the-loop, and an
  `assumptions` ledger for silently-defaulted params), `GET /tasks/{id}/trace`
  and `/events` (SSE) expose the full process log, `/layers/{name}` serves
  display-ready EPSG:4326 GeoJSON for a named final output layer,
  `/workspace/{layer_id}` serves the same for ANY layer still in the
  task's workspace (analysis CRS is preserved in the workspace either
  way), scalar/table outputs are returned under `results`, `/uploads`
  accepts files, `/catalog` lists workflows and tools. Each task gets an
  isolated workspace and trace.

Bundled workflows: `road_fetch_and_buffer` (the MVP scenario),
`preflight_quality_check`, `crs_normalization` (load -> reproject ->
delivery package with manifest).

## Development

```bash
uv sync                                             # install
uv run pytest                                       # 178 tests, all offline
uv run python -m ageo.interface.api.serve           # server on :8000, real OSM
uv run python -m ageo.interface.api.serve --demo    # offline synthetic Kutahya
```

Frontend build/dev loop:

```bash
cd frontend
npm install
npm run build     # emits the FastAPI-served SPA into src/ageo/interface/web/dist
npm run dev       # optional Vite dev server on :5173, proxies API calls to :8000
```

LLM setup: paste your Google AI Studio key into `.env`:

```bash
GEMINI_API_KEY=your_key_here
AGEO_PLANNER_MODEL=gemini/gemini-2.5-flash
AGEO_COMPOSER_MODEL=gemini/gemini-2.5-flash
```

Saved UI settings in `~/.ageo/llm_settings.json` take precedence over `.env`.
If the UI has an old key saved, update it in Settings or remove that JSON file.

### Docker

```bash
docker compose up --build ageo                 # real OSM on :8000
docker compose --profile demo up ageo-demo     # offline demo on :8001
```

The `ageo` service reads `.env` from the project root if present (same keys
as above). LLM settings saved via the UI persist in the `ageo-settings`
volume. `.env` is never baked into the image. Inside a container the server
binds `AGEO_HOST=0.0.0.0`; outside Docker the default stays `127.0.0.1`.

Open http://127.0.0.1:8000/ and try the example chips, e.g.:
`Kutahya'daki "Ataturk Caddesi" icin 25 m buffer uygula`
or the composed multi-criteria scenario:
`Kutahya Evliya Celebi Mahallesi'nde okula 500 m, ana yollara 250 m
mesafede kiralik ev icin uygun alanlari bul`

## Not yet built (by design order)

Vector-store RAG (pgvector) behind the RecipeStore interface, PostGIS
workspace, sandbox story for any future generated-code path, batch folder
processing (Phase 3). Local Docker packaging (Dockerfile + compose) is done.
