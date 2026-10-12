"""Decision records (docs/interfaces.md section 11).

``build_decision`` turns a trust update and the reason it is being judged
(a background trust update, an action request or a step-up result) into the
row stored in the append-only ``decisions`` table. Every decision carries the
evidence behind it: trust, confidence, the per-channel block, bot flags, the
windows involved, model and policy versions, and one plain-language sentence.
"""

from __future__ import annotations

import uuid
from typing import Any

from server.policy.engine import Policy, classify, decide, explain

PASSED_EXPLANATION = "The user passed the identity check, so the session continues."


def build_decision(session: dict[str, str], trigger: str, update: dict[str, Any] | None, policy: Policy,
                   action_code: str | None = None, step_up_result: str | None = None) -> dict[str, Any]:
    sensitivity = None
    if trigger == "action_request":
        sensitivity = policy.action_sensitivity.get(action_code or "", "low")

    if step_up_result == "passed":
        level = classify(update, policy)
        outcome, allowed, text = "continue", None, PASSED_EXPLANATION
    else:
        failed = step_up_result == "failed"
        level = classify(update, policy, step_up_failed=failed)
        outcome, allowed = decide(level, sensitivity)
        text = explain(level, update, step_up_failed=failed, policy=policy)
    if trigger != "action_request":
        allowed = None

    channels = (update or {}).get("channels", {})
    scored = update is not None and update.get("state") == "scored"
    return {
        "decision_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "user_id": session["user_id"],
        "app_id": session["app_id"],
        "role": session["role"],
        "trigger": trigger,
        "action_code": action_code if trigger == "action_request" else None,
        "action_sensitivity": sensitivity,
        "level": level,
        "outcome": outcome,
        "action_allowed": allowed,
        "trust": update["trust"] if scored else None,
        "confidence": update["confidence"] if scored else None,
        "channels": channels,
        "bot_flags": (update or {}).get("bot_flags", []),
        "window_ids": [c["window_id"] for c in channels.values() if c.get("window_id") and c.get("fresh")],
        "model_versions": (update or {}).get("model_versions", {}),
        "policy_version": policy.version,
        "explanation": text,
        "step_up_result": step_up_result,
    }
