# Entity Human-Review Hard Check

Generated: 2026-06-01

## Scope

This hard check reviews the entity-dossier fields still marked for human review after the source-registration audit. It separates real missing/variable information from intentional non-applicability so CedarFix does not treat an absent emergency hotline for a policy ministry or regulator as a data-quality gap.

## Changes Applied

1. `not_applicable_*` operational fields are no longer treated as missing evidence by the entity generator or entity audits. They remain omitted from contact facts unless a real, source-backed operational channel exists.
2. The stale internal `1700` water-hotline claim was removed from the water sector map and BWE responsibility text. Verified per-entity water channels are now used instead: BMLWE `1713`, NLWE `1712`, SLWE `1785`, and BWE official office/branch contacts.
3. MEW contact details were updated from the official MEW contact page: `01/565040 - 1 - 2`, `minister@energyandwater.gov.lb`, and Beirut - Corniche El Nahr. MEW remains review-gated only for public response-time/SLA, not for basic contact.
4. SLWE and NLWE complaint lines were reclassified as non-emergency utility fault/customer-service channels. Life-safety emergencies remain routed to `125` or `112` first.
5. EDL official contact information was updated from the HTTP official contact page, while the LRESRP grievance form was kept project-specific rather than promoted to a general outage complaint channel.
6. EDZ official email was verified on the EDZ contact page as `edz@edz.com.lb`; the previous decoded-email review marker was removed.
7. ISF special-channel data was replaced with the official anonymous complaints form, including crime/cybercrime-style category support, optional contact fields, and attachments. Older unverified tip/cybercrime phone values were removed from the central entity row.
8. MOE contact data was cleaned: official pages support `1789`, `961 1 976555`, fax `01/976535`, and `complaints@moe.gov.lb`; the stale `1543` review marker was removed.
9. MOIM `1766` is now treated as an official inquiries/complaints hotline because it appears on the official MOIM English home page. MOIM email and public response SLA remain unpublished.
10. ISF official contact details were updated from the official Contact Us page: headquarters at Ibrahim Al-Khoury Barracks - Adeeb Ishaq Street, Achrafieh - Beirut, phones `01422000`/`01425250`, and `isf@isf.gov.lb`.
11. SLWE headquarters location was downgraded from an unresolved placeholder to the official city-level center `Saida, Lebanon`, based on the official SLWE overview page. No exact street address was asserted.
12. TRA complaint-process fields were updated from the official TRA complaint page: escalation is after provider unsatisfactory resolution or missed applicable provider deadlines, through the Consumer Protection Directorate at `1739`.
13. Ogero fixed landline/DSL repair timing now captures the official FAQ wording: wait `3 working days` for a landline/DSL line fix before following up through customer-care channels. This was not generalized to public cable/cabinet damage.
14. The entity generator now keeps verified complaint intake separate from unresolved ticket/reference, hidden required-field, and SLA markers. Those weak markers are consolidated into the `deadline_or_sla` review fact instead of making otherwise verified process facts review-gated.
15. Municipality coverage was extended with official-page evidence for Baalbek, Bourj Hammoud, Jounieh, Bint Jbeil, Dekwaneh, and Sin el Fil; existing Aley, Nabatieh, and Zouk Mikael municipality rows were backfilled with registered source IDs.

## Source Checks Performed

