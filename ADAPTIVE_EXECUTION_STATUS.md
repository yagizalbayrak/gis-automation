# Adaptive Execution & Dynamic Calibration - Blueprint vs. Reality

> **Purpose of this file**: the original blueprint (designed in a planning
> session, never itself committed anywhere) proposed two architectural
> pillars - Dynamic User Calibration and a Clarification Engine - plus an
> illustrative GIS-consultancy scenario. This file maps every piece of
> that blueprint to what actually exists in code today, so any session
> (Claude or Codex) can tell built from planned without re-deriving it.
> Rules/architecture live in [AGENTS.md](AGENTS.md); state/history lives in
> [HANDOFF.md](HANDOFF.md); this file is specifically the blueprint tracker.
> Last updated: 2026-07-05.

## One-line status

**3 of an open-ended set of increments landed.** The Clarification Engine
(pillar 2) is fully built and live-verified for both registered workflows
and composer-originated ambiguity. The User Calibration side (pillar 1) has
its data model and LLM injection built, but the onboarding UI and the
"living"/self-adapting part of the profile were never started. Tests:
142/142 green, offline.

## Pillar 1: Dynamic User Calibration

| Piece | Status | Where |
|---|---|---|
| `UserProfile` data model (role, gis_level, crs_awareness, autonomy_preference, explanation_depth, language) | **Done** | `src/ageo/domain/value_objects/user_profile.py` |
| Persisted store (file-backed, single-tenant, mirrors `LlmConfigStore`) | **Done** | `src/ageo/infrastructure/user/profile_store.py` |
| API to read/write the profile | **Done** | `GET/PUT /settings/profile` |
| Compact prompt-line injection into planner + composer LLM calls (`to_prompt_line()`, ~20 tokens) | **Done** | `litellm_planner.py`, `litellm_composer.py` |
| Profile-driven report depth (`plain`/`steps`/`audit`) and language default | **Done** | `ProcessReporter.report(depth=...)`, `/report` endpoint |
| **Onboarding question flow** ("5-7 quick steps" to build the initial profile) | **NOT started** | no UI code exists; the Settings panel (gear icon) only has LLM connection fields, no profile tab |
| **Implicit Profile Updater** (profile silently adapts from chat behavior - e.g. using an EPSG code raises `crs_awareness`, repeated "why did you do that" raises `explanation_depth`) | **NOT started** | no code anywhere; profile only changes via explicit `PUT /settings/profile` |

**In short**: the profile is a real, working data pipe into the LLM and the
report - but a human has to set it by hand via a raw API call today. There
is no "getting to know you" UI, and the profile never moves on its own.

## Pillar 2: Clarification Engine

| Piece | Status | Where |
|---|---|---|
| Structured question schema (severity, TR+EN text, options with recommended flag, blocking, default_if_skipped) | **Done** | `src/ageo/application/agents/clarifier.py` (`PendingQuestion`, `QuestionOption`) - note: this evolved from the original blueprint's exact field names (`reason`/`question`/`options` flat) into `text: {en, tr}` dicts + a `severity` field used for real gating, which the original sketch didn't have wired to any logic |
| Assumption Ledger (records silently-applied defaults so they're never invisible) | **Done** | `clarifier.py` (`Assumption`), rendered in API response, UI card, and report at every depth |
| Gating by `autonomy_preference` for **registered workflow** params | **Done** | `build_questions()`; required params always ask, spec defaults ask only under `strict_confirm`, else ledgered |
| Gating by `autonomy_preference` for **composer-originated** ambiguity (novel/LLM-composed requests) | **Done, live-verified against real Gemini 2.5 Flash** | `ComposerClarificationRequired` in `composer.py`; `guided`/`strict_confirm` ask, `autonomous` auto-resolves only if the composer supplied a recommended option - **first place guided and autonomous actually differ** |
| One-clarification-round cap (no infinite ask loops) | **Done** | a second ask after an answer was supplied becomes an honest `plan_refused:` |
| UI rendering of structured questions + assumptions card | **Done** | `app.js` (`renderStructuredQuestions`, `renderAssumptions`) - built once in increment 2, reused as-is by increment 3 with zero new UI code |
| Eval-harness classification of the new outcome + a real scenario using it | **Done** | `COMPOSED_CLARIFICATION` outcome in `src/ageo/evals/harness.py`; scenario `S26` (the degree/metre trap) upgraded from `expect: gap` to `expect: clarification`, confirmed live |

**In short**: this pillar is complete and working end-to-end, including a
live run against the real model - not just scripted tests.

## The GIS Consultancy Office scenario (Persona A / Persona B)

**Purely illustrative - never implemented.** This was used in the original
planning conversation to pressure-test the architecture's design (a
non-technical urban planner vs. a strict GIS engineer running the same
"Suitability Map & Disaster Risk Assessment" task). No raster tools
(`slope_from_dem`, DEM ingestion, legal-buffer-constraint parsing), no
Tier-2 tool build-out, and no eval scenarios for this specific use case
exist in the codebase. If this scenario is wanted as a real deliverable,
it needs its own scoping pass - it is not on the current roadmap.

## Increments landed so far (chronological)

1. **Increment 1 - User Calibration data plumbing**: `UserProfile` +
   store + API + LLM prompt injection + report depth. (HANDOFF.md
   milestone 11)
2. **Increment 2 - Clarification Engine for registered workflows**:
   `clarifier.py`, structured `questions`/`assumptions` on `TaskResponse`,
   UI rendering. (HANDOFF.md milestone 12)
3. **Increment 3 - Clarification Engine for composer/novel requests**:
   `ComposerClarificationRequired`, guided-vs-autonomous divergence,
   live-verified. (HANDOFF.md milestone 13)

Full technical detail for each lives in HANDOFF.md's milestone log; this
file only tracks blueprint-coverage, not implementation mechanics.

## What is explicitly NOT done (candidates for a future increment)

- Onboarding UI to build the initial profile (Settings panel profile tab).
- Implicit Profile Updater (auto-adapting profile from chat signals).
- Composer clarifications' `guided` vs `strict_confirm` currently behave
  identically (both always ask) - untested whether that should ever
  diverge; not a bug, just an unexplored axis.
- The GIS Consultancy Office scenario (raster/DEM tooling) - illustrative
  only, no implementation exists or is scheduled.
- Anything under HANDOFF.md's "Next steps" (Tier-1 tools, progressive map
  rendering, batch processing, pgvector RAG, PostGIS) is unrelated to this
  blueprint and tracked there instead.
