"""
IEP-7 — Explanation Service (Template Mode MVP)
=================================================
Owned by: AI Engineer 1 (Stretch)

MVP: Template-based explanations using structured decision fields.
Stretch: Replace _generate_llm() with Qwen2.5-7B-Instruct inference.
"""

import time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
from cedarfix_shared.schemas import ExplanationResult
import os

MODE = os.getenv("MODE", "template")

app = FastAPI(title="IEP-7: Explanation Service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "explanation-service", "mode": MODE}


class ExplainRequest(BaseModel):
    complaint_id: str
    complaint_type: Optional[str] = None
    severity: Optional[str] = None
    assigned_entity: Optional[str] = None
    routing_confidence: Optional[float] = None
    is_duplicate: bool = False
    urgency_factors: List[str] = []


@app.post("/explain", response_model=ExplanationResult)
async def explain(request: ExplainRequest):
    if MODE == "llm":
        text, factors = _generate_llm(request)
    else:
        text, factors = _generate_template(request)

    return ExplanationResult(
        complaint_id=request.complaint_id,
        explanation_text=text,
        mode=MODE,
        key_factors=factors,
    )


def _generate_template(req: ExplainRequest):
    """
    Template-based explanation. Fast, interpretable, no GPU needed.
    AI Engineer 1: Improve templates with more nuanced language.
    """
    factors = []
    parts = []

    ctype = (req.complaint_type or "issue").replace("_", " ")
    parts.append(f"This complaint has been classified as a {ctype}")

    if req.severity:
        parts.append(f"with {req.severity.upper()} severity")
        factors.append(f"Severity: {req.severity}")

    if req.is_duplicate:
        parts.append("This appears to be a duplicate of an existing report.")
        factors.append("Duplicate complaint detected")
    
    if req.assigned_entity and req.assigned_entity != "Human Review Queue":
        conf_label = "high" if (req.routing_confidence or 0) > 0.85 else "moderate"
        parts.append(f"It has been routed to {req.assigned_entity} with {conf_label} confidence.")
        factors.append(f"Routed to: {req.assigned_entity}")

    if req.urgency_factors:
        parts.append("Priority factors: " + "; ".join(req.urgency_factors[:3]) + ".")
        factors.extend(req.urgency_factors[:3])

    return " ".join(parts) + ".", factors


def _generate_llm(req: ExplainRequest):
    """
    Stretch: Use Qwen2.5-7B-Instruct to generate a natural language explanation.
    
    Implementation steps for AI Engineer 1:
    1. pip install transformers accelerate
    2. Load model: AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
    3. Build prompt from req fields
    4. Generate response with max_new_tokens=200
    5. Return generated text
    """
    # Fall back to template until LLM is implemented
    return _generate_template(req)
