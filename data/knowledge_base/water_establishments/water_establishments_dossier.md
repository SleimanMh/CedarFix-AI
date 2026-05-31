# Water Establishments Dossier

Generated: 2026-05-31

Scope: Beirut and Mount Lebanon Water Establishment (BMLWE/EBML), North Lebanon Water Establishment (NLWE/EELN), South Lebanon Water Establishment (SLWE), Bekaa Water Establishment (BWE), MEW oversight, and Litani River Authority (LRA) boundary cases.

Structured companion tables in this folder:

- `source_registry.csv`
- `page_inventory.csv`
- `source_candidate_review.csv`
- `scrape_run_report.md`
- `coverage_summary.csv`
- `water_entity_resolution.csv`
- `contact_points.csv`
- `branch_service_areas.csv`
- `complaint_channels.csv`
- `required_fields.csv`
- `water_service_catalog.csv`
- `not_responsible_for.csv`
- `trusted_context.csv`
- `irl_complaint_patterns.csv`
- `boundary_conditions.csv`
- `irrigation_boundaries.csv`
- `sla_policy.csv`
- `research_backlog.csv`
- `water_production_audit_report.md`

## Routing Conclusions

- Keep `WATER_ESTABLISHMENT_BY_LOCATION` in routing rules. The router resolves it through `water_entity_resolution.csv` after extracting municipality/GPS.
- Water routing needs an exact municipality or GPS. Without location, route to HITL and ask for municipality/neighborhood.
- Primary operational entities are the four regional water establishments. MEW is policy/oversight escalation, not first-line field dispatch.
- Do not promise restoration deadlines. The official pages confirm complaint channels and customer-service processes, but not generic repair SLAs.
- Treat urgent flooding, rescue, collapse, electrical hazard, or sewage entering homes as emergency/HITL with Civil Defense or ISF as needed before ordinary water-establishment follow-up.
- Treat irrigation complaints as HITL when the location may involve Litani/Qasimiya/Ras Al Ain irrigation assets; LRA may be the better entity than the regional water establishment.

## Coverage From Runtime Municipality Map

| Entity | Runtime mapped municipalities | Governorates | District notes |
|---|---:|---|---|
| BMLWE | 352 | Beirut; Mount Lebanon | Beirut, Baabda, Metn/Matn, Kesrouane, Jbeil/Byblos, Aley, Chouf |
| NLWE | 320 | North; Aakkar | Tripoli, Koura, Zgharta, Bcharre, Batroun, Minieh-Danniyeh, Akkar/Halba/Qobayat |
| SLWE | 237 | South; Nabatieh | Saida, Sour/Tyre, Jezzine, Nabatieh, Bint Jbeil, Marjayoun, Hasbaya |
| BWE | 185 | Beqaa; Baalbek-Hermel | Zahle, Western Bekaa, Rashaya, Baalbek, Hermel |

## Complaint Types

Primary water-establishment complaint types:

- Area or building water outage when the public supply did not arrive.
- Dirty, brown, smelly, polluted, or unsafe water from tap/public source.
- Public water pipe leak, burst pipe, valve/meter-box leak, missing cover tied to water infrastructure.
- Low pressure or intermittent supply.
- Meter, bill, subscription, transfer, cancellation, and customer-service follow-up.
- New water connection or temporary subscription request.
- Public sewage overflow when evidence points to water-establishment sewerage/wastewater network.
- Water testing request or water-quality concern.

Secondary/edge types:

- Rainwater/storm drain complaints: default municipality or MPWT by road class, unless evidence points to sewer/water network.
- Public health pollution: co-route or HITL with MOE when contamination affects rivers, groundwater, coastline, or industrial pollution.
- Emergency flood/rescue/gas/electrical risk: Civil Defense first.
- Irrigation: regional water establishment only when within its service scope and not clearly LRA/Litani infrastructure.

Not responsible:

- Private building plumbing, rooftop tanks, private pumps, private wells, internal apartment leaks.
- Roads, potholes, sidewalks, bridges, and traffic signs unless caused by a water pipe and only as co-entity.
- Electricity outages powering pumps; keep water establishment primary for citizen-facing water complaint, with EDL/MEW secondary context if source-backed.
- Municipal storm drains and local rainwater drainage unless sewer/public water network evidence exists.
- Litani/Qasimiya/Ras Al Ain irrigation assets where LRA owns/operates the project.

## Entity Details

### BMLWE / EBML

F001 legal mandate:
Official EBML pages state responsibility for potable water distribution, irrigation water, water quality monitoring, network study/implementation/investment/maintenance/renewal, reservoirs, wastewater refining plants, and wastewater collection/treatment/disposal in coordination with MEW-approved plans.

