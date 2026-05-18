"""
Correction pass: arabizi_vocabulary.json v1.5.0 → v1.5.1

Fixes reported by native-speaker review (2026-05-18):

  1. REMOVE miye* forms — the standard Lebanese Arabizi word for water is "may".
     "miye" is not the accepted form; every miye-based token is replaced with the
     may-equivalent (most already existed from v1.4.0, so duplicates are skipped).

  2. REMOVE mat3a forms — "mat3a" doesn't correspond to a real Lebanese word.
     The correct adjective/past-participle is "2at3a" (قطعة - cut).
     Replace: "kahraba mat3a" → "kahraba 2at3a" etc.

  3. REMOVE tire2 forms — "tire2" is not Lebanese Arabizi; the word for road is
     "tari2" (already in vocab).  Remove all tire2-containing seeds.

  4. REMOVE khafer forms — "khafer" does not exist in Lebanese Arabic.
     Replace with ri7a besh3a / ri7a bish3a / ri7a mish taybe variants.

  5. REMOVE 3ain forms — for water supply context, "nab3" (spring) and
     "beer may" (water well) are the correct Lebanese words, not 3ain (عين = eye).

  6. ADD shar2ata — Lebanese slang for electric shock / electrocution.
     This is the colloquial word used in Beirut; sa32 (in HIGH_RISK_HINTS) is
     the MSA/formal form and is kept in metadata only.

  7. ADD nab3 / beer may — correct water-source tokens for WATER/no_supply.

  8. ADD ri7a besh3a variants — replace khafer bad-smell signals.

  9. ADD lissa ma rja3et forms — persistence signal for water_cut and power_outage
     using the correct lissa + ma rja3et construction.

  10. UPDATE term_metadata — deprecate wrong entries, add correct ones.
"""
from __future__ import annotations
import json
from pathlib import Path

VOCAB_PATH = Path(__file__).resolve().parents[1] / "data/knowledge_base/arabizi_vocabulary.json"

# ── Tokens to unconditionally strip from ALL issue_type_keywords lists ────────
REMOVE_TOKENS: frozenset[str] = frozenset({
    # -- miye (wrong form; use may) --
    "miye 2at3a", "miye mat3a", "miye mkat3a", "miye ma rja3et",
    "mat3a l miye", "miye lissa mat3a", "ma fi miye",
    "men 2 yom ma fi miye", "men emes ma fi miye", "miye inkata3et",
    "3 iyem bdoun miye",
    "mayye 2at3a", "mayye mat3a", "mayye ma rja3et", "ma fi mayye",
    "lissa mat3a l miye", "miye lissa mat2a3a",
    "miye wse5a", "miye bi ri7a", "miye lawante", "miye mla2wate",
    "miye bi ri7a khafer", "miye sawda", "miye bi lawn ghareeb",
    "tasarroub miye", "miye 3am tsarrab", "miye 3am titsarrab",
    "anboub 3am ysarrab miye",
    "miye 3am teje bi shwayy", "daght l miye khafif",
    "miye nazzalet ktir", "ma fi daght miye",
    "ma fi miye bil mantiqa", "miye ma 3am tousal",
    "ma 3enna miye bil bayt", "l 5azzan fadi w ma fi miye",
    "miye ma 3am teje",
    "miye l sarif 3am tifout",
    "miye dakhlet 3al bayt", "miye dakhlet la 2abi",
    "share3 ghatat bil miye", "miye ghatat l share3",
    "miye wa2fe 3al share3",
    "sayel l miye", "miye 3am tsayel", "miye sayel 3al tari2",
    "miye wa2fe 3al tari2",
    "miye 3am tit2elle3 men l ardiye", "miye 3am tirja3 men l ardiye",
    # -- mat3a (wrong form; use 2at3a / 2ata3et) --
    "kahraba mat3a", "kahraba mat3a men yom", "kahraba lissa mat3a",
    "kahrabe mat3a",
    # -- tire2 (wrong form; tari2 is correct) --
    "tire2 ta3eb", "tire2 msh mnee7", "tire2 nkassar",
    "tire2 ta3eb men l 7ufra", "tire2 ma2tou3",
    # -- khafer (doesn't exist; use ri7a besh3a variants) --
    "ri7a khafer men l zbele", "ri7a khafer men l zibele",
    "khafer men l zbele",
    "ri7a khafer w zibele mfarrishe", "zibele mfarrishe w ri7a khafer",
    # -- 3ain for water source (not Lebanese; use nab3 / beer may) --
    "3ain jfefit", "3ain msedoude", "3ain l 2arye jefit",
    "mayyet l balad 2at3et",
})

