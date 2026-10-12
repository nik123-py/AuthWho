"""Background policy monitor (proposal Section 8, step 8).

Runs in the worker after every trust update. It classifies the update with the
session's policy and records a decision only when the session's trust level
changes, so the decisions table tells the story of a session without one row
per window. A strong deviation asks the application for step-up; critical
(confirmed automation) ends the session. Roles exempted in the policy are never
acted on. Action requests and step-up results are judged by the session API.
"""

from __future__ import annotations

from typing import Any, Protocol

from server.policy.decisions import build_decision
from server.policy.engine import classify


class Control(Protocol):
    def publish_decision(self, decision: dict) -> None: ...

    def require_step_up(self, session_id: str, decision_id: str) -> None: ...

    def terminate(self, session_id: str, decision_id: str) -> None: ...


class PolicyMonitor:
    def __init__(self, repo, control: Control) -> None:
        self.repo = repo
        self.control = control
        self._levels: dict[str, str] = {}

    def on_update(self, update: dict[str, Any]) -> dict[str, Any] | None:
        sid = update["session_id"]
        ctx = self.repo.session_context(sid)
        if ctx is None:
            return None
        policy, exempt = self.repo.load_policy(ctx["app_id"], ctx["role"])
        if exempt:
            return None
        level = classify(update, policy)
        if self._levels.get(sid) == level:
            return None
        self._levels[sid] = level
        decision = build_decision(ctx, "trust_update", update, policy)
        self.repo.insert_decision(decision)
        self.control.publish_decision(decision)
        if decision["outcome"] == "step_up":
            self.control.require_step_up(sid, decision["decision_id"])
        elif decision["outcome"] == "terminate":
            self.control.terminate(sid, decision["decision_id"])
        return decision

    def forget(self, session_id: str) -> None:
        self._levels.pop(session_id, None)
