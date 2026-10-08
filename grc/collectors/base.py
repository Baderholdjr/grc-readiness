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


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingCredentials(f"{name} is not set")
    return value


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
