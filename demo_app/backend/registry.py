"""Page and action registry for the demo app (``docs/interfaces.md`` section 15).

The SDK reports these numeric codes through ``setPage`` and ``markAction``.
This is the single place where pages and actions are defined; the policy
work in P4 attaches action sensitivities to ``ActionSpec``.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    code: int


PAGES: dict[str, int] = {
    "home": 1,
    "write": 2,
    "form": 3,
    "payees": 4,
    "reports": 5,
    "collect": 6,
    "settings": 7,
}

ACTIONS: dict[str, ActionSpec] = {
    "add_payee": ActionSpec(code=1),
    "export_report": ActionSpec(code=2),
}


def registry_payload() -> dict:
    return {
        "pages": dict(PAGES),
        "actions": {name: spec.code for name, spec in ACTIONS.items()},
    }
