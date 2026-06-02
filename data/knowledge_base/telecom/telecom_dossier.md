# Telecom Dossier

Generated: 2026-06-02

## Scope

This shard covers operational routing for telecom complaints in CedarFix:

- `OGERO`: fixed-line telecom operator for landline, DSL, VDSL, fiber, public telecom cabinets, and Ogero cable damage.
- `TRA`: telecom regulator and consumer escalation path after provider non-response or for regulatory/mobile billing disputes.
- `MOBILE_OPERATOR`: category boundary for Alfa/Touch first-line mobile handling. The seeded operator channels live in `mobile_operator_channels.csv`; exact form fields, email endpoints, ticket behavior, and restoration SLAs remain open.
- `HITL`: required for private router/device issues, private ISP/satellite services, unclear provider, or missing fixed-line location/account context.

## Routing Rules

- Fixed internet, DSL, VDSL, fiber, or landline fault with location/line context: `OGERO`.
- Fixed telecom complaint without location or line/account context: `HITL`, secondary `OGERO`.
- Ogero public cable/cabinet damage: `OGERO`, HITL when exact location/public obstruction is unclear.
- Mobile coverage, 4G/5G, Alfa/Touch signal complaints: not Ogero; use the named Alfa/Touch operator-first channel and TRA/regulatory escalation only after provider handling fails or regulatory context is clear.
- Mobile billing, roaming, overcharge, or unresolved provider complaint: `TRA`.
- Private router, Wi-Fi password, single-device, home LAN: `HITL/private CPE boundary` unless Ogero line fault evidence exists.
- Private ISP/reseller/satellite service: `HITL/private provider boundary` until Ogero last-mile involvement is verified.

## Contact Summary

- Ogero customer care: `1515`.
- Ogero main phone: `+961-1-840000`.
- Ogero contact form: `https://ogero.gov.lb/contact.php`.
- TRA hotline: `1739`.
- TRA complaint page: `https://www.tra.gov.lb/Protecting-your-rights-Resolving-your-complaints`.
- Alfa customer care: `111` and `+961-3-391111`.
- Alfa official support reference: `https://www.alfa.com.lb/en/support/faq`.
- Touch customer care: `111` and `+961-3-800111`.
- Touch contact form: `https://www.touch.com.lb/autoforms/portal/touch/support/contact-us`.

## SLA Policy

Ogero fixed landline/DSL FAQ evidence includes a 3-working-day wait-before-followup signal for line fixes; do not extend it to all public telecom asset damage. Alfa/Touch restoration times are not captured. TRA evidence captures provider-first handling with a 10-day acknowledgment and 20-day escalation signal, but no TRA resolution time should be promised without source-backed wording.

## Production Notes

The runtime router now subtypes telecom text into fixed internet, landline, cable cut, cabinet damage, mobile network, regulatory billing/escalation, private CPE, and private ISP boundaries.
