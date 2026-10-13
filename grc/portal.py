"""Client site: a small website where the client's people see their readiness and answer requests.

`grc portal --out DIR` writes a deployable bundle:

  DIR/public/index.html, app.js, app.css   the site (static, no third-party code)
  DIR/public/portal.json                  everything the site shows, built from the engagement record
  DIR/worker.js                           the Cloudflare Worker: checks the login, serves the site,
                                          turns an answer into a pull request
  DIR/wrangler.toml                       deployment settings (worker name, repository, Access app)

What the site may and may not do:
  - It shows the same plain-language content as the client view (no hours, budget, risks or rule codes).
  - An answer becomes engagement/submissions/SUB-….yaml in a pull request. The analyst reviews it like any
    other change. A submission never changes a control, gap or evidence status by itself.

Several frameworks: pass more than one engagement directory (`--engagement` on the command, `extra` here);
each becomes a tab, and requests are tagged with the framework they belong to.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path

from . import client_view
from .model import ENGINE, LEGS, Engagement, to_date

SITE = ENGINE / "portal"
SUB_STATUSES = ("received", "accepted", "needs_more", "withdrawn")

WHY = {
    "Gap": "We found this during the readiness review. Closing it is part of the plan we agreed with you.",
    "Opportunity for improvement": "The internal audit suggested this. It is optional, but auditors like to see that suggestions are considered.",
    "Minor nonconformity": "The internal audit found this. Certification auditors check that findings like this are corrected.",
    "Major nonconformity": "The internal audit found this, and it would block certification until it is corrected.",
    "Policy / procedure": "Auditors expect a current, approved document that says how this is done.",
    "Impact assessment": "Each AI system needs a written assessment of how it could affect people, approved before use and kept up to date.",
    "Management review action": "Your leadership agreed this action at the management review.",
}
STATE_WORDS = {"Ready": "Done", "In progress": "Under way", "Unverified claim": "You've told us; we're checking",
               "Not started": "Not started", "Excluded": "Not applicable", "Missing": "Not started"}
LEG_STATUS = {"verified": "checked", "partial": "partly checked", "claimed": "told to us, not yet checked",
              "not_started": "not started"}
NO_ACTION = "no action needed"


def request_key(framework: str, kind: str, ref: str, asks: list[str] | None = None) -> str:
    """Stable id for a request: the same request keeps its id across builds, so answers stay attached.

    For a requirement the open asks are part of the id: when what we need changes (for example the
    document is accepted and now records are needed), it is a new request, and an earlier "Accepted"
    answer no longer hides it."""
    extra = "|" + "\n".join(asks) if asks else ""
    return hashlib.sha256(f"{framework}|{kind}|{ref}{extra}".encode()).hexdigest()[:12]


def item_key(framework: str, item: dict) -> str:
    asks = [str(a) for a in item["ask"] if a] if item["kind"] == "Requirement" else None
    return request_key(framework, item["kind"], item["ref"], asks)


def _d(v) -> dt.date | None:
    try:
        return to_date(v)
    except (TypeError, ValueError):
        return None


def submissions_by_key(model: Engagement) -> dict[str, dict]:
    """The latest well-formed submission for each request key."""
    latest: dict[str, dict] = {}
    for sid, s in model.submissions.items():
        # withdrawn answers (duplicates, sent by mistake) never hide an earlier accepted one
        if not isinstance(s, dict) or s.get("_error") or s.get("status") not in SUB_STATUSES or s.get("status") == "withdrawn":
            continue
        req = s.get("request") if isinstance(s.get("request"), dict) else {}
        key = str(req.get("key") or "")
        at = str(s.get("submitted_at") or "")
        if key and (key not in latest or at >= latest[key]["at"]):
            latest[key] = {"id": sid, "at": at, "status": s["status"], "note": str(s.get("note") or "")}
    return latest


def _requests(model: Engagement, subs: dict[str, dict]) -> list[dict]:
    fw = model.engagement.get("framework", "")
    req_index = model.requirement_index
    out = []
    for i in client_view.items(model):
        asks = [str(a) for a in i["ask"] if a]
        aggregate = i["kind"] == "Requirements"            # "N without an owner": the lead resolves it with the client
        action = not aggregate and not all(NO_ACTION in a.lower() for a in asks)
        key = item_key(fw, i)
        r = req_index.get(i["ref"]) if i["kind"] == "Requirement" else None
        if r:
            why = f"{model.catalog['framework'].get('short_name')} asks for this: {str(r.get('intent') or '').rstrip('.')}."
            examples = [str(x) for x in r.get("evidence_examples") or []]
        else:
            why = WHY.get(i["kind"], "")
            examples = ["The completed document, approved by its owner"] if i["kind"] == "Policy / procedure" else []
        if aggregate:
            why = "Each requirement needs one accountable person at your organization. Your engagement lead will agree these with you."
            asks = asks[:1]
        sub = subs.get(key)
        title = i["title"]
        if title in req_index and i["kind"] != "Requirement":   # findings name their requirement by number
            title = f"{req_index[title].get('title', title)} (requirement {title})"
        if not title:
            title = asks[0][:90] + ("…" if len(asks[0]) > 90 else "") if asks else f"{i['kind']} {i['ref']}"
        out.append({
            "key": key, "framework": fw, "kind": i["kind"], "ref": i["ref"], "title": title, "owner": i["owner"],
            "due": i["due"].isoformat() if i["due"] else None, "overdue": i["overdue"], "asks": asks, "why": why,
            "examples": examples, "action": action, "answerable": not aggregate,
            "submission": {"status": sub["status"], "at": sub["at"][:10], "note": sub["note"]} if sub else None,
        })
    return out


def _areas(model: Engagement) -> list[dict]:
    from .rules import leg_effective, requirement_state
    groups = [g for g in model.catalog.get("groups") or [] if isinstance(g, dict)]
    out = []
    for g in groups:
        reqs = []
        for r in model.requirements:
            if str(r.get("group")) != str(g.get("id")):
                continue
            state = requirement_state(model, r["id"])
            test = (model.controls.get(r["id"]) or {}).get("test") or {}
            reqs.append({"id": r["id"], "title": r.get("title", ""), "kind": r.get("kind", ""), "state": state,
                         "plain": STATE_WORDS.get(state, state),
                         "legs": {k: LEG_STATUS.get(leg_effective(model, test.get(k) or {}), "not started") for k in LEGS}})
        if not reqs:
            continue
        applicable = [x for x in reqs if x["state"] != "Excluded"]
        out.append({"id": str(g.get("id")), "title": g.get("title", ""), "total": len(applicable),
                    "ready": sum(1 for x in applicable if x["state"] == "Ready"),
                    "underway": sum(1 for x in applicable if x["state"] in ("In progress", "Unverified claim")),
                    "requirements": reqs})
    return out


def _path(model: Engagement) -> dict:
    e = model.engagement
    names = {str(p.get("id")): p.get("objective") for p in model.playbook.get("phases") or [] if isinstance(p, dict)}
    phases = []
    for p in e.get("phases") or []:
        if isinstance(p, dict) and _d(p.get("start")) and _d(p.get("end")):
            phases.append({"id": str(p.get("id")), "label": str(p.get("label") or ""),
                           "name": str(p.get("objective") or names.get(str(p.get("id"))) or p.get("id")),
                           "start": _d(p["start"]).isoformat(), "end": _d(p["end"]).isoformat()})
    d = e.get("dates") or {}
    stages = [{"name": n, "date": _d(d.get(k)).isoformat()} for k, n in
              (("stage1", "Stage 1 audit"), ("stage2", "Stage 2 audit")) if _d(d.get(k))]
    return {"phases": phases, "stages": stages,
            # phases and audit stages are drawn on the path; list only the other dated events
            "upcoming": [{"date": x.isoformat(), "text": t} for x, t in client_view.milestones(model)
                         if not t.startswith("Phase starts") and "certification audit" not in t]}


def framework_data(model: Engagement, subs: dict[str, dict] | None = None) -> dict:
    """One framework tab. `subs`: submissions by request key; answers from every tab are stored in the
    main engagement (the Worker writes to one repository folder), so the caller passes those."""
    from .rules import metrics
    m = metrics(model)
    reqs = _requests(model, submissions_by_key(model) if subs is None else subs)
    needs = [r for r in reqs if r["action"]]
    overdue = sum(1 for r in needs if r["overdue"])
    fw = model.catalog["framework"]
    return {
        "key": model.engagement.get("framework", ""), "name": fw.get("short_name", ""), "full_name": fw.get("name", ""),
        "system": fw.get("management_system", ""),
        "ready": m["requirements_ready"], "applicable": m["requirements_applicable"], "checks_pct": m["legs_verified_pct"],
        "attention": bool(overdue or m.get("nc_open_major")), "overdue": overdue, "open_requests": len(needs),
        "stats": [{"label": a, "value": b} for a, b in client_view.overview(model)],
        "path": _path(model), "areas": _areas(model), "requests": reqs,
    }


def data(model: Engagement, extra: list[Engagement] | None = None) -> dict:
    cv = model.engagement.get("client_view") or {}
    models = [model] + list(extra or [])
    subs = submissions_by_key(model)
    for m in extra or []:            # an engagement used on its own may hold answers too
        for k, v in submissions_by_key(m).items():
            if k not in subs or v["at"] > subs[k]["at"]:
                subs[k] = v
    return {
        "schema": 1,
        "client": model.client,
        "as_of": model.today.isoformat(),
        "intro": str(cv.get("intro") or ""),
        "contact": str(cv.get("contact") or ""),
        "sandbox": bool((model.engagement.get("sandbox") or {}).get("enabled")),
        "frameworks": [framework_data(m, subs) for m in models],
    }


def _toml(v: str) -> str:
    """A TOML basic string. JSON escaping is compatible, but without \\u escapes for non-ASCII
    (TOML rejects surrogate pairs) and with control characters removed."""
    v = re.sub(r"[\x00-\x1f\x7f\ud800-\udfff]", "", str(v))
    return json.dumps(v, ensure_ascii=False)


def worker_name(model: Engagement) -> str:
    cfg = model.engagement.get("portal") or {}
    name = str(cfg.get("worker_name") or "")
    if not name:
        base = re.sub(r"\(.*?\)", "", model.client).lower()
        if not re.search(r"[a-z0-9]", base):        # e.g. "(Example Client)"
            base = model.client.lower()
        name = "grc-portal-" + "-".join(re.findall(r"[a-z0-9]+", base))[:40]
    return name.strip("-")[:63]


def wrangler_toml(model: Engagement, repo: str) -> str:
    cfg = model.engagement.get("portal") or {}
    team = str(cfg.get("access_team") or "")
    domains = ",".join(str(x).lower() for x in cfg.get("allowed_email_domains") or [])
    return "\n".join([
        "# Generated by `grc portal`. Change the settings in engagement.yaml (portal:), not here.",
        f"name = {_toml(worker_name(model))}",
        'main = "worker.js"',
        'compatibility_date = "2025-06-01"',
        "workers_dev = true",
        "",
        "[observability]",
        "enabled = true               # Worker logs in the Cloudflare dashboard (no answer text is logged)",
        "",
        "[assets]",
        'directory = "public"',
        'binding = "ASSETS"',
        "run_worker_first = true      # every request, pages included, passes the login check",
        "",
        "[vars]",
        f"GITHUB_REPO = {_toml(repo)}",
        f"BASE_BRANCH = {_toml(cfg.get('base_branch') or 'main')}",
        f"ACCESS_TEAM = {_toml(team)}",
        f"ACCESS_AUD = {_toml(cfg.get('access_aud') or '')}",
        f"ALLOWED_EMAIL_DOMAINS = {_toml(domains)}",
        "# Secret, set by the deploy workflow from PORTAL_GITHUB_TOKEN: GITHUB_TOKEN",
        "",
    ])


def build(model: Engagement, out: Path, repo: str = "", extra: list[Engagement] | None = None) -> list[str]:
    out = Path(out)
    pub = out / "public"
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True)
    for name in ("index.html", "app.js", "app.css"):
        shutil.copyfile(SITE / "site" / name, pub / name)
    shutil.copyfile(SITE / "worker.js", out / "worker.js")
    d = data(model, extra)
    (pub / "portal.json").write_text(json.dumps(d, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (out / "wrangler.toml").write_text(wrangler_toml(model, repo), encoding="utf-8")
    log = [f"client site written to {out}/ (worker {worker_name(model)})"]
    for f in d["frameworks"]:
        log.append(f"  {f['name']}: {f['ready']} of {f['applicable']} requirements ready; "
                   f"{f['open_requests']} request(s) need the client, {f['overdue']} overdue")
    cfg = model.engagement.get("portal") or {}
    if not (cfg.get("access_team") and cfg.get("access_aud")):
        log.append("  note: portal.access_team / portal.access_aud are not set - the deployed site will refuse every "
                   "request until they are (see docs/CLIENT-SITE.md)")
    if not repo:
        log.append("  note: no repository given (--repo or $GITHUB_REPOSITORY) - answers cannot be sent")
    return log


# ------------------------------------------------------------------ analyst report
def report(model: Engagement, out: Path) -> list[tuple[str, str, str]]:
    """submissions.md: answers from the client site, newest first, waiting ones on top."""
    if not model.submissions:
        return []
    from .client_view import md
    rows = []
    for sid, s in model.submissions.items():
        if not isinstance(s, dict) or s.get("_error"):
            rows.append(("0", sid, "unreadable", "", "", "", ""))
            continue
        req = s.get("request") if isinstance(s.get("request"), dict) else {}
        rows.append(("0" if s.get("status") == "received" else "1", sid, str(s.get("status")), str(s.get("submitted_at") or "")[:10],
                     f"{req.get('kind', '')} {req.get('ref', '')}", str(s.get("submitted_by") or ""),
                     ", ".join(str(e) for e in s.get("evidence") or [])))
    rows.sort(key=lambda r: r[3], reverse=True)   # newest first ...
    rows.sort(key=lambda r: r[0])                 # ... with the ones waiting for review on top (stable sort)
    waiting = sum(1 for r in rows if r[2] == "received")
    L = ["# Client submissions\n\n",
         f"Answers sent from the client site. {waiting} waiting for review. To review one, edit its file in "
         "`engagement/submissions/`: set `status` (accepted, needs_more with a `note` the client will see, or withdrawn) and "
         "`reviewed_by`, and file any evidence in `evidence/index.yaml` (list it under `evidence:`). A submission never changes "
         "a control's status by itself.\n\n",
         "| Submission | Status | Sent | Request | From | Evidence filed |\n|---|---|---|---|---|---|\n"]
    L += [f"| {md(r[1])} | {md(r[2])} | {md(r[3])} | {md(r[4])} | {md(r[5])} | {md(r[6])} |\n" for r in rows]
    (out / "submissions.md").write_text("".join(L), encoding="utf-8")
    return [("Client submissions", "submissions.md", f"{len(rows)} answer(s) from the client site, {waiting} waiting for review")]