| Target | Official/source check | Result | Data action |
|---|---|---|---|
| SLWE contact/customer-service | Official SLWE contact, customer-service, e-payment, visit-registration, FAQ, and overview pages show hotline `1785`, district distribution numbers, customer-service workflows, outage/cutoff causes, billing deadline rules, warning periods, and official center in Saida. | Contact/fault channel verified; city-level center verified as Saida; exact street address and restoration SLA not found. | Keep `1785` as utility fault/customer-service channel; set HQ/address to `Saida, Lebanon`; keep public ticket/restoration SLA review-gated. |
| MOIM contact | Official MOIM page footer shows Beirut - Hamra - Sanayeh, `01/754200`, `01/751601`, `01/751602`, minister office `70242613`, complaints `70243359`; official English home page also says inquiries and complaints use hotline `1766`. | Contact/complaints-room and `1766` hotline verified; no official email or general SLA found. | Keep phone/contact verified; add `1766`; keep email and response-time review-gated. |
| Central Inspection contact/complaints | Official CIB contact/complaint pages expose contact form, make-a-complaint form fields, Baydoun Building - Verdun Street, in-person/registered-mail/internet submission, complaint reference slip for in-person registration, and anonymous complaint handling. Browser access hit a certificate-date error, so `curl -k` was used for the hard check. | Complaint process verified; no office email/phone values found in the extracted official HTML; response-time SLA not found. | Keep process high confidence; keep phone/email and response-time review-gated. |
| MPWT contact | Official MPWT contact page shows `+(961) 5 459980`, `mail@ministry.gov.lb`, and contact form fields. | Non-emergency contact verified; no public ticket/SLA found. | Keep contact verified; keep ticket/SLA review-gated. |
| MEW contact | Official MEW contact page shows Beirut - Corniche El Nahr, `01/565040 - 1 - 2`, fax `01/449639`, and `minister@energyandwater.gov.lb`. | Contact verified. | Updated central entity row and regenerated dossier. |
| BWE contact/customer-service | Browser and curl hard checks failed on BWE HTTPS with TLS protocol errors; HTTP versions returned 404. Existing registered evidence remains from prior BWE official-page verification. No source-backed `1700` evidence found in current hard check. | BWE office/branch contacts retained; `1700` claim removed. | Keep BWE emergency hotline non-applicable; keep ticket/SLA review-gated. |
| EDL contact | Official EDL HTTP contact page shows Al Nahr Street - Beirut, phone `01/442720-29`, fax numbers, `info@edl.gov.lb`, customer-service offices, and local offices. Official EDL grievance page shows a project-specific LRESRP grievance phone/email/form. | Basic contact/email verified; general grid-fault ticket/reference policy still not published. LRESRP grievance is project-specific and must not be used for ordinary outage dispatch. | Update EDL contact/email; keep ordinary ticket/SLA review-gated. |
| EDZ contact | Official EDZ contact page shows phones `+961-8-823455`, `+961-8-804636`, `+961-8-803687`, address Berbara - Jisr Street - Zahle, email `edz@edz.com.lb`, office hours, and contact form fields. | Email/contact marker resolved. Ordinary complaint response-time SLA still not published. | Update EDZ official email and source URL; keep EDZ SLA review-gated. |
| ISF anonymous complaints/contact | Official ISF anonymous complaints page exposes an online complaint form with categories such as crime/cybercrime/drugs/traffic/cyberbullying/violence, optional contact fields, and attachments. Official ISF Contact Us page lists headquarters, `01422000`, `01425250`, `isf@isf.gov.lb`, `112`, and station-directory context. | Anonymous online channel, headquarters contact, and official email verified. Old `1788` and `01-293293` values remain unverified and were removed from verified fields. | Add `SRC-ISF-ANONYMOUS-COMPLAINTS` and `SRC-ISF-CONTACT`; update ISF phone/email/HQ fields; keep public response/SLA review-gated. |
| MOE contact/complaints | Official MOE contact page and environmental complaint instructions show short code `1789`, phone `961 1 976555`, fax `01/976535`, and `complaints@moe.gov.lb`; complaint handling gives a complaint number/date but no remediation deadline. | Operational contact marker resolved; response-time/remediation SLA not published. | Remove stale `1543_needs_reverification`; keep SLA review-gated. |
| TRA complaint process | Official TRA complaint page says consumers may contact TRA through the Consumer Protection Directorate at `1739` if provider resolution is unsatisfactory or provider deadlines in applicable regulations are missed. | Complaint-process and escalation-policy markers resolved; do not treat TRA as first-line fixed-service dispatch. | Update TRA ticket/reference policy to source-backed escalation condition. |
| Ogero FAQ | Official Ogero FAQ says to wait `3 working days` to get a landline/DSL line fixed, then contact customer-care channels if not fixed within the estimated time. | Fixed landline/DSL repair wait captured; public cable/cabinet repair timing remains unpublished. | Update fixed-service SLA row; keep infrastructure damage timing review-gated. |

