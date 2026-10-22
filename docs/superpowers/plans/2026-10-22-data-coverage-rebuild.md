# MOOCCubeX Data Coverage Rebuild Plan

**Goal:** Re-select and rebuild the learning-data scope from measured interaction coverage, keeping only source-backed events and concept prerequisites, with at least 2,000 train-split interactions per the advisor's requirement.

**Architecture:** Re-download the official MOOCCubeX payloads, profile exact problem-to-concept joins across CS, Math, and Psychology in one history pass, then process the best supported single domain. Keep the current processed files unchanged until coverage, split counts, and learner-state counts have been compared and verified.

**Tech Stack:** Existing streaming Python downloader and pipeline, SQLite staging, PostgreSQL importer.

**Spec:** User request on 2026-10-22 to redo data properly and not settle for a one-learner/low-history demo.

## Global Constraints

- Never synthesize interactions, labels, links, or prerequisite edges.
- Preserve source IDs exactly; join only by verified IDs.
- Keep learner state time-bounded and compute it only from prior events.
- Compare all candidate domains using the same history and problem-concept source.
- Do not replace the current dataset until the candidate is audited; remove raw payload only after successful rebuild and import verification.

## Review Focus

- Domain scope only includes concepts supported by prerequisite data and must be intersected with problem-concept links exactly.
- Interactions with no problem-concept link remain unmatched; do not infer links from names.
- Multi-concept questions contribute once per exact linked concept, never as duplicated events.
- All-domain profiling must be one streaming history scan, not three scans of the 22.45 GB file.
- Report split and per-learner histories so one selected UI learner is not mistaken for the whole evaluation sample.

### Task 1: Measure domain coverage

**Files:** `scripts/profile_data_coverage.py`, tests, `docs/data_audit.md`.

- Download official concept, problem-concept, all three prerequisite files, and user-problem history.
- Stream history once; report exact linked events, distinct learners/problems/concepts, per-learner event distribution, and temporal split counts for each candidate domain.
- Apply the 2,000 minimum to the chronological train split, not raw rows or total events before splitting.
- Verify IDs and counts on small fixtures before processing raw.

### Task 2: Select and rebuild

**Files:** `src/pipeline.py`, `data/processed/*`, README/data audit.

- Choose the candidate domain with the strongest exact interaction coverage among domains that have annotated prerequisite edges.
- Keep the full supported learner cohort; do not set a single-learner or low arbitrary learner cap.
- Create train/validation/test chronologically, then compute initial state strictly before the test cutoff.
- Compare output counts to the coverage profile and document all discarded unmatched/out-of-scope events.

### Task 3: Verify integration and cleanup

**Files:** importer/API behavior and data audit.

- Import rebuilt tables idempotently and verify learners, observed concepts, and recommendation routes.
- Delete large raw/staging inputs only after processed outputs and importer verification succeed; preserve manifest, profile, and checksums.
