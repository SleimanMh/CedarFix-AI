# Telecom Dossier

Generated: 2026-05-31

## Scope

This shard covers operational routing for telecom complaints in CedarFix:

- `OGERO`: fixed-line telecom operator for landline, DSL, VDSL, fiber, public telecom cabinets, and Ogero cable damage.
- `TRA`: telecom regulator and consumer escalation path after provider non-response or for regulatory/mobile billing disputes.
- `MOBILE_OPERATOR`: placeholder boundary for Alfa/Touch first-line mobile handling until operator-specific entities/channels are modeled.
- `HITL`: required for private router/device issues, private ISP/satellite services, unclear provider, or missing fixed-line location/account context.

## Routing Rules

- Fixed internet, DSL, VDSL, fiber, or landline fault with location/line context: `OGERO`.
- Fixed telecom complaint without location or line/account context: `HITL`, secondary `OGERO`.
- Ogero public cable/cabinet damage: `OGERO`, HITL when exact location/public obstruction is unclear.
- Mobile coverage, 4G/5G, Alfa/Touch signal complaints: not Ogero; use operator-first boundary and TRA/regulatory path.
- Mobile billing, roaming, overcharge, or unresolved provider complaint: `TRA`.
- Private router, Wi-Fi password, single-device, home LAN: `HITL/private CPE boundary` unless Ogero line fault evidence exists.
- Private ISP/reseller/satellite service: `HITL/private provider boundary` until Ogero last-mile involvement is verified.

## Contact Summary

- Ogero customer care: `1515`.
- Ogero main phone: `+961-1-840000`.
- Ogero contact form: `https://ogero.gov.lb/contact.php`.
- TRA hotline: `1739`.
- TRA complaint page: `https://www.tra.gov.lb/Filing-complaint-with-TRA`.

## SLA Policy

No generic Ogero repair/restoration SLA is captured in the verified sources. Do not promise repair times. TRA is an escalation channel after provider failure or missed deadlines; do not promise regulator resolution times without source-backed wording.

## Production Notes

The runtime router now subtypes telecom text into fixed internet, landline, cable cut, cabinet damage, mobile network, regulatory billing/escalation, private CPE, and private ISP boundaries.