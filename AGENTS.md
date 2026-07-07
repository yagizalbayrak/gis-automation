# Autonomous GIS Workbench (`ageo`) - Agent Handover & Working Guide

This file is the working guide for any coding agent (Codex, Claude, etc.)
continuing this project. Read it fully before changing code.

Companion documents - each has ONE job, keep them consistent:
- **[HANDOFF.md](HANDOFF.md)** - living project STATE: milestone log,
  decisions, known bugs, agreed next steps. The user alternates between
  Claude Code and Codex; update HANDOFF.md at every significant milestone
  so the other model can resume seamlessly. Start every session by
  reading it.
- **[PROJECT_BRIEF_FABLE5.md](PROJECT_BRIEF_FABLE5.md)** - product brief,
  source of truth for scope.
- **[ADAPTIVE_EXECUTION_STATUS.md](ADAPTIVE_EXECUTION_STATUS.md)** - maps
  the Adaptive Execution & Dynamic Calibration blueprint (User Calibration
  + Clarification Engine pillars) to what is actually built vs. still
  planned. Read this before assuming any part of that blueprint exists.
- **[README.md](README.md)** - user-facing feature status.
- **[CLAUDE.md](CLAUDE.md)** - Claude Code entry point (points back here;
  rules live in THIS file only).

### How to write HANDOFF.md updates (style guide for any model)

Follow this template exactly so entries stay scannable and consistent
across Claude and Codex sessions - do not freelance a different format.

- **Milestone log entry**: append, never rewrite history. One line:
  `N. **Short Title** - what was built (key files/components, one
  notable technical decision if any) (X tests).` Keep it to 3-6 lines
  max; link out to AGENTS.md section 3 or a results file instead of
  duplicating detail. Always end with the current total test count in
  parentheses, even if unchanged.
- **"Current state" bullets**: `- **Label**: fact, fact, fact.` Bold
  label is a noun phrase (LLM, Tests, Runs...), not a sentence. Quote
  file paths, env vars and endpoint names with backticks. Update the
  `Tests: X/X green` line and the `Last updated:` line at the top of the
  file every session, even a small one.
- **"Next steps" entries**: `N. **Phase name**: what to do, why it
  matters or what it depends on, any caveat (approval needed, contract
  risk, etc).` Order = agreed priority, most urgent first. When you
  finish a step, delete it from this list (the milestone log is the
  history; this list is only the todo).
- **"Key decisions" / "Critical bugs"**: one bullet each, single
  sentence, imperative or factual - `X -> Y` or `X because Y`. Only add
  an entry if it would surprise a future session or cost real time to
  re-derive; do not log routine implementation choices here.
