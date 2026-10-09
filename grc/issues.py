"""Sync gaps.yaml -> GitHub Issues + Milestones (one milestone per phase).

Idempotent: each issue carries a hidden marker `<!-- grc:GAP-01 -->` so reruns
update rather than duplicate. Closed/risk-accepted gaps close their issue.
gaps.yaml is the source of truth; edits made in the GitHub UI to title/body
are overwritten on the next sync (comments and assignees are left alone).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from .model import Engagement

API = os.environ.get("GITHUB_API_URL") or "https://api.github.com"
LABEL_COLORS = {"grc-gap": "183B4E", "severity:high": "B60205", "severity:medium": "FBCA04", "severity:low": "0E8A16"}


class GitHub:
    def __init__(self, repo: str, token: str):
        self.repo, self.token = repo, token

    def call(self, method: str, path: str, body: dict | None = None):
        url = path if path.startswith("http") else f"{API}/repos/{self.repo}{path}"
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None

    def paged(self, path: str):
        page = 1
        while True:
            sep = "&" if "?" in path else "?"
            items = self.call("GET", f"{path}{sep}per_page=100&page={page}")
            if not items:
                return
            yield from items
            page += 1


def _assignable(users: list[str]) -> list[str]:
    return [u for u in users if "/" not in u]  # teams can't be assignees


def _with_assignees(gh: "GitHub", method: str, path: str, payload: dict, log: list[str], gid: str):
    """Assignees without repo access make the whole request fail (422); retry without them."""
    try:
        return gh.call(method, path, payload)
    except urllib.error.HTTPError as exc:
        if exc.code == 422 and payload.get("assignees"):
            log.append(f"{gid}: could not assign {', '.join(payload['assignees'])} (no repo access?) - left unassigned")
            return gh.call(method, path, {k: v for k, v in payload.items() if k != "assignees"})
        raise


def overdue_marker(gid: str, due: str) -> str:
    return f"<!-- grc:overdue:{gid}:{due} -->"


def issue_body(model: Engagement, g: dict) -> str:
    reqs = model.requirement_index
    lines = [f"<!-- grc:{g['id']} -->",
             f"**Gap:** {g['id']} · **Area:** {g['area']} · **Severity:** {g.get('severity', 'n/a')}",
             f"**Owner:** {g.get('owner', 'unassigned')}"
             + (" (" + ", ".join(f"@{u}" for u in model.github_users(g.get("owner"))) + ")" if model.github_users(g.get("owner")) else "")
             + f" · **Due:** {g.get('due', 'n/a')} · **Phase:** {g.get('phase', 'n/a')}",
             "", "### What to verify / close", model.fmt(g["finding"]), "", "### Requirements"]
    for r in g.get("requirements", []):
        title = reqs.get(r, {}).get("title", "?")
        lines.append(f"- `{r}` {title} — [`engagement/controls/{r}.yaml`](../blob/main/engagement/controls/{r}.yaml)")
    lines += ["", "### Four-part evidence test (update the control YAML in a PR, not here)"]
    for t in model.playbook["evidence_test"]:
        lines.append(f"- [ ] **{t['label']}** — {model.fmt(t['question'])}")
    lines += ["", "### To close",
              "Open a PR that (1) adds the closure evidence to `engagement/evidence/index.yaml`, "
              "(2) updates the linked control files, and (3) sets this gap to `closed` with `closure_evidence`. "
              "CI rejects a closed gap without evidence.", "",
              "_Managed by `grc sync-issues` from `engagement/gaps.yaml`._"]
    return "\n".join(lines)


def write_issue_numbers(gaps_path: Path, mapping: dict[str, int]) -> None:
    """Insert/refresh `issue: N` under each gap id without disturbing comments."""
    text = gaps_path.read_text(encoding="utf-8").splitlines(keepends=True)
    out, i = [], 0
    while i < len(text):
        line = text[i]
        out.append(line)
        m = re.match(r"^(\s*)- id:\s*\"?(GAP-\d+)\"?\s*$", line)
        if m and m.group(2) in mapping:
            indent = m.group(1) + "  "
            # drop any existing issue line within this item
            j = i + 1
            block = []
            while j < len(text) and not re.match(r"^\s*- id:", text[j]) and (text[j].startswith(indent) or not text[j].strip()):
                if not re.match(rf"^{indent}issue:\s*\d+", text[j]):
                    block.append(text[j])
                j += 1
            out.append(f"{indent}issue: {mapping[m.group(2)]}\n")
            out.extend(block)
            i = j
            continue
        i += 1
    gaps_path.write_text("".join(out), encoding="utf-8")


def sync(model: Engagement, repo: str | None, token: str | None, dry_run: bool = True, write_back: bool = False) -> list[str]:
    log: list[str] = []
    if dry_run or not (repo and token):
        for g in model.gaps:
            state = "closed" if g["status"] in ("closed", "risk_accepted") else "open"
            log.append(f"[dry-run] {state:6} [{g['id']}] {g['area']}: {model.fmt(g['finding'])[:70]}")
        return log
    gh = GitHub(repo, token)

    # labels
    existing_labels = {lab["name"] for lab in gh.paged("/labels")}
    wanted = {"grc-gap"} | {f"severity:{g['severity']}" for g in model.gaps if g.get("severity")} \
        | {f"phase:{g['phase']}" for g in model.gaps if g.get("phase")}
    for name in sorted(wanted - existing_labels):
        gh.call("POST", "/labels", {"name": name, "color": LABEL_COLORS.get(name, "C5DEF5")})
        log.append(f"label created: {name}")

    # milestones per phase
    milestones = {m["title"]: m for m in gh.paged("/milestones?state=all")}
    ms_number = {}
    for ph in model.phases:
        title = f"{ph['label']} — {ph['objective']}"
        body = {"title": title, "due_on": f"{ph['end']}T23:59:59Z",
                "description": "Deliverables:\n" + "\n".join(f"- {d}" for d in ph["deliverables"])}
        if title in milestones:
            ms_number[ph["id"]] = milestones[title]["number"]
        else:
            ms = gh.call("POST", "/milestones", body)
            ms_number[ph["id"]] = ms["number"]
            log.append(f"milestone created: {title}")

    # issues
    found: dict[str, dict] = {}
    for iss in gh.paged("/issues?state=all&labels=grc-gap"):
        m = re.search(r"<!-- grc:(GAP-\d+) -->", iss.get("body") or "")
        if m:
            found[m.group(1)] = iss
    mapping = {}
    for g in model.gaps:
        labels = ["grc-gap"] + ([f"severity:{g['severity']}"] if g.get("severity") else []) \
            + ([f"phase:{g['phase']}"] if g.get("phase") else [])
        payload = {"title": f"[{g['id']}] {g['area']}: {model.fmt(g['finding'])[:90]}",
                   "body": issue_body(model, g), "labels": labels,
                   "state": "closed" if g["status"] in ("closed", "risk_accepted") else "open"}
        if g.get("phase") in ms_number:
            payload["milestone"] = ms_number[g["phase"]]
        users = _assignable(model.github_users(g.get("owner")))
        if users:
            payload["assignees"] = users
        if g["id"] in found:
            num = found[g["id"]]["number"]
            _with_assignees(gh, "PATCH", f"/issues/{num}", payload, log, g["id"])
            log.append(f"updated #{num} {g['id']} ({payload['state']})")
        else:
            state = payload.pop("state")
            iss = _with_assignees(gh, "POST", "/issues", payload, log, g["id"])
            num = iss["number"]
            if state == "closed":
                gh.call("PATCH", f"/issues/{num}", {"state": "closed"})
            log.append(f"created #{num} {g['id']}")
        mapping[g["id"]] = num
        # Overdue reminder: one comment per gap per due date, mentioning the owners.
        due = str(g.get("due") or "")
        if due and g["status"] in ("open", "in_progress") and dt.date.fromisoformat(due) < model.today:
            marker = overdue_marker(g["id"], due)
            comments = gh.call("GET", f"/issues/{num}/comments?per_page=100") or []
            if not any(marker in (c.get("body") or "") for c in comments):
                who = " ".join(f"@{u}" for u in model.github_users(g.get("owner"))) or f"**{g.get('owner', 'Owner')}**"
                gh.call("POST", f"/issues/{num}/comments", {"body": f"{marker}\n⏰ {who}: this gap was due **{due}**. "
                        "Please update it (or its due date) in `engagement/gaps.yaml` through a PR."})
                log.append(f"overdue reminder on #{num} {g['id']}")
    if write_back:
        write_issue_numbers(model.engagement_dir / "gaps.yaml", mapping)
        log.append("wrote issue numbers to gaps.yaml")
    return log
