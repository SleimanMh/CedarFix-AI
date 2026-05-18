"""
Expand arabizi_vocabulary.json from v1.4.0 → v1.5.0.

Gap analysis (audit date 2026-05-18):
  - Average word-level hit rate on 40 arabizi/mixed corpus rows: 48.9%
  - 17/40 rows below 50%; RPT-B001-070 at 0% (miye/mat3a fully unrecognised)

Critical gaps fixed:
  1. miye / miye 2at3a / miye mat3a    -- Beirut standard word for water (NOT may)
  2. mat3a                             -- cut/outage adjective; water AND electricity
  3. zibele                            -- vowelised form of zbele
  4. 7ufra                             -- pothole variant used in Batch 002 corpus
  5. balo3a msdoude / bala2a msdoude  -- drain spelling variants + South dialect
  6. moulid / muwalid kharban          -- generator broken (ELECTRICITY)
  7. sa32 / sa3q                       -- electrocution token (HIGH_RISK_HINT)
  8. nar / 7ari2a                      -- fire synonyms beyond nnar
  9. kahrabe                           -- documented in source_notes but absent from keywords
  10. sayel                            -- flowing water (FLOODING)
  11. khafer / ri7a khafer             -- bad smell (WASTE)
  12. darb                             -- road/path (Beqaa / South dialect)
  13. mayye                            -- water (Beqaa/rural/South variant)
  14. 3ain                             -- spring/water source (rural)
  15. tire2                            -- road (variant of tari2)
  16. ardiye                           -- floor level; miye tit2elle3 men l ardiye
  17. French loanwords in mixed rows:  -- panne / eau coupee / ordures / route
  18. wadi 3am yetfayan                -- flash flood wadi overflow (Beqaa/mountain)
"""
from __future__ import annotations
import json
from pathlib import Path

VOCAB_PATH = Path(__file__).resolve().parents[1] / "data/knowledge_base/arabizi_vocabulary.json"


def extend(lst: list, new_items: list[str]) -> list:
    """Append items not already present (case-insensitive deduplicate)."""
    existing = {i.lower() for i in lst}
    for item in new_items:
        if item.lower() not in existing:
            lst.append(item)
            existing.add(item.lower())
    return lst


