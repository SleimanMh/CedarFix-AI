# Arabizi Evaluation Suite Schema

The active Arabizi smoke/regression seed set is consolidated in
`data/eval/arabizi_eval_suite.csv`.

The suite is machine-readable and uses `row_type` to separate five cases:

- `CLEAN`: clean Arabizi classification rows.
- `NOISY`: typo/OCR/code-switching classification rows.
- `OOV`: rows with meaningful unknown Arabizi tokens.
- `PAIR`: cross-language duplicate, related, or unrelated pair rows.
- `NOTATION`: notation-only rows that test romanization behavior without
  creating routing claims.

## Columns

- `suite_id`: unique row identifier.
- `row_type`: `CLEAN`, `NOISY`, `OOV`, `PAIR`, or `NOTATION`.
- `source_id`: source row identifier from the original seed.
- `text`: single-report text for `CLEAN`, `NOISY`, `OOV`, and `NOTATION`.
- `report_a_text`, `report_b_text`: pair texts for `PAIR`.
- `language`: language for single-report rows.
- `lang_a`, `lang_b`: pair languages for `PAIR`.
- `noise_type`: semicolon-separated noise tags for `NOISY`.
- `oov_tokens`: semicolon-separated unknown meaningful tokens for `OOV`.
- `expected_normalized_ar`: expected Arabic-script output for `NOTATION`.
- `expected_sector`: CedarFix sector or `ALL_SUPPORT` for notation-only rows.
- `expected_issue_type`: official issue type or `ALL_SUPPORT`.
- `expected_severity`: `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- `expected_route_entity`: expected routing target for classification rows.
- `expected_hitl`: `TRUE` or `FALSE` for notation rows.
- `expected_pair_label`: `DUPLICATE`, `RELATED`, or `UNRELATED`.
- `expected_reason`: concise pair-label rationale.
- `expected_notation_rules`: semicolon-separated notation rule IDs.
- `difficulty`: `LOW`, `MEDIUM`, or `HIGH` for pair rows.
- `notes`: source and reviewer notes.

## Data Status

Current seed counts:

- `CLEAN`: 4 rows
- `NOISY`: 2 rows
- `OOV`: 1 row
- `PAIR`: 5 rows
- `NOTATION`: 1 row

These rows are useful for smoke tests and regression checks, but they are not
enough to report final classification metrics. Final metrics require real
reports or native-Lebanese-speaker-approved authored examples.

Minimum reporting thresholds:

- at least 20 reviewed `CLEAN`/`NOISY` rows before reporting sector or issue metrics
- at least 10 reviewed `OOV` rows before reporting OOV metrics
- high-risk OOV recall must be reported separately from overall OOV recall
