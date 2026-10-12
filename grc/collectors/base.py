"""Collector framework.

A *check* is configured in engagement/collectors.yaml. Running it calls a
collector function that returns a CheckResult. The result is written as:

  engagement/evidence/collected/<EV-ID>.json   snapshot (metadata only, no secrets/PII)
  engagement/evidence/collected.yaml           machine-owned evidence index entries

Humans own evidence/index.yaml; machines own collected.yaml. Nothing a
collector does can mark a control 'verified' - that still requires a reviewed
PR that cites the evidence.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

PASS, FAIL, ERROR, SKIPPED = "pass", "fail", "error", "skipped"


class MissingCredentials(Exception):
    """Raised when a collector's credentials aren't configured. The check is skipped, not failed."""


@dataclass
class CheckResult:
    result: str                      # pass | fail | error | skipped
    summary: str                     # one line for reports and the evidence title suffix
    details: dict = field(default_factory=dict)   # metadata only: counts, settings, ids
    findings: list[str] = field(default_factory=list)  # human-readable reasons for fail

    def digest(self) -> str:
        canon = json.dumps({"result": self.result, "details": self.details, "findings": self.findings},
                           sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canon.encode()).hexdigest()


REGISTRY: dict[str, Callable[..., CheckResult]] = {}


def collector(name: str):
    def wrap(fn):
        REGISTRY[name] = fn
        return fn
    return wrap


SANDBOXED_SECRETS = {"DRATA_API_KEY", "ANTHROPIC_API_KEY", "JIRA_API_TOKEN", "MS_CLIENT_SECRET",
                     "MLFLOW_TRACKING_TOKEN"}
# Non-secret settings (repository variables). In sandbox mode they get harmless defaults.
SANDBOX_SETTINGS = {"JIRA_BASE_URL": "https://sandbox.atlassian.net", "JIRA_EMAIL": "sandbox@example.com",
                    "MS_TENANT_ID": "sandbox-tenant", "MS_CLIENT_ID": "sandbox-client",
                    "MLFLOW_TRACKING_URI": "https://mlflow.sandbox.example"}


def env(name: str) -> str:
    from .. import sandbox
    if sandbox.active() and name in SANDBOXED_SECRETS:
        return "sandbox"
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingCredentials(f"{name} is not set")
    return value


def setting(name: str) -> str:
    """A non-secret setting such as a base URL (repository variable)."""
    from .. import sandbox
    value = os.environ.get(name, "").strip()
    if not value and sandbox.active() and name in SANDBOX_SETTINGS:
        return SANDBOX_SETTINGS[name]
    if not value:
        raise MissingCredentials(f"{name} is not set")
    return value


def parse_time(value) -> dt.datetime | None:
    """ISO-8601 (with Z or offset) or epoch milliseconds -> aware UTC datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        return dt.datetime.fromtimestamp(int(value) / 1000, dt.timezone.utc)
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":   # Jira style +0000
        s = s[:-2] + ":" + s[-2:]
    # Python 3.10's fromisoformat wants 0, 3 or 6 fractional digits (Graph sends 7, some APIs 1-2)
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def match(name: str, wanted: list[str]) -> str | None:
    low = (name or "").lower()
    for w in wanted:
        if w.lower() in low:
            return w
    return None


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def run_check(name: str, params: dict) -> CheckResult:
    fn = REGISTRY.get(name)
    if fn is None:
        return CheckResult(ERROR, f"Unknown collector '{name}'")
    try:
        return fn(**(params or {}))
    except MissingCredentials as exc:
        return CheckResult(SKIPPED, f"Skipped: {exc}")
    except Exception as exc:  # network/API errors must not crash the whole run
        return CheckResult(ERROR, f"{type(exc).__name__}: {exc}"[:300])


def as_jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))