F002 taxonomy:
`water_outage`, `dirty_water`, `pipe_leak_public`, `water_pressure_low`, `meter_billing_dispute`, `new_water_connection`, `water_contamination`, `irrigation_water_issue`, `sewage_overflow_linked_to_water_network`.

F003 not responsible:
EDL electricity faults, municipal/MPWT road damage, private building plumbing, rainwater flooding handled as Civil Defense/municipal emergency, Litani irrigation assets where applicable.

F004 citizen services:
Website/app ticketing system, forms for subscription/meter/name transfer/cancellation, bill payment, department offices, call center.

F005 contacts:
Hotline `1713`; phone `+961-1-386760/+961-1-386761/+961-1-386762`; email `info@ebml.gov.lb`; head office `Beirut - Badaro - Sami Soloh Street, EBML Building`.

F006 channels:
Phone, online ticketing system, website request forms, mobile app, walk-in department offices.

F007 geographic coverage:
Beirut and Mount Lebanon; official page describes Beirut and Mount Lebanon from Madfoun/Batroun-Jbeil boundary to Al Awwali.

F008 SLA:
No official repair SLA found. Official FAQ says faults/leaks can be reported via ticketing system/app or 1713, but does not promise restoration time.

F009 emergency instructions:
For active flooding/rescue/electrical hazard, do not wait for ordinary ticket workflow; route emergency first to Civil Defense/ISF as appropriate, then BMLWE for network repair.

Sources: `SRC-BMLWE-ABOUT`, `SRC-BMLWE-CONTACT`, `SRC-BMLWE-FAQ`, `SRC-BMLWE-FORMS`, `SRC-BMLWE-TICKET`.

### NLWE / EELN

F001 legal mandate:
Official NLWE about page says it was established under Law 221 and its amendments, is under MEW supervision, and provides water services to North Lebanon. Its mission includes safe sustainable water, source protection, reduced losses, and expansion of drainage, irrigation, and sanitation service scope.

F002 taxonomy:
`water_outage`, `dirty_water`, `pipe_leak_public`, `water_pressure_low`, `meter_billing_dispute`, `new_water_connection`, `water_contamination`, `sewage_services`, `service_request`.

F003 not responsible:
Electricity, road damage, private building plumbing, private wells, Civil Defense rescue/flood emergency, LRA irrigation assets where applicable.

F004 citizen services:
Customer-service complaints, service requests/forms, subscriptions, transfer/suspend/cancel subscription, bill inquiry/payment via e-services, branch offices.

F005 contacts:
Complaint/customer-service phone `1712`; main office `+961-6-430075`; email `comms@eeln.gov.lb`; main office `Tripoli - Salahuddine Kabbara Street, Dam w Farz`.

Branch phones: Tripoli `06/430075`; Kobayat `06/350341`; Halba `06/690095`; Menieh `06/460726`; Dinniyeh `06/491146`; Batroun `06/642020`; Koura `06/651012`; Zgharta `06/660347`; Bsharri `06/672260`.

F006 channels:
Phone, online contact form, e-services bill inquiry/payment, walk-in offices.

Required complaint fields:
Subscriber name, subscription number, problem, address.

F007 geographic coverage:
North Lebanon and Akkar by CedarFix municipality map; official branch list covers North districts and Akkar branch areas.

F008 SLA:
No official repair SLA found. NLWE contact page states messages are answered within 24 hours; treat that as contact-form response expectation only, not outage restoration.

F009 emergency instructions:
For sewage entering homes, rescue/flooding, collapse, or public danger, route emergency first and keep NLWE as infrastructure owner/follow-up entity.

Sources: `SRC-NLWE-HOME`, `SRC-NLWE-ABOUT`, `SRC-NLWE-CONTACT`, `SRC-NLWE-CUSTOMER-SERVICE`, `SRC-NLWE-SERVICE-REQUESTS`, `SRC-NLWE-ESERVICES`, `SRC-NLWE-OMT`.

### SLWE

F001 legal mandate:
Official SLWE overview says it was created after Law 221 and merged prior Sidon, Nabaa Tasseh, Tyre, and Jabal Amel water interests. Its tasks include drinking-water distribution projects, wastewater collection/treatment/disposal, tariff proposals, and monitoring drinking water and wastewater quality. It explicitly notes the irrigation-water exception assigned to the Litani River Authority under Article 7.

F002 taxonomy:
`water_outage`, `dirty_water`, `pipe_leak_public`, `water_pressure_low`, `meter_billing_dispute`, `new_water_connection`, `water_contamination`, `sewage_overflow_public`, `service_request`.

