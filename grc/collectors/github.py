"""GitHub collectors: prove that engineering controls operate in the client's repos.

Credentials: GH_COLLECTOR_TOKEN - a fine-grained token with read-only access to
the client repositories (Metadata, Contents, Pull requests, Actions; plus
Administration:read to see classic branch protection). For checks against the
engagement repo itself, GITHUB_TOKEN is used as a fallback.
"""
from __future__ import annotations

import datetime as dt
import os

from . import http
from .base import FAIL, PASS, CheckResult, MissingCredentials, collector, utcnow

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


def _token(repo: str) -> str:
    tok = os.environ.get("GH_COLLECTOR_TOKEN", "").strip()
    if tok:
        return tok
    if repo.lower() == os.environ.get("GITHUB_REPOSITORY", "").lower() and os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    raise MissingCredentials("GH_COLLECTOR_TOKEN is not set")


def _get(repo: str, path: str, params: dict | None = None):
    headers = {"Authorization": f"Bearer {_token(repo)}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    return http.request("GET", f"{API}/repos/{repo}{path}", headers=headers, params=params)


@collector("github.branch_protection")
def branch_protection(repo: str, branch: str = "main", min_approvals: int = 1,
                      require_code_owner_review: bool = False, required_checks: list[str] | None = None,
                      block_force_push: bool = True) -> CheckResult:
    """Effective protection from rulesets (and classic protection if readable)."""
    approvals, code_owner, checks, force_blocked, sources = 0, False, set(), False, []
    rules = _get(repo, f"/rules/branches/{branch}") or []
    for r in rules:
        t, p = r.get("type"), r.get("parameters") or {}
        if t == "pull_request":
            approvals = max(approvals, int(p.get("required_approving_review_count", 0)))
            code_owner = code_owner or bool(p.get("require_code_owner_review"))
        elif t == "required_status_checks":
            checks |= {c.get("context") for c in p.get("required_status_checks", [])}
        elif t == "non_fast_forward":
            force_blocked = True
    if rules:
        sources.append("rulesets")
    try:
        cp = _get(repo, f"/branches/{branch}/protection")
        rv = cp.get("required_pull_request_reviews") or {}
        approvals = max(approvals, int(rv.get("required_approving_review_count", 0)))
        code_owner = code_owner or bool(rv.get("require_code_owner_reviews"))
        checks |= set((cp.get("required_status_checks") or {}).get("contexts", []))
        force_blocked = force_blocked or not (cp.get("allow_force_pushes") or {}).get("enabled", False)
        sources.append("classic")
    except http.HTTPError as exc:
        if exc.status not in (403, 404):
            raise
    findings = []
    if approvals < min_approvals:
        findings.append(f"requires {approvals} approval(s); expected >= {min_approvals}")
    if require_code_owner_review and not code_owner:
        findings.append("code owner review is not required")
    missing = sorted(set(required_checks or []) - checks)
    if missing:
        findings.append(f"required status checks missing: {', '.join(missing)}")
    if block_force_push and not force_blocked:
        findings.append("force pushes are not blocked")
    details = {"repo": repo, "branch": branch, "required_approvals": approvals,
               "code_owner_review": code_owner, "required_checks": sorted(c for c in checks if c),
               "force_push_blocked": force_blocked, "sources": sources}
    status = FAIL if findings or not sources else PASS
    if not sources:
        findings.append("no branch protection or ruleset applies to this branch")
    return CheckResult(status, f"{repo}@{branch}: {approvals} approval(s), checks={details['required_checks'] or 'none'}",
                       details, findings)


@collector("github.pr_reviews")
def pr_reviews(repo: str, base: str = "main", days: int = 90, label: str | None = None,
               min_rate: float = 1.0, max_prs: int = 100) -> CheckResult:
    """Share of merged PRs in the window approved by someone other than the author."""
    since = utcnow() - dt.timedelta(days=days)
    merged = []
    page = 1
    while len(merged) < max_prs:
        prs = _get(repo, "/pulls", {"state": "closed", "base": base, "sort": "updated", "direction": "desc",
                                    "per_page": 100, "page": page}) or []
        if not prs:
            break
        for pr in prs:
            if not pr.get("merged_at"):
                continue
            merged_at = dt.datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            if merged_at < since:
                continue
            if label and label not in {lab["name"] for lab in pr.get("labels", [])}:
                continue
            merged.append(pr)
        if dt.datetime.fromisoformat(prs[-1]["updated_at"].replace("Z", "+00:00")) < since:
            break
        page += 1
    approved, unapproved = 0, []
    for pr in merged[:max_prs]:
        author = (pr.get("user") or {}).get("login")
        reviews = _get(repo, f"/pulls/{pr['number']}/reviews", {"per_page": 100}) or []
        if any(r.get("state") == "APPROVED" and (r.get("user") or {}).get("login") != author for r in reviews):
            approved += 1
        else:
            unapproved.append(pr["number"])
    n = len(merged[:max_prs])
    rate = approved / n if n else 0.0
    findings = []
    if n == 0:
        findings.append(f"no merged PRs into {base} in the last {days} days" + (f" with label '{label}'" if label else ""))
    elif rate < min_rate:
        findings.append(f"{len(unapproved)} of {n} merged PRs had no independent approval: "
                        + ", ".join(f"#{x}" for x in unapproved[:20]))
    details = {"repo": repo, "base": base, "window_days": days, "label": label, "population": n,
               "independently_approved": approved, "approval_rate": round(rate, 3),
               "unapproved_prs": unapproved[:50]}
    return CheckResult(FAIL if findings else PASS,
                       f"{repo}: {approved}/{n} merged PRs independently approved ({days}d)", details, findings)


@collector("github.workflow_runs")
def workflow_runs(repo: str, workflow: str, branch: str = "main", days: int = 30,
                  min_runs: int = 1, max_failure_rate: float = 0.2) -> CheckResult:
    """A CI gate (e.g. model release gate) is running and passing."""
    since = (utcnow() - dt.timedelta(days=days)).date().isoformat()
    data = _get(repo, f"/actions/workflows/{workflow}/runs",
                {"branch": branch, "created": f">={since}", "per_page": 100, "status": "completed"}) or {}
    runs = data.get("workflow_runs", [])
    conclusions = [r.get("conclusion") for r in runs]
    failures = sum(c == "failure" for c in conclusions)
    rate = failures / len(runs) if runs else 0.0
    latest = runs[0] if runs else None
    findings = []
    if len(runs) < min_runs:
        findings.append(f"only {len(runs)} completed run(s) of {workflow} on {branch} in {days} days")
    if latest and latest.get("conclusion") != "success":
        findings.append(f"latest run concluded '{latest.get('conclusion')}'")
    if runs and rate > max_failure_rate:
        findings.append(f"failure rate {rate:.0%} exceeds {max_failure_rate:.0%}")
    details = {"repo": repo, "workflow": workflow, "branch": branch, "window_days": days, "runs": len(runs),
               "failures": failures, "latest_conclusion": latest.get("conclusion") if latest else None,
               "latest_run_url": latest.get("html_url") if latest else None,
               "latest_head_sha": latest.get("head_sha") if latest else None}
    return CheckResult(FAIL if findings else PASS,
                       f"{repo} {workflow}: {len(runs)} runs, {failures} failed ({days}d)", details, findings)


@collector("github.file_present")
def file_present(repo: str, path: str, ref: str = "main", max_age_days: int | None = None) -> CheckResult:
    """A policy/procedure/config file exists in the repo; records its blob sha and last change date."""
    try:
        meta = _get(repo, f"/contents/{path}", {"ref": ref})
    except http.HTTPError as exc:
        if exc.status == 404:
            return CheckResult(FAIL, f"{repo}:{path} not found", {"repo": repo, "path": path, "ref": ref},
                               [f"{path} does not exist on {ref}"])
        raise
    commits = _get(repo, "/commits", {"path": path, "sha": ref, "per_page": 1}) or []
    last = commits[0]["commit"]["committer"]["date"] if commits else None
    findings = []
    if max_age_days and last:
        age = (utcnow() - dt.datetime.fromisoformat(last.replace("Z", "+00:00"))).days
        if age > max_age_days:
            findings.append(f"last changed {age} days ago (review expected every {max_age_days} days)")
    details = {"repo": repo, "path": path, "ref": ref, "blob_sha": meta.get("sha"), "size": meta.get("size"),
               "last_changed": last, "url": meta.get("html_url")}
    return CheckResult(FAIL if findings else PASS, f"{repo}:{path} present (last changed {last})", details, findings)
