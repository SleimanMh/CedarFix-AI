# Arabizi Evaluation File Schemas

The CSV files in this directory are intentionally header-only until reviewed
evaluation rows exist. Keep schema documentation here, not inside the CSV files,
so metric runners can safely treat each CSV as machine-readable data.

## `arabizi_clean_eval.csv`

Purpose: clean Arabizi evaluation set. Clean means native-speaker-written, no OCR
errors, no typos, and no code-switching. Use this to measure best-case
classification performance on well-formed Arabizi.

Columns:

- `report_id`: unique identifier, format `CLEAN-NNNN`.
- `text`: Arabizi report text; no Arabic script in this file.
- `language`: must be `arabizi`.
- `expected_sector`: `ROADS`, `WATER`, `ELECTRICITY`, `WASTE`, `FLOODING`, `SAFETY`, or `OTHER`.
- `expected_issue_type`: official issue type from `docs/ANNOTATION_GUIDELINES.md`.
- `expected_severity`: `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- `expected_route_entity`: `CDR`, `MUN`, `BMLWE`, `NLWE`, `SLWE`, `BWE`, `RWA`, `EDL`, `CD`, `ISF`, `MOE`, `MPWT`, or `HITL`.
- `notes`: reviewer notes, dialect details, or edge-case flags.

## `arabizi_noisy_eval.csv`

Purpose: noisy and realistic Arabizi/mixed evaluation set. Noisy rows may contain
OCR errors, spelling inconsistency, code-switching, abbreviations, emoji, or
run-on words.

Additional column:

- `noise_type`: semicolon-separated values from `OCR`, `TYPO`, `CODESW`, `ABBREV`, `EMOJI`, `RUNON`, `DIACRITICS`.

## `arabizi_oov_eval.csv`

Purpose: out-of-vocabulary evaluation set. Every row must contain at least one
meaningful Arabizi token that is absent from production vocabulary.

Additional column:

- `oov_tokens`: semicolon-separated unknown tokens verified as meaningful and absent from production vocabulary.

## Data Status

All three CSVs currently have zero reviewed rows. Do not fabricate examples.
Rows must be real reports or native-Lebanese-speaker-approved authored examples.

Minimum reporting threshold:

- at least 20 reviewed rows before reporting clean/noisy sector or issue metrics
- at least 10 reviewed rows before reporting OOV metrics
- high-risk OOV recall must be reported separately from overall OOV recall
