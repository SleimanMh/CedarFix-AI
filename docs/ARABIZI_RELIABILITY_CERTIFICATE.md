# Arabizi Reliability Certificate

Version 1.0 | Purpose: live, presentation-ready robustness evidence for one
citizen report.

## What It Adds

The Stress Lab proves fixed adversarial cases. The Reliability Certificate goes
one level higher: it takes a live report typed during the demo, generates noisy
variants, reruns IEP-1, and produces a JSON plus standalone HTML artifact.

This is the most defensible "wow" pattern for CedarFix because it is not a
magic chatbot moment. It is an engineering proof:

```text
one report -> adversarial variants -> repeated inference -> stability metrics
           -> OOV/HITL evidence -> review actions -> lineage artifact
```

## Run

```bash
python scripts/certify_arabizi_input.py
python scripts/certify_arabizi_input.py --text "fi jora kbire 3al tari2 w l wad3 m5atra ktir" --language arabizi
```

Artifacts:

```bash
data/eval/arabizi_reliability_certificate_v1.json
data/eval/arabizi_reliability_certificate_v1.html
```

## What The Certificate Shows

- original operational decision
- generated adversarial variants
- stable sector rate
- stable issue rate
- HITL rate
- drift score distribution
- normalization coverage
- OOV token list
- recommended review actions
- vocabulary hash for lineage

## Demo Use

Open the HTML artifact during the demo after submitting a live Arabizi report.
The professor sees not only the prediction, but the system trying to break its
own prediction and reporting where it is stable or uncertain.

Strong demo line:

> We do not claim Arabizi is solved by a dictionary. For every live report,
> CedarFix can produce a robustness certificate: it perturbs the input, checks
> decision stability, exposes drift and OOV terms, and routes uncertainty to
> HITL instead of hiding it.

## Scope

This is single-input robustness evidence, not final model accuracy. Final
accuracy still requires Batch 002+ held-out Arabizi/mixed rows and calibrated
routing evaluation.
