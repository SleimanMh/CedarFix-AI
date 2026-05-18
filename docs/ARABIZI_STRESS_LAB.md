# Arabizi Stress Lab

Version 1.0 | Purpose: demo CedarFix surviving messy Lebanese Arabizi without
pretending the dictionary is complete.

## What It Proves

The Stress Lab is a repeatable adversarial demo and regression artifact. It
does not claim final model accuracy. It proves that the current IEP-1 contract
can:

- keep the same operational sector under noisy Arabizi variants
- preserve the exact issue when wording is unambiguous
- expose ambiguity instead of hiding it
- show OOV, orthographic noise, code mix, drift score, and HITL triggers
- generate a JSON artifact that can be logged to MLflow

## Run

```bash
python scripts/run_arabizi_stress_lab.py
python scripts/run_arabizi_stress_lab.py --json --no-save
```

Artifact:

```bash
data/eval/arabizi_stress_lab_v1.json
```

## Current Gates

| Gate | Threshold |
| --- | ---: |
| Stable sector rate | >= 90% |
| Acceptable decision rate | >= 90% |
| Strict issue rate observed | >= 75% |
| HITL-triggering variants | >= 3 |
| OOV/noise variants | >= 3 |

The distinction between strict issue and acceptable decision is deliberate.
Some inputs are genuinely ambiguous, such as transformer + exposed wire or dirty
water without explicit sewer wording. A top-tier system should show those
ambiguities and route them safely, not force a brittle single label.

## Demo Script

Use three live moments:

1. Type a clean Lebanese Arabizi pothole report:

   ```text
   fi jora kbire 3al tari2 w l wad3 m5atra ktir
   ```

2. Show the Stress Lab variants:

   - missing `7`: `hofra`
   - repeated letters: `hofraaaaaa`
   - fused text: `fishare3l7amra`
   - panic shorthand: `5tr444444`
   - French code-switch: `transformateur`

3. Show the evidence fields:

   - predicted sector / issue type
   - known terms
   - OOV tokens
   - normalization coverage
   - drift score
   - HITL decision
   - strict issue vs acceptable decision

This is the professor-facing "wow" layer: it is visual, adversarial, measurable,
and honest about uncertainty.

## CI

Permanent tests:

```bash
python -m unittest scripts.tests.test_arabizi_stress_lab -v
```

The test suite fails if the Stress Lab drops below the operational stability
gates or stops exposing professor-visible evidence fields.
