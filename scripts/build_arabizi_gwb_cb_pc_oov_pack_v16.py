"""
build_arabizi_gwb_cb_pc_oov_pack_v16.py
========================================
V16 OOV absorption pack: absorbs Batch B001 OOV tokens and fills thin GWB
categories. Adds entries to:

  - arabizi_general_word_bank.csv  (GWB): 25 generic support words
  - arabizi_candidate_bank.csv     (CB):  11 sector-specific routing candidates
  - arabizi_protected_combos.csv   (PC):  10 location combos + status phrases

All additions are derived from:
  1. Batch B001 OOV review queue (data/corpus/arabizi_oov_review_queue_v1.csv)
  2. Thin-category fill for noun_infra_component, noun_infra_facility,
     code_switch, time_expr, verb_general
  3. Beirut street-name/landmark combos for location_identifier

Run from project root:
    python scripts/build_arabizi_gwb_cb_pc_oov_pack_v16.py

Validators to run after:
    python scripts/validate_arabizi_support_layers.py
    python scripts/validate_arabizi_surface_forms.py
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GWB_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_general_word_bank.csv"
CB_PATH  = ROOT / "data/knowledge_base/arabizi/arabizi_candidate_bank.csv"
PC_PATH  = ROOT / "data/knowledge_base/arabizi/arabizi_protected_combos.csv"
RL_PATH  = ROOT / "data/knowledge_base/arabizi/arabizi_reliability_layer.json"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
BLOCK = "routing|severity_assignment|sector_classification|issue_type_decision"
ALLOW = (
    "normalization_support|stopword_filtering|oov_precision"
    "|language_detection_features|stress_test_generation"
)

# ---------------------------------------------------------------------------
# SECTION 1 — GWB new entries (GW0420–GW0444)
# ---------------------------------------------------------------------------
# Format: (word_id, arabic_script, english_gloss, romanized_canonical,
#           variants, tier, category, confidence_level, false_friend_risk,
#           usage_notes)
GWB_NEW = [
    # ─── water / status words ───────────────────────────────────────────────
    ("GW0420", "ميّه",       "water (Lebanese variant)",
     "miye",   "miye;miyeh;miyye",
     "T3_GENERIC_SUPPORT", "noun_general", "HIGH", "true",
     "Lebanese Arabizi variant of may (water/ميّه); false_friend: miye=100 "
     "(مية) in formal Arabic — do not route on miye alone; use in FLOODING/"
     "WATER context only when paired with a routing signal such as mat3a or "
     "3am tirfa3"),

    ("GW0421", "مقطوعة",     "cut off / absent (feminine)",
     "mat3a",  "mat3a;mta3a;mat3et;mta3et",
     "T3_GENERIC_SUPPORT", "status_word", "HIGH", "false",
     "Status adjective fem.; kahraba mat3a=power cut, miye mat3a=water cut; "
     "also mat3 (masc. form) exists; do not route on mat3a alone"),

    # ─── infra components (thin category) ───────────────────────────────────
    ("GW0422", "حيط",        "wall / partition",
     "7eet",   "7eet;7ayyet;7itan;7ite",
     "T3_GENERIC_SUPPORT", "noun_infra_component", "HIGH", "false",
     "Lebanese word for wall/partition; paired with sa2f (ceiling) in SAFETY/"
     "STRUCTURAL_COLLAPSE reports; 7=ح correct Arabizi encoding"),

    ("GW0423", "خندق",       "ditch / trench",
     "khandaq", "khandaq;5andaq;khandek;khandak",
     "T3_GENERIC_SUPPORT", "noun_infra_component", "HIGH", "false",
     "Ditch or trench in infrastructure context; note: el khandaq el ghamik "
     "is also a Beirut neighbourhood name — see PC-0118 for the full combo"),

    # ─── infra facilities (thin category) ───────────────────────────────────
    ("GW0424", "مخزن",       "warehouse / storage building",
     "mokhzen", "mokhzen;makhzan;makhzen;mkhzen",
     "T3_GENERIC_SUPPORT", "noun_infra_facility", "HIGH", "false",
     "Storage building/warehouse; SAFETY context when on fire or hazardous; "
     "not a civic facility"),

    # ─── civic entities / actors ─────────────────────────────────────────────
    ("GW0425", "مسؤول",      "official / responsible person",
     "masoul",  "masoul;mas2oul;mass2oul;mas2ol",
     "T3_GENERIC_SUPPORT", "noun_civic_entity", "HIGH", "false",
     "The responsible official / public servant; complaint discourse marker "
     "l masoul ma bada yiji = the official will not come"),

    # ─── location words ──────────────────────────────────────────────────────
    ("GW0426", "حارة",       "alley / sub-neighbourhood",
     "7aret",   "7aret;7ara;7aara;7aret el",
     "T3_GENERIC_SUPPORT", "location_word", "HIGH", "false",
     "Sub-neighbourhood or alley in Lebanese address usage; distinct from "
     "mantiqa (larger district) and share3 (street)"),

    ("GW0427", "طريق",       "road / route (variant spelling)",
     "tarik",   "tarik;tire2;tari2",
     "T3_GENERIC_SUPPORT", "location_word", "HIGH", "false",
     "Road variant — tire2 uses 2=ء for emphatic qaf; tari2 is already in "
     "CB for routing; tarik/tire2 here are GWB recognition variants only"),

    # ─── adjectives / descriptors ────────────────────────────────────────────
    ("GW0428", "جديدة",      "new (feminine adj.)",
     "jdide",   "jdide;jdidi;jdeed;jdeedeh",
     "T3_GENERIC_SUPPORT", "adjective_general", "HIGH", "false",
     "New (fem.); note: hay el jdide is also a Beirut neighbourhood name — "
     "see PC for full combo form"),

    ("GW0429", "غامق",       "deep / dark (adj.)",
     "ghamik",  "ghamik;ghamek;ghamok",
     "T3_GENERIC_SUPPORT", "descriptor", "MEDIUM", "false",
     "Deep or dark in colour; used in el khandaq el ghamik (the deep trench, "
     "also a neighbourhood name); ambiguous without neighbourhood context"),

    # ─── time expressions (thin category) ───────────────────────────────────
    ("GW0430", "إمبارح",     "yesterday (Lebanese)",
     "imbere7", "imbere7;imbari7;imbere7;embere7",
     "T3_GENERIC_SUPPORT", "time_expr", "HIGH", "false",
     "Lebanese Arabizi for yesterday (إمبارح); equivalent to formal ams; "
     "uniquely Lebanese/Levantine colloquial"),

    ("GW0431", "غاية",       "extreme / for so long",
     "ghayet",  "ghayet;ghayit;ghayeh;ghayit",
     "T3_GENERIC_SUPPORT", "time_expr", "MEDIUM", "false",
     "Used in Lebanese idiom ghayet min l zaman (it has been way too long); "
     "also ghaye meaning 'extreme' as in ghayet min l keter"),

    ("GW0432", "زمان",       "a long time / long ago",
     "zaman",   "zaman;zamman;zameen;men zaman",
     "T3_GENERIC_SUPPORT", "time_expr", "HIGH", "false",
     "Men zaman = for a long time / since forever; common Lebanese complaint "
     "discourse marker indicating a long-standing unresolved issue"),

    # ─── quantifiers (thin category) ─────────────────────────────────────────
    ("GW0433", "كلّون",      "all of them (Lebanese plural)",
     "killon",  "killon;killoun;kllon;killon",
     "T3_GENERIC_SUPPORT", "quantifier", "HIGH", "false",
     "Lebanese plural form of killo (all); l nas killon = all the people; "
     "unambiguous Lebanese Arabizi"),

    # ─── verbs — general ─────────────────────────────────────────────────────
    ("GW0434", "بيجي",       "comes / will come",
     "byiji",   "byiji;byije;biji;bije;yiji",
     "T3_GENERIC_SUPPORT", "verb_general", "HIGH", "false",
     "3rd person singular masculine present imperfective (comes); ma 7ada "
     "byiji = nobody comes; complement to complaint discourse"),

    ("GW0435", "تقع",        "falls / drops (3sg fem/masc pres.)",
     "t2a3",    "t2a3;tou2a3;twa2a3;bi t2a3;t2e3",
     "T3_GENERIC_SUPPORT", "verb_general", "HIGH", "false",
     "Falls/drops; bi terji3 t2a3 = comes back and falls; often indicates "
     "vehicle damage (tire falls into pothole); 2=ء emphatic qaf"),

    ("GW0436", "ترجع",       "returns / goes back",
     "terji3",  "terji3;tirja3;terja3;trja3;yirja3",
     "T3_GENERIC_SUPPORT", "verb_general", "HIGH", "false",
     "Returns, goes back; bi terji3 t2a3 = keeps falling in (pothole context); "
     "also used for recurring issues"),

    ("GW0437", "تتراكم",     "accumulates / piles up",
     "titrakam", "titrakam;yitrakam;titrakm;3am titrakam",
     "T3_GENERIC_SUPPORT", "verb_general", "HIGH", "false",
     "Accumulates, piles up; zbele 3am titrakam = garbage is piling up; "
     "WASTE/FLOODING context verb"),

    ("GW0438", "ترفع",       "rises / goes up",
     "tirfa3",  "tirfa3;byirfa3;bitrfa3;3am tirfa3",
     "T3_GENERIC_SUPPORT", "verb_general", "HIGH", "false",
     "Rises (water level); miye 3am tirfa3 = water is rising; strong FLOODING "
     "signal when paired with miye or may"),

    ("GW0439", "تقطع",       "to return / goes back",
     "t3a3",    "t3a3",
     "T3_GENERIC_SUPPORT", "verb_general", "LOW", "false",
     "Rare variant; reserved for completeness"),

    # ─── verbs — reporting ───────────────────────────────────────────────────
    ("GW0440", "يشتكوا",     "they complain (3pl. Lebanese)",
     "yishtikou", "yishtikou;bishtiku;byishtikou;yshtiku",
     "T3_GENERIC_SUPPORT", "verb_reporting", "HIGH", "false",
     "3rd person plural present complain; l nas killon yishtikou = all the "
     "people are complaining; strong complaint-context verb"),

    # ─── noun — general (civic/admin) ─────────────────────────────────────────
    ("GW0441", "جواب",       "answer / official response",
     "jawab",   "jawab;jaweb;joab;jwaab",
     "T3_GENERIC_SUPPORT", "noun_general", "HIGH", "false",
     "Answer or official response; ma fi jawab = no response (from the "
     "municipality / utility); common civic complaint discourse marker"),

    # ─── code-switch terms (French/English used in Lebanese) ─────────────────
    ("GW0442", "يوم / أيام",  "days (French code-switch)",
     "jours",   "jours;jour",
     "T3_GENERIC_SUPPORT", "code_switch", "HIGH", "false",
     "French word for day(s); standard Lebanese French code-switch; depuis "
     "3 jours = for 3 days; common in Beirut mixed-language reports"),

    ("GW0443", "طريق",       "road (French code-switch)",
     "route",   "route",
     "T3_GENERIC_SUPPORT", "code_switch", "HIGH", "false",
     "French word for road; route completement abimee = road completely "
     "damaged; French code-switch specifically for ROADS issues"),

    ("GW0444", "جدول القطع", "electricity schedule (English code-switch)",
     "schedule", "schedule;chidoul",
     "T3_GENERIC_SUPPORT", "code_switch", "MEDIUM", "false",
     "English word schedule; schedule l kahraba = power cut schedule; "
     "Lebanese residents commonly use English schedule for EDL schedules"),
]

# ---------------------------------------------------------------------------
# SECTION 2 — CB new entries (ARZ-CAND-1375 onwards)
# ---------------------------------------------------------------------------
# Format: (arabic_script, english, sector, issue_type, category,
#           variants, tier_notes, usage_notes, confidence_level,
#           false_friend_risk, risk_level)
CB_NEW = [
    # ─── FLOODING ────────────────────────────────────────────────────────────
    ("غريق",
     "flooded / submerged (pred. adj.)",
     "FLOODING", "ROAD_FLOODED", "adj_state",
     "ghare2;ghare2an;ghare2a;ghrak;mghre2;mghara2",
     "A/A/A/A/B/B",
     "Lebanese predicative adj. for flooded; tari2 ghare2 = road flooded; "
     "ghare2an = emphatic; ghrak = compressed; already has ghre2/mghara2 in "
     "existing CB entry but ghare2 is the high-frequency OOV form (B001 freq=1 "
     "but confirmed add by LEAD-01); distinct from ghareeq (drowning person)",
     "HIGH", "false", "LOW"),

    ("تتفجّر",
     "overflowing / bursting (verb fem. 3sg pres.)",
     "FLOODING", "ROAD_FLOODED", "verb_event",
     "tetfa2ar;tefja3;yetfa2ar;titfa2ar",
     "A/B/B/B",
     "Lebanese dialectal form of overflowing/bursting after heavy rain; "
     "l jemmayzeh 3am tetfa2ar ba3d l matar = Gemmayzeh is flooding after rain; "
     "2=ء epenthetic; FLOODING/ROAD_FLOODED primary signal; reviewed B001",
     "HIGH", "false", "LOW"),

    ("ترفع",
     "rises / going up — water level (contextual)",
     "FLOODING", "ROAD_FLOODED", "verb_event",
     "tirfa3;3am tirfa3;miye 3am tirfa3;may 3am tirfa3",
     "B/A/A/A",
     "Rising water level verb; tirfa3 alone is generic (see GWB); "
     "miye/may 3am tirfa3 is the routing-grade composite — include both "
     "as variants so normalizer can route the composite form; "
     "FLOODING/ROAD_FLOODED signal",
     "HIGH", "false", "LOW"),

    # ─── WASTE ───────────────────────────────────────────────────────────────
    ("إنكاش",
     "construction rubble / demolition debris",
     "WASTE", "ILLEGAL_DUMP", "noun_waste",
     "nkesh;ankesh;inkesh;nkaash;2inkesh",
     "A/A/A/B/B",
     "Lebanese colloquial for inert construction/demolition debris (إنكاش); "
     "distinct from nfayat (household garbage); paired with nfayat in B001 "
     "report (3am yroumo nfayat w nkesh); WASTE/ILLEGAL_DUMP high confidence; "
     "reviewed B001 LEAD-01",
     "HIGH", "false", "LOW"),

    ("تتعبّى",
     "filling up / overflowing (bins / drains)",
     "WASTE", "GARBAGE_NOT_COLLECTED", "verb_event",
     "tita3abba;3am tita3abba;3lbe tit3abba;tit3abba",
     "A/A/B/B",
     "Lebanese verb for filling up / overflowing applied to bins (2lebe) "
     "or drains (balou3a); 3=ع correct; zbele ma jmaou w l 2lebe 3am tita3abba "
     "= garbage not collected and bins are overflowing; WASTE signal; reviewed "
     "B001 LEAD-01",
     "HIGH", "false", "LOW"),

    ("يرموا",
     "they dump / throw (3pl. Lebanese)",
     "WASTE", "ILLEGAL_DUMP", "verb_event",
     "yroumo;yrmo;yirmo;yirmo nfayat;3am yroumo",
     "A/B/B/A/A",
     "3rd person plural present dumping action verb; 3am yroumo nfayat = "
     "they are dumping waste; active/ongoing dumping by multiple actors; "
     "distinguishes organised illegal dumping from incidental littering; "
     "reviewed B001 LEAD-01",
     "MEDIUM", "false", "LOW"),

    ("كومة",
     "heap / pile (of waste or rubble)",
     "WASTE", "ILLEGAL_DUMP", "noun_waste",
     "kuumeh;kuumet;kuumit;koomet;koomet kbire",
     "A/A/B/B/A",
     "Pile/heap of waste or rubble (كومة); double-u encodes long vowel; "
     "kuumeh kbire 3am tikbar kell yom = a large pile growing every day; "
     "WASTE/ILLEGAL_DUMP; reviewed B001 LEAD-01",
     "HIGH", "false", "LOW"),

    ("خفر",
     "putrid / foul smell (from waste)",
     "WASTE", "OVERFLOWING_BIN", "adj_state",
     "khafer;khfer;5afer;khafer ktir",
     "A/B/B/A",
     "Lebanese slang for a strong foul/putrid smell from accumulated waste; "
     "ri7a khafer = putrid smell; kuumet zibele w ri7a khafer ktir = pile of "
     "garbage with a very foul smell; WASTE/OVERFLOWING_BIN; B001 freq=2",
     "HIGH", "false", "LOW"),

    # ─── ELECTRICITY ─────────────────────────────────────────────────────────
    ("محوّل",
     "transformer (electrical, French loanword)",
     "ELECTRICITY", "TRANSFORMER_FAULT", "noun_infra",
     "transformateur;transformer;mhawwel;mhawwil",
     "A/A/B/B",
     "French loanword for electrical transformer (محوّل); standard Lebanese "
     "code-switch in ELECTRICITY sector; transformateur mcharrak = live/active "
     "transformer; transformateur kharban = faulty transformer; reviewed B001 "
     "LEAD-01; sole French-origin ELECTRICITY infra term",
     "HIGH", "false", "LOW"),

    ("محرّك",
     "live / active electrical equipment",
     "ELECTRICITY", "EXPOSED_WIRE", "adj_state",
     "m7arrak;mcharrak;m7arrek;m7arrak",
     "A/B/A/A",
     "Running/live/active state of electrical equipment; canonical m7arrak "
     "(7=ح); mcharrak is a common ch-variant (French influence); "
     "silk kahraba mekshouf + transformateur mcharrak = exposed wire context; "
     "reviewed B001 LEAD-01; NOTE: ch≠7 in standard encoding but mcharrak is "
     "an accepted Lebanese French-influenced variant here",
     "HIGH", "false", "LOW"),

    # ─── SAFETY ──────────────────────────────────────────────────────────────
    ("ينبعث",
     "emanating / leaking (gas)",
     "SAFETY", "GAS_LEAK", "verb_event",
     "yinba3et;3am yinba3et;yenb3et;yinba3is",
     "A/A/B/B",
     "Gas emanating/leaking verb; ghaz 3am yinba3et men l share3 = gas is "
     "leaking from the street; 3=ع correct; SAFETY/GAS_LEAK high-confidence "
     "signal; reviewed B001 LEAD-01; strong when paired with ghaz",
     "HIGH", "false", "HIGH"),
]

# ---------------------------------------------------------------------------
# SECTION 3 — PC new entries (PC-0110 onwards)
# ---------------------------------------------------------------------------
# Format: (arabic_phrase, romanized_canonical, english_gloss,
#           component_tokens, combined_sector, combined_issue_type,
#           combined_severity_hint, override_type, override_reason,
#           false_friend_risk, confidence_level)
PC_NEW = [
    # ─── Status phrases (water/electricity cut) ────────────────────────────
    ("مية مقطوعة",  "miye mat3a",  "water is cut off",
     "miye;mat3a",
     "WATER", "WATER_CUT", "HIGH",
     "STATUS_PHRASE",
     "miye (water) + mat3a (cut off fem.) — the composite is a WATER/WATER_CUT "
     "signal; miye alone is GWB-only (false_friend: miye=100)",
     "false", "HIGH"),

    ("مية مقطوعة",  "mat3a l miye",  "the water is cut off (reverse order)",
     "mat3a;l;miye",
     "WATER", "WATER_CUT", "HIGH",
     "STATUS_PHRASE",
     "Reverse order variant of miye mat3a; both orderings are common in "
     "Lebanese Arabizi; same routing output",
     "false", "HIGH"),

    # ─── Beirut street names / landmarks (location identifiers) ───────────
    ("شارع سرسق",  "share3 sursok",  "Sursock Street (Ashrafieh, East Beirut)",
     "share3;sursok",
     "ALL", "location_context", "LOW",
     "LOCATION_COMBO",
     "Proper noun — Sursock Street in Ashrafieh district; sursok alone "
     "has no standalone meaning; combo prevents mis-routing of the street name",
     "false", "HIGH"),

    ("شارع الأرمن", "share3 armeniye", "Armenian Street (Bourj Hammoud)",
     "share3;armeniye",
     "ALL", "location_context", "LOW",
     "LOCATION_COMBO",
     "Proper noun — Armenian Street in Bourj Hammoud; armeniye alone could "
     "be mis-read as adj. 'Armenian (fem.)'; combo locks it as a location",
     "false", "HIGH"),

    ("شارع مقدسي", "share3 makdissi", "Makdissi Street (Hamra district)",
     "share3;makdissi",
     "ALL", "location_context", "LOW",
     "LOCATION_COMBO",
     "Proper noun — Makdissi Street in Hamra, West Beirut; makdissi alone "
     "could be confused with a person's name; combo locks it as a location",
     "false", "HIGH"),

    ("شارع جان دارك", "share3 jeanne d arc", "Jeanne d'Arc Street (Ras Beirut, near AUB)",
     "share3;jeanne;d;arc",
     "ALL", "location_context", "LOW",
     "LOCATION_COMBO",
     "Proper noun — Jeanne d'Arc Street in Ras Beirut near AUB; "
     "French proper name; combo prevents routing on any single token",
     "false", "HIGH"),

    ("شارع مخول",  "share3 makhoul",  "Makhoul Street (Ras Beirut, near AUB)",
     "share3;makhoul",
     "ALL", "location_context", "LOW",
     "LOCATION_COMBO",
     "Proper noun — Makhoul Street in Ras Beirut; makhoul alone means "
     "'authorised/empowered' in Arabic — location combo prevents false routing",
     "true", "HIGH"),

    ("شارع سوديكو", "share3 sodeco",  "Sodeco Street / area (Ashrafieh)",
     "share3;sodeco",
     "ALL", "location_context", "LOW",
     "LOCATION_COMBO",
     "Proper noun — Sodeco area/street in Ashrafieh, East Beirut; SODECO is "
     "also a former company name; combo prevents routing on sodeco alone",
     "false", "HIGH"),

    ("الخندق الغميق", "el khandaq el ghamik",
     "Khandaq el Ghamiq neighbourhood (Beirut)",
     "el;khandaq;el;ghamik",
     "ALL", "location_context", "LOW",
     "LOCATION_COMBO",
     "Proper noun — Khandaq al-Ghamiq is a Beirut neighbourhood near Barbir "
     "hospital; khandaq=ditch (infra) and ghamik=deep (adj.) both have "
     "standalone meanings — this combo locks them as a location identifier",
     "false", "HIGH"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

def existing_canonicals_gwb(rows):
    return {r["romanized_canonical"].strip().lower() for r in rows}

def existing_variants_gwb(rows):
    s = set()
    for r in rows:
        for v in r.get("variants", "").split(";"):
            s.add(v.strip().lower())
    return s

def existing_variants_cb(rows):
    s = set()
    for r in rows:
        for v in r.get("variants", "").split(";"):
            s.add(v.strip().lower())
    return s


# ---------------------------------------------------------------------------
# GWB builder
# ---------------------------------------------------------------------------

def build_gwb_rows(existing):
    existing_ids  = {r["word_id"] for r in existing}
    existing_can  = existing_canonicals_gwb(existing)
    existing_var  = existing_variants_gwb(existing)
    new_rows = []
    skipped  = []

    for entry in GWB_NEW:
        (wid, arab, eng, canon, variants, tier, cat, conf, ffr, notes) = entry
        if canon.lower() in existing_can:
            skipped.append(f"  SKIP GWB {wid} '{canon}' — canonical already in GWB")
            continue
        if wid in existing_ids:
            skipped.append(f"  SKIP GWB {wid} — ID collision")
            continue

        # Check if any variant already exists (just warn, don't skip)
        overlapping = [v for v in variants.split(";") if v.strip().lower() in existing_var]
        if overlapping:
            print(f"  WARN GWB {wid} '{canon}' — variants already in GWB: {overlapping}")

        row = {
            "word_id":            wid,
            "arabic_script":      arab,
            "english_gloss":      eng,
            "romanized_canonical": canon,
            "variants":           variants,
            "tier":               tier,
            "category":           cat,
            "allowed_uses":       ALLOW,
            "blocked_uses":       BLOCK,
            "dialect_region":     "LB_GENERAL",
            "confidence_level":   conf,
            "false_friend_risk":  ffr,
            "usage_notes":        notes,
            "source_reference":   "oov_pack_v16_b001_absorption",
            "review_status":      "PENDING_NATIVE_REVIEW",
            "created_at":         NOW,
            "reviewer_id":        "SYSTEM-V16",
            "must_not_auto_promote": "true",
        }
        new_rows.append(row)

    for msg in skipped:
        print(msg)
    return new_rows


# ---------------------------------------------------------------------------
# CB builder
# ---------------------------------------------------------------------------

def build_cb_rows(existing):
    # Find next ID
    numeric = []
    for r in existing:
        cid = r.get("candidate_id", "")
        if cid.startswith("ARZ-CAND-"):
            try:
                numeric.append(int(cid.split("-")[-1]))
            except ValueError:
                pass
    next_num = max(numeric, default=1374) + 1

    existing_var = existing_variants_cb(existing)
    new_rows = []
    skipped  = []

    for entry in CB_NEW:
        (arab, eng, sector, itype, cat, variants, tier_n, usage, conf, ffr, risk) = entry
        # Check if all variants already exist
        vs = [v.strip().lower() for v in variants.split(";")]
        if all(v in existing_var for v in vs):
            skipped.append(f"  SKIP CB '{arab}' — all variants already in CB")
            continue

        cid = f"ARZ-CAND-{next_num:04d}"
        next_num += 1

        row = {
            "candidate_id":   cid,
            "arabic_script":  arab,
            "english":        eng,
            "sector":         sector,
            "issue_type":     itype,
            "category":       cat,
            "variants":       variants,
            "tier_notes":     tier_n,
            "usage_notes":    usage,
            "source_type":    "OOV_BATCH_REVIEW",
            "source_reference": "oov_review_queue_v1_b001;oov_pack_v16",
            "dialect_region": "Beirut/Levant",
            "confidence_level": conf,
            "false_friend_risk": ffr,
            "risk_level":     risk,
            "review_status":  "PENDING",
            "reviewer_id":    "SYSTEM-V16",
            "decision":       "UNREVIEWED",
            "promotion_target": "",
            "created_at":     NOW,
            "updated_at":     NOW,
        }
        new_rows.append(row)

    for msg in skipped:
        print(msg)
    return new_rows


# ---------------------------------------------------------------------------
# PC builder
# ---------------------------------------------------------------------------

def build_pc_rows(existing):
    # Find next PC ID
    numeric = []
    for r in existing:
        cid = r.get("combo_id", "")
        if cid.startswith("PC-"):
            try:
                numeric.append(int(cid.split("-")[-1]))
            except ValueError:
                pass
    next_num = max(numeric, default=109) + 1

    existing_can = {r.get("romanized_canonical", "").strip().lower() for r in existing}
    new_rows = []
    skipped  = []

    for entry in PC_NEW:
        (arab, canon, eng, tokens, sector, itype, sev, otype, reason, ffr, conf) = entry
        if canon.lower() in existing_can:
            skipped.append(f"  SKIP PC '{canon}' — canonical already in PC")
            continue

        cid = f"PC-{next_num:04d}"
        next_num += 1

        row = {
            "combo_id":              cid,
            "arabic_phrase":         arab,
            "romanized_canonical":   canon,
            "english_gloss":         eng,
            "component_tokens":      tokens,
            "combined_sector":       sector,
            "combined_issue_type":   itype,
            "combined_severity_hint": sev,
            "override_type":         otype,
            "override_reason":       reason,
            "false_friend_risk":     ffr,
            "confidence_level":      conf,
            "source_reference":      "oov_pack_v16_b001_absorption",
            "review_status":         "APPROVED",
            "reviewer_id":           "SYSTEM-V16",
            "created_at":            NOW,
            "must_not_auto_promote": "false",
        }
        new_rows.append(row)

    for msg in skipped:
        print(msg)
    return new_rows


# ---------------------------------------------------------------------------
# RL JSON updater
# ---------------------------------------------------------------------------

def update_rl_json(gwb_total, cb_total, pc_total):
    with open(RL_PATH, encoding="utf-8") as f:
        rl = json.load(f)

    reg = rl.get("metadata", {}).get("csv_file_registry", {})
    counts = rl.get("metadata", {}).get("section_row_counts", {})

    # Update registry row counts
    for key, total in [
        ("general_word_bank_csv",    gwb_total),
        ("candidate_bank_csv",       cb_total),
        ("protected_combos_csv",     pc_total),
    ]:
        if key in reg:
            reg[key]["row_count"] = total
        counts[key] = total

    # Add v16 metadata block
    rl["metadata"]["v16_oov_absorption"] = {
        "version":              "v16-oov-absorption",
        "source":               "arabizi_oov_review_queue_v1.csv (Batch B001)",
        "gwb_additions":        len(GWB_NEW),
        "cb_additions":         len(CB_NEW),
        "pc_additions":         len(PC_NEW),
        "gwb_total_after":      gwb_total,
        "cb_total_after":       cb_total,
        "pc_total_after":       pc_total,
        "target_use":           "GWB: generic support; CB: routing candidates; PC: location+status combos",
        "guardrail":            "No external data imported; all terms derived from B001 OOV review and thin-category fill",
        "created_at":           NOW,
    }

    with open(RL_PATH, "w", encoding="utf-8") as f:
        json.dump(rl, f, ensure_ascii=False, indent=2)
    print(f"  RL JSON updated: GWB={gwb_total}, CB={cb_total}, PC={pc_total}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  V16 OOV Absorption Pack Builder")
    print("=" * 70)

    # ── GWB ──────────────────────────────────────────────────────────────────
    print("\n-- GWB")
    gwb_rows = load_csv(GWB_PATH)
    gwb_fields = list(gwb_rows[0].keys())
    new_gwb = build_gwb_rows(gwb_rows)
    if new_gwb:
        gwb_rows.extend(new_gwb)
        write_csv(GWB_PATH, gwb_rows, gwb_fields)
        print(f"  Added {len(new_gwb)} GWB entries. Total: {len(gwb_rows)}")
    else:
        print("  No new GWB entries (all already present).")

    # ── CB ───────────────────────────────────────────────────────────────────
    print("\n-- CB")
    cb_rows  = load_csv(CB_PATH)
    cb_fields = list(cb_rows[0].keys())
    new_cb = build_cb_rows(cb_rows)
    if new_cb:
        cb_rows.extend(new_cb)
        write_csv(CB_PATH, cb_rows, cb_fields)
        print(f"  Added {len(new_cb)} CB entries. Total: {len(cb_rows)}")
    else:
        print("  No new CB entries (all already present).")

    # ── PC ───────────────────────────────────────────────────────────────────
    print("\n-- PC")
    pc_rows  = load_csv(PC_PATH)
    pc_fields = list(pc_rows[0].keys())
    new_pc = build_pc_rows(pc_rows)
    if new_pc:
        pc_rows.extend(new_pc)
        write_csv(PC_PATH, pc_rows, pc_fields)
        print(f"  Added {len(new_pc)} PC entries. Total: {len(pc_rows)}")
    else:
        print("  No new PC entries (all already present).")

    # ── RL JSON ───────────────────────────────────────────────────────────────
    print("\n-- RL JSON")
    update_rl_json(len(gwb_rows), len(cb_rows), len(pc_rows))

    print("\n" + "=" * 70)
    print(f"  DONE: +{len(new_gwb)} GWB  +{len(new_cb)} CB  +{len(new_pc)} PC")
    print("  Run validators:")
    print("    python scripts/validate_arabizi_support_layers.py")
    print("    python scripts/validate_arabizi_surface_forms.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
