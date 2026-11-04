"""IT general control (ITGC) tests run on real GitHub data: change management and logical access.

    python -m grc itgc change --repo acme/payments --from 2026-07-01 --to 2026-09-30 --id ITGC-CHG-2026Q3
    python -m grc itgc access --repo acme/payments --id ITGC-ACC-2026Q3

Each test writes program/itgc/<ID>/:
  population.json   every item in the population as fetched from GitHub, with its SHA-256 (re-performable)
  workpaper.yaml    attributes, the risk-based sample, the automated result of every attribute for every
                    sampled item, and blanks the auditor completes (conclusion, performed_by, reviewed_by)
  workpaper.md      the same, readable

Change management (population: every change that reached the production branch in the period)
  CHG-1  The change went through a pull request (no direct push to the branch).
  CHG-2  Someone other than the author approved it before it was merged.
  CHG-3  The approval was given on the code that was merged (no unreviewed commits after it).
  CHG-4  Automated checks ran on the merged code and none failed.
  CHG-5  The change links to a ticket or issue (configurable pattern; --no-ticket to drop the attribute).

Sample: every high-risk item is tested (direct pushes, changes to sensitive paths such as CI workflows or
access configuration, emergency/hotfix labels), plus a random sample of the rest drawn deterministically from
the test id, sized like the internal audit (grc.audit.default_sample_size). The population hash and seed are
recorded so anyone can re-perform the selection.

Logical access (population: every collaborator and pending invitation on the repository)
  ACC-1  The person is on the approved access list (program/itgc/access/<owner>__<repo>.yaml).
  ACC-2  Their permission is no higher than approved.
  ACC-3  Admin access is limited to the people approved for it.

Automation tests the attributes; it never concludes. The auditor reviews each exception, writes the
conclusion, and a different person reviews the workpaper (program validate enforces both).
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path

import yaml

from .audit import default_sample_size, draw

ITGC_DIR = Path("program") / "itgc"
DEFAULT_SENSITIVE = [".github/workflows/*", ".github/CODEOWNERS", "CODEOWNERS", "**/*.tf", "infra/**",
                     "terraform/**", "**/iam*", "**/*policy*.json", "Dockerfile", "**/Dockerfile"]
DEFAULT_TICKET = r"(#\d+|\b[A-Z][A-Z0-9]+-\d+\b|https?://\S+/(issues|browse)/\S+)"
EMERGENCY_LABELS = {"emergency", "hotfix", "expedite", "urgent"}
PERMISSION_RANK = {"read": 1, "pull": 1, "triage": 2, "write": 3, "push": 3, "maintain": 4, "admin": 5}

CHANGE_ATTRIBUTES = [
    {"id": "CHG-1", "text": "The change reached the branch through a pull request (not a direct push)."},
    {"id": "CHG-2", "text": "Someone other than the author approved the pull request before it was merged."},
    {"id": "CHG-3", "text": "The approval was given on the final code: no commits were added after it."},
    {"id": "CHG-4", "text": "Automated checks ran on the merged code and none failed."},
    {"id": "CHG-5", "text": "The change links to a ticket or issue."},
]
ACCESS_ATTRIBUTES = [
    {"id": "ACC-1", "text": "The person is on the approved access list for the repository."},
    {"id": "ACC-2", "text": "Their permission is no higher than the permission approved for them."},
    {"id": "ACC-3", "text": "If they have admin access, they are approved for admin."},
]


# ------------------------------------------------------------------ GitHub
class Source:
    """Read-only GitHub REST client. Token: GH_COLLECTOR_TOKEN, else GITHUB_TOKEN/GH_TOKEN."""

    def __init__(self, repo: str, token: str | None = None, transport=None):
        from .issues import GitHub
        self.repo = repo
        tok = token or os.environ.get("GH_COLLECTOR_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not tok and transport is None:
            raise SystemExit("itgc: set GH_COLLECTOR_TOKEN (read-only token for the repository under test)")
        self.gh = GitHub(repo, tok or "")
        self.transport = transport   # tests: callable(path) -> JSON
        self.calls = 0

    def get(self, path: str):
        self.calls += 1
        if self.transport:
            return self.transport(path)
        return self.gh.call("GET", path)

    def paged(self, path: str, limit: int = 5000):
        page, n = 1, 0
        while True:
            sep = "&" if "?" in path else "?"
            items = self.get(f"{path}{sep}per_page=100&page={page}") or []
            if isinstance(items, dict):           # e.g. {"workflow_runs": [...]} - not used here
                items = items.get("items") or []
            if not items:
                return
            for it in items:
                yield it
                n += 1
                if n >= limit:
                    return
            if len(items) < 100:
                return
            page += 1


def _ts(s: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _sha256(items: list[dict]) -> str:
    return hashlib.sha256(json.dumps(items, sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------------ change management
def change_population(src: Source, start: dt.date, end: dt.date, base: str = "main") -> list[dict]:
    """Every change that reached `base` between start and end (inclusive): merged PRs and direct pushes."""
    lo = dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone.utc)
    hi = dt.datetime.combine(end, dt.time.max, tzinfo=dt.timezone.utc)
    items, merge_shas = [], set()
    for pr in src.paged(f"/pulls?state=closed&base={base}&sort=updated&direction=desc"):
        merged = _ts(pr.get("merged_at"))
        if _ts(pr.get("updated_at")) and _ts(pr["updated_at"]) < lo:
            break
        if not merged or not (lo <= merged <= hi):
            continue
        merge_shas.add(pr.get("merge_commit_sha"))
        items.append({"id": f"#{pr['number']}", "kind": "pull_request", "number": pr["number"],
                      "title": (pr.get("title") or "")[:200], "body": (pr.get("body") or "")[:2000],
                      "branch": (pr.get("head") or {}).get("ref"), "head_sha": (pr.get("head") or {}).get("sha"),
                      "merge_sha": pr.get("merge_commit_sha"), "author": (pr.get("user") or {}).get("login"),
                      "merged_at": pr.get("merged_at"), "labels": sorted(l["name"] for l in pr.get("labels") or []),
                      "url": pr.get("html_url")})
    # commits on the branch that no merged PR accounts for are direct pushes
    since, until = lo.strftime("%Y-%m-%dT%H:%M:%SZ"), hi.strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in src.paged(f"/commits?sha={base}&since={since}&until={until}"):
        sha = c.get("sha")
        if sha in merge_shas:
            continue
        prs = src.get(f"/commits/{sha}/pulls") or []
        if any(p.get("merged_at") and (p.get("base") or {}).get("ref") == base for p in prs):
            continue                                   # a commit brought in by a merged PR
        commit = c.get("commit") or {}
        items.append({"id": f"commit:{sha[:10]}", "kind": "direct_push", "sha": sha,
                      "title": (commit.get("message") or "").splitlines()[0][:200] if commit.get("message") else "",
                      "author": (c.get("author") or {}).get("login") or (commit.get("author") or {}).get("name"),
                      "committed_at": (commit.get("committer") or {}).get("date"), "url": c.get("html_url")})
    return sorted(items, key=lambda i: (i.get("merged_at") or i.get("committed_at") or "", i["id"]))


def _files(src: Source, item: dict) -> list[str]:
    if item["kind"] == "pull_request":
        return [f["filename"] for f in src.paged(f"/pulls/{item['number']}/files", limit=3000)]
    data = src.get(f"/commits/{item['sha']}") or {}
    return [f["filename"] for f in data.get("files") or []]


def _sensitive(files: list[str], patterns: list[str]) -> list[str]:
    return sorted({f for f in files for p in patterns if fnmatch.fnmatch(f, p) or fnmatch.fnmatch("/" + f, "*/" + p)})


def risk(item: dict, sensitive_patterns: list[str]) -> list[str]:
    why = []
    if item["kind"] == "direct_push":
        why.append("direct push to the branch")
    hit = _sensitive(item.get("files") or [], sensitive_patterns)
    if hit:
        why.append("changes sensitive paths: " + ", ".join(hit[:5]) + (" ..." if len(hit) > 5 else ""))
    if EMERGENCY_LABELS & {l.lower() for l in item.get("labels") or []}:
        why.append("emergency change")
    return why


def test_change(src: Source, item: dict, ticket: re.Pattern | None) -> dict:
    """Automated result of each attribute for one change: {CHG-n: {result, note}}."""
    out = {}
    if item["kind"] == "direct_push":
        out["CHG-1"] = {"result": "exception", "note": f"pushed straight to the branch by {item.get('author')}"}
        out["CHG-2"] = {"result": "exception", "note": "no pull request, so nobody approved it"}
        out["CHG-3"] = {"result": "not_applicable", "note": "no approval to compare with the merged code"}
        out["CHG-4"] = {"result": "exception", "note": "no pull request, so no checks gated the change"}
        if ticket:
            ok = bool(ticket.search(item.get("title") or ""))
            out["CHG-5"] = {"result": "pass" if ok else "exception",
                            "note": "ticket in commit message" if ok else "no ticket reference in the commit message"}
        return out
    out["CHG-1"] = {"result": "pass", "note": f"pull request {item['id']}"}
    merged = _ts(item.get("merged_at"))
    reviews = list(src.paged(f"/pulls/{item['number']}/reviews"))
    indep = [r for r in reviews if r.get("state") == "APPROVED" and (r.get("user") or {}).get("login") != item.get("author")
             and (_ts(r.get("submitted_at")) or merged) <= merged]
    if indep:
        who = sorted({(r.get("user") or {}).get("login") for r in indep})
        out["CHG-2"] = {"result": "pass", "note": f"approved by {', '.join(who)}"}
        on_head = [r for r in indep if r.get("commit_id") == item.get("head_sha")]
        out["CHG-3"] = ({"result": "pass", "note": "approval is on the merged head commit"} if on_head else
                        {"result": "exception", "note": "commits were added after the last approval"})
    else:
        self_ok = [r for r in reviews if r.get("state") == "APPROVED"]
        out["CHG-2"] = {"result": "exception", "note": "no approval by anyone other than the author"
                        + (" (the only approval is the author's own)" if self_ok else f" ({len(reviews)} review(s), none approving)")}
        out["CHG-3"] = {"result": "not_applicable", "note": "no independent approval to compare with the merged code"}
    runs = (src.get(f"/commits/{item['head_sha']}/check-runs?per_page=100") or {}).get("check_runs", [])
    concl = [r.get("conclusion") for r in runs]
    failed = [r.get("name") for r in runs if r.get("conclusion") in ("failure", "timed_out", "cancelled", "action_required")]
    if not runs:
        out["CHG-4"] = {"result": "exception", "note": "no automated checks ran on the merged code"}
    elif failed:
        out["CHG-4"] = {"result": "exception", "note": f"{len(failed)} check(s) did not pass: {', '.join(sorted(set(failed))[:5])}"}
    elif any(c is None for c in concl):
        out["CHG-4"] = {"result": "exception", "note": "checks were still running when it was merged"}
    else:
        out["CHG-4"] = {"result": "pass", "note": f"{len(runs)} check(s) passed"}
    if ticket:
        text = " ".join(str(item.get(k) or "") for k in ("title", "body", "branch"))
        m = ticket.search(text)
        out["CHG-5"] = ({"result": "pass", "note": f"references {m.group(0)[:60]}"} if m else
                        {"result": "exception", "note": "no ticket or issue reference in the title, description or branch"})
    return out


# ------------------------------------------------------------------ access
def access_population(src: Source) -> list[dict]:
    items = []
    for c in src.paged("/collaborators?affiliation=all"):
        perms = c.get("permissions") or {}
        role = c.get("role_name") or next((p for p in ("admin", "maintain", "push", "triage", "pull") if perms.get(p)), "pull")
        items.append({"id": c["login"], "kind": "collaborator", "permission": {"push": "write", "pull": "read"}.get(role, role),
                      "type": c.get("type")})
    for inv in src.paged("/invitations"):
        u = (inv.get("invitee") or {}).get("login") or inv.get("email") or f"invitation-{inv.get('id')}"
        items.append({"id": u, "kind": "pending_invitation",
                      "permission": {"push": "write", "pull": "read"}.get(inv.get("permissions"), inv.get("permissions")),
                      "invited_at": inv.get("created_at")})
    return sorted(items, key=lambda i: i["id"].lower())


def approved_access_path(repo: str) -> Path:
    return ITGC_DIR / "access" / f"{repo.replace('/', '__')}.yaml"


def test_access(item: dict, approved: dict[str, dict]) -> dict:
    a = approved.get(item["id"].lower())
    out = {}
    if not a:
        out["ACC-1"] = {"result": "exception", "note": f"not on the approved list ({item['kind'].replace('_', ' ')})"}
        out["ACC-2"] = {"result": "exception", "note": f"has {item['permission']} with no approval"}
    else:
        out["ACC-1"] = {"result": "pass", "note": f"approved: {a.get('reason') or a.get('role')}"}
        ok = PERMISSION_RANK.get(item["permission"], 9) <= PERMISSION_RANK.get(str(a.get("permission")), 0)
        out["ACC-2"] = ({"result": "pass", "note": f"{item['permission']} (approved {a.get('permission')})"} if ok else
                        {"result": "exception", "note": f"has {item['permission']}, approved for {a.get('permission')}"})
    if item["permission"] == "admin":
        ok = bool(a) and a.get("permission") == "admin"
        out["ACC-3"] = {"result": "pass" if ok else "exception",
                        "note": "approved for admin" if ok else "admin access without admin approval"}
    else:
        out["ACC-3"] = {"result": "pass", "note": "no admin access"}
    return out


# ------------------------------------------------------------------ workpapers
HEADER = ("# ITGC workpaper - generated by `grc itgc`, completed by the auditor.\n"
          "# The automated results are evidence, not a conclusion. For each exception: confirm it, explain it in\n"
          "# `auditor_note` or raise a finding. Then set conclusion (effective / not_effective), summary,\n"
          "# performed_by and performed_on. A different person sets reviewed_by and reviewed_on.\n")


def _write(test_id: str, population: list[dict], wp: dict, root: Path) -> Path:
    d = root / ITGC_DIR / test_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "population.json").write_text(json.dumps({"test": test_id, "sha256": _sha256(population), "count": len(population),
                                                   "items": population}, indent=1, default=str) + "\n", encoding="utf-8")
    (d / "workpaper.yaml").write_text(HEADER + yaml.safe_dump(wp, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    (d / "workpaper.md").write_text(render_md(wp), encoding="utf-8")
    return d


def run_change(src: Source, test_id: str, start: dt.date, end: dt.date, base: str = "main",
               sensitive: list[str] | None = None, ticket_pattern: str | None = DEFAULT_TICKET,
               sample_size: int | None = None, root: Path = Path("."), today: dt.date | None = None) -> dict:
    sensitive = sensitive or DEFAULT_SENSITIVE
    ticket = re.compile(ticket_pattern) if ticket_pattern else None
    pop = change_population(src, start, end, base)
    for it in pop:
        it["files"] = _files(src, it)
        it["risk"] = risk(it, sensitive)
    high = [it["id"] for it in pop if it["risk"]]
    rest = [it["id"] for it in pop if not it["risk"]]
    n = default_sample_size(len(rest)) if sample_size is None else min(sample_size, len(rest))
    chosen = set(high) | set(draw(rest, n, test_id))
    by_id = {it["id"]: it for it in pop}
    attrs = [a for a in CHANGE_ATTRIBUTES if ticket or a["id"] != "CHG-5"]
    sample = []
    for iid in [it["id"] for it in pop if it["id"] in chosen]:
        it = by_id[iid]
        res = test_change(src, it, ticket)
        sample.append({"item": iid, "title": it.get("title", ""), "author": it.get("author"),
                       "when": it.get("merged_at") or it.get("committed_at"), "url": it.get("url"),
                       "selected_because": "; ".join(it["risk"]) or ("random sample" if n < len(rest) else
                                                                     "whole population tested"),
                       "attributes": res,
                       "result": "exception" if any(v["result"] == "exception" for v in res.values()) else "pass",
                       "auditor_note": ""})
    wp = {"id": test_id, "kind": "change_management", "repository": src.repo, "branch": base,
          "period": {"from": start.isoformat(), "to": end.isoformat()},
          "objective": "Changes to the production branch are authorized, independently reviewed, tested and traceable.",
          "attributes": attrs,
          "population": {"size": len(pop), "pull_requests": sum(1 for i in pop if i["kind"] == "pull_request"),
                         "direct_pushes": sum(1 for i in pop if i["kind"] == "direct_push"),
                         "sha256": _sha256(pop), "source": f"GitHub REST API, {src.repo}@{base}",
                         "fetched_on": (today or dt.date.today()).isoformat(), "api_calls": src.calls},
          "sampling": {"method": "risk-based: every high-risk item, plus a deterministic random sample of the rest "
                                 "(Python random.Random(seed))",
                       "seed": test_id, "high_risk": len(high), "random": len(chosen) - len(high),
                       "sensitive_paths": sensitive, "ticket_pattern": ticket_pattern},
          "sample": sample,
          "results": _results(sample, attrs),
          "conclusion": "not_concluded", "summary": "", "exception_rationale": "", "findings": [],
          "prepared_by": "grc itgc (automated)", "performed_by": "", "performed_on": None,
          "reviewed_by": "", "reviewed_on": None}
    _write(test_id, pop, wp, root)
    return wp


def run_access(src: Source, test_id: str, approved_file: Path | None = None, root: Path = Path("."),
               today: dt.date | None = None) -> dict:
    path = root / (approved_file or approved_access_path(src.repo))
    if not path.exists():
        raise SystemExit(f"itgc access: no approved access list at {path}. Create it first (docs/ITGC.md):\n"
                         "  approved:\n    - {user: alice, permission: admin, reason: Repository owner}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    approved = {str(a.get("user", "")).lower().lstrip("@"): a for a in data.get("approved") or [] if isinstance(a, dict)}
    pop = access_population(src)
    sample = []
    for it in pop:                                   # small populations: test every item
        res = test_access(it, approved)
        sample.append({"item": it["id"], "title": f"{it['kind'].replace('_', ' ')}: {it['permission']}",
                       "selected_because": "100% tested", "attributes": res,
                       "result": "exception" if any(v["result"] == "exception" for v in res.values()) else "pass",
                       "auditor_note": ""})
    present = {it["id"].lower() for it in pop}
    unused = sorted(u for u in approved if u not in present)
    wp = {"id": test_id, "kind": "logical_access", "repository": src.repo,
          "period": {"from": (today or dt.date.today()).isoformat(), "to": (today or dt.date.today()).isoformat()},
          "objective": "Only approved people have access to the repository, at no more than the approved level.",
          "attributes": ACCESS_ATTRIBUTES,
          "approved_list": {"file": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                            "reviewed_by": data.get("reviewed_by", ""), "reviewed_on": str(data.get("reviewed_on") or ""),
                            "approved_but_absent": unused},
          "population": {"size": len(pop), "admins": sum(1 for i in pop if i["permission"] == "admin"),
                         "pending_invitations": sum(1 for i in pop if i["kind"] == "pending_invitation"),
                         "sha256": _sha256(pop), "source": f"GitHub REST API, {src.repo} collaborators and invitations",
                         "fetched_on": (today or dt.date.today()).isoformat(), "api_calls": src.calls},
          "sampling": {"method": "100% of the population", "seed": test_id},
          "sample": sample, "results": _results(sample, ACCESS_ATTRIBUTES),
          "conclusion": "not_concluded", "summary": "", "exception_rationale": "", "findings": [],
          "prepared_by": "grc itgc (automated)", "performed_by": "", "performed_on": None,
          "reviewed_by": "", "reviewed_on": None}
    _write(test_id, pop, wp, root)
    return wp


def _results(sample: list[dict], attrs: list[dict]) -> dict:
    out = {"tested": len(sample), "exceptions": sum(1 for s in sample if s["result"] == "exception"), "by_attribute": {}}
    for a in attrs:
        ex = [s["item"] for s in sample if (s["attributes"].get(a["id"]) or {}).get("result") == "exception"]
        na = sum(1 for s in sample if (s["attributes"].get(a["id"]) or {}).get("result") == "not_applicable")
        out["by_attribute"][a["id"]] = {"exceptions": len(ex), "not_applicable": na, "items": ex}
    return out


# ------------------------------------------------------------------ report
def render_md(wp: dict) -> str:
    esc = lambda s: str("" if s is None else s).replace("|", "\\|").replace("\n", " ")
    pop, smp, res = wp["population"], wp["sampling"], wp["results"]
    title = "Change management" if wp["kind"] == "change_management" else "Logical access"
    lines = [f"# {wp['id']}: {title} ITGC test, {wp['repository']}", "",
             f"**Objective:** {wp['objective']}", "",
             f"**Period:** {wp['period']['from']} to {wp['period']['to']}. **Population:** {pop['size']} item(s) from "
             f"{pop['source']}, fetched {pop['fetched_on']} (SHA-256 `{pop['sha256'][:16]}…`).", "",
             f"**Sample:** {res['tested']} item(s). {smp['method']}." + (f" High-risk: {smp.get('high_risk')}, random: "
                                                                        f"{smp.get('random')}." if 'high_risk' in smp else ""), "",
             f"**Conclusion:** {wp.get('conclusion', 'not_concluded').replace('_', ' ')}"
             + (f" by {wp['performed_by']} on {wp['performed_on']}" if wp.get("performed_by") else " (the auditor concludes, not the tool)")
             + (f"; reviewed by {wp['reviewed_by']} on {wp['reviewed_on']}" if wp.get("reviewed_by") else "") + ".", ""]
    if wp.get("summary"):
        lines += [wp["summary"].strip(), ""]
    lines += ["## Results by attribute", "", "| Attribute | Test | Exceptions |", "|---|---|---|"]
    for a in wp["attributes"]:
        b = res["by_attribute"].get(a["id"], {})
        n, na = b.get("exceptions", 0), b.get("not_applicable", 0)
        lines.append(f"| {a['id']} | {esc(a['text'])} | {n} of {res['tested'] - na}" + (f" ({na} not applicable)" if na else "") + " |")
    ids = [a["id"] for a in wp["attributes"]]
    lines += ["", "✓ pass, ✗ exception, – not applicable (an earlier attribute already failed).", "", "## Sample", "", "| Item | Selected because | " + " | ".join(ids) + " | Result |",
              "|---|---|" + "---|" * len(ids) + "---|"]
    for s in wp["sample"]:
        cells = [{"pass": "✓", "exception": "✗"}.get((s["attributes"].get(i) or {}).get("result"), "–") for i in ids]
        item = f"[{s['item']}]({s['url']})" if s.get("url") else s["item"]
        lines.append(f"| {item} {esc(s.get('title', ''))[:70]} | {esc(s['selected_because'])[:80]} | " + " | ".join(cells)
                     + f" | {s['result']} |")
    exc = [(s, i, v) for s in wp["sample"] for i, v in s["attributes"].items() if v["result"] == "exception"]
    if exc:
        lines += ["", "## Exceptions", "", "| Item | Attribute | Detail | Auditor note |", "|---|---|---|---|"]
        lines += [f"| {s['item']} | {i} | {esc(v['note'])} | {esc(s.get('auditor_note'))} |" for s, i, v in exc]
    if wp.get("approved_list", {}).get("approved_but_absent"):
        lines += ["", "Approved but not present (consider removing from the approved list): "
                  + ", ".join(wp["approved_list"]["approved_but_absent"])]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ validation of completed workpapers
def load_workpapers(root: Path) -> dict[str, tuple[Path, dict]]:
    out = {}
    d = root / ITGC_DIR
    for p in sorted(d.glob("*/workpaper.yaml")) if d.is_dir() else []:
        try:
            out[p.parent.name] = (p, yaml.safe_load(p.read_text(encoding="utf-8")) or {})
        except yaml.YAMLError as exc:
            out[p.parent.name] = (p, {"_error": f"not valid YAML ({str(exc).splitlines()[0][:120]})"})
    return out


def check(root: Path, today: dt.date, independent=None):
    """P4xx findings for completed ITGC workpapers."""
    from .model import to_date
    from .rules import Finding
    out = []
    same = independent or (lambda a, b: a.strip().lower().lstrip("@") == b.strip().lower().lstrip("@"))
    for tid, (path, wp) in load_workpapers(root).items():
        f = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        if "_error" in wp:
            out.append(Finding("error", "P401", wp["_error"], f))
            continue
        if wp.get("id") != tid:
            out.append(Finding("error", "P401", f"workpaper id '{wp.get('id')}' doesn't match its folder {tid}/", f))
        concl = wp.get("conclusion", "not_concluded")
        if concl not in ("not_concluded", "effective", "not_effective"):
            out.append(Finding("error", "P401", f"{tid}: conclusion must be not_concluded, effective or not_effective", f))
        exc = [s for s in wp.get("sample") or [] if isinstance(s, dict) and s.get("result") == "exception"]
        if concl == "effective" and exc and not str(wp.get("exception_rationale") or "").strip():
            out.append(Finding("error", "P402", f"{tid}: concluded effective with {len(exc)} exception(s) and no "
                                                "exception_rationale", f))
        if concl == "not_effective" and not wp.get("findings"):
            out.append(Finding("error", "P402", f"{tid}: concluded not effective but cites no finding", f))
        if concl != "not_concluded" and not (wp.get("performed_by") and to_date(wp.get("performed_on"))):
            out.append(Finding("error", "P403", f"{tid}: a conclusion needs performed_by and performed_on", f))
        rb = str(wp.get("reviewed_by") or "")
        if rb:
            if concl == "not_concluded":
                out.append(Finding("error", "P404", f"{tid}: reviewed before it was concluded", f))
            if same(rb, str(wp.get("performed_by") or "")):
                out.append(Finding("error", "P404", f"{tid}: reviewed by the person who performed it", f))
            if not to_date(wp.get("reviewed_on")):
                out.append(Finding("error", "P404", f"{tid}: reviewed_by needs reviewed_on", f))
        if concl == "not_concluded":
            fetched = to_date((wp.get("population") or {}).get("fetched_on"))
            if fetched and (today - fetched).days > 30:
                out.append(Finding("warning", "P405", f"{tid}: generated {fetched} and still not concluded", f))
        for s in exc:
            if concl != "not_concluded" and not str(s.get("auditor_note") or "").strip():
                out.append(Finding("warning", "P406", f"{tid}: exception on {s.get('item')} has no auditor_note", f))
    return out
