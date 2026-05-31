"""
Patch bad prompts in the 4 expanded routing eval files.
Only touches the `prompt` field of specific case IDs.
All case IDs, metadata and routing expectations are left unchanged.
"""
import json, pathlib

ROOT     = pathlib.Path(__file__).parent.parent
EVAL_DIR = ROOT / "data/eval"

# ── Fixes: {file_stem: {case_id: new_prompt}} ─────────────────────────────────
# All replacements use canonical terms from data/knowledge_base/arabizi_vocabulary.json
# or match the style of the water-eval seed cases (natural Lebanese speech).

PATCHES = {
    "electricity_routing_eval_v1": {
        # "cut l kahraba" = English verb on Arabic noun, not natural Arabizi
        "ELEC-EVAL-011": "l kahraba 2at3a bi zahle aktar men 12 sa3a",
        # "الكهرباء ما في في طرابلس" = "ما في في" double preposition, reads wrong
        "ELEC-EVAL-015": "ما في كهربا في طرابلس",
        # "lal apart" = "apart" is not Lebanese Arabic; use "she22a"
        "ELEC-EVAL-038": "kahraba ma 3am teje lal she22a bass l bneye mashi bi beirut",
        # "شكوى EDL ما بيردوا" is a fragment; needs a full sentence with action
        "ELEC-EVAL-041": "EDL ma 3am tredd 3al shekwe, baddi rafe3 l amr lal wezare bi tripoli",
    },

    "telecom_routing_eval_v1": {
        # "internet cut no location given" reads like a metadata note, not a complaint
        "TEL-EVAL-040": "my internet is cut, not sure who to call",
    },

    "roads_public_works_routing_eval_v1": {
        # "jisr jisr l wati" = "bridge bridge el Wati" - place name doubled wrongly
        "RPW-EVAL-021": "fi jisr 3ando tasha22o2at 7add jisr l wati bi l be2a",
        # "ma fi ma 7ada shar7o" — "shar7" = explain; for snow clearance use "yfarrjo" or "yshiyo"
        "RPW-EVAL-030": "tari2 zahle l jbaleye masde bsabb l tel7 w l baladiye ma 3am te3mel shi",
        # "has water leak through" = awkward; rephrase to natural English
        "RPW-EVAL-043": "bridge near marjayoun has cracks and water seeping through the foundation",
    },

    "waste_environment_routing_eval_v1": {
        # "nahr el assi" = wrong; Arabizi for عاصي is "3assi"; trailing "pollution" is redundant
        "WE-EVAL-047": "nahr l 3assi malawwas bi hermel",
    },
}

# ── Apply patches ──────────────────────────────────────────────────────────────

for stem, fixes in PATCHES.items():
    path = EVAL_DIR / (stem + ".jsonl")
    cases = [json.loads(l) for l in open(path, encoding="utf-8")]

    changed = 0
    for c in cases:
        if c["id"] in fixes:
            old = c["prompt"]
            c["prompt"] = fixes[c["id"]]
            print(f"  [{c['id']}]")
            print(f"    OLD: {old}")
            print(f"    NEW: {c['prompt']}")
            changed += 1

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    expected = len(fixes)
    print(f"\n{path.name}: patched {changed}/{expected} cases\n" + "─" * 60)

print("\nAll done.")
