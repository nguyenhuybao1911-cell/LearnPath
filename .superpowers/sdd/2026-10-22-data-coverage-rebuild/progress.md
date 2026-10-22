# SDD ledger — data coverage rebuild

Ruling: use the shared workspace as requested; do not alter Git metadata or commit.

## Complete

- Audited MOOCCubeX and TEMPO-DQ checkouts, schemas and public payload URLs. Downloaded exact official MOOCCubeX payloads; `user-problem.json` was 22,453,311,654 bytes and its SHA-256 matched the recorded checksum.
- Corrected domain scope to include all catalog concepts whose exact source field/ID suffix matches the domain, plus uniquely mapped prerequisite endpoints. No ID rewriting or name-similarity inference.
- Profiled CS, Math and Psychology. Selected CS: 39,292 catalog concepts, 3,288 problem-concept pairs, 612 annotated positive prerequisite edges, 7,975 interactions / 608 learners; temporal split 5,582 / 1,196 / 1,197. Math: 9 interactions; Psychology: 307.
- Processed CS with seed 42, preserved distinct log events/retakes, did not expand `attempts`, split by UTC time, and computed learner state/difficulty without future leakage.
- Verified processed outputs, relationships, unique `log_id`s, split counts, mastery and train-only difficulty. Read unmatched gzip to EOF, verified CRC and 133,349,499 rows; removed it afterwards to save 896,212,883 bytes.
- Imported twice into isolated PostgreSQL database `learnpath_candidate_20261022`; counts remained stable. Health endpoint and learner-state endpoint returned expected counts and valid UTF-8 concept names. Original DB was not modified.
- Ran Python suite: 26 tests passed. Re-ran processed-data verifier after cleanup; retained counts still match summary/profile.
- Preserved prior processed outputs at `data/backup/processed_previous_20261022/` (62,001,522 bytes). Removed raw payload (22,908,424,980 bytes) and staging remnants (82,216 bytes) after checks.
- Updated README, data audit and Vietnamese Word handoff report.

## Scope boundary

This work covers An's data/schema/import work for days 1–2 and Bảo's day 2 data processing/profile work. It does not claim the later model/evaluation/presentation tasks are complete. Existing evaluation artifacts in the preserved older processed set must not be presented as results for the new 7,975-interaction dataset.
