"""Session control API (docs/interfaces.md section 11).

Called by the application backend with ``X-AuthWho-App-Key``:
- ``GET /v1/sessions/{id}/status``: active, step_up_required or terminated;
- ``POST /v1/sessions/{id}/actions``: judge a pending action with the latest
  trust update and the session's policy, record the decision and answer
  whether the action may proceed;
- ``POST /v1/sessions/{id}/step-up-result``: the application ran its own
  identity check (TOTP or password) and reports the result. A pass makes the
  session active again and restarts trust from full (the worker resets its
  engine); a failure is critical and ends the session.

The response to the application carries only a neutral sentence for the
person using the session, never scores or channels. Nothing here can disable,
lock or delete an account.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from server.collector.router import ApiError, AppKey
from server.policy.decisions import build_decision
from server.policy.engine import explain_for_user
from server.session.control import TERMINATED

router = APIRouter()


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    sensitivity: Literal["low", "medium", "high"] | None = None


class StepUpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool


def _parts(request: Request, session_id: uuid.UUID):
    st = request.app.state
    sid = str(session_id)
    ctx = st.policy_repo.session_context(sid)
    if ctx is None:
        raise ApiError(404, {"error": "unknown_session"})
    return st.session_control, st.policy_repo, sid, ctx


def _evidence(control, sid):
    """The latest trust update, unless a passed step-up is newer than it."""
    update = control.last_trust(sid)
    verified = control.verified_at(sid)
    if update is not None and verified is not None:
        at = datetime.fromisoformat(update["at"].replace("Z", "+00:00")).timestamp()
        if at <= verified:
            return None
    return update


@router.get("/v1/sessions/{session_id}/status", dependencies=[AppKey])
def session_status(session_id: uuid.UUID, request: Request):
    control, _repo, sid, _ctx = _parts(request, session_id)
    return {"status": control.status(sid) or TERMINATED, "decision_id": control.last_decision_id(sid)}


@router.post("/v1/sessions/{session_id}/actions", dependencies=[AppKey])
def session_action(session_id: uuid.UUID, body: ActionBody, request: Request):
    control, repo, sid, ctx = _parts(request, session_id)
    status = control.status(sid) or TERMINATED
    if status == TERMINATED:
        raise ApiError(409, {"error": "session_ended"})
    policy, exempt = repo.load_policy(ctx["app_id"], ctx["role"])
    if exempt:
        return {"decision_id": None, "outcome": "continue", "action_allowed": True,
                "explanation_for_user": explain_for_user("continue")}
    if body.action_code not in policy.action_sensitivity and body.sensitivity:
        policy = replace(policy, action_sensitivity={**policy.action_sensitivity, body.action_code: body.sensitivity})
    if status == "step_up_required":
        return {"decision_id": control.last_decision_id(sid), "outcome": "step_up", "action_allowed": False,
                "explanation_for_user": explain_for_user("step_up")}
    decision = build_decision(ctx, "action_request", _evidence(control, sid), policy, action_code=body.action_code)
    repo.insert_decision(decision)
    control.publish_decision(decision)
    if decision["outcome"] == "step_up":
        control.require_step_up(sid, decision["decision_id"])
    elif decision["outcome"] == "terminate":
        control.terminate(sid, decision["decision_id"])
    return {"decision_id": decision["decision_id"], "outcome": decision["outcome"],
            "action_allowed": decision["action_allowed"],
            "explanation_for_user": explain_for_user(decision["outcome"])}


@router.post("/v1/sessions/{session_id}/step-up-result", dependencies=[AppKey])
def step_up_result(session_id: uuid.UUID, body: StepUpBody, request: Request):
    control, repo, sid, ctx = _parts(request, session_id)
    if (control.status(sid) or TERMINATED) == TERMINATED:
        raise ApiError(409, {"error": "session_ended"})
    policy, _exempt = repo.load_policy(ctx["app_id"], ctx["role"])
    result = "passed" if body.passed else "failed"
    decision = build_decision(ctx, "step_up_result", control.last_trust(sid), policy, step_up_result=result)
    repo.insert_decision(decision)
    control.publish_decision(decision)
    if body.passed:
        control.mark_verified(sid, decision["decision_id"])
    else:
        control.terminate(sid, decision["decision_id"])
    return {"decision_id": decision["decision_id"], "outcome": decision["outcome"],
            "status": control.status(sid) or TERMINATED}