F003 not responsible:
Electricity, roads, private plumbing, Civil Defense rescue/flood emergency, and Litani/Qasimiya/Ras Al Ain irrigation assets.

F004 citizen services:
Customer-service center, bill inquiry, transactions/instructions, payment collector information, district distribution offices.

F005 contacts:
Hotline `1785`.

District distribution phones: Saida `07-757000`; Zahrani `07-420206`; Jezzine `07-781725`; Nabatieh `07-530018`; Bint Jbeil `07-450006`; Marjayoun-Hasbaya `07-830016`; Tyre/Sour `07-740196`.

F006 channels:
Phone hotline, district phones, bill inquiry page, walk-in district offices. No official public email or generic repair ticket number found.

F007 geographic coverage:
South Lebanon and Nabatieh by CedarFix municipality map. Contact-office list aligns with Saida, Zahrani, Jezzine, Nabatieh, Bint Jbeil, Marjayoun-Hasbaya, and Tyre.

F008 SLA:
No official repair SLA found. Official customer-service page says faults/problems should be reported immediately via hotline 1785.

F009 emergency instructions:
For active sewage/flooding danger, route emergency first. For irrigation, keep HITL until confirming whether SLWE or LRA owns the asset.

Sources: `SRC-SLWE-HOME`, `SRC-SLWE-ABOUT`, `SRC-SLWE-LEGAL`, `SRC-SLWE-CONTACT`, `SRC-SLWE-CUSTOMER-SERVICE`, `SRC-SLWE-BILLING`, `SRC-SLWE-OMT`, `SRC-LRA-ORGANIGRAM`, `SRC-LRA-BASIN`.

### BWE

F001 legal mandate:
Official BWE about page says BWE is a public investment institution under MEW supervision, exclusively entrusted with managing drinking water, irrigation water, and wastewater collection/treatment in Bekaa and Baalbek-Hermel.

F002 taxonomy:
`water_outage`, `dirty_water`, `pipe_leak_public`, `water_pressure_low`, `meter_billing_dispute`, `new_water_connection`, `water_contamination`, `irrigation_water_issue`, `wastewater_service`, `water_testing_request`.

F003 not responsible:
Electricity, roads, private plumbing, private wells, rescue flooding, and LRA/Litani irrigation assets where applicable.

F004 citizen services:
Invoice inquiries, new subscriptions, water testing, repair/maintenance requests, contact form, branch offices, FAQ/service instructions.

F005 contacts:
Invoice inquiry `1781`; main office `08/814500`; email `info@bwe.gov.lb`; head office `Zahle Highway, Abed Deyem Building, Floors 3 & 4`.

Branch phones: Zahle `08/820236`; Baalbek `08/370335`; Stations-YOYO `08/811389`; South Bekaa/Joub Jannine `08/663414`.

F006 channels:
Phone, online contact form, walk-in offices. BWE customer-service page says invoice inquiries use 1781 and offices can handle new subscription, water testing, repair, or maintenance requests.

F007 geographic coverage:
Bekaa and Baalbek-Hermel governorates.

F008 SLA:
No official repair SLA found. BWE FAQ distinguishes cutoffs without prior notice for sudden network failure, local/general pollution, or emergency repairs, and cutoffs with prior notice for planned works, cleaning, maintenance, rationing, or subscriber-connection repair.

F009 emergency instructions:
For life-safety flooding/collapse/electrical hazards, route emergency first. For Bekaa irrigation complaints, keep HITL if Litani/LRA assets may be involved.

Sources: `SRC-BWE-ABOUT`, `SRC-BWE-HOME`, `SRC-BWE-CONTACT`, `SRC-BWE-CUSTOMER-SERVICE`, `SRC-BWE-FAQ`, `SRC-BWE-WATER-QUALITY`, `SRC-LRA-ORGANIGRAM`, `SRC-LRA-BASIN`.

## Shared HITL Rules

| Trigger | Action |
|---|---|
| Missing municipality/GPS | Ask for municipality/neighborhood; do not choose BMLWE/NLWE/SLWE/BWE blindly. |
| Private plumbing/roof tank/internal pump | Mark private/building-management unless public meter/source/network evidence exists. |
| Dirty water affecting multiple homes | Route to WE, add HITL/public-health note; co-route MOE if contamination source is environmental/industrial/river/coastal. |
| Sewage overflow in public street | WE if sewer/wastewater network evidence; municipality if local drainage/manhole ownership unclear; HITL if health or ownership ambiguity. |
| Sewage/flood entering home or rescue risk | Civil Defense first; WE/MUN/MPWT as technical follow-up. |
| Pipe leak damaging road | WE primary for pipe; MUN/MPWT secondary for road/public-space repair depending road class. |
| Pumping outage caused by EDL/fuel | WE remains citizen-facing primary; EDL/MEW secondary context if source-backed. |
| Irrigation water in Litani/Qasimiya/Ras Al Ain zone | HITL; LRA may be primary. |
| Request asks for deadline/SLA | Do not invent. Return intake channel, process stage, and any official notice only. |

