"""Client view: what the client's people need to know and do, in plain language.

Written for control owners and executives rather than analysts:
  - where things stand and what's coming up
  - "what we need from you", grouped by owner, overdue first
  - items with no owner yet, so someone can pick them up

Deliberately left out: hours and budget, the analyst's working rules and engagement risks,
validation codes, and anything else that only matters inside the engagement team.

Output: client-view.html (one self-contained file: no external resources, safe to email or attach)
and client-view.md (readable on GitHub). Every value from the record is escaped in both.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from pathlib import Path

from .model import LEGS, Engagement, to_date

UNASSIGNED = "Not yet assigned"
LEG_NAMES = {"documented": "Documented", "implemented": "In use", "evidenced": "Records", "tested": "Tested"}


def _d(v) -> dt.date | None:
    try:
        return to_date(v)
    except (TypeError, ValueError):
        return None


def _owner(model: Engagement, name) -> str:
    return str(name).strip() if name and str(name).strip() else UNASSIGNED


def _lib_doc_for(model: Engagement) -> dict[str, str]:
    from . import documents
    out = {}
    for did, e in documents.library(model).items():
        for r in e.get("satisfies") or []:
            out[str(r)] = did
    return out


def items(model: Engagement) -> list[dict]:
    """Every request to the client: {owner, kind, ref, title, ask, due, overdue, sort}."""
    from . import documents, impact, review
    from .rules import leg_effective
    out = []
    today = model.today
    doc_for = _lib_doc_for(model)
    docs = documents.docs(model)
    by_phase_end = {str(p.get("id")): _d(p.get("end")) for p in model.engagement.get("phases") or [] if isinstance(p, dict)}

    def add(owner, kind, ref, title, ask, due=None, order=50):
        due = _d(due)
        out.append({"owner": _owner(model, owner), "kind": kind, "ref": str(ref), "title": str(title or ""), "ask": ask,
                    "due": due, "overdue": bool(due and due < today), "order": order})

    # requirements: the legs still open, in plain language
    unowned: list[str] = []
    for r in model.requirements:
        rid = r["id"]
        if not model.is_applicable(rid):
            continue
        c = model.controls.get(rid, {})
        test = c.get("test") or {}
        eff = {k: leg_effective(model, test.get(k) or {}) for k in LEGS}
        if all(v == "verified" for v in eff.values()):
            continue
        examples = ", ".join(r.get("evidence_examples") or []) or "records showing it operates"
        asks = []
        if eff["documented"] != "verified":
            did = doc_for.get(rid)
            d = docs.get(did) if did else None
            if d and d["meta"].get("status") == "approved" and documents.is_effective(model, did):
                asks.append(f"Documented: covered by {did} (approved); we will link it.")
            elif d and d["meta"].get("status") == "approved":
                asks.append(f"Documented: {did} is due for review (or changed since approval) — review and re-approve it.")
            elif d:
                asks.append(f"Documented: {did} is {d['meta'].get('status', 'draft')} — complete and approve it.")
            elif did:
                asks.append(f"Documented: an approved {documents.library(model)[did]['title']} ({did}) — we will draft it with you.")
            else:
                asks.append("Documented: an approved policy or procedure that covers this.")
        if eff["implemented"] in ("not_started", "claimed"):
            asks.append("In use: " + ("you've told us this is in place — show us where it runs."
                                      if eff["implemented"] == "claimed" else "confirm the process is in use and where it runs."))
        elif eff["implemented"] == "partial":
            asks.append("In use: what you've shown us is being reviewed — no action needed for now.")
        if eff["evidenced"] in ("not_started", "claimed"):
            asks.append(f"Records: share {examples}.")
        elif eff["evidenced"] == "partial":
            asks.append(f"Records: some received; share the rest ({examples}).")
        if eff["tested"] != "verified" and all(eff[k] == "verified" for k in ("documented", "implemented", "evidenced")):
            asks.append("Tested: the internal audit will sample it — no action needed until then.")
        if not asks:   # not ready, but nothing to ask the client for right now
            asks.append("Being reviewed by the engagement team — no action needed for now.")
        if asks and str(c.get("owner") or "").strip():
            add(c.get("owner"), "Requirement", rid, r["title"], asks, order=60)
        elif asks:
            unowned.append(f"{rid} {r['title']}")
    if unowned:
        add(None, "Requirements", f"{len(unowned)} without an owner", "",
            ["Name an accountable owner for each; their requests then appear under their name.",
             "; ".join(unowned[:60]) + (" …" if len(unowned) > 60 else "")], order=5)

    for g in model.gaps:
        if g.get("status") in ("open", "in_progress"):
            add(g.get("owner"), "Gap", g.get("id"), g.get("area"), [model.fmt(str(g.get("finding") or ""))],
                g.get("due") or by_phase_end.get(str(g.get("phase"))), order=20)
    for f in model.findings:
        if isinstance(f, dict) and f.get("status") not in ("closed", "accepted"):
            ofi = f.get("grade") == "ofi"
            what = "Opportunity for improvement" if ofi else f"{str(f.get('grade', '')).capitalize()} nonconformity"
            nxt = ({"open": "Consider this improvement and tell us whether and how you'll act on it."} if ofi else {
                   "open": "Agree the root cause and a corrective action with a due date.",
                   "action_planned": "Carry out the corrective action and keep evidence of it.",
                   "implemented": "Evidence is with the reviewer, who will confirm it worked."}).get(f.get("status"), "")
            add(f.get("owner"), what, f.get("id"), f.get("requirement"), [str(f.get("description") or ""), nxt] if nxt
                else [str(f.get("description") or "")], f.get("due"), order=10)
    for did, d in docs.items():
        meta = d["meta"]
        if meta.get("status") in ("draft", "in_review"):
            left = documents.open_markers(d["body"])
            ask = (f"{left} item(s) still to complete, then approval." if left else "Ready for review and approval.")
            add(meta.get("owner"), "Policy / procedure", did, meta.get("title"), [ask], order=40)
        elif meta.get("status") == "approved" and not documents.is_effective(model, did):
            add(meta.get("owner"), "Policy / procedure", did, meta.get("title"),
                ["Due for review (or changed since approval): review and re-approve it."], documents.next_review(model, meta), order=30)
    inv = {i.get("id"): i for i in model.inventory if isinstance(i, dict)}
    active = impact.active_by_system(model)
    for s in impact.required_systems(model):
        ia = active.get(s["id"])
        if not ia:
            add(s.get("owner"), "Impact assessment", s["id"], s.get("name"), ["Start the AI impact assessment for this system."], order=35)
        elif not impact.is_effective(model, ia):
            nr = impact.next_review(model, ia)
            ask = ("Complete the assessment and have it approved by someone other than the assessor."
                   if ia.get("status") != "approved" else "Due for reassessment.")
            add(inv.get(s["id"], {}).get("owner") or s.get("owner"), "Impact assessment", ia.get("id"), s.get("name"), [ask],
                nr if ia.get("status") == "approved" else None, order=35)
    for a in review.actions(model):
        if a.get("status") == "open":
            add(a.get("owner"), "Management review action", f"{a['review']}/{a.get('id')}", "",
                [str(a.get("action") or "")], a.get("due"), order=25)
    # one section per person, however the owner name was capitalised
    canon: dict[str, str] = {}
    for i in out:
        i["owner"] = canon.setdefault(i["owner"].lower(), i["owner"])
    out.sort(key=lambda x: (not x["overdue"], x["due"] or dt.date.max, x["order"], x["ref"]))
    return out


def milestones(model: Engagement) -> list[tuple[dt.date, str]]:
    from . import review
    e = model.engagement
    ms = []
    objectives = {str(p.get("id")): p.get("objective") for p in model.playbook.get("phases") or [] if isinstance(p, dict)}
    for p in e.get("phases") or []:
        if isinstance(p, dict) and _d(p.get("start")):
            name = p.get("objective") or objectives.get(str(p.get("id"))) or p.get("label") or p.get("id")
            ms.append((_d(p["start"]), f"Phase starts: {name}"))
    d = e.get("dates") or {}
    if _d(d.get("stage1")):
        ms.append((_d(d["stage1"]), "Stage 1 certification audit"))
    if _d(d.get("stage2")):
        ms.append((_d(d["stage2"]), "Stage 2 certification audit"))
    for a in model.audits:
        if isinstance(a, dict) and _d((a.get("planned") or {}).get("start")):
            ms.append((_d(a["planned"]["start"]), f"Internal audit {a.get('id')} begins"))
    for rid, r in review.reviews(model).items():
        if r.get("status") == "planned" and _d(r.get("planned_on")):
            ms.append((_d(r["planned_on"]), f"Management review {rid}"))
    future = sorted(m for m in ms if m[0] >= model.today)
    stages = [m for m in future if "certification audit" in m[1]]
    others = [m for m in future if m not in stages][:8]
    return sorted(others + stages)


def overview(model: Engagement) -> list[tuple[str, str]]:
    from .rules import metrics
    m = metrics(model)
    pct = lambda a, b: f"{(a / b):.0%}" if b else "—"
    rows = [("Requirements fully ready", f"{m['requirements_ready']} of {m['requirements_applicable']} ({pct(m['requirements_ready'], m['requirements_applicable'])})"),
            ("Evidence checks complete", f"{m['legs_verified_pct']}%"),
            ("Open gaps", str(m["gaps_open"])),
            ("Policies and procedures approved", f"{m.get('docs_approved', 0)} of {m.get('docs_required', 0)}"),
            ]
    if model.uses_impact_assessments:
        rows.append(("AI systems with an approved impact assessment", f"{m.get('ia_current', 0)} of {m.get('ia_required', 0)}"))
    if m.get("findings_total"):
        rows.append(("Open nonconformities", f"{m.get('nc_open_major', 0)} major · {m.get('nc_open_minor', 0)} minor"))
    return rows


# ------------------------------------------------------------------ Markdown
def md(v) -> str:
    """Record text as inert Markdown: one line, no HTML, no tables/links/emphasis from the data."""
    t = " ".join(str(v if v is not None else "").split())
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_\[\]|#])", r"\\\1", t)


def render_md(model: Engagement, path: Path) -> Path:
    its = items(model)
    owners = sorted({i["owner"] for i in its}, key=lambda o: (o == UNASSIGNED, o.lower()))
    cv = model.engagement.get("client_view") or {}
    L = [f"# {md(model.client)} — readiness for {md(model.catalog['framework'].get('short_name'))}\n\n",
         f"As of {model.today}. {md(cv.get('intro') or 'What has been done, what is coming up, and what we need from you.')}\n\n"]
    if (model.engagement.get("sandbox") or {}).get("enabled"):
        L.append("> **Test engagement.** Some content is simulated data.\n\n")
    L.append("## Where things stand\n\n| | |\n|---|---|\n" + "".join(f"| {md(a)} | {md(b)} |\n" for a, b in overview(model)))
    ms = milestones(model)
    if ms:
        L.append("\n## Coming up\n\n" + "".join(f"- **{d}** — {md(t)}\n" for d, t in ms))
    L.append(f"\n## What we need from you\n\n{len(its)} open item(s) across {len(owners)} owner(s)"
             f"{', ' + str(sum(i['overdue'] for i in its)) + ' overdue' if any(i['overdue'] for i in its) else ''}.\n")
    for o in owners:
        mine = [i for i in its if i["owner"] == o]
        users = ", ".join("@" + u for u in model.github_users(o)) if o != UNASSIGNED else ""
        L.append(f"\n### {md(o)}{' (' + md(users) + ')' if users else ''} — {len(mine)} item(s)\n\n")
        if o == UNASSIGNED:
            L.append("_These need an owner. The engagement lead will agree one with you._\n\n")
        for i in mine:
            due = f" — due {i['due']}" + (" **(overdue)**" if i["overdue"] else "") if i["due"] else ""
            L.append(f"- **{md(i['kind'])} {md(i['ref'])}** {md(i['title'])}{due}\n" + "".join(f"  - {md(a)}\n" for a in i["ask"] if a))
    if cv.get("contact"):
        L.append(f"\n---\nQuestions: {md(cv['contact'])}\n")
    path.write_text("".join(L), encoding="utf-8")
    return path


# ------------------------------------------------------------------ HTML
CSS = """
:root{--ink:#1d2a33;--muted:#5c6b75;--line:#e3e8ec;--navy:#183B4E;--bg:#f6f8f9;--warn:#b42318;--warnbg:#fde8e7;--ok:#1a7f37}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
main{max-width:960px;margin:0 auto;padding:24px 16px 48px}h1{font-size:24px;margin:0 0 4px;color:var(--navy)}
h2{font-size:18px;margin:28px 0 10px;color:var(--navy)}.sub{color:var(--muted);margin:0 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px}.card b{display:block;font-size:20px}
.card span{color:var(--muted);font-size:13px}ul.ms{list-style:none;padding:0;margin:0}ul.ms li{padding:6px 0;border-bottom:1px solid var(--line)}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:8px 0 12px}select,label{font:inherit}
.owner{background:#fff;border:1px solid var(--line);border-radius:8px;margin:12px 0;padding:4px 14px 10px}
.owner h3{font-size:16px;margin:10px 0 6px}.item{border-top:1px solid var(--line);padding:8px 0}.item:first-of-type{border-top:0}
.tag{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:10px;padding:0 8px;margin-right:6px;color:var(--muted)}
.due{font-size:13px;color:var(--muted)}.over .due{color:var(--warn);font-weight:600}.over{background:linear-gradient(90deg,var(--warnbg),transparent 40%)}
.item ul{margin:4px 0 0 18px;padding:0}.banner{background:#fff4ce;border:1px solid #f2d675;padding:8px 12px;border-radius:6px}
footer{color:var(--muted);font-size:13px;margin-top:32px}@media print{.controls{display:none}body{background:#fff}.owner{break-inside:avoid}}
"""
JS = """
const sel=document.getElementById('who'),od=document.getElementById('od');
function apply(){document.querySelectorAll('.owner').forEach(o=>{const show=!sel.value||o.dataset.owner===sel.value;
let n=0;o.querySelectorAll('.item').forEach(i=>{const v=show&&(!od.checked||i.classList.contains('over'));i.hidden=!v;if(v)n++});o.hidden=!n});
document.getElementById('none').hidden=!!document.querySelector('.owner:not([hidden])');}
sel.addEventListener('change',apply);od.addEventListener('change',apply);
"""


def render_html(model: Engagement, path: Path) -> Path:
    e = html.escape
    its = items(model)
    owners = sorted({i["owner"] for i in its}, key=lambda o: (o == UNASSIGNED, o.lower()))
    cv = model.engagement.get("client_view") or {}
    fw = model.catalog["framework"].get("short_name")
    H = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
         "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
         "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'\">",
         f"<title>{e(model.client)} — {e(fw)} readiness</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(model.client)} — {e(fw)} readiness</h1>",
         f"<p class=\"sub\">As of {e(str(model.today))}. {e(cv.get('intro') or 'What has been done, what is coming up, and what we need from you.')}</p>"]
    if (model.engagement.get("sandbox") or {}).get("enabled"):
        H.append("<p class=\"banner\"><b>Test engagement.</b> Some content is simulated data.</p>")
    H.append("<h2>Where things stand</h2><div class=\"cards\">")
    H += [f"<div class=\"card\"><b>{e(b)}</b><span>{e(a)}</span></div>" for a, b in overview(model)]
    H.append("</div>")
    ms = milestones(model)
    if ms:
        H.append("<h2>Coming up</h2><ul class=\"ms\">" + "".join(f"<li><b>{e(str(d))}</b> — {e(t)}</li>" for d, t in ms) + "</ul>")
    n_over = sum(i["overdue"] for i in its)
    H.append(f"<h2>What we need from you</h2><p class=\"sub\">{len(its)} open item(s) across {len(owners)} owner(s)"
             + (f", <b>{n_over} overdue</b>" if n_over else "") + ".</p>")
    H.append("<div class=\"controls\"><label>Owner <select id=\"who\"><option value=\"\">Everyone</option>"
             + "".join(f"<option value=\"{e(o, quote=True)}\">{e(o)}</option>" for o in owners)
             + "</select></label><label><input type=\"checkbox\" id=\"od\"> Overdue only</label></div>")
    H.append("<p id=\"none\" class=\"sub\"" + ("" if not its else " hidden") + ">Nothing to show for this selection.</p>")
    for o in owners:
        mine = [i for i in its if i["owner"] == o]
        users = ", ".join("@" + u for u in model.github_users(o)) if o != UNASSIGNED else ""
        H.append(f"<section class=\"owner\" data-owner=\"{e(o, quote=True)}\"><h3>{e(o)}"
                 + (f" <span class=\"tag\">{e(users)}</span>" if users else "") + f" <span class=\"tag\">{len(mine)}</span></h3>")
        if o == UNASSIGNED:
            H.append("<p class=\"sub\">These need an owner. The engagement lead will agree one with you.</p>")
        for i in mine:
            due = (f"<span class=\"due\">due {e(str(i['due']))}{' — overdue' if i['overdue'] else ''}</span>" if i["due"] else "")
            H.append(f"<div class=\"item{' over' if i['overdue'] else ''}\"><span class=\"tag\">{e(i['kind'])}</span>"
                     f"<b>{e(i['ref'])}</b> {e(i['title'])} {due}<ul>"
                     + "".join(f"<li>{e(a)}</li>" for a in i["ask"] if a) + "</ul></div>")
        H.append("</section>")
    H.append("<footer>Generated from the engagement record" + (f". Questions: {e(cv['contact'])}" if cv.get("contact") else "")
             + ".</footer></main><script>" + JS + "</script></body></html>")
    path.write_text("".join(H), encoding="utf-8")
    return path


def render(model: Engagement, out: Path) -> list[tuple[str, str, str]]:
    render_md(model, out / "client-view.md")
    render_html(model, out / "client-view.html")
    its = items(model)
    return [("Client view", "client-view.md", f"For the client's people: progress, dates and {len(its)} open request(s) by owner "
             "([HTML to share](client-view.html?raw=1))")]
