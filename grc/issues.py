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
LABEL_COLORS = {"grc-gap": "183B4E", "grc-finding": "5319E7", "grc-review-action": "0E8A16", "grade:major": "B60205", "grade:minor": "FBCA04",
                "grade:ofi": "0E8A16", "severity:high": "B60205", "severity:medium": "FBCA04", "severity:low": "0E8A16"}


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
        lines.append(f"- `{r}` {title} — [`{model.record_dir}/controls/{r}.yaml`](../blob/main/{model.record_dir}/controls/{r}.yaml)")
    lines += ["", "### Four-part evidence test (update the control YAML in a PR, not here)"]
    for t in model.playbook["evidence_test"]:
        lines.append(f"- [ ] **{t['label']}** — {model.fmt(t['question'])}")
    lines += ["", "### To close",
              "Open a PR that (1) adds the closure evidence to `engagement/evidence/index.yaml`, "
              "(2) updates the linked control files, and (3) sets this gap to `closed` with `closure_evidence`. "
              "CI rejects a closed gap without evidence.", "",
              "_Managed by `grc sync-issues` from `engagement/gaps.yaml`._"]
    return "\n".join(lines)


def finding_body(model: Engagement, f: dict) -> str:
    req = model.requirement_index.get(f.get("requirement"), {})
    who = model.github_users(f.get("owner"))
    src = f["source"].replace("_", " ") + (f" {f['audit']}" + (f"/{f['workpaper']}" if f.get("workpaper") else "") if f.get("audit") else "")
    lines = [f"<!-- grc:{f['id']} -->",
             f"**{f['id']}** · **{f['grade'].upper()}** · `{f.get('requirement')}` {req.get('title', '')} · source: {src}",
             f"**Owner:** {f.get('owner') or 'unassigned'}" + (" (" + ", ".join(f"@{u}" for u in who) + ")" if who else "")
             + f" · **Due:** {f.get('due', 'n/a')} · **Status:** {f['status']}",
             "", "### Finding", f["description"], ""]
    if f.get("grade") == "ofi":
        lines += ["_Opportunity for improvement: no corrective action is required, but record what was decided._"]
    else:
        lines += ["### Corrective action lifecycle (update `engagement/findings.yaml` in a PR)",
                  f"- [{'x' if f.get('correction') else ' '}] **Correction**: fix the nonconformity itself",
                  f"- [{'x' if f.get('root_cause') else ' '}] **Root cause** identified",
                  f"- [{'x' if f.get('corrective_action') else ' '}] **Corrective action** planned (owner + due date)",
                  f"- [{'x' if f.get('evidence') else ' '}] **Implemented**, with evidence",
                  f"- [{'x' if (f.get('effectiveness') or {}).get('effective') else ' '}] **Effectiveness reviewed** "
                  "by someone other than the owner, with evidence",
                  "", "CI won't let this close without each step."]
    lines += ["", "_Managed by `grc sync-issues` from `engagement/findings.yaml`._"]
    return "\n".join(lines)


def tracked_items(model: Engagement) -> list[dict]:
    """Everything mirrored to Issues: gaps, findings and review actions, in one shape. A second framework's
    record in the same repository gets namespaced markers ("iso27001:GAP-01") and a [ISO 27001] title prefix."""
    items = _items(model)
    ns = model.namespace
    for it in items:
        it["gid"] = it["id"]
        if ns:
            it["id"] = f"{ns}:{it['gid']}"
            it["body"] = it["body"].replace(f"<!-- grc:{it['gid']} -->", f"<!-- grc:{it['id']} -->", 1)
            it["body"] = it["body"].replace("`engagement/", f"`{model.record_dir}/")
            it["title"] = f"[{model.catalog['framework'].get('short_name', ns)}] {it['title']}"
    return items