## Trusted Internet Context

New structured context lives in `trusted_context.csv`.

Use it as high-trust background, not as a substitute for entity-specific intake pages:

- MEW National Water Strategy 2024-2035: policy context for water security, public-service provision, sustainable utilities, governance, water quality, digital transformation, non-revenue-water reduction, and energy-cost reduction.
- World Bank Second Greater Beirut Water Supply Project: BMLWE strategic context for Greater Beirut/Mount Lebanon service improvement, water-loss reduction, process digitalization, billing/collection, and operational management.
- World Bank Lake Qaraoun Pollution Prevention Project: Litani/Qaraoun wastewater and pollution boundary evidence.
- UNICEF WASH programme and emergency releases: trusted context for public-system constraints, pump/treatment/maintenance problems, emergency repair support, chlorine/lab support, damaged water facilities, and partner coordination with Water Establishments.
- OMT partner payment pages: BMLWE, NLWE, SLWE, and BWE water-dues settlement channels.
- EBML Google Play/App Store listings: BMLWE app supports account management, bill payment, alerts/news, water center/POS location, and ticketing; exact in-app ticket fields and reference-number behavior still require device/browser verification.

Do not infer official restoration SLAs from these institutional sources. They explain system conditions and programmes; they do not publish citizen-level repair deadlines.

## IRL Complaint Patterns

New anonymized pattern evidence lives in `irl_complaint_patterns.csv`.

Use it for realistic evals and HITL behavior:

- Long-duration public-network outages where residents received no WE water in the prior month.
- Private tanker dependence during BMLWE-area drought and rationing.
- Power-linked pumping outages in BMLWE and SLWE areas.
- Tyre/Sour conflict-damage repair and restoration scenarios.
- North Lebanon dirty-water and unanswered-maintenance-call patterns.
- Tripoli private-well cholera boundary: do not blame NLWE/public network without source ownership evidence.
- East Zahle/Beqaa low-supply and private-tank substitution.
- Public main leak causing property damage.

Privacy rule: keep this table pattern-level. Do not preserve complainant names, social handles, account numbers, exact home addresses, or phone numbers from public reports.

## Source URLs

