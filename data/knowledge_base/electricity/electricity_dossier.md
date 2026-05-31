# Electricity Establishments Dossier

Generated: 2026-05-31

## Scope

This shard covers operational routing for electricity complaints in CedarFix:

- `EDL`: national public grid operator outside the Zahle concession exception.
- `EDZ`: private concession utility for Zahle and surrounding regions.
- `CD`: emergency first responder for electrical fires, sparking public wires, electrocution risk, and rescue.
- `MUN`: local streetlight/public-lighting fixture complaints when no public electrical hazard is present.
- `MEW`: policy or unresolved escalation layer, not first-line field dispatch.

## Routing Rules

- Ordinary grid outage outside Zahle: `EDL`.
- Confirmed Zahle/EDZ concession complaint: `EDZ`.
- Missing location: `HITL`, because EDL versus EDZ depends on location.
- Streetlight out without visible hazard: `MUN`.
- Sparking wire, exposed wire, transformer fire, or electrical box fire: `CD` first for scene safety plus `EDL` or `EDZ` by location.
- Private generator or subscription generator dispute: `HITL`, not EDL by default.
- Internal building wiring or breaker issue: `HITL/private-property boundary`, not public-utility dispatch unless public danger exists.

## Contact Summary

- EDL: `1444` in the main entity catalog; direct current form fields still need official extraction.
- EDZ: complaint form requires `meter_serial_number` and `subscription_number`.
- Civil Defense: `125` emergency line verified on the official page.
- MEW: `01/565040-1-2`, `minister@energyandwater.gov.lb` for ministry contact; not field dispatch.

## SLA Policy

No official generic restoration SLA was captured for EDL or EDZ. The product should not promise repair or restoration times. Emergency response can instruct the user to call `125` for immediate public danger.

## Production Notes

The runtime router should subtype electricity text into outage, exposed wire, sparking box, streetlight, transformer, meter/bill, and private generator before selecting the entity. Location-sensitive EDZ routing stays mandatory.