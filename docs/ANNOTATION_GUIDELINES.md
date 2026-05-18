# CedarFix Command AI — Annotation Guidelines

Version 1.0 | Apply to all corpus batches | Last updated: 2026-05-17

Reference files:
- `data/knowledge_base/sector_agency_map.csv` — routing and HITL policy
- `data/knowledge_base/municipality_responsibility_map.csv` — district codes and water authorities
- `data/knowledge_base/issue_severity_reference.yaml` — severity keywords and SLAs
- `data/knowledge_base/gps_bounds.json` — GPS validation bounds
- `data/knowledge_base/arabizi_vocabulary.json` — high-precision Arabizi seeds, not an exhaustive dictionary
- `docs/CORPUS_AUTHORING_PROTOCOL.md` — authoring workflow

---

## 1. Schema Reference

| Field | Type | Allowed values |
|-------|------|---------------|
| `report_id` | string | `RPT-BNNN-NNN` |
| `cluster_id` | string | `CLU-BNNN-NNN` or empty (NOISE only) |
| `language` | enum | `en`, `ar`, `arabizi`, `fr`, `mixed` |
| `raw_text` | string | Original text exactly as submitted |
| `normalized_text` | string | Clean meaning-preserving text used for modeling. For non-Arabizi, copy `raw_text`; never use `SAME`. For Arabizi, use Arabic-script normalization. |
| `normalization_applied` | bool | `true` only for Arabizi rows normalized into Arabic script; `false` otherwise |
| `district_code` | string | Must exist in `municipality_responsibility_map.csv` |
| `lat` | float | 33.05–34.69 (Lebanon bounds) |
| `lon` | float | 35.10–36.62 (Lebanon bounds) |
| `sector` | enum | `ROADS`, `WATER`, `ELECTRICITY`, `WASTE`, `FLOODING`, `SAFETY`, `OTHER` |
| `issue_type` | string | See Section 3 for allowed values per sector |
| `severity` | enum | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `route_entity` | enum | `CDR`, `MUN`, `BMLWE`, `NLWE`, `SLWE`, `BWE`, `RWA`, `EDL`, `CD`, `ISF`, `MOE`, `MPWT`, `HITL` |
| `priority_label` | int | 1 (highest) to 5 (lowest) — see Section 5 |
| `priority_reason` | string | Short explanation for the assigned cluster-level priority |
| `hitl_required` | bool | `true` or `false` |
| `public_safety` | bool | `true` or `false` |
| `image_label` | enum | `NONE`, `POTHOLE`, `FLOODING`, `EXPOSED_WIRE`, `GARBAGE`, `STRUCTURAL_DAMAGE`, `OTHER_INFRA` |
| `image_consistent` | enum | `true`, `false`, `N/A` — consistent with `issue_type`? |
| `duplicate_role` | enum | `ORIGINAL`, `DUPLICATE`, `RELATED`, `NOISE` |
| `hard_negative_for_cluster_id` | string | Required for NOISE rows; empty for all other rows |
| `created_at_offset_minutes` | int | Minutes since cluster `created_at_reference`; 0 for ORIGINAL and NOISE |
| `labeler_id` | string | Assigned team member ID |
| `reviewer_id` | string | Second reviewer ID, or `UNASSIGNED` before second review |
| `review_status` | enum | `PENDING_SECOND_REVIEW`, `APPROVED`, `NEEDS_FIX` |
| `notes` | string | Annotation rationale; required for RELATED and NOISE; required on override |

Pairwise labels in `data/corpus/cedarfix_pairs_v1.csv` are the evaluation surface for IEP-2:

| Pair label | Meaning |
|------------|---------|
| `DUPLICATE` | Two reports describe the same physical incident |
| `RELATED` | Reports are causally or operationally related but not strict duplicates |
| `HARD_NEGATIVE` | Reports are geographically plausible but must not be merged |
| `UNRELATED` | Reports are unrelated and not designed as hard negatives |

---

## 2. Sector Taxonomy and Decision Rules

Use this decision tree top-to-bottom. Assign the FIRST matching sector.

### SAFETY
Assign if: the report describes risk of death or serious injury to people, or a crime in progress.
Examples: fire, explosion, building collapse, exposed live wire in public space, gas leak, armed incident, person trapped.
**Rule: HITL always. Never auto-route.**

### ELECTRICITY
Assign if: the report is about the public electricity supply, exposed wires, transformers, or street lights.
Examples: power cut, flickering lights, blown transformer, exposed wire, no public lighting.
**Rule: HITL always. Never auto-route.**
Note: Private generator (moualid) complaints are ELECTRICITY/OTHER — still HITL.

