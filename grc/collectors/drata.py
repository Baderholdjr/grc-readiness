"""Drata collectors (Drata Public API v2).

Credentials: DRATA_API_KEY (read-only key). Optional DRATA_API_BASE for other
regions (default https://public-api.drata.com/public/v2).
Reference: https://developers.drata.com/openapi/reference/v2/overview/
"""
from __future__ import annotations

import datetime as dt
import os

from . import http
from .base import FAIL, PASS, CheckResult, collector, env, utcnow


def _base() -> str:
    return os.environ.get("DRATA_API_BASE", "https://public-api.drata.com/public/v2").rstrip("/")


def _get(path: str, params: dict | None = None):
    headers = {"Authorization": f"Bearer {env('DRATA_API_KEY')}", "Accept": "application/json"}
    return http.request("GET", f"{_base()}{path}", headers=headers, params=params)


def _all(path: str, params: dict | None = None, limit: int = 5000) -> list[dict]:
    """Follow Drata's cursor pagination."""
    items, cursor = [], None
    while True:
        q = {"size": 500, **(params or {})}
        if cursor:
            q["cursor"] = cursor
        page = _get(path, q) or {}
        items.extend(page.get("data", []))
        cursor = (page.get("pagination") or {}).get("cursor")
        if not cursor or len(items) >= limit:
            return items


def _date(value) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(str(value)[:10])


def _match(name: str, wanted: list[str]) -> str | None:
    low = name.lower()
    for w in wanted:
        if w.lower() in low:
            return w
    return None


@collector("drata.policies")
def policies(names: list[str], max_age_days: int | None = None) -> CheckResult:
    """Named policies exist, are approved, and are not past their renewal date."""
    today = utcnow().date()
    found: dict[str, dict] = {}
    for p in _all("/policies"):
        w = _match(p.get("name", ""), names)
        if w and w not in found:
            found[w] = p
    findings, rows = [], []
    for w in names:
        p = found.get(w)
        if not p:
            findings.append(f"policy matching '{w}' not found in Drata")
            continue
        approved, renewal = _date(p.get("approvedAt")), _date(p.get("renewalDate"))
        row = {"name": p.get("name"), "version": p.get("version"), "status": p.get("status"),
               "approved_at": approved.isoformat() if approved else None,
               "renewal_date": renewal.isoformat() if renewal else None}
        rows.append(row)
        if not approved:
            findings.append(f"'{p.get('name')}' has no approval date")
        if renewal and renewal < today:
            findings.append(f"'{p.get('name')}' renewal was due {renewal}")
        if max_age_days and approved and (today - approved).days > max_age_days:
            findings.append(f"'{p.get('name')}' approved {approved}, older than {max_age_days} days")
    return CheckResult(FAIL if findings else PASS,
                       f"{len(rows)}/{len(names)} policies found and approved", {"policies": rows}, findings)


@collector("drata.risks")
def risks(title_contains: list[str] | None = None, min_count: int = 1,
          require_owner: bool = True, require_treatment: bool = True) -> CheckResult:
    """The (AI) risk register is populated and every risk has an owner and treatment."""
    items = _all("/risks-search")
    if title_contains:
        items = [r for r in items if _match(f"{r.get('title', '')} {r.get('description', '')}", title_contains)]
    no_owner = [r.get("riskId") for r in items if require_owner and not r.get("owners")]
    no_treat = [r.get("riskId") for r in items if require_treatment and not r.get("treatmentPlan")]
    status: dict[str, int] = {}
    for r in items:
        status[str(r.get("status"))] = status.get(str(r.get("status")), 0) + 1
    findings = []
    if len(items) < min_count:
        findings.append(f"only {len(items)} matching risk(s); expected at least {min_count}")
    if no_owner:
        findings.append(f"{len(no_owner)} risk(s) without an owner: {', '.join(map(str, no_owner[:15]))}")
    if no_treat:
        findings.append(f"{len(no_treat)} risk(s) without a treatment plan: {', '.join(map(str, no_treat[:15]))}")
    details = {"filter": title_contains, "count": len(items), "by_status": status,
               "without_owner": no_owner[:50], "without_treatment": no_treat[:50]}
    return CheckResult(FAIL if findings else PASS, f"{len(items)} risks; {len(no_owner)} unowned, {len(no_treat)} untreated",
                       details, findings)


@collector("drata.vendors")
def vendors(names: list[str] | None = None, category: str | None = None) -> CheckResult:
    """AI suppliers are in the vendor program and their reviews are current."""
    today = utcnow().date()
    items = _all("/vendors")
    if category:
        items = [v for v in items if str(v.get("category", "")).upper() == category.upper()]
    selected = [v for v in items if not names or _match(v.get("name", ""), names)]
    findings, rows = [], []
    if names:
        have = {_match(v.get("name", ""), names) for v in selected}
        for w in names:
            if w not in have:
                findings.append(f"vendor '{w}' is not in the Drata vendor program")
    for v in selected:
        renewal = _date(v.get("renewalDate"))
        rows.append({"name": v.get("name"), "risk": v.get("risk"), "status": v.get("status"),
                     "renewal_date": renewal.isoformat() if renewal else None,
                     "renewal_status": v.get("renewalDateStatus")})
        if renewal and renewal < today:
            findings.append(f"'{v.get('name')}' review/renewal overdue since {renewal}")
        if not v.get("risk"):
            findings.append(f"'{v.get('name')}' has no risk rating")
    return CheckResult(FAIL if findings else PASS, f"{len(rows)} vendor(s) checked", {"vendors": rows}, findings)


@collector("drata.monitoring_tests")
def monitoring_tests(workspace_id: int, name_contains: list[str]) -> CheckResult:
    """Selected Drata monitoring tests are currently passing."""
    tests = [t for t in _all(f"/workspaces/{workspace_id}/monitoring-tests") if _match(t.get("name", ""), name_contains)]
    rows = [{"test_id": t.get("testId"), "name": t.get("name"), "result": t.get("checkResultStatus"),
             "last_passed_at": t.get("lastPassedAt"), "failed_since": t.get("failedSince")} for t in tests]
    findings = [f"'{r['name']}' is {r['result']}" for r in rows if r["result"] != "PASSED"]
    if not rows:
        findings.append(f"no monitoring tests match {name_contains}")
    return CheckResult(FAIL if findings else PASS,
                       f"{sum(r['result'] == 'PASSED' for r in rows)}/{len(rows)} monitoring tests passing",
                       {"tests": rows}, findings)


@collector("drata.training")
def training(field: str = "aiAwarenessTrainingStatus", min_pass_rate: float = 0.95) -> CheckResult:
    """Training completion rate across in-scope personnel (counts only, no names)."""
    counts = {}
    for status in ("PASS", "FAIL", "MISCONFIGURED", "NOT_ASSESSED"):
        page = _get("/personnel-search", {f"{field}[]": status, "includeTotalCount": True, "size": 1}) or {}
        counts[status] = int((page.get("pagination") or {}).get("totalCount") or 0)
    in_scope = sum(counts.values())
    rate = counts["PASS"] / in_scope if in_scope else 0.0
    findings = []
    if in_scope == 0:
        findings.append(f"no in-scope personnel reported for {field}")
    elif rate < min_pass_rate:
        findings.append(f"completion {rate:.0%} below target {min_pass_rate:.0%}")
    return CheckResult(FAIL if findings else PASS, f"{field}: {counts['PASS']}/{in_scope} complete ({rate:.0%})",
                       {"field": field, "counts": counts, "pass_rate": round(rate, 3)}, findings)
