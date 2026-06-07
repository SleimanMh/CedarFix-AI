"""
Scene analyser for IEP-2: wraps CLIP inference and produces
a structured VisualUnderstandingJSON + image quality assessment.

Phase 1: CLIP zero-shot prompts.
Phase 2: Qwen2.5-VL for image reasoning and alignment (VLMAnalyzer).

AI Engineer 2 owns this file.
"""

import base64
import json
import logging
import os
import re
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from cedarfix_shared.schemas import (
    ComplaintType,
    ImageQualityJSON,
    SeverityLevel,
    VisualUnderstandingJSON,
    VisualIssueCandidate,
    VLMImageAnalysis,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# VLM Configuration
# ---------------------------------------------------------------------------

VLM_BASE_URL: str = os.getenv("VLM_BASE_URL", "")
VLM_MODEL: str = os.getenv("VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
VLM_ENABLED: bool = os.getenv("VLM_ENABLED", "true").lower() == "true"
VLM_TIMEOUT: float = float(os.getenv("VLM_TIMEOUT", "25"))
VLM_API_KEY: str = os.getenv("VLM_API_KEY", "none")

# ---------------------------------------------------------------------------
# CLIP zero-shot prompt banks
# ---------------------------------------------------------------------------

# Category prompts — ordered: first N are infrastructure, rest are negatives
_INFRA_PROMPTS: List[Tuple[str, str, str]] = [
    # (prompt_text, visual_category, visual_subcategory)
    ("a photo of road damage or pothole",              "roads",       "pothole"),
    ("a photo of a large hole or crater in the road",  "roads",       "pothole"),
    ("a photo of cracked or broken asphalt",           "roads",       "road_damage"),
    ("a photo of flooding or standing water on street","drainage",    "flooding"),
    ("a photo of garbage or waste piled on street",    "sanitation",  "waste_accumulation"),
    ("a photo of a broken traffic light or signal",    "roads",       "traffic_light"),
    ("a photo of a damaged or cracked sidewalk",       "roads",       "sidewalk_damage"),
    ("a photo of a broken or dark street lamp",        "electricity", "streetlight"),
    ("a photo of a leaking or burst water pipe",       "water",       "pipe_leak"),
    ("a photo of broken infrastructure or utility",    "other",       "other"),
]

_NEGATIVE_PROMPTS = [
    "a random photo unrelated to infrastructure",
    "a selfie or indoor photo",
    "a nature landscape or food photo",
]

_ALL_PROMPTS = [p for p, _, _ in _INFRA_PROMPTS] + _NEGATIVE_PROMPTS
_N_INFRA = len(_INFRA_PROMPTS)

# Objects CLIP can detect via the top matching prompts
_OBJECT_MAP: Dict[str, List[str]] = {
    "pothole":           ["pothole", "road hole", "crater"],
    "road_damage":       ["cracked asphalt", "broken road"],
    "flooding":          ["standing water", "flooded street"],
    "waste_accumulation":["garbage pile", "waste"],
    "traffic_light":     ["broken traffic light"],
    "sidewalk_damage":   ["cracked sidewalk"],
    "streetlight":       ["broken street lamp"],
    "pipe_leak":         ["leaking pipe", "burst pipe"],
    "other":             ["damaged infrastructure"],
}

_SEVERITY_PROMPTS: List[Tuple[str, SeverityLevel]] = [
    ("severe damage completely blocking the road, dangerous flooding, imminent collapse",
     SeverityLevel.CRITICAL),
    ("large pothole or significant road damage, major flooding",
     SeverityLevel.HIGH),
    ("moderate road damage or partial obstruction, noticeable damage",
     SeverityLevel.MEDIUM),
    ("minor crack or small pothole, minimal visible damage",
     SeverityLevel.LOW),
]

# Three-dimensional semantic descriptors derived from CLIP visual_subcategory.
# Used when the VLM is unavailable.  (domain, physical_component, failure_mode)
_SUBCATEGORY_TO_DESCRIPTORS: Dict[str, Tuple[str, str, str]] = {
    "pothole":            ("transportation", "road_surface",      "damage"),
    "road_damage":        ("transportation", "road_surface",      "damage"),
    "flooding":           ("environment",    "drainage_system",   "overflow"),
    "waste_accumulation": ("environment",    "public_space",      "accumulation"),
    "traffic_light":      ("transportation", "traffic_signal",    "damage"),
    "sidewalk_damage":    ("transportation", "sidewalk",          "damage"),
    "streetlight":        ("transportation", "street_light",      "damage"),
    "pipe_leak":          ("utilities",      "water_pipe",        "damage"),
    "other":              ("other",          "other",             "other"),
}

# Quality heuristics — minimum image size (px)
_MIN_USABLE_PIXELS = 128 * 128


# ---------------------------------------------------------------------------
# SceneAnalyzer
# ---------------------------------------------------------------------------

class SceneAnalyzer:
    """
    Wraps a loaded CLIP model and produces structured scene understanding.
    Instantiated once inside ImageUnderstandingModel.
    """

    def __init__(self, clip_model: CLIPModel, clip_processor: CLIPProcessor):
        self._model = clip_model
        self._processor = clip_processor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_quality(self, image: Image.Image) -> ImageQualityJSON:
        """Fast heuristic quality check (no ML, sub-millisecond)."""
        issues: List[str] = []
        w, h = image.size
        pixels = w * h
        if pixels < _MIN_USABLE_PIXELS:
            issues.append("image_too_small")
        if image.mode not in ("RGB", "RGBA", "L"):
            issues.append("unsupported_mode")
        # Brightness heuristic: very dark or very bright
        try:
            import numpy as np
            arr = np.array(image.convert("L"), dtype=float)
            mean_brightness = arr.mean()
            if mean_brightness < 20:
                issues.append("too_dark")
            elif mean_brightness > 240:
                issues.append("overexposed")
        except Exception:
            pass
        quality_score = max(0.0, 1.0 - len(issues) * 0.3)
        return ImageQualityJSON(
            usable=len(issues) == 0,
            quality_score=round(quality_score, 2),
            issues=issues,
        )

    def analyze_scene(self, image: Image.Image) -> VisualUnderstandingJSON:
        """
        Run CLIP zero-shot over infrastructure prompts.
        Returns a fully populated VisualUnderstandingJSON.
        """
        # --- Infrastructure category classification ---
        category, subcategory, infra_confidence, top_idx = self._classify_category(image)

        # --- Object list from top matching prompt ---
        detected_objects = _OBJECT_MAP.get(subcategory, ["infrastructure damage"])

        # --- Damage assessment ---
        damage_visible = infra_confidence > 0.35

        # --- Severity ---
        severity = self._estimate_severity(image) if damage_visible else SeverityLevel.LOW

        # --- Caption (rule-based for Phase 1; replace with BLIP-2 in Phase 2) ---
        caption = self._make_caption(subcategory, severity, detected_objects)

        # --- Three semantic descriptor fields (for cross-modal overlap scoring) ---
        sem_domain, phys_comp, fail_mode = _SUBCATEGORY_TO_DESCRIPTORS.get(
            subcategory, ("other", "other", "other")
        )

        return VisualUnderstandingJSON(
            caption=caption,
            visual_category=category,
            visual_subcategory=subcategory,
            detected_objects=detected_objects,
            damage_visible=damage_visible,
            visual_severity=severity,
            confidence=round(infra_confidence, 3),
            semantic_domain=sem_domain,
            physical_component=phys_comp,
            failure_mode=fail_mode,
            visual_candidates=[VisualIssueCandidate(
                visual_category=category,
                visual_subcategory=subcategory,
                caption=caption,
                semantic_domain=sem_domain,
                physical_component=phys_comp,
                failure_mode=fail_mode,
                confidence=round(infra_confidence, 3),
                evidence=caption,
            )],
        )

    def get_image_embedding(self, image: Image.Image) -> List[float]:
        """Returns L2-normalised 512-dim CLIP image feature."""
        inputs = self._processor(images=image, return_tensors="pt")
        with torch.no_grad():
            vision_out = self._model.vision_model(pixel_values=inputs["pixel_values"])
            features = self._model.visual_projection(vision_out.pooler_output)
            features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features[0].tolist()

    def get_text_embedding(self, text: str) -> List[float]:
        """
        Returns L2-normalised 512-dim CLIP text feature for the given text.

        Because CLIP embeds text and images in the SAME shared space, the
        cosine similarity between this vector and an image embedding produced
        by get_image_embedding() is meaningful without any projection.

        This is the CORRECT approach for intra-complaint alignment.
        The random projection used in fusion.py is only for projecting image
        embeddings into the sentence-transformer text space for fused storage —
        it must NOT be used as an alignment signal.
        """
        inputs = self._processor(
            text=[text], return_tensors="pt", padding=True, truncation=True
        )
        with torch.no_grad():
            text_out = self._model.text_model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )
            features = self._model.text_projection(text_out.pooler_output)
            features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features[0].tolist()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clip_probs(self, texts: List[str], image: Image.Image) -> List[float]:
        """Compute CLIP zero-shot probabilities over a list of text prompts."""
        img_inputs = self._processor(images=image, return_tensors="pt")
        txt_inputs = self._processor(
            text=texts, return_tensors="pt", padding=True, truncation=True
        )
        with torch.no_grad():
            vision_out = self._model.vision_model(pixel_values=img_inputs["pixel_values"])
            image_features = self._model.visual_projection(vision_out.pooler_output)
            image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)

            text_out = self._model.text_model(
                input_ids=txt_inputs["input_ids"],
                attention_mask=txt_inputs["attention_mask"],
            )
            text_features = self._model.text_projection(text_out.pooler_output)
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)

            logit_scale = self._model.logit_scale.exp()
            logits = (image_features @ text_features.T) * logit_scale
            probs = logits.softmax(dim=-1)[0].tolist()
        return probs

    def _classify_category(
        self, image: Image.Image
    ) -> Tuple[str, str, float, int]:
        """Returns (category, subcategory, infra_confidence, top_infra_idx)."""
        probs = self._clip_probs(_ALL_PROMPTS, image)
        infra_probs = probs[:_N_INFRA]
        neg_probs = probs[_N_INFRA:]
        infra_total = sum(infra_probs)
        neg_total = sum(neg_probs)
        infra_confidence = infra_total / (infra_total + neg_total + 1e-8)

        top_idx = max(range(_N_INFRA), key=lambda i: infra_probs[i])
        _, cat, sub = _INFRA_PROMPTS[top_idx]
        return cat, sub, infra_confidence, top_idx

    def _estimate_severity(self, image: Image.Image) -> SeverityLevel:
        texts = [p for p, _ in _SEVERITY_PROMPTS]
        probs = self._clip_probs(texts, image)
        best = max(range(len(probs)), key=lambda i: probs[i])
        return _SEVERITY_PROMPTS[best][1]

    @staticmethod
    def _make_caption(
        subcategory: str, severity: SeverityLevel, objects: List[str]
    ) -> str:
        # TODO Phase 2: replace with BLIP-2 generated caption
        obj_str = objects[0] if objects else subcategory.replace("_", " ")
        sev_label = severity.value.lower()
        return f"A {sev_label} severity {obj_str} visible in the image."