## Remaining Real Human-Review Targets

Post-regeneration count after this deeper official-source pass: `20/127` facts still have `human_review_required=true`, down from `42/127` at the start of the hard-check cleanup, `36/127` before the continuation pass, `34/127` before the TRA/Ogero probe, `32/127` after the telecom update, and `22/127` before the final complaint-process cleanup. The latest reduction came from source-backed TRA escalation policy, Ogero fixed landline/DSL repair timing, and the generator change that stops unpublished ticket/reference and hidden required-field markers from duplicating as complaint-process gaps. Remaining flags are dominated by unpublished public response SLAs, intentionally variable municipality coverage, and three contact-style gaps.

1. MUN: all generic municipality contact fields remain variable by municipality. This requires a municipality-by-municipality batch using `municipality_official_channels.csv`, DGLAC/MOIM evidence, and local official websites/social pages.
2. Water establishments: public ticket numbers and repair/restoration SLAs remain mostly unpublished. Do not infer restoration times from outage articles or partner reports.
3. SLWE: official center is verified as Saida, but public ticket number and restoration SLA remain unpublished. The verified `1785`, district, billing, e-payment, visit-registration, and service-request surfaces remain high-confidence process facts.
4. EDL: ordinary grid-fault ticket/reference policy remains unpublished. The LRESRP grievance form is project-specific and should not be generalized to normal electricity outages.
5. Central Inspection: office phone/email are not published in the official pages extracted; complaint form requires complainant phone/email but that is not an office contact. Response-time SLA remains unpublished.
6. MOIM: official email and public response-time policy remain unpublished in checked official pages, even after adding the verified `1766` inquiries/complaints hotline.
7. ISF: official email and headquarters contact are now verified. The remaining ISF review flag is public response/SLA related, not a contact gap.
8. Ogero: fixed landline/DSL repair wait is now captured, but public cable/cabinet damage repair timing remains unpublished.

## Latest Batch Artifacts

- `reports/entity_remaining_gap_register_2026-06-01.csv`: fact-level register of all 20 remaining review-gated entity facts.
- `reports/remaining_gap_next10_batch_2026-06-01.md`: executed 10-step batch report and remaining manual targets.
- `data/knowledge_base/municipalities/municipality_channel_discovery_queue_2026-06-01.csv`: top-50 municipality official-channel discovery queue; current top-50 coverage is 5 verified contact+complaint-channel municipalities, 4 verified contact-only municipalities, and 41 still needing discovery.
- `data/knowledge_base/municipalities/municipality_townhall_contact_candidates_2026-06-01.csv`: top-200 candidate-only contact values requiring official confirmation before promotion.
- `data/knowledge_base/municipalities/source_registry.csv`: municipality source registry shard; current municipality channel/workflow source references have 0 unregistered source IDs.

## Latest Validation

- `scripts/generate_entity_dossiers.py`: generated 18 entity dossiers.
- `scripts/audit_entity_accuracy.py --fail-on-blocking`: 0 blocking issue groups; wrote `entity_accuracy_audit_2026-06-01.md`.
- `scripts/audit_entity_reliability.py --fail-on-critical`: 0 critical reliability findings; wrote `entity_reliability_audit_2026-06-01.md`.
- `scripts/validate_routing_kb.py`: passed with expected duplicate-source and cross-taxonomy warnings.
- `git diff --check`: no whitespace errors; Git reported existing CRLF normalization warnings.

## Reliability Position

After this hard check, the entity dossiers should be considered source-registered and reliability-gated, not permanently 100% factual. The key safety property is that the KB now avoids overclaiming: missing, variable, unpublished, or extraction-blocked fields are explicitly review-gated instead of promoted as verified facts.