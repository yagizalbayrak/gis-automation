# HANDOFF.md - Living Project State (Context Handoff)

> **Protocol:** This file is the shared memory between AI sessions (Claude
> Code <-> Codex). Whoever completes a significant milestone MUST append to
> "Milestone log" and refresh "Current state" + "Next steps" before ending
> the session. Rules and architecture live in [AGENTS.md](AGENTS.md) - do
> not duplicate them here; this file records STATE and HISTORY.
> Last updated: 2026-07-03 by Codex.

## Current state (the short version)

- **Product**: Autonomous GIS Workbench (`ageo`) - natural-language TR/EN
  geospatial automation. Brief: `PROJECT_BRIEF_FABLE5.md`.
- **Tests**: 97/97 green, all offline (`uv run pytest`, ~2 s).
- **Runs**: `uv run python -m ageo.interface.api.serve` (real OSM) or
  `--demo` (offline synthetic Kutahya). Web UI at `/` on :8000
  (respects `PORT`). Preview configs in `.claude/launch.json`.
- **LLM**: user's own **Gemini 2.5 Flash** key, configured via the UI
  Settings panel, stored at `~/.ageo/llm_settings.json` (owner-only,
  masked in API). Adapters read live config per call. A local `.env`
  template now exists for headless tests/evals; set `GEMINI_API_KEY=...`
  there. Saved UI settings take precedence over `.env`.
- **Verified against real data**: 576 named roads fetched from Overpass
  for Kutahya; real "Atatürk Bulvarı" buffered 25 m in EPSG:5254 and
  rendered on the MapLibre map. Zero console errors.
- **Evaluation baseline** (see `evals_results/FINDINGS.md`): 50-scenario
  pool, Gemini 2.5 Flash - 49/50 behave as intended; 27 plans composed
  first-try (max 13 steps); 19 honest refusals naming missing
  capabilities; all geodetic trap scenarios dodged.
- **Tier-1 tool progress**: `calculate_area` and `calculate_length` are now
  registered. They require projected metric polygon/line layers, support
  m2/ha and m/km respectively, and return measured layers plus compact
  table/total outputs. API responses keep map layers in `outputs` and expose
  scalar/table outputs in `results`. S33/S34-shaped composed plans are
  covered offline with the demo gateway. Live evals still need explicit user
  approval because they send prompt and tool-catalog context to the
  configured external LLM.
- Parallel Codex checkout exists at `~/Desktop/gis-automation-v2-codex`
  (server seen on :8001). Keep the two trees in sync deliberately - they
  do NOT share state.

## Architecture in one paragraph

Requests climb an escalation ladder: DeterministicPlanner (pattern match,
zero tokens) -> HybridPlanner LLM fallback (one small call, sanitized) ->
PlanComposer (one strong call composing a NEW WorkflowSpec-shaped JSON
plan). Every plan - bundled or composed - must pass `validate_workflow()`
(structure + static CRS-coherence simulation), then executes step-by-step
through the guarded `ToolExecutor` (CRS/geometry guards, trace events).
18 deterministic tools; geometries never enter LLM context (LayerRef
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

1. **Continue Tier-1 tools** from evals_results/FINDINGS.md: centroid,
   simplify_geometry, count_points_in_polygons
   /aggregate, nearest_neighbor_distance, merge_layers, csv_to_point_layer,
   DXF+KML in save_vector, voronoi, grid_generation. After EACH tool,
   re-run its gap scenarios (`uv run python -m ageo.evals --only S43 ...`)
   - the refused->composed flip is the progress metric. Live evals require
   explicit approval because they send prompt/catalog context to the
   configured external LLM.
2. **Progressive map rendering** (explicitly requested by owner, still
   owed): workspace-layer endpoint + step ids in trace + ghost layers with
   fade-in during execution. Implementation sketch in AGENTS.md section 8.
3. First real composer flight in the browser UI with the user's Gemini key
   (eval ran headless; UI path untested with live LLM).
4. Phase 3 batch folder processing; then pgvector RAG, PostGIS workspace,
   Docker packaging (AGENTS.md section 8).
