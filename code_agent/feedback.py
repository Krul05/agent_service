from __future__ import annotations

import re
from dataclasses import dataclass

VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\s*$", re.IGNORECASE | re.MULTILINE)

NEXT_ACTIONS_BLOCK_RE = re.compile(
    r"^\s*NEXT_ACTIONS:\s*(.*)$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class ReviewVerdict:
    verdict: str
    next_actions_text: str


def parse_review(body: str) -> ReviewVerdict:
    text = body or ""
    m = VERDICT_RE.search(text)
    verdict = (m.group(1).upper() if m else "FAIL")

    na = ""
    m2 = NEXT_ACTIONS_BLOCK_RE.search(text)
    if m2:
        na = m2.group(0).strip()

    return ReviewVerdict(verdict=verdict, next_actions_text=na)
