"""Optional LLM layer over the deterministic case narrative.

Per DEMO-SPEC the shipped narrative is the template composer
(:mod:`app.copilot.composer`) -- it renders instantly and cannot fail live. An
LLM is strictly optional and off by default: when a provider is configured it
is handed the *finished* facts (score, fired rules, evidence, chosen action)
and asked only to rewrite them into prose. It never computes a score, decides
an action, or invents a fact, and nothing it returns is parsed back into a
decision. That keeps the brief's non-negotiable intact -- rules compute,
thresholds decide, AI only phrases.

Providers are pluggable via ``FINGUARD_LLM_PROVIDER``:

    none      -> the composer paragraph, unchanged (default)
    gemini    -> Google Gemini (google-genai, GEMINI_API_KEY)
    anthropic -> Claude (anthropic SDK, ANTHROPIC_API_KEY)

Every response is cached to disk keyed on the case facts, so a live call never
happens twice, and any failure -- no key, no package, a timeout, a blank reply
-- degrades silently to the composer paragraph. The demo can never hang on it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_CACHE_DIR,
    LLM_MAX_TOKENS,
    LLM_PROVIDER,
)

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


def active_provider() -> str:
    """The provider that will actually be used, given config and keys.

    Falls back to ``none`` when the selected provider has no key, so a
    half-configured ``.env`` degrades to the composer rather than erroring.
    """
    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        return "gemini"
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return "anthropic"
    return "none"


def _cache_key(case: dict[str, Any]) -> str:
    """Keyed on the facts and the provider, so a changed case regenerates."""
    payload = json.dumps(
        {
            "provider": active_provider(),
            "account": case["account_id"],
            "score": case["score"],
            "breakdown": [(r["rule_id"], r["points"]) for r in case["breakdown"]],
            "action": (case.get("recommended_action") or {}).get("code"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def _cached(key: str) -> str | None:
    path = LLM_CACHE_DIR / f"{key}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _store(key: str, text: str) -> None:
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (LLM_CACHE_DIR / f"{key}.txt").write_text(text, encoding="utf-8")


def _facts(case: dict[str, Any]) -> str:
    return json.dumps(
        {
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
            "evidence": case.get("evidence", [])[:6],
            "profile": case.get("profile"),
            "composed_narrative": case.get("summary"),
        },
        indent=2,
    )


def _call_gemini(case: dict[str, Any]) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_facts(case),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=LLM_MAX_TOKENS,
            temperature=0.4,
        ),
    )
    return (response.text or "").strip()


def _call_anthropic(case: dict[str, Any]) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _facts(case)}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def narrate(case: dict[str, Any]) -> tuple[str, str]:
    """Return ``(narrative, source)`` where source is composer | cache | <provider>.

    Never raises. ``case['summary']`` is the composer paragraph and is the
    fallback for every path, so the analyst always gets a complete case.
    """
    provider = active_provider()
    composed = case["summary"]

    if provider == "none":
        return composed, "composer"

    key = _cache_key(case)
    hit = _cached(key)
    if hit is not None:
        return hit, "cache"

    try:
        text = _call_gemini(case) if provider == "gemini" else _call_anthropic(case)
        if not text:
            return composed, "composer"
        _store(key, text)
        return text, provider
    except Exception:
        # Offline, missing package, rate limited, malformed response -- all one
        # outcome: the deterministic composer paragraph, which is always valid.
        return composed, "composer"
