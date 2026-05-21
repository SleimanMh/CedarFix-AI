#!/usr/bin/env python3
"""
build_v12_support_layers.py

Creates two new authoritative support CSV files that materialize
the layered vocabulary governance architecture:

  1. arabizi_general_word_bank.csv
       T3/T4 generic words — context only, NEVER route, NEVER assign severity.
       Sources: arabizi_reliability_layer.json general_word_bank (111)
               + ~90 new Lebanon-native entries (generator culture, water
                 tanker culture, reporting verbs, location modifiers, etc.)

  2. arabizi_protected_combos.csv
       Phrase locks — multi-token phrases whose combined meaning is lost
       if split by naive tokenization.
       Sources: arabizi_candidate_bank.csv protected_combo category (50)
               + 25 new issue-level phrase locks with proper sector mapping

Central rule materialised here:
  - Domain vocabulary can vote on issue/routing.
  - Generic vocabulary (general_word_bank) can ONLY provide context.
  - Protected combos override naive token splitting.

Idempotent build script — safe to re-run.

Default behaviour: exits with an error if output CSV files already exist
(preventing accidental overwrites of manually-curated data).

Flags:
  --force     overwrite output files even when they already exist
  --dry-run   print what would be written without touching disk
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime


def normalize_ff(val):
    """Normalize false_friend_risk to canonical 'true'/'false' boolean strings."""
    v = str(val).strip().lower()
    if v in ('true', '1', 'yes'):  return 'true'
    if v in ('false', '0', 'no'): return 'false'
    if v == 'low':                 return 'false'
    if v in ('medium', 'high'):    return 'true'
    return 'false'  # unknown values default to safe false

BASE = r"C:\Users\HP\Desktop\Project 503N\data\knowledge_base"
ARABIZI = rf"{BASE}\arabizi"
BANK_PATH = rf"{ARABIZI}\arabizi_candidate_bank.csv"
LAYER_PATH = rf"{ARABIZI}\arabizi_reliability_layer.json"
GWB_OUT = rf"{ARABIZI}\arabizi_general_word_bank.csv"
PC_OUT  = rf"{ARABIZI}\arabizi_protected_combos.csv"

TODAY = "2026-05-19"

# ─────────────────────────────────────────────────────────────────
# SECTION 1: GENERAL WORD BANK
# ─────────────────────────────────────────────────────────────────

GWB_COLS = [
    "word_id","arabic_script","english_gloss","romanized_canonical",
    "variants","tier","category","allowed_uses","blocked_uses",
    "dialect_region","confidence_level","false_friend_risk",
    "usage_notes","source_reference","review_status","created_at",
    "reviewer_id","must_not_auto_promote"
]

BLOCKED = "routing|severity_assignment|sector_classification|issue_type_decision"
ALLOWED_CONTEXT = "context_enrichment|duration_context|evidence_support"

def gwb_row(word_id, arabic_script, english_gloss, romanized_canonical,
            variants, tier, category, allowed_uses, blocked_uses,
            dialect_region, confidence_level, false_friend_risk,
            usage_notes, source_reference, review_status, created_at,
            reviewer_id="UNASSIGNED", must_not_auto_promote="true"):
    return {
        "word_id": word_id,
        "arabic_script": arabic_script,
        "english_gloss": english_gloss,
        "romanized_canonical": romanized_canonical,
        "variants": variants,
        "tier": tier,
        "category": category,
        "allowed_uses": allowed_uses,
        "blocked_uses": blocked_uses,
        "dialect_region": dialect_region,
        "confidence_level": confidence_level,
        "false_friend_risk": normalize_ff(false_friend_risk),
        "usage_notes": usage_notes,
        "source_reference": source_reference,
        "review_status": review_status,
        "created_at": created_at,
        "reviewer_id": reviewer_id,
        "must_not_auto_promote": must_not_auto_promote,
    }


def export_gwb_from_json():
    """Export 111 entries from reliability_layer.json general_word_bank."""
    with open(LAYER_PATH, "r", encoding="utf-8") as f:
        layer = json.load(f)

    rows = []
    for e in layer.get("general_word_bank", []):
        allowed = e.get("allowed_uses", "")
        if isinstance(allowed, list):
            allowed = "|".join(allowed)
        blocked = e.get("blocked_uses", "")
        if isinstance(blocked, list):
            blocked = "|".join(blocked)
        if not blocked:
            blocked = BLOCKED
        variants = e.get("all_common_variants", "")
        if isinstance(variants, list):
            variants = ";".join(variants)
        notes = e.get("notes", "")
        row = gwb_row(
            word_id            = e.get("term_id", ""),
            arabic_script      = e.get("arabic_lemma", ""),
            english_gloss      = e.get("english_gloss", ""),
            romanized_canonical= e.get("preferred_variant", ""),
            variants           = variants,
            tier               = "T3_GENERIC_SUPPORT",
            category           = e.get("category", ""),
            allowed_uses       = allowed if allowed else ALLOWED_CONTEXT,
            blocked_uses       = blocked,
            dialect_region     = e.get("dialect_region", "Lebanese_Arabic"),
            confidence_level   = e.get("confidence_level", "MEDIUM"),
            false_friend_risk  = e.get("false_friend_risk", "FALSE"),
            usage_notes        = notes,
            source_reference   = "reliability_layer_v1_export",
            review_status      = e.get("review_status", "APPROVED"),
            created_at         = e.get("created_at_utc", TODAY),
            reviewer_id        = "SYSTEM-V11",
            must_not_auto_promote = "true",
        )
        rows.append(row)

    return rows


# ─── New Lebanon-native entries (GW0112 onwards) ───────────────
# Tier T3_GENERIC_SUPPORT = high-frequency generic words (connectors,
#   pronouns, time expressions, question words, social phrases)
# Tier T4_VARIANT_LOOKUP = technical/domain-adjacent nouns that are still
#   generic context (infrastructure facility names, civic process nouns)

NEW_GWB = [
    # ── GENERATOR CULTURE (Lebanon private diesel generator economy)
    gwb_row("GW0112","مولدة","private diesel generator","mowlide",
            "mowlide;moulide;mouled;generatir","T4_VARIANT_LOOKUP","noun_infra_facility",
            "context_enrichment|electricity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Lebanese private diesel generator; households subscribe to building generator when grid fails",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0113","جنراتور","generator (loanword)","generatir",
            "generatir;generator;jinrator","T4_VARIANT_LOOKUP","noun_infra_facility",
            "context_enrichment|electricity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "English/French loanword for diesel generator; extremely common in Lebanese dialect",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0114","اشتراك","subscription (generator/services)","ishtirake",
            "ishtirake;ishtiraak;ishtrak","T3_GENERIC_SUPPORT","noun_civic_process",
            "context_enrichment|evidence_support","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Generator subscription, also water/internet subscription; billing term",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0115","محوّل","transformer","mohawal",
            "mohawal;mouhawal;m7awwel","T4_VARIANT_LOOKUP","noun_infra_component",
            "context_enrichment|electricity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Electrical transformer; central node in generator and grid infrastructure",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0116","أمبير","ampere (subscription unit)","ampeer",
            "ampeer;amper;ampeir","T4_VARIANT_LOOKUP","noun_unit_measure",
            "context_enrichment|electricity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Ampere used as billing unit for generator subscriptions in Lebanon",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0117","كاتمان","power rationing schedule","katman",
            "katman;kat man;kateman","T4_VARIANT_LOOKUP","noun_civic_process",
            "context_enrichment|electricity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "EDL/municipality power rationing schedule; defines hours of grid electricity",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0118","تيار","current / electricity flow","tayyar",
            "tayyar;tayaar;tayer","T3_GENERIC_SUPPORT","noun_infra_facility",
            "context_enrichment|electricity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Can mean electric current or water current; context disambiguates",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0119","عدّاد","meter (electricity/water)","3addad",
            "3addad;3adad;addad","T4_VARIANT_LOOKUP","noun_infra_component",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Metering device; used for both electricity and water billing",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0120","سنترال","distribution board / switchboard","santral",
            "santral;sentral;sentrel","T4_VARIANT_LOOKUP","noun_infra_component",
            "context_enrichment|electricity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Electrical distribution board in a building; French loanword central",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── WATER TANKER CULTURE
    gwb_row("GW0121","صهريج","water cistern / tanker","sehreej",
            "sehreej;sahrej;sahrij;sehraj","T4_VARIANT_LOOKUP","noun_infra_facility",
            "context_enrichment|water_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Underground water cistern or tanker truck; central to Lebanese water supply",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0122","تنكة","water tank / tanker truck","tanke",
            "tanke;tanka;tankeh;tank","T4_VARIANT_LOOKUP","noun_infra_facility",
            "context_enrichment|water_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Private water tanker truck delivery; ubiquitous in areas with unreliable piped water",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0123","مضخة","pump","mad5a",
            "mad5a;madakha;mad5e","T4_VARIANT_LOOKUP","noun_infra_component",
            "context_enrichment|water_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Water pump; also used in flooding/drainage contexts",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0124","خزّان","water storage tank","khazzen",
            "khazzen;khazzan;khazzane","T4_VARIANT_LOOKUP","noun_infra_component",
            "context_enrichment|water_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Roof-top or underground household water storage tank",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0125","بئر","well / water source","bir",
            "bir;bi2r;biyar","T4_VARIANT_LOOKUP","noun_nature_infra",
            "context_enrichment|water_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Water well; rural areas use wells as primary water source",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0126","أنبوب","pipe / tube","anboub",
            "anboub;anabib;anbob","T4_VARIANT_LOOKUP","noun_infra_component",
            "context_enrichment|water_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Water/gas pipe; burst pipe is a common complaint context",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── REPORTING / EVIDENCE LANGUAGE
    gwb_row("GW0127","صورة","photo / image","soura",
            "soura;sora;swira","T3_GENERIC_SUPPORT","noun_evidence",
            "context_enrichment|evidence_support","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Photo as evidence; often in complaints: fi soura (there is a photo)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0128","فيديو","video","video",
            "video;vidyo;vid","T3_GENERIC_SUPPORT","noun_evidence",
            "context_enrichment|evidence_support","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Code-switch loanword; evidence of infrastructure issue",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0129","اتصلنا","we called","ittasalna",
            "ittasalna;taslna;tsalna","T3_GENERIC_SUPPORT","verb_reporting",
            "context_enrichment|reporting_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Complaint reporting verb; indicates prior contact attempt",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0130","بلّغنا","we reported / we informed","ballaghna",
            "ballaghna;balaghna;bl3na","T3_GENERIC_SUPPORT","verb_reporting",
            "context_enrichment|reporting_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Key reporting verb; used to show issue was already escalated",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0131","شكوى","formal complaint","shakwa",
            "shakwa;shekwa;shaki","T4_VARIANT_LOOKUP","noun_civic_process",
            "context_enrichment|reporting_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Formal complaint filing; indicates escalation context",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0132","صوّرنا","we photographed / we filmed","sawwarna",
            "sawwarna;sawarna;sawwart","T3_GENERIC_SUPPORT","verb_evidence",
            "context_enrichment|evidence_support","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Evidence collection verb; complaint includes media proof",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0133","شفنا","we saw / we witnessed","shufna",
            "shufna;shofna;shuft","T3_GENERIC_SUPPORT","verb_evidence",
            "context_enrichment|evidence_support","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "First-person witness verb; increases complaint credibility",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0134","كتبنا","we wrote / we messaged","katebna",
            "katebna;katabna;ktebt","T3_GENERIC_SUPPORT","verb_reporting",
            "context_enrichment|reporting_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Reporting verb; used to show written contact was made with municipality",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── LOCATION MODIFIERS (relative location phrases)
    gwb_row("GW0135","بالحارة","in the neighbourhood","bi l 7ara",
            "bi l 7ara;bel 7ara;bi 7ara","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Neighbourhood-level location; very common in complaints",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0136","عند المفرق","at the junction","3and l mafrak",
            "3and l mafrak;3end l mafrak;3and mafrak","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Road junction location; important for ROADS issue localisation",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0137","على الجسر","on the bridge","3al jisr",
            "3al jisr;3al jiser;3a l jisr","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Bridge location; common structural risk point for roads",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0138","في الزقاق","in the alley","fi l za2a2",
            "fi l za2a2;bi l za2a2;fi za2a2","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Alley/side street location; common in dense urban areas",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0139","بالضيعة","in the village","bi l day3a",
            "bi l day3a;bel day3a;bi day3a","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Village location; distinguishes urban/rural complaint context",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0140","عند المدخل","at the entrance","3and l mad5al",
            "3and l mad5al;3end l mad5al;3and mad5al","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Building or area entrance; common location for dumped waste, flooding, etc.",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0141","على الطريق العام","on the public road","3al tari2 l 3am",
            "3al tari2 l 3am;3a tari2 l 3am;3al tari3 l 3am","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Public road, as opposed to private access road; affects jurisdiction",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0142","في الحي","in the district / in the area","fi l 7ay",
            "fi l 7ay;bi l 7ay;fil 7ay","T3_GENERIC_SUPPORT","location_modifier",
            "context_enrichment|location_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "District-level location; common in urban complaint context",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── QUESTION WORDS (for complaint parsing / message classification)
    gwb_row("GW0143","وين","where","wein",
            "wein;wen;win","T3_GENERIC_SUPPORT","question_word",
            "context_enrichment|question_detection","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Where; question word indicating location inquiry or outrage",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0144","شو","what","shu",
            "shu;sho;shou","T3_GENERIC_SUPPORT","question_word",
            "context_enrichment|question_detection","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "What; very high frequency Lebanese question word",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0145","كيف","how","kif",
            "kif;keef;kyf","T3_GENERIC_SUPPORT","question_word",
            "context_enrichment|question_detection","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "How; used in outrage phrases (kif ydal hayke) and genuine questions",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0146","ليش","why","lesh",
            "lesh;lish;laysh","T3_GENERIC_SUPPORT","question_word",
            "context_enrichment|question_detection","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Why; often signals complaint frustration (lesh ma ji7da)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0147","إمتى","when","emte",
            "emte;emte2;imte","T3_GENERIC_SUPPORT","question_word",
            "context_enrichment|question_detection","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "When; signals timeline inquiry or complaint urgency",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0148","مين","who","min",
            "min;meen;mn","T3_GENERIC_SUPPORT","question_word",
            "context_enrichment|question_detection","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Who; used to identify responsible party in complaints",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0149","أديش","how much / how many","adesh",
            "adesh;adde;addesh;2adesh","T3_GENERIC_SUPPORT","question_word",
            "context_enrichment|question_detection","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "How much; used to quantify duration or frequency of issue",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── ADDITIONAL TIME EXPRESSIONS
    gwb_row("GW0150","من الصبح","since morning","men l subeh",
            "men l subeh;mn l subeh;men l sbe7","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Since morning; indicates duration of ongoing issue",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0151","بالمسا","in the evening","bil masa",
            "bil masa;bel masa;bil mase","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Evening timing; relevant for lighting, safety, and noise complaints",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0152","كل ليلة","every night","kel lele",
            "kel lele;kell lele;kel leile","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|frequency_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Every night; indicates recurring nightly issue",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0153","كل صبح","every morning","kel subeh",
            "kel subeh;kell subeh;kel sbe7","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|frequency_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Every morning; indicates recurring daily issue",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0154","هالأسبوع","this week","hal esbu3",
            "hal esbu3;hale esbo3;hal asbo3","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "This week; temporal anchoring for complaint",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0155","هالشهر","this month","hal shahr",
            "hal shahr;hale shahr","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "This month; temporal anchoring for complaint",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0156","بعد المطر","after rain","ba3d l matar",
            "ba3d l matar;ba3de matar;ba3d matar","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|weather_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "After rain; triggers flooding, road, and water complaints",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0157","الشتوية","the rainy season / this winter","l shatwiye",
            "l shatwiye;shatwiye;hal shatwiye","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|weather_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "The rainy season; context for seasonal flooding/road issues",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0158","قبل الشتا","before winter","2abel l shata",
            "2abel l shata;abel l shete;abel l shata","T3_GENERIC_SUPPORT","time_expr",
            "context_enrichment|weather_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Before winter; urgency framing for pre-winter repairs",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── ASSESSMENT / CONFIDENCE WORDS
    gwb_row("GW0159","متأكد","certain / confirmed","mita2aked",
            "mita2aked;mta2kked;mita2kked","T3_GENERIC_SUPPORT","modal",
            "context_enrichment|confidence_signal","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Certainty marker; increases confidence in complaint claim",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0160","مضمون","guaranteed / definitely","madmoun",
            "madmoun;madmun;madmon","T3_GENERIC_SUPPORT","modal",
            "context_enrichment|confidence_signal","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Certainty/guarantee; used to assert fact in complaint context",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0161","يمكن","maybe / perhaps","yimkin",
            "yimkin;ymken;yemkin","T3_GENERIC_SUPPORT","modal",
            "context_enrichment|uncertainty_signal","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Possibility marker; introduces uncertainty in claim",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0162","طبعاً","of course / naturally","taba3an",
            "taba3an;tab3an;taba3en","T3_GENERIC_SUPPORT","discourse",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Discourse marker; confirms expected outcome or obvious fact",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0163","بالنسبة لي","as far as I'm concerned","bi l nisbe li",
            "bi l nisbe li;bel nisbe li;bi nisbe","T3_GENERIC_SUPPORT","discourse",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Personal perspective marker; frames individual complaint opinion",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── LEBANESE SOCIAL / CODE-SWITCH PATTERNS
    gwb_row("GW0164","merci","thank you (French)","merci",
            "merci;mersi","T3_GENERIC_SUPPORT","code_switch",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "French code-switch; extremely common in Lebanese Arabic; STOPLIST candidate",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0165","bonjour","hello (French)","bonjour",
            "bonjour;bon jour;bonjor","T3_GENERIC_SUPPORT","code_switch",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "French greeting; very common in Lebanese messages; STOPLIST candidate",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0166","تفضّل","please / go ahead (Arabic)","tfaddal",
            "tfaddal;tfadal;tafaddal","T3_GENERIC_SUPPORT","politeness",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Politeness/invitation marker; opening phrase in formal complaints",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0167","ياللا","let's go / come on","yalla",
            "yalla;yala;yella","T3_GENERIC_SUPPORT","discourse",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Discourse filler / urgency particle; very common in WhatsApp messages",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0168","يعني","I mean / like / you know","ya3ni",
            "ya3ni;yani;ya3ne","T3_GENERIC_SUPPORT","discourse",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Filler/hedging word; very high frequency across all complaint types",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0169","هيدا","this one / this (masc)","hayda",
            "hayda;haida;heyda","T3_GENERIC_SUPPORT","pronoun",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Demonstrative pronoun masculine; pointing to specific item in complaint",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0170","هيدي","this one / this (fem)","haydi",
            "haydi;haidi;heydi","T3_GENERIC_SUPPORT","pronoun",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Demonstrative pronoun feminine; pointing to specific item in complaint",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── NUMBER WORDS (for duration quantification)
    gwb_row("GW0171","واحد","one","wa7ad",
            "wa7ad;wa7ed;wahed","T3_GENERIC_SUPPORT","number_quantity",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Number one; used in duration: wa7ad yom (one day)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0172","تنين","two","tnein",
            "tnein;tenein;tnin","T3_GENERIC_SUPPORT","number_quantity",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Number two; tnein iyam (two days), tnein esbu3 (two weeks)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0173","تلاتة","three","tlete",
            "tlete;tlata;telte","T3_GENERIC_SUPPORT","number_quantity",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Number three; common in duration phrases",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0174","خمسة","five","5amse",
            "5amse;khemse;khamse","T3_GENERIC_SUPPORT","number_quantity",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Number five; 5 iyam = 5 days, high frequency in complaints",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0175","عشرة","ten","3ashra",
            "3ashra;3ashe;3ashara","T3_GENERIC_SUPPORT","number_quantity",
            "context_enrichment|duration_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Number ten; 3ashra iyam (ten days) signals extended issue",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── CONNECTOR EXPANSION
    gwb_row("GW0176","لأنو","because","la2anno",
            "la2anno;la2ann;la2an","T3_GENERIC_SUPPORT","connector",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Causal connector; introduces reason for complaint",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0177","بدل","instead of","badal",
            "badal;badel;baddal","T3_GENERIC_SUPPORT","connector",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Contrast connector; badal yji7do (instead of coming to fix it)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0178","غير","except / other than","gheer",
            "gheer;ghir;gheyr","T3_GENERIC_SUPPORT","connector",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Exception/contrast word; also used in negation phrases",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0179","متل","like / as","metel",
            "metel;metl;mitel","T3_GENERIC_SUPPORT","connector",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Comparison particle; metel ma huwe (same as it is) — also in protected combos",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0180","عشان","for / because (Egyptian-influence)","3ashen",
            "3ashen;3shan;3ashen","T3_GENERIC_SUPPORT","connector",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Causal/purpose connector; less common than la2anno but used in Lebanese Arabic",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0181","وإلا","or else / otherwise","w illa",
            "w illa;w ella;wela","T3_GENERIC_SUPPORT","connector",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Disjunctive/conditional; used in urgency phrases (w illa shu beddo yisir)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── CIVIC / MUNICIPAL VOCABULARY
    gwb_row("GW0182","بلدية","municipality","baladiye",
            "baladiye;baladiyye;baladiyeh","T4_VARIANT_LOOKUP","noun_civic_entity",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Local municipality; the main target of infrastructure complaints in Lebanon; NEVER auto-route on this alone",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0183","محافظة","governorate","mu7afazet",
            "mu7afazet;mohafazet;mu7afaze","T4_VARIANT_LOOKUP","noun_civic_entity",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Governorate level; routes above municipality; context only",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0184","مسؤول","responsible person / official","mas2oul",
            "mas2oul;masoul;mas3oul","T3_GENERIC_SUPPORT","noun_civic_entity",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Responsible party / official; used in complaints to identify accountable person",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0185","وزارة الأشغال","Ministry of Public Works","wizaret l ashghal",
            "wizaret l ashghal;wizara l ashghal;mw", "T4_VARIANT_LOOKUP","noun_civic_entity",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Ministry responsible for roads and public works; context clue for ROADS routing",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0186","مياه لبنان","Liban Eau (water authority)","miyah lubnan",
            "miyah lubnan;liban eau;miyeh lubnan","T4_VARIANT_LOOKUP","noun_civic_entity",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Lebanese water utility authority; context clue for WATER routing",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0187","كهرباء لبنان","Electricite du Liban (EDL)","kahraba lubnan",
            "kahraba lubnan;EDL;electricite du liban","T4_VARIANT_LOOKUP","noun_civic_entity",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Lebanese national electricity utility; context clue for ELECTRICITY routing",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0188","الدفاع المدني","Civil Defence (fire/rescue)","l difa3 l madane",
            "l difa3 l madane;difa3 madane;civil defense","T4_VARIANT_LOOKUP","noun_civic_entity",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Lebanese Civil Defence; fire and rescue service; context escalation signal",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),

    # ── INFRASTRUCTURE STATUS WORDS
    gwb_row("GW0189","كارثة","disaster / catastrophe","karsa",
            "karsa;karitha;karse","T3_GENERIC_SUPPORT","intensifier",
            "context_enrichment|severity_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Hyperbole/severity intensifier; does NOT alone determine severity",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0190","وضع","situation / state","wad3",
            "wad3;wade3;wad","T3_GENERIC_SUPPORT","noun_general",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Situation descriptor; high frequency in complaints (wad3 ktir mni7/zeft)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0191","مشكلة","problem / issue","mashkle",
            "mashkle;mishkle;meshkle","T3_GENERIC_SUPPORT","noun_general",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Generic problem word; extremely high frequency; present in protected combos (nafs l mashkle)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0192","حل","solution / fix","7al",
            "7al;hal;7alle","T3_GENERIC_SUPPORT","noun_general",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Solution/fix request; ma fi 7al = no solution has been provided",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0193","إصلاح","repair / fix (formal)","isla7",
            "isla7;islah;2isla7","T3_GENERIC_SUPPORT","noun_civic_process",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Formal repair noun; used in official complaint language",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0194","صيانة","maintenance","siyane",
            "siyane;siane;syane","T3_GENERIC_SUPPORT","noun_civic_process",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Maintenance request; siyane routine maintenance vs emergency repair",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0195","تأخير","delay","ta2khir",
            "ta2khir;ta5ir;ta2kheer","T3_GENERIC_SUPPORT","noun_general",
            "context_enrichment|complaint_signal","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Delay; complaint signal that response has been slow",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0196","إهمال","negligence","i7mal",
            "i7mal;ihmal;e7mal","T3_GENERIC_SUPPORT","noun_general",
            "context_enrichment|complaint_signal","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Negligence accusation; strong complaint word; does not determine sector",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0197","تقرير","report","ta2rir",
            "ta2rir;takrir;taqrir","T3_GENERIC_SUPPORT","noun_civic_process",
            "context_enrichment|reporting_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Formal report; submission/evidence context",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0198","جواب","reply / answer","jweb",
            "jweb;jaweb;jwab","T3_GENERIC_SUPPORT","noun_general",
            "context_enrichment|complaint_signal","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Reply/answer; used in response failure context (ma fi jweb = no reply)",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0199","متابعة","follow-up","metab3e",
            "metab3e;mutaba3a;metab3e","T3_GENERIC_SUPPORT","noun_civic_process",
            "context_enrichment|reporting_context","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","HIGH","FALSE",
            "Follow-up; signal that prior complaint was filed and not acted upon",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
    gwb_row("GW0200","واجب","duty / obligation","wajib",
            "wajib;wajeb;waajib","T3_GENERIC_SUPPORT","noun_general",
            "context_enrichment","routing|severity_assignment|sector_classification",
            "Lebanese_Arabic","MEDIUM","FALSE",
            "Duty/responsibility; haida wajibkon (this is your duty) in accountability complaints",
            "V12_LEBANON_NATIVE","PENDING_NATIVE_REVIEW",TODAY),
]


# ─────────────────────────────────────────────────────────────────
# SECTION 2: PROTECTED COMBOS
# ─────────────────────────────────────────────────────────────────

PC_COLS = [
    "combo_id","arabic_phrase","romanized_canonical","english_gloss",
    "component_tokens","combined_sector","combined_issue_type","combined_severity_hint",
    "override_type","override_reason","false_friend_risk","confidence_level",
    "source_reference","review_status","reviewer_id","created_at",
    "must_not_auto_promote"
]

def pc_row(combo_id, arabic_phrase, romanized_canonical, english_gloss,
           component_tokens, combined_sector, combined_issue_type,
           combined_severity_hint, override_type, override_reason,
           false_friend_risk, confidence_level, source_reference,
           review_status, reviewer_id, created_at,
           must_not_auto_promote="true"):
    return {
        "combo_id": combo_id,
        "arabic_phrase": arabic_phrase,
        "romanized_canonical": romanized_canonical,
        "english_gloss": english_gloss,
        "component_tokens": component_tokens,
        "combined_sector": combined_sector,
        "combined_issue_type": combined_issue_type,
        "combined_severity_hint": combined_severity_hint,
        "override_type": override_type,
        "override_reason": override_reason,
        "false_friend_risk": normalize_ff(false_friend_risk),
        "confidence_level": confidence_level,
        "source_reference": source_reference,
        "review_status": review_status,
        "reviewer_id": reviewer_id,
        "created_at": created_at,
        "must_not_auto_promote": must_not_auto_promote,
    }


# Sector remapping for existing 50 bank entries
# (bank_id -> (combined_sector, combined_issue_type, combined_severity_hint, override_type))
BANK_REMAP = {
    "ARZ-CAND-1268": ("OTHER","ability_negation",      "LOW",    "NEGATION_COMBO"),
    "ARZ-CAND-1269": ("ALL",  "location_context",      "LOW",    "LOCATION_COMBO"),
    "ARZ-CAND-1270": ("ALL",  "location_context",      "LOW",    "LOCATION_COMBO"),
    "ARZ-CAND-1271": ("ALL",  "complaint_status",      "MEDIUM", "STATUS_PHRASE"),
    "ARZ-CAND-1272": ("ALL",  "complaint_status",      "MEDIUM", "STATUS_PHRASE"),
    "ARZ-CAND-1273": ("ALL",  "duplicate_signal",      "MEDIUM", "COMPOUND_NOUN"),
    "ARZ-CAND-1274": ("ALL",  "duplicate_signal",      "MEDIUM", "STATUS_PHRASE"),
    "ARZ-CAND-1275": ("ALL",  "duration_context",      "MEDIUM", "TEMPORAL_COMBO"),
    "ARZ-CAND-1276": ("ALL",  "duration_context",      "MEDIUM", "TEMPORAL_COMBO"),
    "ARZ-CAND-1277": ("ELECTRICITY","STREETLIGHT_OUT", "MEDIUM", "COMPOUND_NOUN"),
    "ARZ-CAND-1278": ("SAFETY","EXPOSED_WIRE",         "HIGH",   "COMPOUND_NOUN"),
    "ARZ-CAND-1279": ("SAFETY","emergency_service_ref","HIGH",   "COMPOUND_NOUN"),
    "ARZ-CAND-1280": ("OTHER","discourse_marker",      "LOW",    "IDIOM"),
    "ARZ-CAND-1281": ("ALL",  "evidence_combo",        "LOW",    "EVIDENCE_COMBO"),
    "ARZ-CAND-1282": ("ALL",  "evidence_combo",        "LOW",    "EVIDENCE_COMBO"),
    "ARZ-CAND-1283": ("ALL",  "evidence_combo",        "LOW",    "EVIDENCE_COMBO"),
    "ARZ-CAND-1284": ("ALL",  "frequency_context",     "MEDIUM", "TEMPORAL_COMBO"),
    "ARZ-CAND-1285": ("ALL",  "location_context",      "LOW",    "LOCATION_COMBO"),
    "ARZ-CAND-1286": ("ROADS","location_context",      "LOW",    "LOCATION_COMBO"),
    "ARZ-CAND-1287": ("ROADS","location_context",      "MEDIUM", "LOCATION_COMBO"),
    "ARZ-CAND-1288": ("ALL",  "negation_person",       "MEDIUM", "NEGATION_COMBO"),
    "ARZ-CAND-1289": ("ALL",  "negation_time",         "MEDIUM", "NEGATION_COMBO"),
    "ARZ-CAND-1290": ("OTHER","politeness_marker",     "LOW",    "IDIOM"),
    "ARZ-CAND-1291": ("ALL",  "reporting_context",     "LOW",    "COMPOUND_NOUN"),
    "ARZ-CAND-1292": ("ALL",  "reporting_combo",       "LOW",    "EVIDENCE_COMBO"),
    "ARZ-CAND-1293": ("OTHER","request_modifier",      "LOW",    "IDIOM"),
    "ARZ-CAND-1294": ("OTHER","request_softener",      "LOW",    "IDIOM"),
    "ARZ-CAND-1295": ("ALL",  "response_failure",      "HIGH",   "STATUS_PHRASE"),
    "ARZ-CAND-1296": ("ALL",  "response_failure",      "HIGH",   "NEGATION_COMBO"),
    "ARZ-CAND-1297": ("SAFETY","GENERAL_HAZARD",       "HIGH",   "RISK_COMBO"),
    "ARZ-CAND-1298": ("SAFETY","GENERAL_HAZARD",       "HIGH",   "RISK_COMBO"),
    "ARZ-CAND-1299": ("ROADS","road_location",         "LOW",    "LOCATION_COMBO"),
    "ARZ-CAND-1300": ("ALL",  "sensitive_location",    "HIGH",   "LOCATION_COMBO"),
    "ARZ-CAND-1301": ("ALL",  "status_deteriorating",  "HIGH",   "STATUS_PHRASE"),
    "ARZ-CAND-1302": ("ALL",  "status_deteriorating",  "HIGH",   "STATUS_PHRASE"),
    "ARZ-CAND-1303": ("ALL",  "status_deteriorating",  "HIGH",   "STATUS_PHRASE"),
    "ARZ-CAND-1304": ("ALL",  "status_no_improvement", "HIGH",   "STATUS_PHRASE"),
    "ARZ-CAND-1305": ("ALL",  "status_unchanged",      "MEDIUM", "STATUS_PHRASE"),
    "ARZ-CAND-1306": ("ALL",  "duration_until_now",    "HIGH",   "TEMPORAL_COMBO"),
    "ARZ-CAND-1307": ("ALL",  "duration_context",      "HIGH",   "TEMPORAL_COMBO"),
    "ARZ-CAND-1308": ("ALL",  "duration_context",      "MEDIUM", "TEMPORAL_COMBO"),
    "ARZ-CAND-1309": ("ALL",  "duration_context",      "HIGH",   "TEMPORAL_COMBO"),
    "ARZ-CAND-1310": ("ALL",  "time_context",          "MEDIUM", "TEMPORAL_COMBO"),
    "ARZ-CAND-1311": ("ALL",  "urgency_context",       "HIGH",   "URGENCY_COMBO"),
    "ARZ-CAND-1312": ("WASTE","OVERFLOWING_BIN",       "MEDIUM", "COMPOUND_NOUN"),
    "ARZ-CAND-1313": ("WASTE","ILLEGAL_DUMP",          "HIGH",   "COMPOUND_NOUN"),
    "ARZ-CAND-1314": ("WATER","LOW_PRESSURE",          "MEDIUM", "COMPOUND_NOUN"),
    "ARZ-CAND-1315": ("ALL",  "weather_context",       "MEDIUM", "TEMPORAL_COMBO"),
    "ARZ-CAND-1316": ("ALL",  "weather_context",       "MEDIUM", "TEMPORAL_COMBO"),
    "ARZ-CAND-1317": ("ALL",  "weather_context",       "MEDIUM", "TEMPORAL_COMBO"),
}

OVERRIDE_REASON_MAP = {
    "NEGATION_COMBO":  "Negation+noun — split tokens lose negation and produce false positive",
    "COMPOUND_NOUN":   "Two-token compound — each token alone is ambiguous or misleading",
    "IDIOM":           "Idiomatic phrase — literal token meaning differs from phrase meaning",
    "TEMPORAL_COMBO":  "Temporal anchor — split tokens lose the time reference entirely",
    "LOCATION_COMBO":  "Location phrase — split tokens produce false issue detection",
    "STATUS_PHRASE":   "Status description — verb+state combo loses meaning when split",
    "EVIDENCE_COMBO":  "Evidence signal — split would route on partial noun incorrectly",
    "RISK_COMBO":      "Risk phrase — danger signal only present in the full combination",
    "URGENCY_COMBO":   "Urgency phrase — urgency only conveyed by the full expression",
}

def extract_pc_from_bank():
    """Extract 50 protected_combo entries from candidate bank with sector remapping."""
    rows = list(csv.DictReader(open(BANK_PATH, encoding="utf-8-sig")))
    pc_rows = [r for r in rows if r["category"] == "protected_combo"]

    result = []
    counter = 1
    for r in pc_rows:
        bid = r["candidate_id"]
        remap = BANK_REMAP.get(bid, ("OTHER","support_context","LOW","MULTI_WORD_PHRASE"))
        combined_sector, combined_issue_type, combined_severity_hint, override_type = remap

        # Extract canonical romanization (first variant)
        raw_variants = r["variants"]
        canonical = raw_variants.split(";")[0].strip() if raw_variants else ""

        # Derive component_tokens from canonical (split on spaces, strip particles)
        tokens = [t.strip() for t in re.split(r"[\s;]+", canonical) if t.strip()]
        component_tokens = ";".join(tokens)

        override_reason = OVERRIDE_REASON_MAP.get(override_type,
                          "Multi-token phrase — naive split loses combined meaning")

        result.append(pc_row(
            combo_id           = f"PC-{counter:04d}",
            arabic_phrase      = r["arabic_script"],
            romanized_canonical= canonical,
            english_gloss      = r["english"],
            component_tokens   = component_tokens,
            combined_sector    = combined_sector,
            combined_issue_type= combined_issue_type,
            combined_severity_hint= combined_severity_hint,
            override_type      = override_type,
            override_reason    = override_reason,
            false_friend_risk  = normalize_ff(r.get("false_friend_risk", "false")),
            confidence_level   = r.get("confidence_level", "HIGH"),
            source_reference   = f"candidate_bank:{bid}",
            review_status      = "APPROVED",
            reviewer_id        = "SYSTEM-V12",
            created_at         = r.get("created_at", TODAY),
            must_not_auto_promote = "false",
        ))
        counter += 1

    return result, counter


# ─── New issue-level protected combos (PC-051 onwards) ─────────
def new_pc_rows(start_counter):
    """25 new high-value issue-level phrase locks with proper sector mapping."""
    c = start_counter
    rows = []

    def add(arabic_phrase, canonical, english_gloss, tokens,
            sector, issue_type, severity, override_type):
        nonlocal c
        reason = OVERRIDE_REASON_MAP.get(override_type,
                 "Multi-token phrase — naive split loses combined meaning")
        rows.append(pc_row(
            combo_id           = f"PC-{c:04d}",
            arabic_phrase      = arabic_phrase,
            romanized_canonical= canonical,
            english_gloss      = english_gloss,
            component_tokens   = tokens,
            combined_sector    = sector,
            combined_issue_type= issue_type,
            combined_severity_hint= severity,
            override_type      = override_type,
            override_reason    = reason,
            false_friend_risk  = "FALSE",
            confidence_level   = "HIGH",
            source_reference   = "V12_ISSUE_LEVEL_NEW",
            review_status      = "PENDING_NATIVE_REVIEW",
            reviewer_id        = "UNASSIGNED",
            created_at         = TODAY,
            must_not_auto_promote = "true",
        ))
        c += 1

    # WATER
    add("ما في ميّ",   "ma fi may",      "no water",
        "ma;fi;may",        "WATER","NO_WATER",    "CRITICAL","NEGATION_COMBO")
    add("ما في ميّ من مبارح", "ma fi may men mbere7", "no water since yesterday",
        "ma;fi;may;men;mbere7", "WATER","NO_WATER","CRITICAL","NEGATION_COMBO")
    add("ميّ عكرة",   "may 3akkure",     "dirty / turbid water",
        "may;3akkure",      "WATER","DIRTY_WATER",  "HIGH",   "COMPOUND_NOUN")
    add("ميّ صفرا",   "may asfar",       "yellow water",
        "may;asfar",        "WATER","DIRTY_WATER",  "HIGH",   "COMPOUND_NOUN")
    add("ميّ سمّة",   "may smem",        "contaminated / poisonous water",
        "may;smem",         "WATER","DIRTY_WATER",  "CRITICAL","COMPOUND_NOUN")
    add("انقطع الميّ", "n2ata3 l may",   "water got cut off",
        "n2ata3;l;may",     "WATER","NO_WATER",    "HIGH",   "STATUS_PHRASE")

    # ELECTRICITY
    add("الكهرباء انقطعت","l kahraba n2ata3et","electricity got cut",
        "l;kahraba;n2ata3et","ELECTRICITY","POWER_OUTAGE","HIGH","STATUS_PHRASE")
    add("الكهرباء ما رجعت","l kahraba ma rja3et","electricity did not come back",
        "l;kahraba;ma;rja3et","ELECTRICITY","POWER_OUTAGE","HIGH","NEGATION_COMBO")
    add("ضوء انقطع",   "daw n2ata3",      "streetlight went out",
        "daw;n2ata3",       "ELECTRICITY","STREETLIGHT_OUT","MEDIUM","STATUS_PHRASE")
    add("سلك عريان",  "selk 3aryan",     "exposed/bare wire",
        "selk;3aryan",      "SAFETY","EXPOSED_WIRE","CRITICAL","COMPOUND_NOUN")

    # SAFETY
    add("ريحة غاز",   "ri7et ghaz",      "smell of gas",
        "ri7et;ghaz",       "SAFETY","GAS_LEAK",    "CRITICAL","COMPOUND_NOUN")
    add("عمود واقع",  "3amoud waki3",    "pole fell / falling pole",
        "3amoud;waki3",     "SAFETY","STRUCTURAL_COLLAPSE","CRITICAL","STATUS_PHRASE")
    add("سقف واقع",   "se2ef waki3",     "ceiling collapsed / falling ceiling",
        "se2ef;waki3",      "SAFETY","STRUCTURAL_COLLAPSE","CRITICAL","STATUS_PHRASE")
    add("جدار خايف",  "jedar 5ayef",     "wall is dangerous / about to collapse",
        "jedar;5ayef",      "SAFETY","STRUCTURAL_RISK","HIGH","STATUS_PHRASE")

    # ROADS
    add("حفرة بالطريق","7ufra bi l tari2","pothole in the road",
        "7ufra;bi;l;tari2", "ROADS","POTHOLE",      "MEDIUM", "LOCATION_COMBO")
    add("غطا منهول مكسور","ghata man7al maksour","broken manhole cover",
        "ghata;man7al;maksour","ROADS","MANHOLE",   "HIGH",   "COMPOUND_NOUN")
    add("الطريق مسدود","l tari2 mesdoud","road is blocked",
        "l;tari2;mesdoud",  "ROADS","ROAD_BLOCKED", "HIGH",   "STATUS_PHRASE")
    add("جسر خايف",   "jisr 5ayef",      "bridge is dangerous",
        "jisr;5ayef",       "ROADS","STRUCTURAL_RISK","CRITICAL","STATUS_PHRASE")
    add("حفريات بلا إشارات","7afriyet bla isharat","excavation without warning signs",
        "7afriyet;bla;isharat","ROADS","ROAD_DIG_OPEN","HIGH","COMPOUND_NOUN")

    # WASTE
    add("زبلة عم تحترق","zbele 3am te7tere2","garbage is burning",
        "zbele;3am;te7tere2","WASTE","BURNING_WASTE","CRITICAL","STATUS_PHRASE")
    add("حريق زبلة",  "7ariq zbele",     "garbage fire",
        "7ariq;zbele",      "WASTE","BURNING_WASTE","CRITICAL","RISK_COMBO")

    # FLOODING
    add("الطريق غريق","l tari2 gheri2",  "road is flooded",
        "l;tari2;gheri2",   "FLOODING","FLOOD_ROAD",  "HIGH",   "STATUS_PHRASE")
    add("صرفة مكشوفة","sarfe mekshouf",  "open sewage drain",
        "sarfe;mekshouf",   "FLOODING","SEWAGE_OVERFLOW","HIGH","COMPOUND_NOUN")
    add("بلوعة مكسورة","balou3a makshoure","broken/open drain",
        "balou3a;makshoure","FLOODING","SEWAGE_OVERFLOW","HIGH","COMPOUND_NOUN")
    add("ميّ عم تجري بالطريق","may 3am tjri bi l tari2","water running in the street",
        "may;3am;tjri;bi;l;tari2","FLOODING","FLOOD_ROAD","HIGH","STATUS_PHRASE")

    return rows


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def write_csv(path, cols, rows, dry_run=False):
    if dry_run:
        print(f"   [dry-run] would write {len(rows)} rows → {path}")
        return len(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Build V12 Arabizi support layer CSVs."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite output files even if they already exist."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching disk."
    )
    args = parser.parse_args()

    if not args.force and not args.dry_run:
        existing = [p for p in (GWB_OUT, PC_OUT) if os.path.exists(p)]
        if existing:
            for p in existing:
                print(f"[ABORT] File already exists: {p}")
            print("Use --force to overwrite or --dry-run to preview.")
            sys.exit(1)

    print("=== Build V12 Support Layers ===\n")

    # ── General Word Bank ──────────────────────────────────────
    print("① Exporting general_word_bank from reliability_layer.json…")
    json_rows = export_gwb_from_json()
    print(f"   Exported {len(json_rows)} entries from JSON")

    print(f"② Adding {len(NEW_GWB)} new Lebanon-native entries…")
    gwb_rows = json_rows + NEW_GWB
    n_gwb = write_csv(GWB_OUT, GWB_COLS, gwb_rows, dry_run=args.dry_run)
    print(f"   Wrote {n_gwb} total rows → {GWB_OUT}\n")

    # ── Protected Combos ───────────────────────────────────────
    print("③ Extracting protected_combo entries from candidate bank…")
    bank_pc, next_counter = extract_pc_from_bank()
    print(f"   Extracted {len(bank_pc)} entries from bank (remapped sectors)")

    print(f"④ Building new issue-level phrase locks…")
    new_pc = new_pc_rows(next_counter)
    print(f"   Added {len(new_pc)} new entries")

    pc_rows = bank_pc + new_pc
    n_pc = write_csv(PC_OUT, PC_COLS, pc_rows, dry_run=args.dry_run)
    print(f"   Wrote {n_pc} total rows → {PC_OUT}\n")

    # ── Summary ───────────────────────────────────────────────
    print("─" * 60)
    print(f"arabizi_general_word_bank.csv : {n_gwb} entries")
    print(f"  • {len(json_rows)} from reliability_layer.json (all T3_GENERIC_SUPPORT)")
    print(f"  • {len(NEW_GWB)} new Lebanon-native entries (GW0112–GW{111 + len(NEW_GWB):04d})")
    print()
    print(f"arabizi_protected_combos.csv  : {n_pc} entries")
    print(f"  • {len(bank_pc)} from candidate bank (sector-remapped)")
    print(f"  • {len(new_pc)} new issue-level phrase locks")
    print()
    print("Central rule materialised:")
    print("  Generic word bank   -> context only (BLOCKED: routing|severity|sector)")
    print("  Protected combos    -> phrase locks, override naive tokenisation")
    print("-" * 60)
    action = "Dry-run complete (no files written)." if args.dry_run else "Done."
    print(action)


if __name__ == "__main__":
    main()