# ---------------------------------------------------------------------------
# VLM Analyzer — Qwen2.5-VL Phase 2
# ---------------------------------------------------------------------------

_VLM_SYSTEM = """\
You are an expert image analyst for CedarFix, a Lebanese public infrastructure complaint platform.
Extract factual visual information only.
Do not decide the responsible public entity. Do not perform routing.
Do not output primary_entity, secondary_entity, possible_entities, negative_entities,
requires_human_review, review_reason, or hitl_required.
Given an image, return ONLY a valid JSON object (no markdown, no explanation):
{
  "image_type": "<infrastructure_damage | natural_scene | indoor | person | vehicle | other>",
  "is_valid_complaint_image": <true|false>,
  "is_harmful": <true|false>,
  "is_ai_generated": <true|false>,
  "damage_visible": <true|false>,
    "visual_category": "<free-form, specific snake_case label that best groups the visible issue (e.g. street_furniture, urban_greenery, vandalism, animal_hazard, environmental_hazard, road_surface, drainage, water_network, electrical_grid, public_space_issue). Use 'other' only if truly impossible to identify>",
    "visual_subcategory": "<free-form, highly specific snake_case label for what is actually visible (e.g. broken_bench, fallen_tree, graffiti, stray_animal_attack, chemical_spill, illegal_dumping, collapsed_wall, broken_railing, damaged_sign, pipe_leak, pothole). Avoid broad labels>",
  "caption": "<a single descriptive sentence of what you actually see in the image, written as a natural English description — e.g. 'A damaged park bench with broken wooden slats lying on the ground near a pedestrian path.'>",
  "semantic_domain": "<free-form broad domain from what is visible, e.g. transportation, utilities, environment, safety, public_space>",
  "physical_component": "<free-form specific visible element, e.g. road_surface, sidewalk, bus_stop_shelter, drainage_grate, telecom_cable>",
  "failure_mode": "<free-form visible failure, e.g. broken, missing, overflow, low_hanging, obstruction, exposed_wires>",
  "damage_severity": "<CRITICAL | HIGH | MEDIUM | LOW | NONE>",
    "visual_candidates": [
        {
            "visual_category": "<free-form group for one visible issue>",
            "visual_subcategory": "<free-form specific visible issue>",
            "caption": "<specific sentence for this candidate>",
            "semantic_domain": "<free-form broad domain>",
            "physical_component": "<specific visible component>",
            "failure_mode": "<specific visible failure>",
            "confidence": <0.0-1.0>,
            "evidence": "<short visual evidence from the image>"
        }
    ],
    "location_cues": {
        "detected_text": ["<visible text>"],
        "landmarks": ["<landmarks>"],
        "street_signs": ["<street signs>"],
        "storefront_names": ["<shop/store names>"],
        "confidence": <0.0-1.0>
    },
    "routing_features": {
        "domain": "",
        "physical_component": "",
        "failure_mode": "",
        "hazard_type": "",
        "affected_public_space": true,
        "requires_emergency_attention": false
    },
    "evidence": {
        "text_evidence": [],
        "image_evidence": [],
        "missing_information": []
    },
    "alignment_features": {
        "domain": "",
        "physical_component": "",
        "failure_mode": "",
        "visible_hazard": true,
        "objects": [],
        "actions": [],
        "location_context": []
    },
  "confidence": <0.0-1.0>,
  "reasoning": "<1-2 sentences explaining what you see>"
}

Rules:
- caption: ALWAYS fill this with a concrete, specific description of what is visible. Do NOT say "the image shows infrastructure damage" — describe exactly what you see (e.g. "A large pothole filled with brown water on a cracked asphalt road.", "Graffiti covering a concrete wall near a bridge abutment.", "A fallen tree blocking a two-lane residential street.").
- If the image indicates a complaint, set is_valid_complaint_image=true and use specific labels in visual_category + visual_subcategory.
- NEVER use broad placeholders like "other", "infrastructure_issue", or "damage" when a more specific label is possible.
- visual_candidates: return up to 3 distinct visible public-space issue candidates from the image, ordered by confidence.
- Do not return duplicate candidates. If the same storm/damage scene contains multiple visible hazards, list the
  separate damaged or hazardous components separately, e.g. an obstructing fallen tree/debris and low-hanging or
  downed utility lines/cables should be separate candidates.
- Each candidate must be internally consistent: visual_subcategory, physical_component, and failure_mode must refer
  to the same visible object. Do not return visual_subcategory=downed_tree with physical_component=power_line.
- If wires, lines, or cables are visibly hanging low, crossing a road, sagging, detached, or downed, include a
  separate utility-line/cable candidate even if a fallen tree or debris is also visible.
- visual_candidates must be based only on what is visible in the image. Do not infer hidden problems.
- Keep visual_category, visual_subcategory, semantic_domain, physical_component, and failure_mode aligned with the first candidate.
- If the image is not a complaint, still describe what it contains accurately in caption and use specific labels for the visible content.
- is_valid_complaint_image: true only if the image shows real infrastructure damage or a public-space problem.
- is_harmful: true for graphic violence, hate symbols, explicit content.
- is_ai_generated: true only if clearly synthetic/AI-rendered.
- location_cues: do not infer precise location unless strong visible cues exist (text, landmarks, signs, storefront names).
- damage_severity CRITICAL = road fully blocked, imminent danger.
- semantic_domain=transportation for road/traffic/sidewalk; utilities for water/electricity/telecom; environment for flooding/garbage; safety for personal danger.
- physical_component = the specific infrastructure element visibly present or damaged.
- failure_mode: damage = physical breakage; outage = service unavailable; overflow = flooding/excess water; accumulation = waste buildup; blockage = obstruction; contamination = chemical or biological hazard.
- visual_subcategory: ALWAYS be specific. Use 'other' only as a true last resort.
"""

