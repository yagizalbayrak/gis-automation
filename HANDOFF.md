# HANDOFF.md - Living Project State (Context Handoff)

> **Protocol:** This file is the shared memory between AI sessions (Claude
> Code <-> Codex). Whoever completes a significant milestone MUST append to
> "Milestone log" and refresh "Current state" + "Next steps" before ending
> the session. Rules and architecture live in [AGENTS.md](AGENTS.md) - do
> not duplicate them here; this file records STATE and HISTORY.
> Last updated: 2026-07-07 by Codex.

## Current state (the short version)

- **Product**: Autonomous GIS Workbench (`ageo`) - natural-language TR/EN
  geospatial automation. Brief: `PROJECT_BRIEF_FABLE5.md`.
- **Tests**: 178/178 green, all offline (`uv run pytest`, ~2 s).
- **Web UI: React rewrite DONE** (owner-requested: "make it visually much
  better, React, your call on design") - see milestone 16. `frontend/`
  (Vite + TypeScript + Tailwind v4 + MapLibre GL + motion) replaces the
  vanilla-JS `web/static/`; full feature parity, own visual design (not
  a copy of any reference product). Requires `cd frontend && npm install
  && npm run build` once per checkout (gitignored build output at
  `src/ageo/interface/web/dist`); the app degrades to a 503 at "/" without
  it (every other endpoint keeps working, `uv run pytest` never depends
  on the build). **Docker build with the new frontend-builder stage was
  NOT verified this session** (no Docker daemon available) - next session
  should run it once.
- **Tool registry**: 27 tools. All Tier-1 tools from the eval build list
  (evals_results/FINDINGS.md) are registered, and `score_candidates` now
  supports weighted site suitability ranking - see milestones 14 and 18.
- **Progressive map rendering: DONE** (owner-requested, previously owed) -
  see milestone 15 (built against the vanilla UI) and milestone 16 (ported
  to the React UI, re-verified). Browser-verified with zero console
  errors: intermediate layers now fade in on the map as each workflow step
  finishes, instead of only at the end.
- **Runs**: `uv run python -m ageo.interface.api.serve` (real OSM) or
  `--demo` (offline synthetic Kutahya). Web UI at `/` on :8000
  (respects `PORT`; bind host via `AGEO_HOST`, default 127.0.0.1).
  Preview configs in `.claude/launch.json` (`ageo`, `ageo-demo`,
  `frontend-dev` for Vite HMR). Docker: `docker compose up
  --build ageo` (:8000) or `--profile demo up ageo-demo` (:8001) for
  colleagues cloning the repo.
- **LLM**: user's own **Gemini 2.5 Flash** key, configured via the UI
  Settings panel, stored at `~/.ageo/llm_settings.json` (owner-only,
  masked in API). Adapters read live config per call. A local `.env`
  template now exists for headless tests/evals; set `GEMINI_API_KEY=...`
  there. Saved UI settings take precedence over `.env`.
- **Verified against real data**: 576 named roads fetched from Overpass
  for Kutahya; real "Atatürk Bulvarı" buffered 25 m in EPSG:5254 and
  rendered on the MapLibre map. The real OSM gateway now parses nodes,
  open/closed ways and multipolygon relations, so schools/POIs, roads and
  area candidates can all enter site-analysis plans as their real geometry
  types. Zero console errors in the last browser verification run.
- **Evaluation baseline** (see `evals_results/FINDINGS.md`): 50-scenario
  pool, Gemini 2.5 Flash - 49/50 behave as intended; 27 plans composed
  first-try (max 13 steps); 19 honest refusals naming missing
  capabilities; all geodetic trap scenarios dodged.
- **Tier-1 tool progress**: COMPLETE. `calculate_area`/`calculate_length`
  (milestone 9) plus, as of milestone 14, `centroid`, `simplify_geometry`,
  `count_points_in_polygons`, `nearest_neighbor_distance`, `merge_layers`,
  `csv_to_point_layer`, `voronoi_polygons`, `grid_generation`, and DXF/KML
  export in `save_vector`/`package_outputs`. Every gap named in
  evals_results/FINDINGS.md's Tier-1 build list is now built. S33/S34/S43-
  S50-shaped composed plans are covered offline with the demo gateway; live
  evals still need explicit user approval because they send prompt and
  tool-catalog context to the configured external LLM.
- Parallel Codex checkout exists at `~/Desktop/gis-automation-v2-codex`
  (server seen on :8001). Keep the two trees in sync deliberately - they
  do NOT share state.
- **Adaptive Execution & Dynamic Calibration - increments 1+2+3 landed**:
  `UserProfile` (store at `~/.ageo/user_profile.json`,
  `GET|PUT /settings/profile`, compact prompt-line injection into
  planner/composer LLM calls, profile-driven `/report` lang+depth
  defaults); the Clarification Engine for registered workflows
  (`missing_params` upgraded into structured `questions` gated by
  `autonomy_preference`, plus an `assumptions` ledger for silently
  defaulted params); AND now the composer itself can raise a structured
  clarification (`ComposerClarificationRequired`) for genuinely ambiguous
  novel requests instead of only plan/refuse - **this is the first place
  `guided` and `autonomous` actually diverge**: both surface the question,
  but `autonomous` auto-resolves when the composer supplies a recommended
  option (ledgered as `source="composer_recommended"`), never inventing
  an answer otherwise. Reuses the exact same `PendingQuestion`/`Assumption`
  wire shapes and UI rendering as increment 2 - zero UI code changed.
  Full blueprint-vs-reality breakdown (what's done, what's not, per
  pillar): [ADAPTIVE_EXECUTION_STATUS.md](ADAPTIVE_EXECUTION_STATUS.md).
  **Live-verified against the real Gemini 2.5 Flash key (2026-07-05)**:
  `uv run python -m ageo.evals --only S26` -> `composed_clarification`,
  matches expectation. The real model asked for a metric distance,
  offered 111m as the recommended option (~correct conversion of 0.001deg)
  plus two sensible alternatives (50m/200m), with clean EN+TR text - the
  prompt rule works in practice, not just in scripted tests. Still
  missing: a Settings UI tab for the profile.

## Architecture in one paragraph

Requests climb an escalation ladder: DeterministicPlanner (pattern match,
zero tokens) -> HybridPlanner LLM fallback (one small call, sanitized) ->
PlanComposer (one strong call composing a NEW WorkflowSpec-shaped JSON
plan). Every plan - bundled or composed - must pass `validate_workflow()`
(structure + static CRS-coherence simulation), then executes step-by-step
through the guarded `ToolExecutor` (CRS/geometry guards, trace events).
27 deterministic tools; geometries never enter LLM context (LayerRef
handles); per-task isolated workspace + trace; deterministic EN/TR
Reporter. Full map in AGENTS.md section 3.

## Milestone log

1. **Phase 1 deterministic core** - domain CRS invariants, strict Pydantic
   tool contract, guarded executor, workflow registry with static CRS
   checking, TUREF/UTM advisor, road_fetch_and_buffer MVP (27 tests).
2. **Tool completion + planner** - overlay set (clip/intersect/difference/
   dissolve/spatial_join), package_outputs with manifest, LayerRef
   collections, DeterministicPlanner + HybridPlanner + LlmPlannerPort,
   crs_normalization workflow (43 tests).
3. **FastAPI interface** - POST /tasks with needs_input HIL flow, SSE
   trace, display-CRS GeoJSON layers, uploads, catalog; per-task
   workspace isolation (53 tests).
4. **Web UI + demo mode** - MapLibre workbench screen (query/trace/
   outputs/questions), example chips, DemoOsmGateway; browser-verified
   incl. HIL round-trip (54 tests).
5. **LLM planner adapter + Reporter** - LiteLLM planner behind hardened
   HybridPlanner (hallucination/param sanitization, registry authority
   over missing params); deterministic EN/TR ProcessReporter +
   /report endpoint + UI card (65 tests).
6. **PlanComposer + RAG-lite** - LLM-composed plans validated by the same
   Critic as bundled workflows, one feedback retry; RecipeStore with
   bundled JSON recipes; rental site-search scenario E2E in browser
   (73 tests).
7. **LLM settings + real-OSM hardening** - UI settings panel (provider/
   model/key, save + auto-saving connection test), LlmConfigStore;
   Nominatim settlement-over-province ranking, Overpass require_tags +
   maxsize, Turkish diacritics folding in filter_by_attribute
   (80 tests).
8. **Evaluation harness + baseline** - 50-scenario pool (src/ageo/evals/),
   outcome classification, refusal semantics (`plan_refused:`), composer
   max_tokens 8000, no-fake-substitutes prompt rule; findings + tool
   build list in evals_results/FINDINGS.md (85 tests).
9. **Tier-1 measurement tools** - `calculate_area` and `calculate_length`
   wrappers with CRS and geometry guards, hectare/kilometre support,
   compact table and total outputs, API `results` for non-layer outputs,
   demo OSM parks/cycleways for offline S33/S34-shaped execution coverage
   (97 tests).
10. **Local Docker packaging** - multi-stage uv Dockerfile (non-root
    `ageo` user, pre-owned `~/.ageo` for the settings volume),
    docker-compose.yml with `ageo` (real OSM, :8000) + `ageo-demo`
    (profile `demo`, :8001) services, `.dockerignore`; serve.py gained
    `AGEO_HOST` env support (container binds 0.0.0.0, local default
    unchanged). Verified: image builds, demo container serves /catalog
    and the UI, settings volume writable as non-root, compose config
    valid (97 tests).
11. **UserProfile increment 1** - `domain/value_objects/user_profile.py`
    (frozen dataclass + StrEnums, `to_prompt_line()`, `report_depth()`),
    `infrastructure/user/profile_store.py` (mirrors LlmConfigStore, no
    secret/no chmod), `GET|PUT /settings/profile`, `UserProfile` threaded
    through `TaskManager` -> `HybridPlanner.plan(profile=...)` /
    `PlanComposer.compose(profile=...)` -> the two LiteLLM adapters (one
    compact line appended to the user message, ~20 tokens), and
    `ProcessReporter.report(depth=...)` with a `show_detail` gate wired
    into the `/report` endpoint (profile-driven default, old hardcoded
    default preserved when unconfigured). Fixed profile-kwarg
    compatibility across every existing `LlmPlannerPort`/`LlmComposerPort`
    fake (demo, eval harness, test stubs). 18 new tests (115 total).
12. **Clarification Engine (Adaptive Execution increment 2)** - new
    `agents/clarifier.py` (`build_questions()`: PendingQuestion +
    Assumption models, autonomy gating matrix, deterministic TR/EN
    templates, zero tokens); TaskManager emits structured `questions` +
    `assumptions` on TaskResponse (`missing_params` kept for backward
    compat); reporter renders an Assumptions section at EVERY depth;
    web UI renders structured questions (lang-aware text, prefilled
    defaults, recommended hints) + an assumptions card. Intentional
    asymmetry: guided == autonomous for registered workflows until
    composer clarifications land. Browser-verified all three autonomy
    flows in demo mode, zero console errors (134 tests).
13. **Composer ClarificationRequest (Adaptive Execution increment 3)** -
    new `ComposerClarificationRequired` exception in `composer.py` (not an
    `AgeoError`, so existing handlers never swallow it silently);
    `PlanComposer._parse_clarification()` detects and defensively
    sanitizes a new `{"clarification": {...}}` wire shape (checked before
    the empty-steps refusal), reusing increment 2's `PendingQuestion`/
    `Assumption` models; capped at one clarification round per task (a
    second ask after an answer was supplied becomes an honest
    `plan_refused:`); `litellm_composer.py` prompt gained a rule teaching
    the model when to clarify (canonical case: a distance given in
    degrees, not metres) and to never ask twice once answered;
    `TaskManager._submit_composed()` gates guided/strict_confirm (always
    ask) vs. autonomous (auto-resolve only when the composer supplied a
    recommended option, ledgered as `source="composer_recommended"`) -
    **the first point where guided and autonomous actually diverge**.
    Eval harness gained `COMPOSED_CLARIFICATION` outcome + a `clarification`
    expect value; scenario S26 (the degree/metre trap) upgraded from
    `expect: gap` to `expect: clarification`. Zero UI code changed -
    increment 2's generic question/assumption rendering already covers it
    (confirmed by grep, no `question_type`/`source` switch exists in
    `app.js`). All verified with scripted fakes only, zero network calls
    (142 tests). **Live-verified 2026-07-05**: `uv run python -m ageo.evals
    --only S26` against the real configured Gemini 2.5 Flash key ->
    `composed_clarification`, matches expectation - the model asked for a
    metric distance with 111m recommended (correct conversion) plus two
    alternative options, clean EN+TR text. Result in
    `evals_results/20260705_230859.json`.
14. **Remaining Tier-1 tools** - registered all 8 tools still open on
    evals_results/FINDINGS.md's build list: `centroid`/`simplify_geometry`
    (`geometry_ops.py`), `count_points_in_polygons`/
    `nearest_neighbor_distance` (`spatial_analysis.py`),
    `voronoi_polygons`/`grid_generation` (`tessellation.py`, square cells
    only - S46's "hex-grid" title is not literally satisfied),
    `merge_layers` (added to `aggregate.py`), `csv_to_point_layer`
    (`csv_import.py`, `crs_effect=FROM_PARAM` on the `srid` field), and
    DXF/KML added to `save_vector`'s and `package_outputs`' format enum.
    All geometry-deriving tools (centroid, simplify, voronoi, grid) require
    a projected metric CRS, matching the buffer/area/length precedent -
    geographic-degree tessellation would be geodetically distorted the
    same way a degree-based buffer is. One notable decision: KML export
    now REFUSES a non-EPSG:4326 layer (`kml_requires_wgs84`) instead of
    letting GDAL silently reproject, which was verified to happen
    otherwise - preserves the "CRS guard never auto-reprojects" rule for a
    format-level reprojection nobody asked for. 23 new tests (9 tool files'
    worth of unit + guard tests, plus 2 offline composed-plan tests
    exercising `centroid` and `count_points_in_polygons` through the full
    composer -> validator -> runner pipeline with the demo OSM gateway)
    (165 tests). Tier-1 build list is now fully closed; live-LLM re-run of
    S43-S50 to flip their `scenarios.json` `expect` fields is the next
    approval-gated step (see "Next steps").
15. **Progressive map rendering** - the owner-requested "steps appear
    smoothly on the map as they run" feature, implemented per the sketch in
    AGENTS.md section 8: `ToolExecutor.execute()` and `WorkflowRunner.run_spec()`
    now thread a `step_id` through so every `tool_started`/`guard_*`/
    `tool_finished`/`tool_failed` trace event carries which workflow step
    produced it (`orchestration/executor.py`, `orchestration/runner.py`);
    a new `GET /tasks/{id}/workspace/{layer_id}` endpoint
    (`interface/api/app.py`) serves display-CRS GeoJSON for ANY layer still
    in the task's workspace, not just a named final output, with the
    serializer refactored out of the existing `/layers/{name}` endpoint
    into a shared `_serialize_layer()` helper. In `app.js`: on every
    `tool_finished` SSE event (skipping `reproject`/`detect_crs`/
    `validate_geometry`/`save_vector`/`package_outputs` - CRS bookkeeping
    and exports, not visual progress), the produced layer(s) are fetched
    from the new endpoint and drawn as pale "ghost" layers that fade in via
    MapLibre's paint-property transitions, with the map bounds extending
    progressively as each ghost lands; the status chip now pulses via CSS
    while `status === "running"`. One race condition was caught and fixed
    during browser verification: an in-flight ghost fetch could resolve
    *after* the task finished and `clearGhostLayers()` had already run,
    leaving a stray ghost source behind - fixed with a `state.ghostGeneration`
    counter that `clearGhostLayers()` bumps and every async ghost fetch
    checks before drawing, so a late-arriving ghost from a finished (or
    superseded) task generation is silently dropped instead of leaking.
    4 new backend tests (step_id present on every tool-scoped trace event;
    the workspace endpoint serves the same content as the named-output
    endpoint for the same underlying layer; 404s for an unknown layer id
    and an unknown task id) (169 tests). **Browser-verified in `--demo`
    mode** for both a single-step deterministic workflow and the 7-step
    composed rental scenario: network trace confirmed ghost fetches fired
    for every non-skipped step in order, the skip list correctly suppressed
    `reproject` steps, zero stray ghost sources remained after either run
    finished, and zero console errors throughout.
16. **React frontend rewrite** - owner asked for the web UI to be "visually
    much better," React-based, explicitly not a copy of any specific
    reference product, with full design latitude delegated to the agent.
    New `frontend/` project: Vite + React 19 + TypeScript + Tailwind v4 +
    MapLibre GL (wrapped directly, no react-map-gl) + `motion` (animation)
    + `lucide-react` (icons) + bundled `@fontsource-variable/inter`.
    Design direction: a floating glassmorphic control panel over a
    full-bleed map (amber/cyan accent duality, animated cards, pulsing
    status ring), replacing the old fixed two-column vanilla layout.
    Full feature parity with the vanilla UI it replaces: task input +
    example chips, live SSE trace with step-id badges (`TraceCard`),
    understood/plan/assumptions/questions/error cards, outputs list,
    EN/TR report toggle, LLM settings panel (provider/model/key, auto-save-
    before-test preserved), and the full progressive ghost-layer rendering
    from milestone 15 (ported into `MapView.tsx`). `app.py` now serves the
    built SPA (`src/ageo/interface/web/dist`, gitignored) mounted LAST so
    it never shadows an API route, with a graceful 503 fallback ("frontend
    not built yet") instead of crashing app startup when the build is
    missing - keeps `uv run pytest` decoupled from the npm toolchain.
    Dockerfile gained a `frontend-builder` (Node) stage that runs before
    the Python build stage. Old `src/ageo/interface/web/static/` deleted
    outright (not deprecated in place). `test_web_ui_is_served` rewritten
    to check for the hashed `/assets/index-*.js` bundle instead of the old
    fixed `app.js`/`style.css` paths (169 tests, unchanged count - this
    was a rewrite of one existing test, not a net addition).
    **Two real bugs caught and fixed during browser verification** (both
    now documented in AGENTS.md section 6 pitfalls):
    - `maplibre-gl.css`'s `.maplibregl-map { position: relative }` cascade
      silently overrode Tailwind's `.absolute` utility on the map
      container (equal specificity, later stylesheet wins), collapsing
      the map to 0 height. Fixed with an inline `style` (always wins).
    - `motion`'s `height: "auto"` animation on the Settings panel's
      collapse/expand got stuck at `height: 0` and never resolved,
      making the panel invisible despite `open=true`. Fixed by animating
      `opacity`/`y` instead and dropping the height animation entirely.
    **Browser-verified against the production build served through
    FastAPI** (`ageo-demo`, zero real LLM tokens): deterministic buffer
    workflow, the 7-step composed rental scenario (polygon fill + point
    halo rendering confirmed visually), the LLM settings panel (provider/
    model/masked-key display), and the full needs_input -> fill answer ->
    resubmit -> succeeded round-trip - all with zero console errors.
    **Not verified**: the Docker image build (no Docker daemon available
    in the session sandbox) - see "Next steps".
17. **Mainline React import** - moved Claude's `.claude/worktrees/
    laughing-raman-f41055` React/progressive-rendering work into the main
    checkout without `node_modules`, `dist`, `.venv`, or `__pycache__`;
    kept the SPA build output gitignored, adjusted the web UI smoke test
    to accept the intentional 503 fallback on fresh clones, and verified
    the imported main tree with `npm --prefix frontend run build`,
    `uv run pytest`, and a FastAPI-served browser smoke test (169 tests).
18. **Site suitability scoring tool** - added `score_candidates` in
    `tools/impl/spatial_analysis.py` so composed site-analysis plans can
    turn candidate polygons/grid cells into ranked alternatives using
    weighted numeric criteria (`minimize` distance fields, `maximize`
    area/capacity fields). Updated the proximity-site-search recipe to
    teach the composer the pattern: `calculate_area` +
    `nearest_neighbor_distance` + `score_candidates` before final display
    reprojection. Covered direct ranking/top-N/non-numeric guard behavior
    plus a 14-step composed scored rental-site plan through validator and
    runner. Follow-up in the same thread: `DemoComposerLlm` now returns
    the scored plan for rank/score/puanla/sirala prompts, so the live
    `--demo` UI can exercise `score_candidates` without real LLM variance
    (174 tests).
19. **Real OSM geometry parsing for site analysis** - upgraded
    `infrastructure/gis/overpass.py` from way-only extraction to a single
    node/way/relation Overpass request with geometry typing: nodes become
    points (schools/POIs), open ways stay lines (roads), closed area ways
    become polygons, and multipolygon relations preserve outer/inner rings
    before clipping to the selected boundary. Added focused offline gateway
    tests covering query shape, school node + closed polygon parsing, open
    highway lines and a relation with a hole. This is the data-grounding
    piece needed for realistic site-analysis runs; the existing `--demo`
    server remains intentionally synthetic/offline (178 tests).

## Key decisions (and why)

- CRS guard fails loudly, never auto-reprojects: every transformation must
  appear in the audit trace.
- LLM output is data (plans), never code; same validator for composed and
  bundled workflows - no weaker rulebook for generated plans.
- Refusal with a named missing capability beats a fake substitute
  (circular buffer is NOT an isochrone) and beats a partial "prep" plan.
- Reporter is template-based, not LLM: audit facts must not vary with
  model availability.
- Pydantic stays out of domain/ (pure dataclasses there); strict frozen
  models everywhere else.
- Test connection auto-saves the form first (owner personally hit the
  stale-key trap).

## Critical bugs encountered (do not reintroduce)

- Gemini 2.5 truncated plan JSON at max_tokens=2000 (thinking consumes
  output budget) -> composer uses 8000.
- Turkish İ lowercases to "i"+combining-dot U+0307 -> fold diacritics
  BEFORE .lower() (attributes.py); real OSM "Atatürk Bulvarı" vs typed
  "Ataturk Bulvari".
- Nominatim ranks Kutahya PROVINCE above the city -> settlement-preferring
  candidate ranking in overpass.py.
- Province-scale `way["highway"]` Overpass queries are self-DoS ->
  require_tags push-down + [maxsize:33554432].
- pipeline `| tee` into a nonexistent dir kills background eval runs.
- uv editable install: new top-level packages need
  `uv sync --reinstall-package ageo`.

## Next steps (agreed order)

1. **Realistic browser smoke test for site analysis**: restart the server
   without `--demo`, run the Kutahya rental scoring prompt through the
   React UI with the user's Gemini key, and inspect the trace/layers for
   real schools, roads and candidate polygons. This hits Nominatim,
   Overpass and the configured external LLM, so do it deliberately and log
   any prompt/tool-contract failures.
2. **Continue site-analysis capability buildout**: after `score_candidates`,
   the next real site-analysis gaps are bulk/geocoding, network routing/
   isochrones, and raster suitability layers (DEM slope + zonal stats);
   each needs its own deterministic adapter/subsystem rather than prompt
   tuning.
3. **Verify the Docker build** (milestone 16): `docker compose up --build
   ageo-demo`, confirm the built React UI is actually reachable at
   `http://localhost:8001/` from inside the image (not just via the local
   `frontend-dev`/`ageo-demo` preview configs, which is all that could be
   tested this session - no Docker daemon was running in the sandbox).
4. **Live-verify the 8 new Tier-1 tools** (milestone 14): re-run
   `uv run python -m ageo.evals --only S43 S44 S45 S46 S48 S49 S50` against
   the real Gemini key - **needs explicit user approval**, it spends real
   tokens - then flip each scenario's `expect` in `scenarios.json` from
   `gap` to `composed` (or `clarification`) and update FINDINGS.md's
   scoreboard for whichever flip. Two named gaps deliberately remain open
   after this: bulk `geocoding` (S42, Nominatim rate limits) and
   `batch_folder_processing` (S48 - folder-wide merge needs Phase 3 below,
   `merge_layers` alone only handles pre-loaded layers, not a folder scan).
5. A Settings UI tab for the profile is a smaller companion task after the
   real browser composer flight.
6. Phase 3 batch folder processing; then pgvector RAG, PostGIS workspace
   (AGENTS.md section 8).