### FLOODING
Assign if: the report is about water on roads or in buildings due to rain, drain failure, or sewer overflow.
Examples: flooded road, blocked drain, standing water after rain, basement flooding.
Note: If the text describes sewage on the road (not rain-related), this is WATER/SEWAGE_OVERFLOW.

### WATER
Assign if: the report is about the water supply network — supply cuts, pipe leaks, sewage overflow from the network, water quality.
Examples: no water supply, pipe burst, sewage overflow, dirty or brown water.
Note: If there is also flooding due to rain, prefer FLOODING. If the flooding is caused by a broken pipe, use WATER.

### ROADS
Assign if: the report is about road surface quality, road blockage, or road infrastructure.
Examples: pothole, road collapse, road blocked, missing manhole, broken sidewalk, speed bump damage.

### WASTE
Assign if: the report is about solid waste — uncollected garbage, illegal dumping, burning waste, overflowing bins.
Examples: bins not collected, illegal dump site, burning waste pile.

### OTHER
Assign if: no sector can be determined with confidence, or the report is multi-sector and the primary sector is ambiguous.
**Rule: HITL always.**

### Issue type values per sector

```
ROADS: POTHOLE, ROAD_COLLAPSE, ROAD_BLOCKED, ROAD_CRACK, MISSING_MANHOLE, BROKEN_SIDEWALK, ROAD_DAMAGE, ROAD_CLOSED
WATER: WATER_CUT, PIPE_LEAK, SEWAGE_OVERFLOW, DIRTY_WATER, LOW_PRESSURE, NO_SUPPLY
ELECTRICITY: EXPOSED_WIRE, POWER_OUTAGE, STREET_LIGHT, TRANSFORMER_FAULT, VOLTAGE_FLUCTUATION
WASTE: GARBAGE_NOT_COLLECTED, ILLEGAL_DUMP, OVERFLOWING_BIN, BURNING_WASTE, DAMAGED_BIN
FLOODING: ROAD_FLOODED, HOUSE_FLOODED, BLOCKED_DRAIN, FLASH_FLOOD, STANDING_WATER, BASEMENT_FLOODED
SAFETY: STRUCTURAL_COLLAPSE, FIRE, GAS_LEAK, EXPOSED_HAZARD, ARMED_INCIDENT, INJURY, SUSPICIOUS
OTHER: UNCLASSIFIED
```

---

## 3. Severity Decision Matrix

Assign severity based on: physical scope, danger to life, duration, and reversibility.

| Severity | Defining characteristics | Examples |
|----------|--------------------------|---------|
| **CRITICAL** | Immediate danger to life or risk of serious injury; OR infrastructure collapse in progress; OR contamination of drinking water | Exposed live wire, road collapse blocking emergency access, sewage in drinking water, fire, structural collapse, flash flood with people trapped |
| **HIGH** | Significant impact on daily life of multiple households; OR infrastructure failure affecting essential service (water/power for 24+ hours); OR large-scale waste or flooding risk | Water cut 2+ days, power outage overnight, large pothole causing vehicle damage, sewage overflow on road, illegal dump attracting vermin, neighborhood flooding |
| **MEDIUM** | Moderate inconvenience; limited geographic scope; non-emergency; fixable in normal maintenance cycle | Small pothole, bins uncollected 2–3 days, blocked drain with standing water, low water pressure, one street light out |
| **LOW** | Minor, cosmetic, or non-urgent; no immediate safety or service impact | Faded road markings, dripping tap, damaged bin, minor crack, billing dispute |

**Severity escalation rules:**
- A MEDIUM issue that has been present for 2+ weeks without response → escalate to HIGH
- Any issue within 100m of a school, hospital, or market → escalate one level
- A cluster where 3+ DUPLICATE reports have been filed within 2 hours → escalate one level (cluster-level escalation, not per-report)

---

## 4. Route Entity Selection Rules

### Step 1: Determine sector
### Step 2: Apply sector-to-entity mapping

