"""How the engine signs in to the Anthropic API: an API key, or Workload Identity Federation (no stored key).

Precedence: `ANTHROPIC_API_KEY` when it is set; otherwise federation, when `ANTHROPIC_FEDERATION_RULE_ID`,
`ANTHROPIC_ORGANIZATION_ID` and `ANTHROPIC_SERVICE_ACCOUNT_ID` are set (and `ANTHROPIC_WORKSPACE_ID` for a rule that
covers several workspaces). The identity token comes from GitHub Actions (the job needs `id-token: write`), requested
fresh for each exchange because GitHub's tokens last about 5 minutes, or from the file `ANTHROPIC_IDENTITY_TOKEN_FILE`
names. It is exchanged at Anthropic's token endpoint for a short-lived access token, cached in memory until shortly
before it expires. Neither token is written anywhere or printed.
"""
from __future__ import annotations

import os
import time
import urllib.parse

AUDIENCE = "https://api.anthropic.com"
TOKEN_URL = os.environ.get("ANTHROPIC_OAUTH_TOKEN_URL") or "https://api.anthropic.com/v1/oauth/token"
FEDERATION_VARS = ("ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_SERVICE_ACCOUNT_ID")
_cache: dict = {}


class AuthUnavailable(Exception):
    """No usable credentials, or the exchange was refused. The message is safe to show (no token in it)."""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def federation_configured() -> bool:
    return all(_env(v) for v in FEDERATION_VARS)


def _identity_source() -> str | None:
    if _env("ANTHROPIC_IDENTITY_TOKEN_FILE"):
        return "file"
    if _env("ACTIONS_ID_TOKEN_REQUEST_URL") and _env("ACTIONS_ID_TOKEN_REQUEST_TOKEN"):
        return "github"
    return None


def method() -> str | None:
    """'key', 'federation', or None when nothing usable is configured."""
    if _env("ANTHROPIC_API_KEY"):
        return "key"
    if federation_configured() and _identity_source():
        return "federation"
    return None


def missing() -> str:
    """Why no credentials are usable, in one line, for the run's report."""
    if federation_configured() and not _identity_source():
        return ("workload identity is configured, but this job can't get an identity token: give the workflow "
                "`id-token: write` (Actions) or set ANTHROPIC_IDENTITY_TOKEN_FILE")
    partial = [v for v in FEDERATION_VARS if _env(v)]
    if partial:
        absent = [v for v in FEDERATION_VARS if not _env(v)]
        return f"workload identity is only partly configured: {', '.join(absent)} not set"
    return "no Anthropic credentials: set ANTHROPIC_API_KEY, or the workload identity variables (see docs/AUTOMATION.md)"


def _identity_token(http) -> str:
    path = _env("ANTHROPIC_IDENTITY_TOKEN_FILE")
    if path:
        try:
            token = open(path, encoding="utf-8").read().strip()
        except OSError as exc:
            raise AuthUnavailable(f"can't read ANTHROPIC_IDENTITY_TOKEN_FILE ({exc.__class__.__name__})") from exc
        if not token:
            raise AuthUnavailable("ANTHROPIC_IDENTITY_TOKEN_FILE is empty")
        return token
    url = _env("ACTIONS_ID_TOKEN_REQUEST_URL")
    sep = "&" if "?" in url else "?"
    try:
        resp = http.request("GET", f"{url}{sep}audience={urllib.parse.quote(AUDIENCE, safe='')}",
                            headers={"Authorization": f"Bearer {_env('ACTIONS_ID_TOKEN_REQUEST_TOKEN')}"}, retries=3, timeout=30)
    except Exception as exc:
        raise AuthUnavailable(f"GitHub didn't issue an identity token ({str(exc)[:120]})") from exc
    token = (resp or {}).get("value") if isinstance(resp, dict) else None
    if not token:
        raise AuthUnavailable("GitHub's identity token response had no token")
    return token


def _exchange(http) -> tuple[str, float]:
    body = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": _identity_token(http),
            "federation_rule_id": _env("ANTHROPIC_FEDERATION_RULE_ID"),
            "organization_id": _env("ANTHROPIC_ORGANIZATION_ID"),
            "service_account_id": _env("ANTHROPIC_SERVICE_ACCOUNT_ID")}
    if _env("ANTHROPIC_WORKSPACE_ID"):
        body["workspace_id"] = _env("ANTHROPIC_WORKSPACE_ID")
    try:
        resp = http.request("POST", TOKEN_URL, body=body, retries=3, timeout=60)
    except Exception as exc:
        s = str(exc)
        if "401" in s[:40] or "authentication" in s.lower():
            raise AuthUnavailable("Anthropic refused the workload identity exchange. The Console's Workload identity "
                                  "page (Authentication history) shows why; usually the rule's subject doesn't match "
                                  "this repository or event") from exc
        raise AuthUnavailable(f"the workload identity exchange failed ({s[:160]})") from exc
    token = (resp or {}).get("access_token") if isinstance(resp, dict) else None
    if not token:
        raise AuthUnavailable("the workload identity exchange returned no access token")
    try:
        life = float((resp or {}).get("expires_in") or 300)
    except (TypeError, ValueError):
        life = 300.0
    return token, time.monotonic() + max(life - 60, 30)


def headers(http=None) -> dict:
    """Request headers that authenticate one Anthropic API call. Raises AuthUnavailable."""
    key = _env("ANTHROPIC_API_KEY")
    if key:
        return {"x-api-key": key}
    if not (federation_configured() and _identity_source()):
        raise AuthUnavailable(missing())
    if http is None:
        from .collectors import http
    rule = _env("ANTHROPIC_FEDERATION_RULE_ID")
    hit = _cache.get(rule)
    if not hit or hit[1] <= time.monotonic():
        hit = _cache[rule] = _exchange(http)
    return {"authorization": f"Bearer {hit[0]}"}