_VLM_SYSTEM = """\
You are an expert image analyst for CedarFix, a public infrastructure complaint platform.
Extract factual visual information only from the image.
Do not use complaint text. Do not compare the image to text.
Do not decide routing, responsible entities, review decisions, or moderation decisions.
Return ONLY a valid JSON object. No markdown. No explanation outside JSON.

Use dynamic free-form snake_case labels. There is no fixed taxonomy.
Do not choose the nearest example or known category. Build labels from what is visibly present.

Return this JSON shape:
{
  "image_type": "<free-form broad image type>",
  "is_valid_complaint_image": <true|false>,
  "is_harmful": <true|false>,
  "is_ai_generated": <true|false>,
  "damage_visible": <true|false>,
  "visual_category": "<free-form broad group for the primary visible issue>",
  "visual_subcategory": "<free-form specific label for the primary visible object and problem>",
  "caption": "<one concrete sentence describing only what is visible>",
  "semantic_domain": "<free-form broad domain inferred from visible context>",
  "physical_component": "<free-form specific visible object/component>",
  "failure_mode": "<free-form visible condition/action/failure>",
  "damage_severity": "<CRITICAL | HIGH | MEDIUM | LOW | NONE>",
  "visual_candidates": [
    {
      "visual_category": "<free-form broad group for one visible issue>",
      "visual_subcategory": "<free-form specific label for this visible object and problem>",
      "caption": "<one concrete sentence for this candidate>",
      "semantic_domain": "<free-form broad domain>",
      "physical_component": "<specific visible object/component>",
      "failure_mode": "<specific visible condition/action/failure>",
      "confidence": <0.0-1.0>,
      "evidence": "<short visual evidence from the image>"
    }
  ],
  "location_cues": {
    "detected_text": ["<visible text>"],
    "landmarks": ["<visible landmarks>"],
    "street_signs": ["<visible street signs>"],
    "storefront_names": ["<visible storefront names>"],
    "confidence": <0.0-1.0>
  },
  "routing_features": {
    "domain": "",
    "physical_component": "",
    "failure_mode": "",
    "hazard_type": "",
    "affected_public_space": true,
    "requires_emergency_attention": false
  },
  "evidence": {
    "text_evidence": [],
    "image_evidence": [],
    "missing_information": []
  },
  "alignment_features": {
    "domain": "",
    "physical_component": "",
    "failure_mode": "",
    "visible_hazard": true,
    "objects": [],
    "actions": [],
    "location_context": []
  },
  "confidence": <0.0-1.0>,
  "reasoning": "<1-2 factual sentences about visible evidence>"
}

Rules:
- Use image-only evidence. Never infer hidden causes or unseen infrastructure.
- If the image shows no public-space problem, set is_valid_complaint_image=false and still describe what is visible.
- visual_candidates must contain up to 3 distinct visible public-space issues, ordered by confidence.
- Do not duplicate candidates. If multiple different hazardous objects/components are visible, split them into separate candidates.
- Each candidate must be internally consistent: visual_subcategory, physical_component, failure_mode, caption, and evidence must describe the same visible object/component.
- The top-level visual_category, visual_subcategory, semantic_domain, physical_component, failure_mode, caption, and confidence must match candidate 1.
- Use "other" only if the visible content truly cannot be described more specifically.
- Keep labels specific but free-form. Prefer a precise new label over a generic placeholder.
"""