| Sector | District type | Route entity | Notes |
|--------|--------------|-------------|-------|
| ROADS | National/primary road (CDR jurisdiction) | `CDR` | Applies to Corniche, Ring Road, coastal highways |
| ROADS | Local/neighborhood road | `MUN` | Municipality of that district |
| WATER | Beirut or Mount Lebanon district | `BMLWE` | Check `water_authority_abbr` in municipality map |
| WATER | North Lebanon or Akkar district | `NLWE` | |
| WATER | South Lebanon or Nabatieh district | `SLWE` | |
| WATER | Bekaa or Baalbek-Hermel district | `BWE` | |
| ELECTRICITY | Any district | `EDL` | Always + HITL=true |
| WASTE | Standard collection issue | `MUN` | |
| WASTE | Illegal dumping (construction, medical, industrial) | `MOE` | Ministry of Environment |
| WASTE | Burning waste | `MOE` | Environmental violation |
| FLOODING | Active flooding (water present now) | `CD` | Civil Defense emergency |
| FLOODING | Drainage maintenance (no active flood) | `MUN` | |
| SAFETY | Any | `ISF` or `CD` | ISF for crime/security; CD for structural/fire/explosion; HITL=true always |
| OTHER | Any | Leave route_entity blank or `HITL` | HITL always |

**When in doubt:** Use the routing fallback from `sector_agency_map.csv` and set `hitl_required=true`.

**RWA** (Regional Water Authority): Use only when the specific water authority is unknown. Prefer the specific abbreviation (BMLWE/NLWE/SLWE/BWE) based on district lookup.

---

## 5. Priority Label Definition

Priority label is an integer 1 (highest urgency) to 5 (lowest urgency). It is a cluster-level operational decision label, not a pure copy of per-report severity. Assign the label from the most urgent report in the cluster and propagate it to ORIGINAL, DUPLICATE, and RELATED rows in that cluster.

| Priority | Rule |
|----------|------|
| **1** | Emergency / immediate field review: CRITICAL public-safety incident, exposed wire, structural collapse, fire, gas leak, road collapse, or sewage/contamination emergency |
| **2** | High-priority dispatch: HIGH essential-service failure, active flooding, illegal dumping/public-health risk, or HIGH incident with strong cluster evidence |
| **3** | Standard municipal dispatch: MEDIUM infrastructure issue, routine waste/drainage/road issue, or moderate service disruption |
| **4** | Low-priority maintenance: LOW issue that still needs municipal action |
| **5** | Non-urgent / cosmetic / administrative issue, or a hard negative with LOW operational urgency |

**Override rule:** If `hitl_required=true`, do not automatically set priority to 1. Priority and HITL are separate decisions. Example: a power outage is HITL because of jurisdiction ambiguity, but it may remain priority 2 if there is no exposed wire or direct life-safety signal.

**All reports in the same cluster must have the same priority_label** (priority is a property of the incident, not the individual report).

---

## 6. HITL Trigger Rules

Set `hitl_required=true` if ANY of the following apply:

| Condition | Rationale |
|-----------|-----------|
| `sector=ELECTRICITY` | Public grid vs private generator cannot be auto-determined |
| `sector=SAFETY` | Life safety; wrong routing could cost lives |
| `sector=OTHER` | Sector is unknown; routing is not possible |
| `severity=CRITICAL` AND `public_safety=true` | Model confidence alone is insufficient for life-risk cases |
| `route_entity` cannot be resolved from district + sector | Ambiguous jurisdiction |
| Issue involves multiple sectors (e.g., exposed wire + flooding) | Sector assignment is contested |
| Text contains safety keywords (fire, explosion, collapse, gas, armed) | See `issue_severity_reference.yaml` SAFETY CRITICAL keywords |
| Meaningful unknown Arabizi term appears in a HIGH/CRITICAL or low-confidence report | Language drift could change sector, issue, severity, or route |

**Never set `hitl_required=false` for ELECTRICITY or SAFETY, regardless of how clear the report is.**

---

## 7. Duplicate Role Decision Rules

### ORIGINAL
The first, or most complete, or clearest report in the cluster. Only one ORIGINAL per cluster.

### DUPLICATE
A report that describes the **same physical incident** at the same location and time window. All of the following must be approximately true:
- Same sector and issue_type (or semantically equivalent)
- GPS within 100m of ORIGINAL (±0.0010 degrees)
- Submitted within 72 hours of ORIGINAL
- Describes the same street, intersection, or landmark

### RELATED
A report that is part of the same real-world event chain but describes a different symptom, location, or secondary effect. At least one of:
- Different `issue_type` from ORIGINAL (but same root cause)
- GPS 150–300m from ORIGINAL (adjacent district acceptable)
- Describes a consequence (e.g., road blocked because of collapse in another report)

Use RELATED sparingly. Maximum 1–2 RELATED per cluster.

### NOISE
An independent report that is NOT part of this cluster but appears similar enough to be a hard negative. Characteristics:
- Same area (GPS within 500m of cluster)
- Different sector or different issue_type
- No plausible causal connection to cluster incident
- Set `cluster_id` to empty
- Set `hard_negative_for_cluster_id` to the target cluster ID
- `notes` must explain why it is a hard negative

