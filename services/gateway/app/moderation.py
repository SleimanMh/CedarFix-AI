"""
IEP-0 â€” Moderation Gate
========================
Three-layer content moderation applied BEFORE the main pipeline.

Layer 1: Fast heuristics (< 1ms, always runs)
  - Text too short / too long
  - All-caps / excessive punctuation
  - Exact-duplicate hash check
  - Keyword blocklist (hate, explicit)

Layer 2: LLM text moderation (async, only when Layer 1 flags)
  - Qwen2.5-3B: returns spam / abusive / political classification

Layer 3: VLM image moderation (async, only when image present AND flagged)
  - Qwen2.5-VL: harmful image detection

Decision:
  PASS   â†’ proceed to pipeline normally
  FLAG   â†’ proceed + add to human review queue
  REJECT â†’ block, audit-log, return 400

Key policy rules (from spec):
  - Political content â†’ FLAG not REJECT
  - AI-generated image â†’ weak signal, never hard-reject alone
  - Spam / hate / explicit â†’ REJECT
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Optional, List

from sqlalchemy import text

from cedarfix_shared.llm_audit import llm_audit_context
from cedarfix_shared.schemas import ModerationDecisionEnum, ModerationResult
from cedarfix_shared.storage import read_image_bytes

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODERATION_ENABLED: bool = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "cedarfix")
QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "none")
LLM_THRESHOLD: float = float(os.getenv("MODERATION_LLM_THRESHOLD", "0.75"))

# ---------------------------------------------------------------------------
# Layer 1 â€” Heuristics
# ---------------------------------------------------------------------------

_MIN_TEXT_LEN = 8       # characters
_MAX_TEXT_LEN = 4000    # characters
_CAPS_RATIO_THRESHOLD = 0.75  # fraction of alpha chars that are uppercase

# Keyword blocklists (Arabic + English)
_HATE_KEYWORDS: set[str] = {
    # English hate/explicit
    "kill", "bomb", "terrorist", "fuck", "shit", "bitch", "whore",
    # Arabic hate
    "Ø§Ù‚ØªÙ„", "Ø§Ù†ÙØ¬Ø§Ø±", "Ø¥Ø±Ù‡Ø§Ø¨ÙŠ", "Ù„Ø¹Ù†Ø©",
}
_SPAM_PATTERNS = [
    re.compile(r"(.)\1{6,}"),                # repeated characters: "aaaaaaa"
    re.compile(r"https?://\S+"),             # URLs (unusual in complaint text)
    re.compile(r"\b(buy now|click here|free offer|prize|winner)\b", re.I),
    re.compile(r"[!?]{4,}"),                 # excessive punctuation: "!!!!"
    re.compile(r"\b(\w+)\b(\s+\1){3,}", re.I),  # word repeated 4+ times
]

_CIVIC_EMERGENCY_TERMS = {
    "fire", "smoke", "burning", "building", "explosion", "flood", "flooding",
    "collapsed", "collapse", "accident", "road", "pothole", "sidewalk",
    "electric", "electricity", "wire", "sewer", "garbage", "water",
}

_POLICY_VIOLATION_TERMS = {
    "graphic violence", "gore", "blood", "corpse", "dead body", "weapon",
    "gun", "knife", "threat", "self-harm", "sexual", "explicit", "hate",
    "abusive",
}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()[:16]


def _is_civic_emergency_context(complaint_text: str, reason: str) -> bool:
    context = f"{complaint_text} {reason}".lower()
    return any(term in context for term in _CIVIC_EMERGENCY_TERMS)


def _has_policy_violation_reason(reason: str) -> bool:
    reason_lower = reason.lower()
    return any(term in reason_lower for term in _POLICY_VIOLATION_TERMS)


async def _record_text_hash(text_value: str, user_id: Optional[str]) -> bool:
    """
    Store the normalized text hash in Postgres.
    Returns True when this exact text has already been seen.
    """
    from .database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                INSERT INTO moderation_text_hashes
                    (text_hash, first_seen_at, last_seen_at, seen_count, last_user_id)
                VALUES
                    (:text_hash, NOW(), NOW(), 1, :user_id)
                ON CONFLICT (text_hash) DO UPDATE SET
                    last_seen_at = NOW(),
                    seen_count = moderation_text_hashes.seen_count + 1,
                    last_user_id = EXCLUDED.last_user_id
                RETURNING seen_count
            """),
            {"text_hash": _text_hash(text_value), "user_id": user_id},
        )
        await session.commit()
        return int(result.scalar_one()) > 1


