"""Jira collectors: prove that ticket-based processes operate (incidents, changes, approvals, concerns).

Settings: JIRA_BASE_URL (e.g. https://acme.atlassian.net) and JIRA_EMAIL as repository variables;
JIRA_API_TOKEN as a secret (a read-only user's API token). Jira Cloud REST API v3.
"""
from __future__ import annotations

import base64

from . import http
from .base import FAIL, PASS, CheckResult, collector, env, parse_time, setting, utcnow

MAX_ISSUES = 2000
MAX_PAGES = 100


def _headers() -> dict:
    raw = f"{setting('JIRA_EMAIL')}:{env('JIRA_API_TOKEN')}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode(), "Accept": "application/json"}


def search(jql: str, fields: list[str], limit: int = MAX_ISSUES) -> tuple[list[dict], bool]:
    """Enhanced JQL search (POST /rest/api/3/search/jql, token pagination). Returns (issues, truncated)."""
    url = setting("JIRA_BASE_URL").rstrip("/") + "/rest/api/3/search/jql"
    issues, token, seen = [], None, set()
    for _ in range(MAX_PAGES):
        body = {"jql": jql, "fields": fields, "maxResults": 100}
        if token:
            body["nextPageToken"] = token
        page = http.request("POST", url, headers=_headers(), body=body) or {}
        batch = page.get("issues") or []
        issues.extend(batch)
        token = page.get("nextPageToken")
        more = bool(token) and not page.get("isLast") and bool(batch) and token not in seen
        if len(issues) >= limit:
            return issues[:limit], more or len(issues) > limit
        if not more:
            return issues, False
        seen.add(token)
    return issues, True


def _name(v) -> str | None:
    if isinstance(v, dict):
        return v.get("displayName") or v.get("name") or v.get("value") or v.get("emailAddress")
    return v


@collector("jira.issues")
def issues(jql: str, min_count: int = 0, max_open_age_days: int | None = None, require_assignee: bool = False,
           require_fields: list[str] | None = None, resolved_within_days: int | None = None) -> CheckResult:
    """Tickets matching a JQL query, e.g. AI incidents, change requests, model release approvals, concerns.

    Fails if: fewer than min_count; any OPEN ticket is older than max_open_age_days; any ticket has no
    assignee (require_assignee) or an empty required field (e.g. an approval field); any RESOLVED ticket
    took longer than resolved_within_days.
    """
    require_fields = require_fields or []
    fields = ["summary", "status", "assignee", "created", "resolutiondate"] + require_fields
    items, truncated = search(jql, fields)
    now = utcnow()
    rows, old_open, unassigned, missing, slow = [], [], [], {}, []
    for it in items:
        f = it.get("fields") or {}
        key = it.get("key")
        cat = ((f.get("status") or {}).get("statusCategory") or {}).get("key")
        created, resolved = parse_time(f.get("created")), parse_time(f.get("resolutiondate"))
        is_open = cat != "done"
        rows.append({"key": key, "status": (f.get("status") or {}).get("name"), "open": is_open,
                     "created": created.date().isoformat() if created else None,
                     "resolved": resolved.date().isoformat() if resolved else None,
                     "assignee": bool(f.get("assignee"))})
        if is_open and max_open_age_days is not None and created and (now - created).days > max_open_age_days:
            old_open.append(key)
        if require_assignee and not f.get("assignee"):
            unassigned.append(key)
        for rf in require_fields:
            if f.get(rf) in (None, "", [], {}):
                missing.setdefault(rf, []).append(key)
        if resolved_within_days is not None and created and resolved and (resolved - created).days > resolved_within_days:
            slow.append(key)
    findings = []
    if len(items) < min_count:
        findings.append(f"only {len(items)} matching issue(s); expected at least {min_count}")
    if old_open:
        findings.append(f"{len(old_open)} open issue(s) older than {max_open_age_days} days: {', '.join(old_open[:15])}")
    if unassigned:
        findings.append(f"{len(unassigned)} issue(s) without an assignee: {', '.join(unassigned[:15])}")
    for rf, keys in missing.items():
        findings.append(f"{len(keys)} issue(s) with empty '{rf}': {', '.join(keys[:15])}")
    if slow:
        findings.append(f"{len(slow)} issue(s) resolved after more than {resolved_within_days} days: {', '.join(slow[:15])}")
    n_open = sum(r["open"] for r in rows)
    return CheckResult(FAIL if findings else PASS, f"{len(rows)} issues ({n_open} open)" + (" [truncated]" if truncated else ""),
                       {"jql": jql, "count": len(rows), "open": n_open, "truncated": truncated,
                        "items": [r["key"] for r in rows], "issues": rows[:500]}, findings)