def _image_to_base64(image: Image.Image, max_size: int = 1024) -> str:
    """Resize to at most max_size px on the longest side and encode as JPEG base64."""
    w, h = image.size
    if max(w, h) > max_size:
        scale = max_size / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _snake(value, default: str = "") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or default


def _float(value, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _infer_failure_mode(text: str, fallback: str = "") -> str:
    text = text.lower()
    if any(term in text for term in ("low hanging", "low-hanging", "hanging low", "sagging", "crossing a road")):
        return "low_hanging"
    if any(term in text for term in ("downed", "fallen", "detached", "collapsed")):
        return "downed"
    if any(term in text for term in ("exposed", "open", "uncovered")):
        return "exposed"
    if any(term in text for term in ("blocking", "obstructing", "blocked")):
        return "obstruction"
    return _snake(fallback, "damage")


def _is_component_mismatch(subcategory: str, component: str) -> bool:
    if not component or component == "other":
        return False
    component_tokens = {t for t in component.split("_") if len(t) > 2}
    subcategory_tokens = {t for t in subcategory.split("_") if len(t) > 2}
    if not component_tokens:
        return False
    return component_tokens.isdisjoint(subcategory_tokens)


def _repair_candidate(candidate: VisualIssueCandidate) -> VisualIssueCandidate:
    component = _snake(candidate.physical_component, "")
    subcategory = _snake(candidate.visual_subcategory, "")
    evidence_text = " ".join(
        part for part in (candidate.caption, candidate.evidence, candidate.failure_mode) if part
    )

    if _is_component_mismatch(subcategory, component):
        failure = _infer_failure_mode(evidence_text, candidate.failure_mode or "")
        candidate.visual_subcategory = f"{failure}_{component}"
        candidate.failure_mode = failure

    if (
        candidate.semantic_domain in {None, "", "other", "environment", "safety"}
        and any(token in component for token in ("line", "cable", "wire", "pipe"))
    ):
        candidate.semantic_domain = "utilities"

    return candidate


def _parse_visual_candidates(data: dict) -> list[VisualIssueCandidate]:
    raw_candidates = data.get("visual_candidates")
    candidates: list[VisualIssueCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    if isinstance(raw_candidates, list):
        for raw in raw_candidates[:3]:
            if not isinstance(raw, dict):
                continue
            subcategory = _snake(raw.get("visual_subcategory"), "")
            category = _snake(raw.get("visual_category"), "")
            if not subcategory and not category:
                continue
            key = (
                category,
                subcategory,
                _snake(raw.get("physical_component"), ""),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_repair_candidate(VisualIssueCandidate(
                visual_category=category or "other",
                visual_subcategory=subcategory or category or "other",
                caption=str(raw.get("caption") or "").strip(),
                semantic_domain=_snake(raw.get("semantic_domain"), "") or None,
                physical_component=_snake(raw.get("physical_component"), "") or None,
                failure_mode=_snake(raw.get("failure_mode"), "") or None,
                confidence=_float(raw.get("confidence"), 0.5),
                evidence=str(raw.get("evidence") or "").strip(),
            )))

    if candidates:
        return candidates

    return [_repair_candidate(VisualIssueCandidate(
        visual_category=_snake(data.get("visual_category"), "other"),
        visual_subcategory=_snake(data.get("visual_subcategory"), "other"),
        caption=str(data.get("caption") or "").strip(),
        semantic_domain=_snake(data.get("semantic_domain"), "") or None,
        physical_component=_snake(data.get("physical_component"), "") or None,
        failure_mode=_snake(data.get("failure_mode"), "") or None,
        confidence=_float(data.get("confidence"), 0.5),
        evidence=str(data.get("reasoning") or "").strip(),
    ))]


class VLMAnalyzer:
    """
    Calls Qwen2.5-VL (or any OpenAI-compatible VLM) to produce a
    VLMImageAnalysis with richer semantic understanding than CLIP.

    Only instantiated when VLM_ENABLED=true and VLM_BASE_URL is set.
    """

    def __init__(self):
        if not VLM_BASE_URL:
            raise RuntimeError("VLM_BASE_URL is not set — cannot initialise VLMAnalyzer")

    async def analyze(
        self,
        image: Image.Image,
        complaint_text: Optional[str] = None,
    ) -> Optional[VLMImageAnalysis]:
        """
        Send image to the VLM and parse the structured response.
        Returns None on error — caller should fall back to CLIP result.
        """
        try:
            import openai
            b64 = _image_to_base64(image)
            user_content: list = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                },
            ]
            user_content.append({
                "type": "text",
                "text": (
                    "Analyse this image for public infrastructure damage. "
                    "Return image-only findings; do not compare against any complaint text."
                ),
            })

            client = openai.AsyncOpenAI(
                api_key=VLM_API_KEY,
                base_url=VLM_BASE_URL,
                max_retries=0,
                timeout=VLM_TIMEOUT,
            )
            resp = await client.chat.completions.create(
                model=VLM_MODEL,
                messages=[
                    {"role": "system", "content": _VLM_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=900,
            )
            raw = resp.choices[0].message.content
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                return None
            data = json.loads(raw[start:end])

            loc_raw = data.get("location_cues", {})
            if isinstance(loc_raw, list):
                loc_raw = {
                    "detected_text": [str(x) for x in loc_raw if x],
                    "landmarks": [],
                    "street_signs": [],
                    "storefront_names": [],
                    "confidence": 0.5,
                }

            rf = data.get("routing_features", {}) or {}
            ev = data.get("evidence", {}) or {}
            af = data.get("alignment_features", {}) or {}
            visual_candidates = _parse_visual_candidates(data)
            primary = visual_candidates[0]

            severity = str(data.get("damage_severity") or "LOW").upper()
            if severity in {"NONE", "NO_DAMAGE", "UNKNOWN", ""}:
                severity = "LOW"
            if severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                severity = "LOW"

            return VLMImageAnalysis(
                image_type=data.get("image_type", "other"),
                is_valid_complaint_image=bool(data.get("is_valid_complaint_image", False)),
                is_harmful=bool(data.get("is_harmful", False)),
                is_ai_generated=bool(data.get("is_ai_generated", False)),
                damage_visible=bool(data.get("damage_visible", False)),
                visual_category=primary.visual_category or _snake(data.get("visual_category"), "other"),
                visual_subcategory=primary.visual_subcategory or _snake(data.get("visual_subcategory"), "other"),
                caption=primary.caption or data.get("caption", ""),
                damage_severity=severity,
                location_cues={
                    "detected_text": [str(x) for x in loc_raw.get("detected_text", []) if str(x).strip()],
                    "landmarks": [str(x) for x in loc_raw.get("landmarks", []) if str(x).strip()],
                    "street_signs": [str(x) for x in loc_raw.get("street_signs", []) if str(x).strip()],
                    "storefront_names": [str(x) for x in loc_raw.get("storefront_names", []) if str(x).strip()],
                    "confidence": float(loc_raw.get("confidence", 0.0)),
                },
                confidence=_float(primary.confidence, _float(data.get("confidence"), 0.5)),
                reasoning=data.get("reasoning", ""),
                vlm_alignment=None,
                vlm_alignment_confidence=0.0,
                semantic_domain=primary.semantic_domain or data.get("semantic_domain"),
                physical_component=primary.physical_component or data.get("physical_component"),
                failure_mode=primary.failure_mode or data.get("failure_mode"),
                routing_features={
                    "domain": rf.get("domain") or data.get("semantic_domain") or "unknown",
                    "physical_component": rf.get("physical_component") or data.get("physical_component") or "unknown",
                    "failure_mode": rf.get("failure_mode") or data.get("failure_mode") or "unknown",
                    "hazard_type": rf.get("hazard_type", "none"),
                    "affected_public_space": bool(rf.get("affected_public_space", True)),
                    "requires_emergency_attention": bool(rf.get("requires_emergency_attention", False)),
                },
                evidence={
                    "text_evidence": [str(x) for x in ev.get("text_evidence", []) if str(x).strip()],
                    "image_evidence": [str(x) for x in ev.get("image_evidence", []) if str(x).strip()],
                    "missing_information": [str(x) for x in ev.get("missing_information", []) if str(x).strip()],
                },
                alignment_features={
                    "domain": af.get("domain") or data.get("semantic_domain") or "unknown",
                    "physical_component": af.get("physical_component") or data.get("physical_component") or "unknown",
                    "failure_mode": af.get("failure_mode") or data.get("failure_mode") or "unknown",
                    "visible_hazard": bool(af.get("visible_hazard", data.get("damage_visible", False))),
                    "objects": [str(x) for x in af.get("objects", []) if str(x).strip()],
                    "actions": [str(x) for x in af.get("actions", []) if str(x).strip()],
                    "location_context": [str(x) for x in af.get("location_context", []) if str(x).strip()],
                },
                visual_candidates=visual_candidates,
            )
        except Exception as e:
            log.warning("[IEP-2] VLM analysis failed: %s", e)
            return None


class VLMAlignmentChecker:
    """
    Called when CLIP alignment is UNCERTAIN or CONTRADICTS.
    Asks the VLM to explicitly judge whether the image supports the text.
    """

    def __init__(self):
        if not VLM_BASE_URL:
            raise RuntimeError("VLM_BASE_URL is not set — cannot initialise VLMAlignmentChecker")

    async def check_alignment(
        self,
        image: Image.Image,
        complaint_text: str,
        clip_alignment: str,
    ) -> Optional[dict]:
        """
        Returns dict: {alignment, text_issue, image_issue, confidence, reason}
        alignment values: CONFIRMS | RELATED | UNCERTAIN | CONTRADICTS
        """
        try:
            import openai
            b64 = _image_to_base64(image)
            system = (
                "You are a complaint validator. Given an image and a text description of a public "
                "infrastructure complaint, decide if they match. "
                "Return ONLY valid JSON:\n"
                '{"alignment": "<CONFIRMS|RELATED|UNCERTAIN|CONTRADICTS>", '
                '"text_issue": "<what text claims>", '
                '"image_issue": "<what image shows>", '
                '"confidence": <0.0-1.0>, '
                '"reason": "<1 sentence>"}'
            )
            client = openai.AsyncOpenAI(
                api_key=VLM_API_KEY,
                base_url=VLM_BASE_URL,
                max_retries=0,
                timeout=VLM_TIMEOUT,
            )
            resp = await client.chat.completions.create(
                model=VLM_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": f"Complaint text: \"{complaint_text[:300]}\"\nCLIP initial alignment: {clip_alignment}. Please confirm or correct."},
                    ]},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=256,
            )
            raw = resp.choices[0].message.content
            raw = re.sub(r"```(?:json)?", "", raw).strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                return None
            return json.loads(raw[start:end])
        except Exception as e:
            log.warning("[IEP-2] VLM alignment check failed: %s", e)
            return None