def _items(model: Engagement) -> list[dict]:
    items = []
    for g in model.gaps:
        items.append({"kind": "gap", "noun": "gap", "file": "gaps.yaml", "id": g["id"],
                      "title": f"[{g['id']}] {g['area']}: {model.fmt(g['finding'])[:90]}",
                      "body": issue_body(model, g),
                      "labels": ["grc-gap"] + ([f"severity:{g['severity']}"] if g.get("severity") else [])
                      + ([f"phase:{g['phase']}"] if g.get("phase") else []),
                      "open": g["status"] in ("open", "in_progress"), "owner": g.get("owner"),
                      "due": g.get("due"), "phase": g.get("phase")})
    for f in model.findings:
        items.append({"kind": "finding", "noun": "finding", "file": "findings.yaml", "id": f["id"],
                      "title": f"[{f['id']}] {f['grade']} · {f.get('requirement')}: {f['description'][:85]}",
                      "body": finding_body(model, f), "labels": ["grc-finding", f"grade:{f['grade']}"],
                      "open": f["status"] not in ("closed", "accepted"), "owner": f.get("owner"),
                      "due": f.get("due"), "phase": "test" if f.get("source") == "internal_audit" else None})
    from .review import actions
    for a in actions(model):
        if a.get("status") == "cancelled" and not a.get("issue"):
            continue
        key = f"{a['review']}/{a.get('id')}"
        body = (f"<!-- grc:{key} -->\n**Management review action** from {a['review']} ({model.catalog['framework'].get('short_name', 'ISO')} 9.3).\n\n"
                f"- **Action:** {a.get('action', '')}\n- **Owner:** {a.get('owner') or '—'}\n- **Due:** {a.get('due') or '—'}\n"
                + (f"- **Decision:** {a['decision']}\n" if a.get("decision") else "")
                + f"\nClose it in `engagement/reviews/{a['review']}.yaml` (status: done, closed_on, evidence) through a PR; "
                "this issue follows.\n")
        items.append({"kind": "review", "noun": "management review action", "file": f"reviews/{a['review']}.yaml",
                      "id": key, "title": f"[{key}] {str(a.get('action', ''))[:100]}", "body": body,
                      "labels": ["grc-review-action"], "open": a.get("status") == "open", "owner": a.get("owner"),
                      "due": a.get("due"), "phase": None})
    return items


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
        for it in tracked_items(model):
            log.append(f"[dry-run] {'open' if it['open'] else 'closed':6} {it['title'][:100]}")
        return log
    gh = GitHub(repo, token)

    # labels
    existing_labels = {lab["name"] for lab in gh.paged("/labels")}
    wanted = {lab for it in tracked_items(model) for lab in it["labels"]}
    for name in sorted(wanted - existing_labels):
        gh.call("POST", "/labels", {"name": name, "color": LABEL_COLORS.get(name, "C5DEF5")})
        log.append(f"label created: {name}")

    # milestones per phase
    milestones = {m["title"]: m for m in gh.paged("/milestones?state=all")}
    ms_number = {}
    for ph in model.phases:
        title = (f"{model.catalog['framework'].get('short_name')} " if model.namespace else "") + f"{ph['label']} — {ph['objective']}"
        body = {"title": title, "due_on": f"{ph['end']}T23:59:59Z",
                "description": "Deliverables:\n" + "\n".join(f"- {d}" for d in ph["deliverables"])}
        if title in milestones:
            ms_number[ph["id"]] = milestones[title]["number"]
        else:
            ms = gh.call("POST", "/milestones", body)
            ms_number[ph["id"]] = ms["number"]
            log.append(f"milestone created: {title}")

    # issues: gaps (grc-gap) and audit/other findings (grc-finding)
    found: dict[str, dict] = {}
    for label in ("grc-gap", "grc-finding", "grc-review-action"):
        for iss in gh.paged(f"/issues?state=all&labels={label}"):
            m = re.search(r"<!-- grc:((?:[A-Za-z0-9_-]+:)?(?:(?:GAP|NC|OFI)-\d+|MR-\d{4}-\d{2}/A-\d+)) -->", iss.get("body") or "")
            if m:
                found[m.group(1)] = iss
    mapping = {}
    for it in tracked_items(model):
        payload = {"title": it["title"], "body": it["body"], "labels": it["labels"],
                   "state": "open" if it["open"] else "closed"}
        if it.get("phase") in ms_number:
            payload["milestone"] = ms_number[it["phase"]]
        users = _assignable(model.github_users(it.get("owner")))
        if users:
            payload["assignees"] = users
        if it["id"] in found:
            num = found[it["id"]]["number"]
            _with_assignees(gh, "PATCH", f"/issues/{num}", payload, log, it["id"])
            log.append(f"updated #{num} {it['id']} ({payload['state']})")
        else:
            state = payload.pop("state")
            iss = _with_assignees(gh, "POST", "/issues", payload, log, it["id"])
            num = iss["number"]
            if state == "closed":
                gh.call("PATCH", f"/issues/{num}", {"state": "closed"})
            log.append(f"created #{num} {it['id']}")
        if it["kind"] == "gap":
            mapping[it["gid"]] = num
        # Overdue reminder: one comment per item per due date, mentioning the owners.
        due = str(it.get("due") or "")
        if due and it["open"] and dt.date.fromisoformat(due) < model.today:
            marker = overdue_marker(it["id"], due)
            comments = gh.call("GET", f"/issues/{num}/comments?per_page=100") or []
            if not any(marker in (c.get("body") or "") for c in comments):
                who = " ".join(f"@{u}" for u in model.github_users(it.get("owner"))) or f"**{it.get('owner') or 'Owner'}**"
                gh.call("POST", f"/issues/{num}/comments", {"body": f"{marker}\n⏰ {who}: this {it['noun']} was due **{due}**. "
                        f"Please update it (or its due date) in `{model.record_dir}/{it['file']}` through a PR."})
                log.append(f"overdue reminder on #{num} {it['id']}")
    if write_back:
        write_issue_numbers(model.engagement_dir / "gaps.yaml", mapping)
        log.append("wrote issue numbers to gaps.yaml")
    return log