# ── Normalise for comparison ──────────────────────────────────────────────────
REMOVE_LOWER = frozenset(t.lower() for t in REMOVE_TOKENS)


def extend(lst: list, items: list[str]) -> list:
    existing = {i.lower() for i in lst}
    for item in items:
        if item.lower() not in existing:
            lst.append(item)
            existing.add(item.lower())
    return lst


def purge(lst: list) -> list:
    return [t for t in lst if t.lower() not in REMOVE_LOWER]


def main() -> None:
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    s = vocab["sectors"]

    # ── Strip all wrong tokens from every list ────────────────────────────────
    for sec in s.values():
        kwds = sec.get("issue_type_keywords", {})
        for key in kwds:
            kwds[key] = purge(kwds[key])

    # ── WATER corrections ─────────────────────────────────────────────────────
    # water_cut: add may-based 2at3a forms (may equivalents of removed miye forms)
    extend(s["WATER"]["issue_type_keywords"]["water_cut"], [
        "may 2at3a",           # short adjective form — may is cut
        "may mkat3a",          # fully-cut form
        "lissa ma rja3et l may",   # still hasn't returned — persistence signal
        "lissa 2at3a l may",
        "men 2 yom ma fi may",     # already in v1.4.0 but kept for dedup safety
    ])
    # dirty_water: may-based bad-smell forms replace miye khafer
    extend(s["WATER"]["issue_type_keywords"]["dirty_water"], [
        "may bi ri7a besh3a",
        "may bi ri7a bish3a",
        "may bi ri7a mish taybe",
        "may wse5a",          # may variant (was miye wse5a)
        "may lawanta",        # already in v1.4.0; re-add if missing after purge
        "may sawda",          # already in v1.4.0
        "may bi ri7a",        # already in v1.4.0
        "may mla2wate",       # already in v1.4.0
    ])
    # pipe_leak: may equivalents
    extend(s["WATER"]["issue_type_keywords"]["pipe_leak"], [
        "may 3am tsarrab",
        "may 3am titsarrab",
        "anboub 3am ysarrab may",
    ])
    # low_pressure: may equivalents
    extend(s["WATER"]["issue_type_keywords"]["low_pressure"], [
        "may 3am teje bi shwayy",
        "daght l may khafif",
        "may nazzalet ktir",
        "ma fi daght may",
    ])
    # no_supply: may equivalents + nab3 / beer may
    extend(s["WATER"]["issue_type_keywords"]["no_supply"], [
        "ma fi may bil mantiqa",     # v1.4.0 already had this
        "may ma 3am tousal",         # v1.4.0 already had this
        "ma 3enna may bil bayt",     # v1.4.0 already had this
        "l 5azzan fadi w ma fi may", # v1.4.0 already had this
        # nab3 / beer may — correct Lebanese terms for water source
        "nab3 jefef",
        "nab3 meksouf",
        "nab3 msedoud",
        "beer may jfef",
        "beer may meksouf",
        "l nab3 jefef w ma fi may",
        # French mixed row (water cut)
        "eau coupee",
    ])
    # sewage: may equivalent
    extend(s["WATER"]["issue_type_keywords"]["sewage_overflow"], [
        "may l sarif 3am tifout",
        "sarif 3am yetfayan 3al share3",
    ])

    # ── ELECTRICITY corrections ───────────────────────────────────────────────
    # power_outage: add 2at3a forms (replace mat3a)
    extend(s["ELECTRICITY"]["issue_type_keywords"]["power_outage"], [
        "kahraba 2at3a",
        "kahraba 2at3a men yom",
        "kahraba lissa 2at3a",
        "kahrabe 2at3a",
        "lissa ma rja3et l kahraba",  # already in v1.4.0 mostly
        "lissa 3atme",
    ])
    # exposed_wire: add shar2ata (Lebanese colloquial for electric shock)
    extend(s["ELECTRICITY"]["issue_type_keywords"]["exposed_wire"], [
        "shar2ata",
        "fi 5atar shar2ata",
        "silk kahraba w fi shar2ata",
        "7abal kahraba sa32",   # sa32 is HIGH_RISK_HINT; keep phrase form only
    ])

    # ── FLOODING corrections ─────────────────────────────────────────────────
    # road_flooded: may equivalents
    extend(s["FLOODING"]["issue_type_keywords"]["road_flooded"], [
        "share3 ghatat bil may",
        "may ghatat l share3",
        "may wa2fe 3al share3",
    ])
    # house_flooded: may equivalents (v1.4.0 already has may dakhlet 3al bayt)
    extend(s["FLOODING"]["issue_type_keywords"]["house_flooded"], [
        "may dakhlet 3al bayt",
        "may dakhlet la 2abi",
    ])
    # blocked_drain: may equivalents
    extend(s["FLOODING"]["issue_type_keywords"]["blocked_drain"], [
        "may 3am tit2elle3 men l ardiye",
        "may 3am tirja3 men l ardiye",
    ])
    # standing_water: may equivalents + sayel l may
    extend(s["FLOODING"]["issue_type_keywords"]["standing_water"], [
        "sayel l may",
        "may 3am tsayel",
        "may sayel 3al tari2",
        "may wa2fe 3al tari2",
        "may wa2fe 3al share3",
    ])

    # ── WASTE corrections ────────────────────────────────────────────────────
    # Replace khafer bad-smell phrases with ri7a besh3a variants
    extend(s["WASTE"]["issue_type_keywords"]["garbage_not_collected"], [
        "ri7a besh3a men l zbele",
        "ri7a besh3a men l zibele",
        "ri7a bish3a men l nfayat",
        "ri7a mish taybe men l zbele",
        "ri7a msh mni7a men l 2lebe",
        "ri7et zbele besh3a",
    ])
    extend(s["WASTE"]["issue_type_keywords"]["overflowing_bin"], [
        "ri7a besh3a w zibele mfarrishe",
        "zibele mfarrishe w ri7a besh3a",
    ])

    # ── term_metadata: corrections ────────────────────────────────────────────
    tm = vocab["term_metadata"]

    # -- Remove / deprecate wrong entries --
    for wrong_key in ("miye", "mat3a", "khafer", "3ain"):
        if wrong_key in tm:
            del tm[wrong_key]

    # -- Update mayye: keep as regional note (Beqaa), NOT as Beirut standard --
    if "mayye" in tm:
        tm["mayye"]["arabizi_note"] = (
            "ماية — regional spelling variant. Heard in Beqaa and South Lebanon "
            "but NOT the Beirut standard form. The Beirut standard is 'may'. "
            "Keep as a supplementary candidate only; do not use as a primary seed."
        )
        tm["mayye"]["status"] = "CANDIDATE_ONLY"

    # -- Add correct new entries --
    new_entries = {
        "shar2ata": {
            "arabizi_note": (
                "شرقطة — Lebanese colloquial word for electric shock / electrocution. "
                "More colloquial and specific than sa32 (صاعقة), which is the MSA form. "
                "shar2ata is the word Beirut residents use when describing getting shocked "
                "by a live wire. Maps to ELECTRICITY/exposed_wire. "
                "sa32 is retained in HIGH_RISK_HINTS (MSA form) but shar2ata is the "
                "primary seed for keyword lookup."
            ),
            "sector": "ELECTRICITY",
            "issue_type": "exposed_wire",
            "variant_forms": ["sa32", "sa3q"],
        },
        "nab3": {
            "arabizi_note": (
                "نبع — spring / water source. Lebanese word for a natural water spring. "
                "nab3 jefef = the spring dried up; nab3 meksouf = source exposed (broken). "
                "Use in WATER/no_supply for rural/Beqaa contexts where municipal water "
                "comes from natural springs. beer may = water well, also maps here."
            ),
            "sector": "WATER",
            "issue_type": "no_supply",
            "variant_forms": ["beer may", "nab3 may"],
        },
        "ri7a_besh3a": {
            "arabizi_note": (
                "ريحة بشعة / ريحة مش طيبة — bad/ugly/foul smell. "
                "CORRECT replacement for the erroneous 'khafer' (which does not exist "
                "in Lebanese Arabic). In WASTE context ri7a besh3a confirms garbage "
                "or sewage overflow. Variant forms: ri7a bish3a, ri7a mesh taybe, "
                "ri7a mish taybe, ri7a msh mni7a, ri7a msh taybe, ri7et zbele besh3a."
            ),
            "sector": "WASTE",
            "issue_type": "garbage_not_collected",
            "cross_sector": "WATER/sewage_overflow",
            "variant_forms": [
                "ri7a besh3a", "ri7a bish3a", "ri7a mesh taybe",
                "ri7a mish taybe", "ri7a msh mni7a",
            ],
        },
        "beer_may": {
            "arabizi_note": (
                "بئر مي — water well. Lebanese compound: beer (بئر = well) + may (مي = water). "
                "beer may jfef = the water well dried up. Maps to WATER/no_supply. "
                "Common in rural areas and older Beirut neighbourhoods."
            ),
            "sector": "WATER",
            "issue_type": "no_supply",
            "variant_forms": ["nab3"],
        },
        "2at3a": {
            "arabizi_note": (
                "قطعة — cut (adjective, feminine). The CORRECT Lebanese Arabizi adjective "
                "for 'cut off'. may 2at3a = water cut. kahraba 2at3a = power cut. "
                "REPLACES the erroneous 'mat3a' which was mistakenly added in v1.5.0. "
                "Also accepted: 2ata3et (verb past tense, already in keywords)."
            ),
            "sector": "WATER",
            "issue_type": "water_cut",
            "cross_sector": "ELECTRICITY/power_outage",
            "variant_forms": ["2ata3et", "inkata3et", "2it3et"],
        },
    }
    for key, val in new_entries.items():
        if key not in tm:
            tm[key] = val

    # Stoplist note: flag deprecated wrong terms so the candidate bank promotion
    # script can reject them automatically.
    vocab.setdefault("stoplist_notes", {})[
        "miye"
    ] = "WRONG_FORM — use may (standard Lebanese Arabizi for water)"
    vocab["stoplist_notes"][
        "mat3a"
    ] = "WRONG_FORM — use 2at3a (kahraba 2at3a) or 2ata3et"
    vocab["stoplist_notes"][
        "tire2"
    ] = "WRONG_FORM — use tari2 (standard Lebanese Arabizi for road)"
    vocab["stoplist_notes"][
        "khafer"
    ] = "NON_WORD — does not exist in Lebanese Arabic; use ri7a besh3a / ri7a mish taybe"

    # ── version + changelog ───────────────────────────────────────────────────
    vocab["version"] = "1.5.1"
    vocab["changelog"] = (
        "v1.5.1 (2026-05-18): Native-speaker correction pass. "
        "Removed incorrect forms introduced in v1.5.0: "
        "(1) miye* — wrong; standard Lebanese Arabizi word for water is 'may'; "
        "(2) mat3a — wrong; correct adjective is 2at3a (kahraba 2at3a, may 2at3a); "
        "(3) tire2 — non-existent; correct form is tari2; "
        "(4) khafer — non-existent in Lebanese Arabic; replaced with ri7a besh3a / "
        "ri7a bish3a / ri7a mish taybe variants; "
        "(5) 3ain for water source — replaced with nab3 (نبع) and beer may (بئر مي). "
        "Added: shar2ata (Lebanese colloquial for electric shock), nab3/beer may "
        "(correct water-source tokens), ri7a besh3a variants (correct bad-smell tokens), "
        "2at3a metadata entry. Wrong forms noted in stoplist_notes. "
        + vocab["changelog"]
    )

    # ── write back ────────────────────────────────────────────────────────────
    VOCAB_PATH.write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Written {VOCAB_PATH.name} v{vocab['version']}")

    total = sum(
        len(tokens)
        for sec in vocab["sectors"].values()
        for tokens in sec.get("issue_type_keywords", {}).values()
    )
    print(f"Total keyword entries: {total}")
    print(f"term_metadata entries: {len(vocab['term_metadata'])}")
    print(f"stoplist_notes entries: {len(vocab.get('stoplist_notes', {}))}")


if __name__ == "__main__":
    main()
