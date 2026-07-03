# CLAUDE.md - Claude Code entry point for the Autonomous GIS Workbench

Read these two files before doing anything:

1. **[AGENTS.md](AGENTS.md)** - the canonical working guide: architecture
   map, non-negotiable engineering rules (geodetic guards, plans-as-data,
   layer boundaries, offline tests), pitfalls, and roadmap. It is shared
   with Codex; NEVER let this file and AGENTS.md disagree - rules live
   there, not here.
2. **[HANDOFF.md](HANDOFF.md)** - the living project state: milestone log,
   decisions, known bugs, and the agreed next steps. The user alternates
   between Claude Code and Codex due to token limits; HANDOFF.md is the
   shared memory that bridges sessions.

## Session protocol

- Start: read AGENTS.md + HANDOFF.md, then continue from HANDOFF's
  "Next steps".
- End of any significant milestone: update HANDOFF.md (milestone log,
  current state, next steps) so the next session - either model - can
  resume seamlessly. Update README.md feature status too.
- `uv run pytest` must be green before and after your work (85 tests,
  offline, ~2 s). Never add tests that hit the network or spend tokens.
- UI-visible changes: verify in the browser (preview config `ageo` =
  real OSM, `ageo-demo` = offline) and check the console for errors.

## Quick facts

- Python 3.12+/uv, FastAPI + Pydantic v2 strict, GeoPandas/Shapely 2/
  pyproj, LiteLLM (user's Gemini 2.5 Flash key via UI Settings panel),
  MapLibre vanilla-JS UI. English-only code/comments; TR+EN user-facing.
- Evaluation harness: `uv run python -m ageo.evals` (50 scenarios;
  baseline and tool build list in evals_results/FINDINGS.md).
- The user delegates design decisions: make the expert call, state it,
  proceed - do not present option menus.
