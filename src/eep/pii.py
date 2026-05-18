from __future__ import annotations

import re


# Lebanese phone numbers (03-xxx-xxx, +961 3 xxx xxx, +961 70 xxx xxx, etc.)
# and e-mail addresses.
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?961[-\s]?)?(?:0?(?:1|3|4|5|6|7|8|9|70|71|76|78|79|81))[-\s]?\d{3}[-\s]?\d{3}\b"
)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def scrub_pii(text: str) -> str:
    text = PHONE_RE.sub("[PHONE]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    return text