def main() -> None:
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    s = vocab["sectors"]

    # ── ROADS ─────────────────────────────────────────────────────────────────
    extend(s["ROADS"]["issue_type_keywords"]["pothole"], [
        # 7ufra variant (7ofra is canonical; 7ufra is attested in Batch 002 corpus)
        "7ufra",
        "7ufra kbire",
        "7ufra bla ta7dir",
        "tire2 ta3eb men l 7ufra",
        "t2a3et l 3ajale men l 7ufra",
        # hofra panic form already present; add jorit/joret already present
        # Beqaa/South variant spelling
        "7oufra",
    ])
    extend(s["ROADS"]["issue_type_keywords"]["road_damage"], [
        # tire2 = Beirut colloquial shortening of tari2
        "tire2 ta3eb",
        "tire2 msh mnee7",
        "tire2 nkassar",
        # darb = path/lane; Beqaa & South Lebanon dialect for small road
        "darb meksour",
        "darb ma2tou3",
        "darb ta3eb",
    ])
    extend(s["ROADS"]["issue_type_keywords"]["road_blocked"], [
        "tire2 ma2tou3",
        "sekket l balad masduude",
    ])
    extend(s["ROADS"]["issue_type_keywords"]["road_collapse"], [
        "darb nkassar men ta7t",
    ])

    # ── WATER ─────────────────────────────────────────────────────────────────
    # miye is THE standard Beirut spoken-Arabic word for water; may is also used
    extend(s["WATER"]["issue_type_keywords"]["water_cut"], [
        # Beirut/colloquial form (miye)
        "miye 2at3a",
        "miye mat3a",
        "miye mkat3a",
        "miye ma rja3et",
        "mat3a l miye",
        "miye lissa mat3a",
        "ma fi miye",
        "men 2 yom ma fi miye",
        "men emes ma fi miye",
        "miye inkata3et",
        "3 iyem bdoun miye",
        # Beqaa/rural variant mayye
        "mayye 2at3a",
        "mayye mat3a",
        "mayye ma rja3et",
        "ma fi mayye",
        # lissa signals ongoing cut — strong persistence indicator
        "lissa mat3a l miye",
        "miye lissa mat2a3a",
    ])
    extend(s["WATER"]["issue_type_keywords"]["dirty_water"], [
        # miye forms of dirty-water phrases
        "miye wse5a",
        "miye bi ri7a",
        "miye lawante",
        "miye mla2wate",
        "miye bi ri7a khafer",
        "miye sawda",
        "miye bi lawn ghareeb",
        # loanword: French mixed rows
        "eau sale",
    ])
    extend(s["WATER"]["issue_type_keywords"]["pipe_leak"], [
        "tasarroub miye",
        "miye 3am tsarrab",
        "miye 3am titsarrab",
        "anboub 3am ysarrab miye",
    ])
    extend(s["WATER"]["issue_type_keywords"]["low_pressure"], [
        "miye 3am teje bi shwayy",
        "daght l miye khafif",
        "miye nazzalet ktir",
        "ma fi daght miye",
    ])
    extend(s["WATER"]["issue_type_keywords"]["no_supply"], [
        # miye forms
        "ma fi miye bil mantiqa",
        "miye ma 3am tousal",
        "ma 3enna miye bil bayt",
        "l 5azzan fadi w ma fi miye",
        "miye ma 3am teje",
        # rural/Beqaa: spring/source dried up
        "3ain jfefit",
        "3ain msedoude",
        "3ain l 2arye jefit",
        "mayyet l balad 2at3et",
        # French mixed row loanword
        "eau coupee",
        "eau coupee depuis",
    ])
    extend(s["WATER"]["issue_type_keywords"]["sewage_overflow"], [
        "miye l sarif 3am tifout",
        "sarif 3am yetfayan 3al share3",
    ])

    # ── ELECTRICITY ───────────────────────────────────────────────────────────
    extend(s["ELECTRICITY"]["issue_type_keywords"]["power_outage"], [
        # mat3a is the colloquial adjective form (kahraba mat3a = electricity cut)
        "kahraba mat3a",
        "kahraba mat3a men yom",
        "kahraba lissa mat3a",
        # kahrabe variant (documented in source_notes; now in keywords)
        "kahrabe 2at3et",
        "kahrabe mat3a",
        "kahrabe ma fi",
        # lissa signals ongoing — critical for severity
        "lissa ma rja3et l kahraba",
        "lissa 3atme",
        # French mixed row loanword
        "panne de courant",
        "panne",
        "panne depuis",
    ])
    extend(s["ELECTRICITY"]["issue_type_keywords"]["exposed_wire"], [
        # sa32 = صاعقة / صاعق = electric shock / electrocution
        # already in HIGH_RISK_HINTS; must also appear in keyword lookup
        "sa32",
        "sa3q",
        "lams kahrabe",
        "lams kahraba",
        "7abal kahraba sa32",
        "silk kahraba bi l ard w sa32",
    ])
    extend(s["ELECTRICITY"]["issue_type_keywords"]["transformer_fault"], [
        # moulid = generator; very common Lebanese informal word
        "moulid kharban",
        "moulid 3atlan",
        "moulid ma 3am yishtaghal",
        "moulid nkassar",
        # muwalid = variant spelling (rural/Beqaa)
        "muwalid kharban",
        "muwalid 3atlan",
        "muwalid ma 3am yishtaghal",
        # short forms
        "l moulid kharban",
        "l moulid 3atlan w ma fi kahraba",
    ])
    extend(s["ELECTRICITY"]["issue_type_keywords"]["voltage_fluctuation"], [
        "kahraba 3am titbadal",
        "volt 3am yitghayar",
    ])

    # ── WASTE ─────────────────────────────────────────────────────────────────
    extend(s["WASTE"]["issue_type_keywords"]["garbage_not_collected"], [
        # zibele = vowelised form of zbele; both are used
        "zibele ma jmaou",
        "zibele ma taloo",
        "ma ji 7ada yoshul zibele",
        "shirket l zibele ma 2elet",
        "men iyem w zibele ma t7arrak",
        "l 7awiye 3am tita3abba w ma fi 7ada yoshul zibele",
        # khafer / ri7a khafer = bad smell signal strongly correlated with waste
        "ri7a khafer men l zbele",
        "ri7a khafer men l zibele",
        "khafer men l zbele",
        # French loanword ordures
        "ordures pas ramassees",
        "les ordures pas ramassees",
    ])
    extend(s["WASTE"]["issue_type_keywords"]["illegal_dump"], [
        # zibele forms
        "zibele msoubet bi l ard",
        "zibele msoubet barra",
        "zibele bi l ard l 5ale",
        "shahin zbele",
        "shahin nfayat",
        "shahin zibele mhattout",
        "ramou zibele barra l 7awiye",
        "kuumeh zibele 3am tikbar",
    ])
    extend(s["WASTE"]["issue_type_keywords"]["overflowing_bin"], [
        "zibele 3am tit3abba",
        "zibele 3am titbe3 men l 2lebe",
        "zibele mfarrishe 3al sekke",
        "zibele 3am tsedd tari2",
        "kuumet zibele 3al tari2",
        "ri7a khafer w zibele mfarrishe",
        "zibele mfarrishe w ri7a khafer",
    ])
    extend(s["WASTE"]["issue_type_keywords"]["burning_waste"], [
        "ri7et 7ar2 zibele",
        "zibele 3am ti7tari2",
        "nfayat 3am ti7tari2",
        "3am yi7arkou zibele",
    ])
    extend(s["WASTE"]["issue_type_keywords"]["damaged_bin"], [
        "l 7awiye ta3be w zibele 3am tifout",
    ])

    # ── FLOODING ──────────────────────────────────────────────────────────────
    extend(s["FLOODING"]["issue_type_keywords"]["blocked_drain"], [
        # balo3a variant spellings (both balo3a/balou3a are valid; add msdoude forms)
        "balo3a msdoude",
        "balo3a msduude",
        "balo3a ma 3am tishrab",
        # ardiye = floor/ground; "miye 3am tit2elle3 men l ardiye" = water seeping up
        "miye 3am tit2elle3 men l ardiye",
        "miye 3am tirja3 men l ardiye",
        # South Lebanon drain variant: bala2a
        "bala2a msdoude",
        "bala2a ma 3am tishrab",
        # North/Tripoli: khadra = stone-lined water channel
        "khadra msduude",
        "khadra ma 3am tsarrif",
    ])
    extend(s["FLOODING"]["issue_type_keywords"]["road_flooded"], [
        "share3 ghatat bil miye",
        "miye ghatat l share3",
        "share3 ghare2 bil matar",
        "l share3 ghare2 w ma fi 7ada byemsha",
        "miye wa2fe 3al share3",
    ])
    extend(s["FLOODING"]["issue_type_keywords"]["standing_water"], [
        # sayel = flowing (water) — strong FLOODING signal
        "sayel l miye",
        "miye 3am tsayel",
        "miye sayel 3al tari2",
        "miye wa2fe 3al tari2",
        "miye wa2fe 3al share3",
    ])
    extend(s["FLOODING"]["issue_type_keywords"]["flash_flood"], [
        "sayel nzal",
        "sayel men l jabal",
        "sayel kbir men l jabal",
        # wadi overflow — Beqaa/mountain regions
        "wadi 3am yetfayan",
        "wadi ghamar",
        "wadi 3am yitfa2ar 3al tari2",
    ])
    extend(s["FLOODING"]["issue_type_keywords"]["house_flooded"], [
        "miye dakhlet 3al bayt",
        "miye dakhlet la 2abi",
    ])

    # ── SAFETY ────────────────────────────────────────────────────────────────
    extend(s["SAFETY"]["issue_type_keywords"]["fire"], [
        # nar = fire (variant of nnar; both are used; nnar is repeated-n emphasis)
        "nar",
        "nar kbire",
        "fi nar",
        "3am tit3ala nar",
        "nnar 3am tit3ala",
        # 7ari2a = fire incident (more formal Arabic term used in reports)
        "7ari2a",
        "7ari2a bi l bnayi",
        # French mixed row
        "incendie",
        "feu",
    ])
    extend(s["SAFETY"]["issue_type_keywords"]["structural_collapse"], [
        # debris-fall forms
        "7ajara nzalat",
        "hajra nzal men l jdar",
        "hajra nzalet men l bnayi",
        "shabbe bi 5atar",
        "bne bi 5atar",
        "jdar bi 5atar",
        "7eet nkassar w 7ajara nzalat",
        # derej = stairs; shabbe bi 2eshr derej = building with dangerous steps
        "shabbe bi 2eshr derej w fi 5atar",
    ])
    extend(s["SAFETY"]["issue_type_keywords"]["exposed_hazard"], [
        # sa32 also maps here (electrocution hazard on street)
        "sa32",
        "sa3q",
        "lams kahrabe",
        "5atar 3asabe",
        "5atar 3al rasif",
    ])
    extend(s["SAFETY"]["issue_type_keywords"]["gas_leak"], [
        "ri7a ghaz",
        "ghaz 3am yetfassal",
        "ghaz 2awiye",
    ])

    # ── OTHER (French loanword catch) ─────────────────────────────────────────
    extend(s["OTHER"]["issue_type_keywords"]["unclassified"], [
        "situation critique",
        "danger imminent",
        "non resolu",
    ])

    # ── term_metadata: new entries ────────────────────────────────────────────
    tm = vocab["term_metadata"]
    # Only add if key not already present
    new_metadata = {
        "miye": {
            "arabizi_note": (
                "مية — the standard Beirut/Lebanese colloquial word for water. "
                "Distinct from MSA ماء or Levantine may. "
                "miye 2at3a = water cut; miye mat3a = water cut (adjective form). "
                "CRITICAL: this is the most common water token in Beirut Arabizi reports; "
                "must appear in water_cut AND all other WATER issue types."
            ),
            "sector": "WATER",
            "issue_type": "water_cut",
            "variant_forms": ["mayye", "may", "maye"],
        },
        "mat3a": {
            "arabizi_note": (
                "مقطوعة — cut/outage (feminine adjective). "
                "miye mat3a = water cut; kahraba mat3a = power outage. "
                "Extremely common in Lebanese Arabizi; absence was the primary cause "
                "of 0% hit rate on WATER rows using this construction."
            ),
            "sector": "WATER",
            "issue_type": "water_cut",
            "cross_sector": "ELECTRICITY/power_outage",
            "variant_forms": ["mat2a3a", "mkat3a"],
        },
        "zibele": {
            "arabizi_note": (
                "زبالة — vowelised form of zbele (garbage/waste). "
                "Both forms are attested in Lebanese Arabizi; zbele is the compressed "
                "form, zibele is the fuller vowelised form. "
                "Both must appear in all WASTE issue type keywords."
            ),
            "sector": "WASTE",
            "issue_type": "garbage_not_collected",
            "variant_forms": ["zbele", "zbale", "zibalet"],
        },
        "7ufra": {
            "arabizi_note": (
                "حفرة — pothole. Variant of 7ofra / 7afra with ু-vowel. "
                "7ufra was observed in Batch 002 corpus (RPT-B001-066/067/068) "
                "but was absent from vocabulary, causing low hit rates. "
                "7ofra is canonical; 7ufra, hofra are accepted variants."
            ),
            "sector": "ROADS",
            "issue_type": "pothole",
            "variant_forms": ["7ofra", "7afra", "hofra", "jora", "joura"],
        },
        "moulid": {
            "arabizi_note": (
                "موليد / مولّد — generator (informal Lebanese). "
                "moulid kharban = generator broken; moulid 3atlan = generator down. "
                "muwalid is the rural/Beqaa variant spelling. "
                "Maps to ELECTRICITY/transformer_fault when the context is power from a generator, "
                "not grid electricity."
            ),
            "sector": "ELECTRICITY",
            "issue_type": "transformer_fault",
            "variant_forms": ["muwalid", "mouled", "generator"],
        },
        "sa32": {
            "arabizi_note": (
                "صاعق — electrocution / electric shock. "
                "sa32 is already in HIGH_RISK_HINTS (the authoritative danger list). "
                "It must ALSO appear in ELECTRICITY/exposed_wire and SAFETY/exposed_hazard "
                "so the keyword lookup confirms the sector. "
                "sa3q is an alternative Arabizi spelling of the same word."
            ),
            "sector": "ELECTRICITY",
            "issue_type": "exposed_wire",
            "cross_sector": "SAFETY/exposed_hazard",
            "variant_forms": ["sa3q", "saa2iq"],
            "high_risk_hint": True,
        },
        "nar": {
            "arabizi_note": (
                "نار — fire. Variant of the emphatic nnar (doubled-n expresses urgency). "
                "nar is standard Lebanese Arabic; nnar is the Arabizi panic/emphasis form. "
                "Both must appear in SAFETY/fire keywords. "
                "7ari2a (حريقة) is the formal term for a fire incident."
            ),
            "sector": "SAFETY",
            "issue_type": "fire",
            "variant_forms": ["nnar", "7ari2a"],
        },
        "kahrabe": {
            "arabizi_note": (
                "كهربا — variant of kahraba (electricity). "
                "Both forms are common in Lebanese; kahrabe tends to appear in "
                "certain Beirut neighbourhoods and older speakers. "
                "Documented in source_notes since v1.4.0 but was missing from actual "
                "issue_type_keywords; now added to power_outage and exposed_wire."
            ),
            "sector": "ELECTRICITY",
            "issue_type": "power_outage",
            "variant_forms": ["kahraba"],
        },
        "khafer": {
            "arabizi_note": (
                "خافر — bad/foul smell (Lebanese slang adjective). "
                "ri7a khafer = foul smell. Strong WASTE signal: "
                "garbage, sewage, and burning-waste complaints frequently include "
                "khafer or ri7a khafer as a severity amplifier. "
                "Not sector-specific alone; must co-occur with waste/sewage context."
            ),
            "sector": "WASTE",
            "issue_type": "garbage_not_collected",
            "cross_sector": "WATER/sewage_overflow",
        },
        "sayel": {
            "arabizi_note": (
                "سايل — flowing, running (Lebanese dialect present-participle). "
                "sayel l miye = the water is flowing/running (onto the street). "
                "Disambiguation: in FLOODING context means water overflow; "
                "in WATER/pipe_leak context means pipe running/leaking. "
                "Most common in standing_water and flash_flood contexts."
            ),
            "sector": "FLOODING",
            "issue_type": "standing_water",
            "cross_sector": "WATER/pipe_leak",
        },
        "mayye": {
            "arabizi_note": (
                "ماية — regional variant of may/miye (water). "
                "Common in Beqaa, South Lebanon, and rural areas. "
                "Beirut standard form is miye; Levantine formal form is may. "
                "mayye appears in rural municipal reports particularly from Zahle "
                "and Baalbek areas. All three forms (may/miye/mayye) should be "
                "accepted in WATER sector keywords."
            ),
            "sector": "WATER",
            "issue_type": "water_cut",
            "variant_forms": ["miye", "may"],
        },
        "3ain": {
            "arabizi_note": (
                "عين — spring or water source (natural). "
                "3ain jfefit = the spring dried up; 3ain msedoude = spring blocked. "
                "Rural/Beqaa/South Lebanon contexts where municipal water may come "
                "from natural springs. Maps to WATER/no_supply."
            ),
            "sector": "WATER",
            "issue_type": "no_supply",
        },
        "darb": {
            "arabizi_note": (
                "درب — path / lane / small road. Beqaa and South Lebanon dialect "
                "word for a small road or lane, equivalent to Beirut's sekke or zuqaq. "
                "darb meksour = road damaged; darb ma2tou3 = road blocked. "
                "Should be accepted in ROADS keywords alongside tari2/share3/sekke."
            ),
            "sector": "ROADS",
            "issue_type": "road_damage",
            "dialect": "Beqaa/South",
        },
        "panne": {
            "arabizi_note": (
                "French loanword: panne = breakdown/outage. "
                "panne de courant = power outage. Extremely common in Lebanese "
                "mixed-language reports (code-switching Arabic + French). "
                "Maps to ELECTRICITY/power_outage."
            ),
            "sector": "ELECTRICITY",
            "issue_type": "power_outage",
            "loanword_from": "fr",
        },
        "bala2a": {
            "arabizi_note": (
                "بالوعة — drain. South Lebanon / Bekaa dialect variant of balou3a/balo3a. "
                "bala2a msdoude = drain blocked. Phonetic shift: 3 → 2 in the final "
                "syllable. Both bala2a and balou3a should be accepted in FLOODING/blocked_drain."
            ),
            "sector": "FLOODING",
            "issue_type": "blocked_drain",
            "dialect": "South/Beqaa",
            "variant_forms": ["balou3a", "balo3a"],
        },
    }

    for key, val in new_metadata.items():
        if key not in tm:
            tm[key] = val

    # ── version + changelog ───────────────────────────────────────────────────
    vocab["version"] = "1.5.0"
    old_changelog = vocab["changelog"]
    vocab["changelog"] = (
        "v1.5.0 (2026-05-18): Comprehensive gap expansion after forensic audit of "
        "40 arabizi/mixed corpus rows (avg hit rate was 48.9%; RPT-B001-070 at 0%). "
        "Critical fixes: (1) miye/miye 2at3a/miye mat3a added to WATER — Beirut "
        "standard word for water was completely absent; (2) mat3a adjective form "
        "added to WATER+ELECTRICITY; (3) zibele vowelised form added to all WASTE "
        "issue types; (4) 7ufra added to ROADS/pothole; (5) balo3a msdoude + "
        "bala2a variants added to FLOODING/blocked_drain; (6) moulid/muwalid kharban "
        "added to ELECTRICITY/transformer_fault; (7) sa32/sa3q added to "
        "ELECTRICITY/exposed_wire + SAFETY/exposed_hazard (sa32 was in HIGH_RISK_HINTS "
        "but absent from keyword lookup); (8) nar/7ari2a added to SAFETY/fire; "
        "(9) kahrabe forms added to ELECTRICITY/power_outage; (10) khafer/ri7a khafer "
        "added to WASTE; (11) sayel added to FLOODING; (12) regional coverage: "
        "mayye/3ain/darb (Beqaa/South), bala2a (South drain), wadi yetfayan (Beqaa "
        "flash-flood), khadra (Tripoli water channel); (13) French loanwords for mixed "
        "rows: panne, eau coupee, ordures. 14 new term_metadata entries. "
        "kasaret remains DEFERRED_BATCH_002 (3-example threshold not yet met). "
        + old_changelog
    )

    # ── source_notes: update water note ──────────────────────────────────────
    vocab["source_notes"]["may_water"] = (
        "Lebanese/Levantine water has three common Arabizi forms: "
        "(1) may/maye — Levantine formal/semi-formal; "
        "(2) miye — Beirut standard colloquial (most frequent in Beirut reports); "
        "(3) mayye — Beqaa/South/rural variant. "
        "All three forms must be covered in WATER sector keywords. "
        "v1.4.0 had only 'may' forms; v1.5.0 adds miye and mayye throughout."
    )
    vocab["source_notes"]["kahrabe_variant"] = (
        "kahraba/kahrabe are both attested Lebanese Arabic forms for electricity. "
        "v1.4.0 documented this in source_notes but failed to include kahrabe in "
        "actual issue_type_keywords. v1.5.0 adds kahrabe forms to ELECTRICITY keywords."
    )
    vocab["source_notes"]["dialect_coverage"] = (
        "v1.5.0 adds initial coverage for Beqaa/South/North dialects: "
        "darb (path/road — Beqaa/South), mayye (water — Beqaa/rural), "
        "3ain (spring/water source — rural), bala2a (drain — South Lebanon), "
        "wadi (watercourse — mountain/Beqaa flash-flood context), "
        "khadra (water channel — Tripoli/North). "
        "Primary focus remains Beirut; regional forms are supplementary."
    )

    # ── write back ────────────────────────────────────────────────────────────
    VOCAB_PATH.write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Written {VOCAB_PATH.name} v{vocab['version']}")

    # Print summary
    total = sum(
        len(tokens)
        for sec in vocab["sectors"].values()
        for tokens in sec.get("issue_type_keywords", {}).values()
    )
    print(f"Total keyword entries: {total}")
    print(f"term_metadata entries: {len(vocab['term_metadata'])}")


if __name__ == "__main__":
    main()