def _heuristic_check(text: str) -> tuple[ModerationDecisionEnum, list[str]]:
    """
    Returns (preliminary_decision, flags).
    PASS  = no action needed from heuristics alone
    FLAG  = suspicious but not definitive
    REJECT = clearly spam / hate
    """
    flags: list[str] = []

    # Length checks
    if len(text) < _MIN_TEXT_LEN:
        flags.append("text_too_short")
    if len(text) > _MAX_TEXT_LEN:
        flags.append("text_too_long")

    # All-caps check
    alpha = [c for c in text if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > _CAPS_RATIO_THRESHOLD:
        flags.append("all_caps")

    # Keyword check (hate / explicit)
    text_lower = text.lower()
    for kw in _HATE_KEYWORDS:
        if kw in text_lower:
            flags.append(f"keyword:{kw}")
            break  # one is enough to flag

    # Spam pattern check
    for pat in _SPAM_PATTERNS:
        if pat.search(text):
            flags.append("spam_pattern")
            break

    # Decision
    hard_flags = {"text_too_short", "text_too_long"}
    hate_flags = {f for f in flags if f.startswith("keyword:")}

    if hate_flags:
        return ModerationDecisionEnum.REJECT, flags
    if flags & hard_flags if isinstance(flags, set) else any(f in hard_flags for f in flags):
        return ModerationDecisionEnum.FLAG, flags
    if "spam_pattern" in flags or "exact_duplicate" in flags or "all_caps" in flags:
        return ModerationDecisionEnum.FLAG, flags

    return ModerationDecisionEnum.PASS, flags


# ---------------------------------------------------------------------------
# Layer 2 â€” LLM text moderation
# ---------------------------------------------------------------------------

_LLM_SYSTEM = """\
You are a content moderator for CedarFix, a Lebanese public infrastructure complaint platform.
Analyse the text and return ONLY valid JSON (no markdown):
{
  "is_spam": <true|false>,
  "is_abusive": <true|false>,
  "is_political": <true|false>,
  "decision": "<PASS|FLAG|REJECT>",
  "confidence": <0.0â€“1.0>,
  "reason": "<1 sentence>"
}

Rules:
- REJECT: clear hate speech, explicit abuse, personal attacks, marketing spam.
- FLAG: political opinions/commentary, borderline content, unclear complaint.
- PASS: genuine infrastructure complaint (road, water, electricity, garbage, etc.).
- is_political = true does NOT mean REJECT. Political content â†’ FLAG only.
- Lebanese dialect (Levantine Arabic, Arabizi) is normal â€” do not flag language itself.
"""


async def _llm_moderate_text(text: str) -> Optional[dict]:
    if not QWEN_BASE_URL:
        return None
    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
            max_retries=0,
            timeout=10.0,
        )
        messages = [
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user", "content": f"Complaint text: \"{text[:1000]}\""},
        ]
        async with llm_audit_context(
            complaint_id=None,
            service="gateway",
            call_type="text_moderation",
            provider="qwen",
            model=QWEN_MODEL,
            prompt_version="moderation_text_v1",
            request_payload={
                "messages": messages,
                "response_format": "json_object",
                "temperature": 0.0,
            },
        ) as audit:
            resp = await client.chat.completions.create(
                model=QWEN_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw = resp.choices[0].message.content
            audit["raw_output"] = raw
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                return None
            data = json.loads(raw[start:end])
            audit["parsed_output"] = data
            return data
    except Exception as e:
        log.warning("[IEP-0] LLM moderation call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Layer 3 â€” VLM image moderation (checks harmful image content)
# ---------------------------------------------------------------------------

async def _vlm_moderate_image(image_filename: str) -> Optional[dict]:
    """
    Only called when an image is present AND the text was flagged.
    Reuses VLMAnalyzer's is_harmful detection (lightweight â€” no full analysis).
    """
    vlm_base = os.getenv("VLM_BASE_URL", "")
    if not vlm_base:
        return None
    try:
        import base64
        from io import BytesIO
        from PIL import Image
        import openai

        img = Image.open(BytesIO(read_image_bytes(image_filename))).convert("RGB")
        w, h = img.size
        scale = min(1.0, 512 / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()

        client = openai.AsyncOpenAI(
            api_key=os.getenv("VLM_API_KEY", "none"),
            base_url=vlm_base,
            max_retries=0,
            timeout=20.0,
        )
        system = (
            "You are a safety moderator for a public infrastructure complaint platform. "
            "Return is_harmful=true ONLY for policy-violating image content: graphic violence, "
            "sexual/explicit content, hate symbols, weapons/threats, self-harm, or abusive content. "
            "Public infrastructure problems such as potholes, road damage, building fire, smoke, flooding, "
            "garbage, broken streetlights, exposed utility damage, or other civic hazards are allowed "
            "evidence and MUST return is_harmful=false even if they are dangerous in the real world. "
            "Return ONLY JSON: {\"is_harmful\": <true|false>, \"reason\": \"<1 sentence>\"}"
        )
        model = os.getenv("VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": "Does this image contain policy-violating harmful content, or is it allowed civic infrastructure evidence?"},
        ]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        async with llm_audit_context(
            complaint_id=None,
            service="gateway",
            call_type="image_moderation",
            provider="qwen_vlm",
            model=model,
            prompt_version="moderation_image_v2",
            request_payload={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": "[base64_image_redacted]"}},
                        user_content[-1],
                    ]},
                ],
                "response_format": "json_object",
                "temperature": 0.0,
                "max_tokens": 64,
            },
        ) as audit:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=64,
            )
            raw = resp.choices[0].message.content
            audit["raw_output"] = raw
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                return None
            data = json.loads(raw[start:end])
            audit["parsed_output"] = data
            return data
    except Exception as e:
        log.warning("[IEP-0] VLM image moderation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def moderate(
    complaint_text: str,
    image_filename: Optional[str] = None,
    user_id: Optional[str] = None,
) -> ModerationResult:
    """
    Run all three layers and return a consolidated ModerationResult.
    Fast path: if heuristics pass and no image, skip LLM.
    """
    if not MODERATION_ENABLED:
        return ModerationResult(
            decision=ModerationDecisionEnum.PASS,
            reason="Moderation disabled",
            heuristic_flags=[],
            is_spam=False,
            is_abusive=False,
            is_political=False,
            is_ai_generated_image=False,
            llm_checked=False,
            vlm_checked=False,
        )

    # â”€â”€ Layer 1: Heuristics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    heuristic_decision, heuristic_flags = _heuristic_check(complaint_text)
    try:
        if await _record_text_hash(complaint_text, user_id):
            heuristic_flags.append("exact_duplicate")
            if heuristic_decision == ModerationDecisionEnum.PASS:
                heuristic_decision = ModerationDecisionEnum.FLAG
    except Exception as e:
        log.warning("[IEP-0] Postgres duplicate hash check failed: %s", e)

    is_spam = False
    is_abusive = False
    is_political = False
    is_ai_gen = False
    llm_checked = False
    vlm_checked = False
    final_decision = heuristic_decision
    reason = f"Heuristics: {', '.join(heuristic_flags)}" if heuristic_flags else "Clean"

    # â”€â”€ Layer 2: LLM (only when heuristics flagged anything) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if heuristic_flags and QWEN_BASE_URL:
        llm_data = await _llm_moderate_text(complaint_text)
        llm_checked = True
        if llm_data:
            is_spam = bool(llm_data.get("is_spam", False))
            is_abusive = bool(llm_data.get("is_abusive", False))
            is_political = bool(llm_data.get("is_political", False))
            llm_decision_str = llm_data.get("decision", "PASS")
            llm_conf = float(llm_data.get("confidence", 0.0))
            llm_reason = llm_data.get("reason", "")

            # LLM overrides heuristic only if high confidence
            if llm_conf >= LLM_THRESHOLD:
                try:
                    final_decision = ModerationDecisionEnum(llm_decision_str)
                    reason = llm_reason
                except ValueError:
                    pass  # keep heuristic decision

            # Political â†’ FLAG not REJECT (policy rule)
            if is_political and final_decision == ModerationDecisionEnum.REJECT:
                final_decision = ModerationDecisionEnum.FLAG
                reason = f"Political content detected (downgraded from REJECT): {reason}"

    # â”€â”€ Layer 3: VLM image moderation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    content_flags = [flag for flag in heuristic_flags if flag != "exact_duplicate"]
    should_check_image_policy = image_filename and final_decision != ModerationDecisionEnum.PASS and bool(content_flags)
    if should_check_image_policy:
        vlm_data = await _vlm_moderate_image(image_filename)
        vlm_checked = True
        if vlm_data:
            is_harmful_img = bool(vlm_data.get("is_harmful", False))
            vlm_reason = str(vlm_data.get("reason", ""))
            if is_harmful_img:
                if _is_civic_emergency_context(complaint_text, vlm_reason) and not _has_policy_violation_reason(vlm_reason):
                    final_decision = ModerationDecisionEnum.FLAG
                    reason = f"Civic emergency image allowed for review: {vlm_reason}; {reason}"
                else:
                    # Harmful image -> escalate to REJECT only for actual policy violations.
                    final_decision = ModerationDecisionEnum.REJECT
                    reason = f"Harmful image detected: {vlm_reason}; {reason}"

    # AI-generated image is a weak signal â€” note it but never reject alone
    # (VLMAnalyzer in model.py sets is_ai_generated on the full analysis)

    log.info(
        "[IEP-0] Moderation result: %s | flags=%s | llm=%s | vlm=%s",
        final_decision.value, heuristic_flags, llm_checked, vlm_checked,
    )

    return ModerationResult(
        decision=final_decision,
        reason=reason,
        heuristic_flags=heuristic_flags,
        is_spam=is_spam,
        is_abusive=is_abusive,
        is_political=is_political,
        is_ai_generated_image=is_ai_gen,
        llm_checked=llm_checked,
        vlm_checked=vlm_checked,
    )

