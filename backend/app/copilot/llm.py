"""Optional LLM narrative on top of the deterministic case file.

The brief's division of labour (section 3): *rules compute, thresholds decide,
AI explains*. So the model here is handed a finished set of facts -- the score,
the rules that fired, the evidence, the recommended action -- and asked only to
write them up. It is never asked what the score is, whether the account is
suspicious, or what should be done. Those are already decided by the time this
runs, and nothing it returns is parsed back into a decision.

It is also entirely optional. Without ``ANTHROPIC_API_KEY`` the case file from
:mod:`app.copilot.templates` is served as-is, which is what the demo runs on.
Responses are cached to disk so a live call never happens twice for the same
account, and a failure degrades to the template rather than raising.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent / "cache"
MODEL = "claude-sonnet-5"
MAX_TOKENS = 700

SYSTEM_PROMPT = """You are writing the narrative section of a fraud case file for a bank analyst.

You will be given a completed case: a risk score, the detection rules that fired with their point values, the evidence transactions, and the action the system has already decided on.

Write 3-5 sentences summarising what happened, in plain English, for an analyst who has not seen this account before.

Rules:
- Do not compute, restate differently, or dispute the score. It is final.
- Do not recommend an action. One has already been chosen.
- Do not invent facts. Use only what you are given.
- Refer to the account holder neutrally; do not assume gender.
- Say "mule network", not "money laundering".
- No preamble, no headings, no bullet points. Just the paragraph."""


def _cache_key(case: dict[str, Any]) -> str:
    """Keyed on the facts, so a changed case regenerates and a stable one does not."""
    payload = json.dumps(
        {
            "account": case["account_id"],
            "score": case["score"],
            "breakdown": [(r["rule_id"], r["points"]) for r in case["breakdown"]],
            "action": (case.get("recommended_action") or {}).get("code"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def _cached(key: str) -> str | None:
    path = CACHE_DIR / f"{key}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _store(key: str, text: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.txt").write_text(text, encoding="utf-8")


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def narrate(case: dict[str, Any]) -> tuple[str, str]:
    """Return ``(narrative, source)`` where source is cache | llm | template.

    Never raises: a copilot that can fail live is worse than one that is
    deterministic, so every failure path returns the template summary.
    """
    key = _cache_key(case)
    hit = _cached(key)
    if hit is not None:
        return hit, "cache"

    if not available():
        return case["summary"], "template"

    try:
        from anthropic import Anthropic  # imported lazily: optional dependency

        client = Anthropic()
        facts = {
            "account_id": case["account_id"],
            "score": case["score"],
            "band": case["band_label"],
            "action": (case.get("recommended_action") or {}).get("label"),
            "rules": [
                {
                    "rule": row["rule_id"],
                    "name": row["rule_name"],
                    "points": row["points"],
                    "detail": row["message"],
                }
                for row in case["breakdown"]
            ],
            "evidence": case["evidence"][:6],
            "profile": case["profile"],
            "anomaly": case.get("anomaly"),
        }
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(facts, indent=2)}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            return case["summary"], "template"
        _store(key, text)
        return text, "llm"
    except Exception:
        # Offline, no package, rate limited, malformed response -- all the same
        # outcome: the analyst still gets a complete case file.
        return case["summary"], "template"
