"""Deterministic prompt templates for AI inference.

PROMPT_VERSION is bumped only when the prompt contract changes — it is part of
the auditability key (inference_id, prompt_version, model_id, timestamp).
The system prompt mirrors the benchmark runner (benchmark-spec.md §6/§7) so
benchmark evidence stays representative of production behavior.
"""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "v1.0.0"

SYSTEM_PROMPT = (
    "You are the market-context analysis module of a paper-trading research system. "
    "You ONLY propose directional entries. You NEVER control risk, lot size, exposure, "
    "margin, execution, exit, or compounding - those belong to the system.\n"
    "Respond with EXACTLY one valid JSON object and nothing else: "
    '{"direction": "BUY"|"SELL"|"NO-TRADE", '
    '"confidence": 0.0, "reason": "short string"}\n'
    "- direction: BUY or SELL only when the supplied context clearly "
    "supports it; otherwise NO-TRADE.\n"
    "- confidence: number 0.0 to 1.0.\n"
    "- reason: cite only facts present in the supplied context. "
    "Never invent prices, levels, or news.\n"
    "- If context is insufficient, conflicting, or ambiguous -> NO-TRADE with low confidence."
)

USER_TEMPLATE = "Market context JSON:\n{context}\n\nOutput the JSON decision object now."


def build_user_prompt(context: dict[str, Any]) -> str:
    """Deterministic, sorted-key JSON embedding so every call is reproducible."""
    return USER_TEMPLATE.format(context=json.dumps(context, sort_keys=True))
