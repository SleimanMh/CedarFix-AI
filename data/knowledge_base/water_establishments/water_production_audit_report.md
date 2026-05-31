# Water Production Audit Report

Generated: 2026-05-31

## Routing Resolver Coverage

| Entity | Municipalities | Contacts | Channel modes | Required-field rows | Not-responsible rows | SLA rows | Published response wording |
|---|---:|---:|---|---:|---:|---:|---:|
| BMLWE | 352 | 10 | official_mobile_app;online_contact_form;online_form_or_app;online_ticket;partner_agent;phone;walk_in | 27 | 3 | 2 | 0 |
| NLWE | 320 | 10 | online_contact_form;online_eservices;partner_agent;phone;walk_in | 20 | 2 | 2 | 1 |
| SLWE | 237 | 8 | online_bill_inquiry;online_payment;online_registration;partner_agent;phone;walk_in | 34 | 2 | 2 | 0 |
| BWE | 185 | 6 | informational;office_or_branch;online_contact_form;partner_agent;phone;walk_in | 8 | 3 | 4 | 1 |
| LRA | 0 | 13 | online_contact_form | 12 | 1 | 1 | 0 |
| MEW | 0 | 1 | online_claims_form;online_contact_form;policy_escalation | 17 | 1 | 2 | 0 |

## Eval Gate

- Water routing eval: 355/355 passed.
- Failures: 0.

## Provenance Gate

- Production files checked: 13.
- Issues: 0.

## Remaining Manual Verification

- BMLWE ticket/reference details remain browser/app-verification only.
- NLWE public complaint reference-number policy is not published.
- SLWE HQ address and individual transaction document pages still need manual extraction.
- BWE official pages are browser-verifiable, but automated crawler TLS failures remain in page inventory.
- LRA project-specific irrigation overlap needs map extraction before automatic LRA routing beyond named Litani/Qasimiya/Ras Al Ain cases.
- Generic repair/restoration SLAs remain not published; do not promise restoration times.