- **Scope discipline**: if a change is intentionally partial (an
  increment of a larger design), say so explicitly in the milestone
  entry AND add the deferred part to "Next steps" with a one-line reason
  it was deferred (e.g. "touches the API contract, needs its own
  review"). Future sessions must never have to guess what was left out.
- **AGENTS.md vs HANDOFF.md**: architecture/component descriptions
  (section 3's file map, the API surface paragraph) go in AGENTS.md and
  must be kept literally accurate (paths, function names) - update them
  in the same edit as the HANDOFF.md milestone, not later. HANDOFF.md
  never duplicates architecture, only state/history/decisions/next-steps.
- **README.md**: update the relevant feature-status bullet in the same
  session a feature lands (AGENTS.md section 9 "Definition of done").
  Note explicitly what is NOT done yet (e.g. "no UI tab") rather than
  implying completeness.

## 1. What this product is

A standalone, natural-language GIS automation workbench. Users describe a
spatial task in Turkish or English; the system selects or composes a
deterministic tool chain, executes it with geodetic guarantees, and returns
map layers, reports and an auditable process trace. It is NOT a QGIS/ArcGIS
clone or plugin, and it must never become "LLM writes arbitrary code".

**Core value proposition (owner's words):** if a user asks a problem we have
never seen, the answer is never "we don't have that" - the AI composes a
plan from the tool registry and executes it. Registered workflows are the
fast path, composition is the universal fallback.

## 2. Non-negotiable engineering rules

1. **Determinism over generative chaos.** Few agents, many tested tools.
   LLMs orchestrate and interpret; deterministic tools execute. Never call
   an LLM per file, per layer, or per geometry.
2. **LLM output is DATA, never code.** The composer emits a
   `WorkflowSpec`-shaped JSON plan. It must pass `validate_workflow()`
   (structure + static CRS coherence) before execution, gets exactly one
   retry with the validator error as feedback, and every step still runs
   through the guarded executor. Same rulebook as bundled workflows.
3. **Geodetic integrity is structural, not conventional.**
   - Never buffer/measure in a geographic CRS. `buffer_metric` declares
     `PROJECTED_METRIC`; the executor guard enforces it; the static checker
     proves chains coherent at registration/composition time.
   - The CRS guard FAILS LOUDLY - it never auto-reprojects. Reprojection
     must be an explicit, traceable step.
   - Only pyproj (via `infrastructure/gis/crs_info.py`) touches CRS
     machinery. No manual CRS string manipulation anywhere.
   - EPSG:5254 (TUREF/TM30) is the default metric CRS for western Turkey;
     `suggest_metric_crs(lon, lat)` picks TUREF zones in Turkey, UTM
     elsewhere.
4. **Geometries never enter LLM context.** Layers travel as `LayerRef`
   handles into a per-task workspace. The planner/composer see only the
   user text, tool/workflow catalogs and recipes.
5. **Strict Pydantic v2 everywhere except `domain/`** (frozen models,
   `extra="forbid"`). `domain/` is pure Python dataclasses - no Pydantic,
   no pyproj, no geopandas imports there.
6. **All code, comments, docstrings, identifiers in English.** UI copy and
   NL matching support Turkish + English.
7. **Tests run offline.** All 142 tests mock LLMs (litellm) and OSM (demo
   gateway). Never add a test that spends tokens or hits the network.
   `uv run pytest` must stay green.
8. **Turkish text folding matters.** Real OSM says "Atatürk Bulvarı"; users
   type "Ataturk Bulvari". Case-insensitive matching must fold Turkish
   diacritics, and İ must be translated BEFORE `.lower()` (Python lowercases
   İ into "i" + combining dot U+0307, silently breaking equality). See
   `application/tools/impl/attributes.py`.

## 3. Architecture map (DDD layers)

```
src/ageo/
  domain/                    # pure Python invariants
    value_objects/crs.py         CrsDescriptor, CrsKind
    value_objects/requirements.py InputRequirement, check_crs()  <- THE geodetic gate
    value_objects/user_profile.py UserProfile: role/gis_level/crs_awareness/
                                 autonomy_preference/explanation_depth/language;
                                 to_prompt_line() (compact LLM injection),
                                 report_depth() (Reporter depth mapping)
    ports/crs_info.py            CrsInfoPort protocol
  application/
    tools/contract.py            StrictModel, LayerRef, ToolSpec, Tool, ToolContext,
                                 CrsEffect, layer_ref_kind() (collections support)
    tools/registry.py            ToolRegistry: import-time contract validation; catalog()
                                 is the LLM's ENTIRE view of the system
    tools/errors.py              typed failure taxonomy (guards vs execution vs gateways)
    tools/impl/                  26 tools: io_vector (+DXF/KML), reproject, buffer,
                                 measurements, geometry_quality, attributes, osm,
                                 overlay, aggregate (dissolve, merge_layers), join,
                                 packaging (+DXF/KML), geometry_ops (centroid,
                                 simplify_geometry), spatial_analysis
                                 (count_points_in_polygons, nearest_neighbor_distance),
                                 tessellation (voronoi_polygons, grid_generation),
                                 csv_import (csv_to_point_layer)
    workflows/spec.py            WorkflowSpec/Step/Param; "$params.x", "$steps.id.field"
    workflows/validation.py      validate_workflow(): structural + symbolic CRS
                                 simulation (the deterministic Critic)
    workflows/registry.py        named workflow records
    workflows/defs.py            bundled: road_fetch_and_buffer,
                                 preflight_quality_check, crs_normalization
    orchestration/executor.py    ToolExecutor: the ONLY path tools run through
                                 (input validation -> CRS/geometry guards -> run ->
                                 output validation -> trace events); execute() takes
                                 an optional step_id echoed into every trace event
                                 detail for that call (UI labels layers by step)
    orchestration/runner.py      WorkflowRunner.run()/run_spec(); srid_metric param
                                 contract enforced before step one; passes each
                                 step's id to executor.execute() as step_id
    orchestration/trace.py       TraceEvent/TracePhase/ListTraceSink (= process log)
    agents/planner.py            DeterministicPlanner (regex+patterns, zero tokens),
                                 HybridPlanner (sanitizes LLM decisions: hallucinated
                                 workflows rejected, unknown params dropped,
                                 missing_params recomputed from registry)
    agents/clarifier.py          build_questions(): structured HIL questions
                                 (PendingQuestion) + Assumption ledger, gated by
                                 UserProfile.autonomy_preference; deterministic
                                 TR/EN templates, zero tokens
    agents/composer.py           PlanComposer: compose -> normalize -> validate ->
                                 one feedback retry -> ComposerError; MAX_STEPS=15;
                                 may also raise ComposerClarificationRequired (a
                                 PendingQuestion, capped at one round per task) for
                                 genuinely ambiguous novel requests
    agents/reporter.py           ProcessReporter: deterministic EN/TR reports from
                                 trace; depth param (plain|steps|audit) gates detail
    rag/store.py + bundled_recipes.json  RAG-lite keyword recipes (lazy; pgvector can
                                 implement the same search() later)
  infrastructure/
    gis/crs_info.py              PyprojCrsInfo (lru_cached facts; TUREF/UTM advisor)
    gis/workspace.py             InMemoryWorkspace : ToolContext (PostGIS swaps in here)
    gis/overpass.py              real Nominatim+Overpass gateway (see pitfalls below)
    gis/demo.py                  DemoOsmGateway + DemoComposerLlm + reference rental plan
    llm/config.py                LlmConfigStore -> ~/.ageo/llm_settings.json (chmod 600),
                                 masked keys, live per-call resolution, PROVIDER_PRESETS
    llm/litellm_planner.py       the planner LLM call site
    llm/litellm_composer.py      the composer LLM call site (system prompt with plan
                                 JSON schema + hard geodetic rules)
    user/profile_store.py        UserProfileStore -> ~/.ageo/user_profile.json
                                 (single-tenant, no secret, no chmod); live
                                 per-call resolution like LlmConfigStore
  interface/
    api/app.py                   FastAPI factory create_app(); all endpoints
    api/tasks.py                 TaskManager: plan -> compose fallback -> background
                                 thread; per-task workspace + trace (isolation)
    api/schemas.py               API request/response models
    api/serve.py                 dev server; --demo flag; PORT env respected
    web/dist/                    React SPA BUILD OUTPUT (generated by `npm run
                                 build` in frontend/, gitignored) - app.py mounts
                                 this at "/" LAST so it never shadows an API
                                 route; falls back to a 503 message if missing
tests/                           169 tests, all offline; conftest has fixtures + FakeOsmGateway

frontend/                        React + Vite + TypeScript + Tailwind v4 SPA
                                 (separate npm project, own package.json/
                                 node_modules - NOT part of the uv workspace).
                                 `npm run dev` (Vite dev server, proxies
                                 /tasks|/catalog|/settings|/uploads to :8000)
                                 or `npm run build` (emits into
                                 ../src/ageo/interface/web/dist). MapLibre GL
                                 wrapped directly (no react-map-gl); motion
                                 for animation; lucide-react for icons. See
                                 src/components/MapView.tsx for the
                                 progressive ghost-layer rendering (fetches
                                 GET /tasks/{id}/workspace/{layer_id} on every
                                 non-skipped tool_finished trace event).
```

**Escalation ladder for a request:** DeterministicPlanner (registered
workflow, zero tokens) -> HybridPlanner LLM fallback (registered workflow,
one small-model call) -> PlanComposer (new plan, stronger model). All three
funnel into the same guarded runner.

**API surface:** `POST /tasks?wait=` (statuses: running/succeeded/failed/
needs_input+missing_params/unmatched; composed tasks carry `mode` and
`plan`; responses also carry structured `questions` - clarifier
PendingQuestion objects with severity/TR+EN text/options/defaults - and
an `assumptions` ledger of params that fell back to spec defaults),
`GET /tasks/{id}`, `/trace`, `/events` (SSE),
`/report?lang=en|tr&depth=plain|steps|audit` (both default from the saved
user profile when omitted, else the long-standing `en`/full-detail
default; the Assumptions section renders at EVERY depth),
`/layers/{output}` (always served in EPSG:4326 display CRS;
analytical CRS preserved in workspace), `/workspace/{layer_id}` (same
display-CRS serialization, but for ANY layer still in the task's
workspace, not just a named final output - what the UI's progressive
"ghost" rendering polls mid-run; shares a `_serialize_layer()` helper with
`/layers/{output}`), `POST /uploads`, `GET /catalog`,
`GET|PUT /settings/llm`, `POST /settings/llm/test`,
`GET|PUT /settings/profile` (role/gis_level/crs_awareness/
autonomy_preference/explanation_depth/language; full-replace, no UI tab
yet). The saved profile is injected as a compact one-line string into
the planner's and composer's LLM prompts (`UserProfile.to_prompt_line()`,
~20 tokens) AND gates the clarifier: strict_confirm turns spec defaults
into blocking confirmation questions; guided/autonomous ledger them
(identical for registered workflows - guided and autonomous only diverge
for composer-originated clarifications, where autonomous auto-resolves
if the composer supplied a recommended option). Autonomy never invents
values: required params without defaults are asked under every profile,
and autonomous never auto-resolves a composer clarification without a
recommended option to fall back on. The composer itself may also raise a
`ComposerClarificationRequired` (`ComposerError`'s sibling third outcome,
not a subclass) for genuinely ambiguous novel requests - same
`questions`/`assumptions` response shape, same UI rendering, no separate
API surface.

## 4. How to run

```bash
uv sync                                      # install (uv-managed venv)
uv run pytest                                # 169 tests, offline, ~2s
uv run python -m ageo.interface.api.serve           # real OSM gateway, :8000
uv run python -m ageo.interface.api.serve --demo    # offline synthetic Kutahya
```

**Frontend (`frontend/`, React+Vite+TypeScript+Tailwind - a separate npm
project, not part of `uv sync`):**

```bash
cd frontend
npm install
npm run build     # REQUIRED at least once - emits into
                  # src/ageo/interface/web/dist, which app.py serves at "/".
                  # Without this, "/" returns a 503 telling you to build it
                  # (every other API endpoint still works; pytest never
                  # depends on the build existing).
npm run dev       # optional: Vite dev server (HMR) on :5173, proxies
                  # /tasks|/catalog|/settings|/uploads to the backend on
                  # :8000 - run alongside `uv run ... serve --demo` while
                  # iterating on UI code.
```

Docker (for colleagues without a local uv/node setup): `docker compose up
--build ageo` (real OSM, :8000) or `docker compose --profile demo up
ageo-demo` (offline, :8001). The Dockerfile has a `frontend-builder` stage
(Node) that runs `npm run build` before the Python stage, so the image
always ships with the built UI - no separate step needed. The container
sets `AGEO_HOST=0.0.0.0` (serve.py binds `127.0.0.1` by default outside
Docker); `.env` is read at runtime via compose, never baked into the
image; UI-saved LLM settings persist in the `ageo-settings` volume mounted
at `/home/ageo/.ageo`. **Not verified this session** (no Docker daemon
running in the dev sandbox) - the Dockerfile change is a standard
multi-stage-build pattern, but the next session with Docker available
should run `docker compose up --build ageo-demo` once to confirm.

Web UI at `/`. `.claude/launch.json` defines `ageo` (real) and `ageo-demo`
preview configs (autoPort; server respects `PORT`), plus `frontend-dev`
(Vite dev server, port 5173, for UI iteration with HMR).

LLM: configured from the UI settings panel (gear icon). Owner uses
**Google Gemini 2.5 Flash** (`gemini/gemini-2.5-flash`) with their own AI
Studio key. "Test connection" auto-saves the form first, then makes a real
one-token call. Settings persist at `~/.ageo/llm_settings.json`; adapters
read live config per call (no restart). Env fallbacks:
`AGEO_PLANNER_MODEL`, `AGEO_COMPOSER_MODEL` + provider env keys. The project
also auto-loads a local `.env` for default app/eval runs; paste the Google AI
Studio key as `GEMINI_API_KEY=...`. Saved UI settings take precedence over
`.env`.

## 5. Current state (verified)

See HANDOFF.md for the authoritative, session-updated state. Snapshot:

- 169/169 tests green; zero browser console errors in verification runs.
- **The web UI is now a React SPA** (`frontend/` - Vite + TypeScript +
  Tailwind v4 + MapLibre GL + motion + lucide-react), replacing the
  original vanilla-JS `web/static/`. Same API contract, full feature
  parity (task submission, live SSE trace with step badges, HIL
  questions/clarification, assumptions ledger, composed-plan preview,
  outputs list, EN/TR report toggle, LLM settings panel) plus a
  deliberately elevated visual design (floating glass panel over a
  full-bleed map, animated cards, pulsing status chip). Browser-verified
  in `--demo` mode via the production build served through FastAPI:
  deterministic buffer, 7-step composed rental scenario, LLM settings
  panel, and the needs_input -> answer round-trip all confirmed working
  with zero console errors. See HANDOFF.md milestone 16 for two real bugs
  caught and fixed during that verification (a MapLibre/Tailwind CSS
  cascade collision that collapsed the map to 0 height, and a
  Motion "auto"-height animation that never resolved).
- **Progressive map rendering is DONE** (owner-requested, previously owed):
  every tool-scoped trace event now carries `step_id`; a new
  `GET /tasks/{id}/workspace/{layer_id}` endpoint serves display-CRS
  GeoJSON for any workspace layer, not just named final outputs; the
  React SPA's `MapView` component draws each finished step's layer as a
  pale fading-in "ghost" (skipping `reproject`/`detect_crs`/
  `validate_geometry`/`save_vector`/`package_outputs`) with progressively
  extending map bounds, and the status chip pulses while running.
  Originally browser-verified against the vanilla-JS UI for both a
  single-step deterministic workflow and the 7-step composed rental
  scenario (see milestone 15 for the `state.ghostGeneration` race-condition
  fix); re-verified against the React port in milestone 16.
- **All Tier-1 tools from the eval build list are now registered** (26
  tools total): `centroid`, `simplify_geometry`, `count_points_in_polygons`,
  `nearest_neighbor_distance`, `merge_layers`, `csv_to_point_layer`,
  `voronoi_polygons`, `grid_generation` (square cells only), plus DXF/KML
  drivers added to `save_vector`/`package_outputs`. All require a projected
  metric CRS except `csv_to_point_layer` (CRS from a param) and
  `count_points_in_polygons` (any defined CRS, like `spatial_join`). KML
  export refuses non-EPSG:4326 layers rather than let GDAL reproject
  silently (see `io_vector.py`/`packaging.py`). Offline unit tests +
  2 composed-plan tests cover all of them; live-LLM re-verification of the
  corresponding gap scenarios (S43-S50) is still pending explicit user
  approval (see section 7b/8).
- `UserProfile` increment 1 verified live against the `--demo` server:
  `GET/PUT /settings/profile` roundtrips, and `/report` picks up the
  saved profile's language/depth by default while an unconfigured
  profile still reports exactly as before (no regression). See HANDOFF.md
  milestone 11 for the full component list.
- Clarification Engine (increment 2) browser-verified in demo mode:
  guided profile ledgers `target_srid=EPSG:5254` (assumptions card + a
  report section at every depth, EN/TR); strict_confirm turns the same
  default into a prefilled confirmation question with a recommended
  hint; the classic HIL flow round-trips with structured questions.
  See HANDOFF.md milestone 12.
- Tier-1 `calculate_area` and `calculate_length` are registered and
  offline-tested: they require projected metric polygon/line layers, support
  m2/ha and m/km, and return measured layers plus compact table/total
  outputs. API responses keep map layers in `outputs` and expose scalar/table
  outputs in `results`. Live S33/S34 evals still need explicit user approval
  because they call the configured external LLM with prompt/catalog context.
- Deterministic path verified against REAL OSM in the browser: 576 named
  roads fetched from Overpass for Kutahya city, the real "Atatürk Bulvarı"
  (8 segments) matched via diacritics folding, buffered 25 m in EPSG:5254,
  rendered exactly over the boulevard on the basemap.
- Composed path verified end-to-end with the scripted demo composer AND
  benchmarked headless against the real Gemini 2.5 Flash: 27 plans
  composed first-try, 19 precise refusals (see section 7b). The browser-UI
  composed flow with the live model is still untested.
- Settings flow verified live including auto-save-on-test and provider
  error message extraction.

## 6. Hard-won pitfalls (do not re-learn these)

- **Nominatim ranks the PROVINCE above the city** for "Kutahya". The
  gateway asks for 5 results and prefers settlement-scale addresstypes
  (city/town/municipality/suburb/neighbourhood/...) with real polygons.
- **Overpass volume**: always consider `require_tags` push-down (e.g.
  `["name"]` for named roads), `[maxsize:33554432]` and timeouts. A
  province-wide `way["highway"]` query is a denial-of-service on yourself.
- **Turkish İ/ı** breaks naive lowercase matching (see rule 8 above).
- **Pydantic strict mode**: tuple fields reject Python lists; the runner
  resolves list bindings to tuples, and the composer validates plans via
  `model_validate_json` (JSON arrays -> tuples is allowed in JSON mode).
- **"Test connection" must test what is in the form** - it auto-saves
  first. Don't regress this; the owner personally hit the stale-key trap.
- uv editable install: after creating new top-level packages run
  `uv sync --reinstall-package ageo` if imports go missing.
- **`maplibre-gl.css`'s `.maplibregl-map { position: relative }` cascades
  over Tailwind's `.absolute` utility** on the same element (equal
  specificity, later stylesheet wins) - the map container silently
  collapses to 0 height. Fix: set `position`/`inset` as an inline `style`
  on that specific element instead of Tailwind classes; inline styles
  always win regardless of stylesheet load order.
- **Motion (`motion/react`) animating `height: "auto"` can get stuck at 0**
  and never resolve to the content's natural height (SettingsPanel hit
  this). Prefer animating `opacity`/`y` and letting the element keep its
  natural height instead of chasing `"auto"` height animations.
- **`npm run build`'s output (`src/ageo/interface/web/dist/`) is a build
  artifact, gitignored, and NOT auto-generated by `uv run pytest`** - the
  app degrades to a 503 at "/" (every other endpoint still works) if it's
  missing. Run `cd frontend && npm install && npm run build` at least once
  per checkout before expecting the real UI at "/".

## 7. Owner's directives (product decisions already made)

- Delegates design decisions to the agent; expects production-grade code
  and decisive recommendations, not option lists.
- Composition fallback must ALWAYS attempt novel problems.
- **No dummy-data demos.** Default server uses real OSM; `--demo` exists
  for offline tests only.
- Wants the execution to be **visually captivating**: steps should appear
  smoothly on the map as they run, "professional" feel. (Done: progressive
  ghost-layer rendering + the React UI's visual redesign, see section 5.)
- Works in Turkish and English; reports must support both (done).
- Wanted the web UI **visually much better, React-based**, explicitly not
  a copy of any specific reference product - own design language, agent's
  call. (Done: `frontend/`, see section 5.)

## 7b. Evaluation harness (use it!)

`src/ageo/evals/` holds a 50-scenario pool (TR/EN, moderate->complex) and a
harness that routes each scenario through the production planner ladder and
classifies outcomes. Run `uv run python -m ageo.evals` (live LLM) or
`--no-llm`. Results in `evals_results/`; read
[evals_results/FINDINGS.md](evals_results/FINDINGS.md) for the 2026-07-03
baseline: 49/50 as intended, 27 composed first-try, 19 precise refusals,
and the harvested TOOL BUILD LIST. **All Tier-1 tools are now registered**
(centroid, simplify_geometry, count_points_in_polygons,
nearest_neighbor_distance, merge_layers, csv_to_point_layer, DXF/KML in
save_vector + package_outputs, voronoi_polygons, grid_generation - the
latter produces a SQUARE grid only, not hexagonal, despite S46's "hex-grid"
title) - offline unit + composed-plan tests cover all of them, but the gap
scenarios (S43-S50) still need a live-LLM re-run
(`uv run python -m ageo.evals --only S43 S44 S45 S46 S48 S49 S50`, **needs
explicit user approval**, it spends real Gemini tokens) before their
`expect` fields in `scenarios.json` are flipped from `gap` to `composed`.

## 8. Next work, in order

1. **Verify the Docker build with the new frontend-builder stage** - not
   done this session (no Docker daemon running in the dev sandbox). Run
   `docker compose up --build ageo-demo` once and confirm the built React
   UI actually serves from the image at :8001; the Dockerfile change
   itself is a standard multi-stage pattern (Node stage builds
   `frontend/` into `src/ageo/interface/web/dist`, copied into the Python
   stage) but was never actually executed end-to-end.
2. **Live-verify the new Tier-1 tools** against the real Gemini key: run
   the eval harness on S43/S44/S45/S46/S48/S49/S50 with explicit user
   approval, then flip `scenarios.json`'s `expect` fields and update
   FINDINGS.md's scoreboard for any that now compose successfully. Two
   named gaps remain even after this batch: bulk `geocoding` (S42) and
   `batch_folder_processing` (S48, folder-wide merge - Phase 3 below).
3. **First real composer flight + prompt tuning** with Gemini 2.5 Flash on
   real OSM (the rental chip). Log and fix plan-schema deviations; consider
   adding 1-2 more recipes from failures.
4. **Phase 3 batch processing**: folder-based runs, repeat workflow over
   many files, delivery package + manifest (tools exist: `package_outputs`).
5. **pgvector RAG** behind `RecipeStore.search()` (lazy; keyword fallback
   stays).
6. **PostGIS workspace** implementing `ToolContext` (the seam is
   `infrastructure/gis/workspace.py`).
7. **Sandbox story** for any future generated-code path (local Docker
   packaging is done: Dockerfile + docker-compose.yml, see section 4).

## 9. Definition of done for any change

- `uv run pytest` green (add tests for new behavior; offline always).
- If UI-visible: verify in the browser (launch config `ageo`), check
  console for errors, confirm the trace/report still tell the truth.
- Update README.md status sections when features land.
- Never weaken a guard, validator, or trace to make something pass.