- BMLWE about: https://ebml.gov.lb/about.php?lang=en
- BMLWE contact: https://ebml.gov.lb/contactus.php?lang=en
- BMLWE FAQ: https://ebml.gov.lb/faq.php?lang=en
- BMLWE forms: https://ebml.gov.lb/forms.php?lang=en
- BMLWE OMT payment: https://omt.com.lb/en/services/governmental/ebml
- BMLWE Google Play app: https://play.google.com/store/apps/details?hl=en_US&id=com.tedmob.ebml
- BMLWE Apple App Store app: https://apps.apple.com/lb/app/%D9%85%D8%A4%D8%B3%D8%B3%D8%A9-%D9%85%D9%8A%D8%A7%D9%87-%D8%A8%D9%8A%D8%B1%D9%88%D8%AA-%D9%88%D8%AC%D8%A8%D9%84-%D9%84%D8%A8%D9%86%D8%A7%D9%86/id1490594483
- NLWE about: https://eeln.gov.lb/en/about/
- NLWE contact: https://eeln.gov.lb/en/contact/
- NLWE customer service: https://eeln.gov.lb/en/customer-services/
- NLWE service requests/forms: https://eeln.gov.lb/en/customer-services1/
- NLWE e-services: https://eservices.eeln.gov.lb/Home1?language=en-US
- SLWE overview: https://www.slwe.gov.lb/details.php?id=4&key=153900&lang=ar
- SLWE contact: https://www.slwe.gov.lb/contact.php?lang=ar
- SLWE customer service: https://www.slwe.gov.lb/details.php?id=8&key=%D9%85%D9%82%D8%AF%D9%85%D8%A9&lang=ar
- SLWE billing: https://www.slwe.gov.lb/details.php?id=9&key=%D8%A7%D8%B3%D8%AA%D9%81%D8%B3%D8%A7%D8%B1-%D8%B9%D9%86-%D9%81%D8%A7%D8%AA%D9%88%D8%B1%D8%A9&lang=ar
- BWE about: https://bwe.gov.lb/en/about/
- BWE contact: https://bwe.gov.lb/en/contact/
- BWE customer services: https://bwe.gov.lb/en/customer-services/
- BWE FAQ: https://bwe.gov.lb/en/customer-services1/
- BWE water quality: https://bwe.gov.lb/en/waterquality/
- BWE OMT payment: https://www.omt.com.lb/en/services/governmental/bekaa-water-establishment
- MEW Directorate General of Investment: https://www.energyandwater.gov.lb/ar/details/99833/%D8%A7%D9%84%D9%85%D8%AF%D8%B1%D9%8A-%D8%A9-%D8%A7%D9%84%D8%B9%D8%A7%D9%85%D8%A9-%D8%A7%D9%84%D8%A5%D8%B3%D8%AA%D8%AB%D9%85%D8%A7%D8%B1
- MEW National Water Strategy 2024-2035: https://www.energyandwater.gov.lb/ar/details/100937/%D8%A7%D9%84%D8%A7%D8%B3%D8%AA%D8%B1%D8%A7%D8%AA%D9%8A%D8%AC%D9%8A%D8%A9-%D8%A7%D9%84%D9%88%D8%B7%D9%86%D9%8A%D8%A9-%D9%84%D9%82%D8%B7%D8%A7%D8%B9-%D8%A7%D9%84%D9%85%D9%8A%D8%A7%D9%87
- FAOLEX National Water Strategy PDF mirror: https://faolex.fao.org/docs/pdf/leb237241E.pdf
- LRA organigram: https://www.litani.gov.lb/en-us/aboutlra/organigram
- LRA basin overview: https://www.litani.gov.lb/en-us/aboutlrb
- World Bank Second Greater Beirut Water Supply Project: https://www.worldbank.org/en/news/press-release/2025/01/15/new-world-bank-program-to-improve-water-supply-and-quality-and-advance-water-sector-reforms
- World Bank Lake Qaraoun Pollution Prevention Project: https://www.worldbank.org/en/news/loans-credits/2016/07/14/lebanon-lake-qaraoun-pollution-prevention-project
- UNICEF Lebanon WASH programme: https://www.unicef.org/lebanon/water-sanitation-and-hygiene-wash-programme
- UNICEF Water Establishments empowered: https://www.unicef.org/lebanon/stories/water-establishments-lebanon-empowered
- UNICEF emergency water services support: https://www.unicef.org/lebanon/press-releases/essential-water-services-must-be-safeguarded-they-deliver-lifesaving-support
- UNICEF solar-powered water access: https://www.unicef.org/lebanon/press-releases/solar-powered-solutions-and-infrastructure-upgrades-secure-water-access-over-15
- AFD technical-assistance evaluation: https://www.afd.fr/en/resources/mid-term-evaluation-technical-assistance-program-support-reforms-water-sanitation-and
- Oxfam Water Establishments support evaluation: https://www.oxfam.org/fr/node/25194
- World Bank Lebanon RDNA: https://openknowledge.worldbank.org/entities/publication/705e868a-6275-44f6-ab55-e5e409b3c9b6
- UNHCR Lebanon Response Plan WaSH dashboard: https://data.unhcr.org/en/documents/details/122055
- LebRelief/Information International water-sector survey: https://www.pseau.org/outils/ouvrages/lebrelief_socio_economic_barriers_to_subscription_payment_and_servicing_in_the_water_sector_in_lebanon_2024.pdf
- L'Orient Today Beirut water-truck shortage report: https://today.lorientlejour.com/article/1467893/private-water-trucks-return-early-to-ease-beirut-water-shortage.html
- L'Orient Today Beirut/Mount Lebanon cutoff report: https://today.lorientlejour.com/article/1323720/running-water-cut-off-from-beirut-and-mount-lebanon.html
- L'Orient Today Sour restoration report: https://today.lorientlejour.com/article/1439699/water-supply-to-sour-resumes-announces-south-lebanon-water-establishment.html
- L'Orient Today Tripoli cholera/private-well boundary report: https://today.lorientlejour.com/article/1315491/cholera-detected-in-several-public-water-sources-in-tripoli.html
- This Is Beirut water-shortage report: https://thisisbeirut.com.lb/articles/1322989/water-shortages-plague-beirut-as-low-rainfall-compounds-woes
- IMLebanon SLWE Tyre cutoff report: https://www.imlebanon.org/2024/07/02/south-lebanon-water-establishment-18/