**GPS overlap threshold for NOISE:** NOISE reports must be within 800m of the cluster centroid to be useful as hard negatives.

---

## 8. Edge Cases and Disagreement Resolution

**Multi-sector reports** (e.g., exposed wire AND flooding): Assign to the more dangerous sector. Exposed wire (ELECTRICITY) beats flooding (FLOODING). SAFETY beats everything.

**Ambiguous severity**: If in doubt between MEDIUM and HIGH, prefer HIGH if the issue has been present for more than 3 days without response.

**Arabizi with mixed Arabic script**: Label as `arabizi` if the majority of the text uses Latin-script transliteration. Label as `ar` if the majority is Arabic script with some Arabizi words.

**Route entity unknown**: If the `district_code` is not in `municipality_responsibility_map.csv` or the sector routing is ambiguous, set `route_entity` to the sector fallback from `sector_agency_map.csv` and set `hitl_required=true`.

**Duplicate vs Related borderline**: If you are unsure whether two reports describe the same incident or related incidents, default to RELATED (conservative). IEP-2 treats RELATED as a weaker signal than DUPLICATE. Incorrect RELATED is less harmful than incorrect DUPLICATE.

**Disagreement between labelers**: Keep `review_status=NEEDS_FIX` until the team lead resolves the row. Log the disagreement in the `notes` field as `DISPUTE: <description>`. Do not silently overwrite the original labeler's decision.

**Cluster size**: If a cluster grows beyond 6 reports of the same issue, stop adding DUPLICATEs and start a new cluster for a different scenario. Large clusters dilute evaluation diversity.

---

## 9. Public Safety Flag

Set `public_safety=true` if the incident creates risk of:
- Death or serious injury to bystanders
- Contamination of public water supply
- Structural collapse in an occupied building
- Active fire or explosion hazard
- Traffic accident due to hazard (only if CRITICAL — not for normal potholes)

Set `public_safety=false` for:
- Infrastructure inconvenience (power out, no water) — even if disruptive
- Environmental hazard without immediate human exposure
- Normal potholes or road cracks

**Note:** `public_safety=true` does NOT automatically mean `hitl_required=true` (though it often correlates). HITL is driven by sector policy; public_safety is an independent flag used for priority ranking.

---

## 10. Arabizi OOV and Drift Review

CedarFix must never depend on `arabizi_vocabulary.json` as a closed dictionary. Lebanese citizen language is noisy, local, and creative. The vocabulary is used for normalization, weak supervision, explanation, and monitoring; the model must still process the raw text.

After every corpus batch, run:

```powershell
python scripts/analyze_arabizi_oov.py
python scripts/validate_arabizi_oov_queue.py
```

This generates `data/corpus/arabizi_oov_review_queue_v1.csv`, the review surface for unknown but potentially meaningful Arabizi tokens.

### OOV decision labels

| Decision | Use when |
|----------|----------|
| `ADD_TO_VOCAB` | Token is Lebanese-plausible, semantically useful for municipal reports, and should become a known seed for a specific sector/issue_type |
| `KEEP_MODEL_ONLY` | Token is meaningful in context but too general, verbal, or unstable to belong in the fixed vocabulary |
| `ADD_TO_STOPLIST` | Token is a connector, place artifact, name, acronym, or non-semantic filler repeatedly appearing in OOV output |
| `REJECT_NOISE` | Token is typo noise, keyboard smash, or not Lebanese/municipal signal |
| `NEEDS_MORE_EXAMPLES` | Token may be meaningful, but one example is not enough to safely promote it |

### Review rules

- Do not add a token to the vocabulary only because it appears once.
- Do add urgent safety language quickly if it is plausible and reviewable, e.g. unseen variants of `5tr`, exposed wire, fire, gas, collapse, injury, or active flooding.
- Keep names, streets, buildings, shops, acronyms, and municipalities out of issue vocabulary unless they are needed for routing KBs.
- A token accepted as `ADD_TO_VOCAB` must have `review_status=REVIEWED`, a real `reviewer_id`, `decision=ADD_TO_VOCAB`, and valid `proposed_sector` / `proposed_issue_type`.
- Accepted vocabulary additions must be copied into `arabizi_vocabulary.json` in the next vocabulary version and mentioned in the changelog.

### Professor defense

If asked why the vocabulary is incomplete, answer:

> CedarFix does not assume a fixed dictionary covers Lebanese Arabizi. Unknown terms are monitored as language drift. Raw text still goes to semantic and character/subword models, while high-risk or low-confidence unknowns are routed to HITL and reviewed as vocabulary or retraining candidates.
