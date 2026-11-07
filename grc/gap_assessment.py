"""Gap assessment: a client-facing report on how far the client's existing setup goes towards the framework.

It is built from what the record already holds, so it is as current as the record:
  - the client's existing controls (existing-controls.yaml, from their control register or GRC tool export)
  - what ingest drafted from their policies, spreadsheets and prior audit reports (claims and gaps)
  - anything already verified by the engagement team

Each requirement in scope gets one coverage state:
  Verified           every leg of the four-part evidence test verified (Ready)
  Gap                an open gap names it
  Reported in place  an existing control in place maps to it, or the client says it is in use; not yet tested
  Partly in place    something is written down, or under way, but not reported as in use
  No existing control  nothing found

Output: gap-assessment.md (and .docx with the Office files). No hours, budget or analyst notes.
"""
from __future__ import annotations

import collections
from pathlib import Path

from .model import LEGS, Engagement

STATES = ["Verified", "Reported in place", "Partly in place", "Gap", "No existing control"]
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def _esc(s) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def _table(headers, rows) -> str:
    if not rows:
        return "_None._\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def coverage(model: Engagement) -> dict[str, str]:
    """{requirement id: coverage state} for every applicable requirement in scope."""
    from .rules import leg_effective, requirement_state
    open_gaps = collections.defaultdict(list)
    for g in model.gaps:
        if isinstance(g, dict) and g.get("status") in ("open", "in_progress"):
            for r in g.get("requirements") or []:
                open_gaps[str(r)].append(g)
    reg = collections.defaultdict(set)
    for row in model.existing_controls:
        if isinstance(row, dict):
            for r in row.get("maps") or []:
                reg[str(r)].add(str(row.get("state") or "unknown"))
    out = {}
    for req in model.requirements:
        rid = str(req["id"])
        if not model.in_category_scope(rid) or not model.is_applicable(rid):
            continue
        if requirement_state(model, rid) == "Ready":
            out[rid] = "Verified"
            continue
        if open_gaps.get(rid):
            out[rid] = "Gap"
            continue
        c = model.controls.get(rid) or {}
        legs = {k: leg_effective(model, (c.get("test") or {}).get(k) or {}) for k in LEGS}
        if "in_place" in reg[rid] or legs["implemented"] != "not_started":
            out[rid] = "Reported in place"
        elif reg[rid] or any(v != "not_started" for v in legs.values()):
            out[rid] = "Partly in place"
        else:
            out[rid] = "No existing control"
    return out


def _sources(model: Engagement) -> list[str]:
    """The files ingest read for this record (intake ledger), newest first."""
    import yaml
    name = model.engagement_dir.name
    intake = model.root / ("intake" + name[len("engagement"):]) if name.startswith("engagement") else model.root / "intake"
    led = intake / ".processed.yaml"
    if not led.exists():
        return []
    try:
        data = yaml.safe_load(led.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    how = {"ai": "read by Claude", "register": "control register"}
    rows = sorted(((str(v.get("ingested") or ""), k, str(v.get("mode") or "")) for k, v in data.items() if isinstance(v, dict)),
                  reverse=True)
    return [f"`{k}` ({how.get(m, 'intake template' if m.startswith('template') else m)}{', ' + d if d else ''})" for d, k, m in rows]


def markdown(model: Engagement) -> str:
    cov = coverage(model)
    fw = model.catalog["framework"]["short_name"]
    idx = model.requirement_index
    groups = {str(g["id"]): str(g.get("title") or g["id"]) for g in model.catalog.get("groups") or [] if isinstance(g, dict)}
    counts = collections.Counter(cov.values())
    total = len(cov)
    pct = lambda n: f"{round(100 * n / total)}%" if total else "0%"
    L = [f"# {model.client} — {fw} gap assessment\n",
         f"As of {model.today.isoformat()}. Prepared from the information {model.client} provided: its existing controls, "
         "policies and earlier assessments. What it reports as in place is its own statement until the engagement team "
         "has tested it.\n",
         "## 1. Summary\n",
         f"**{total}** requirements of {fw} apply to {model.client}"
         + (f" (in scope: {', '.join(sorted(c for c in model.categories_in_scope))})" if model.category_index else "") + ".\n",
         _table(["Coverage", "Requirements", "Share", "What it means"], [
             ["Verified", counts["Verified"], pct(counts["Verified"]), "Tested by the engagement team: documented, in use, with records, and tested"],
             ["Reported in place", counts["Reported in place"], pct(counts["Reported in place"]), "An existing control covers it and is reported as working; to be tested"],
             ["Partly in place", counts["Partly in place"], pct(counts["Partly in place"]), "Something is written down or under way, not yet in use"],
             ["Gap", counts["Gap"], pct(counts["Gap"]), "A known gap must be closed (section 3)"],
             ["No existing control", counts["No existing control"], pct(counts["No existing control"]), "Nothing found yet (section 4)"]]),
         ""]
    # 2. by area
    by_group: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for rid, st in cov.items():
        by_group[str(idx[rid].get("group") or "")][st] += 1
    order = [g for g in groups if g in by_group] + sorted(g for g in by_group if g not in groups)
    L += ["## 2. Coverage by area\n",
          _table(["Area", "In scope", *STATES],
                 [[groups.get(g, g or "Other"), sum(by_group[g].values()), *(by_group[g][s] or "" for s in STATES)] for g in order]), ""]
    # 3. gaps
    gaps = [g for g in model.gaps if isinstance(g, dict) and g.get("status") in ("open", "in_progress") and model.gap_in_scope(g)]
    gaps.sort(key=lambda g: (SEV_ORDER.get(str(g.get("severity")), 1), str(g.get("due") or "9999"), str(g.get("id"))))
    L += ["## 3. Gaps to close\n",
          _table(["Gap", "Severity", "Area", "Finding", "Requirements", "Owner", "Due"],
                 [[g.get("id"), g.get("severity") or "medium", g.get("area"), model.fmt(str(g.get("finding") or "")),
                   ", ".join(str(r) for r in g.get("requirements") or []), g.get("owner") or "Not yet assigned",
                   g.get("due") or ""] for g in gaps]), ""]
    # 4. nothing found
    none = [rid for rid, s in cov.items() if s == "No existing control"]
    L += ["## 4. Requirements with no existing control\n",
          f"Nothing in the information provided covers these {len(none)} requirement(s). Each needs a control, or "
          "evidence that one already exists.\n" if none else "",
          _table(["Requirement", "Title", "Area"], [[r, idx[r].get("title"), groups.get(str(idx[r].get("group") or ""), "")] for r in none]), ""]
    # 5. the client's own controls
    rows = [r for r in model.existing_controls if isinstance(r, dict)]
    if rows:
        st = collections.Counter(str(r.get("state") or "unknown") for r in rows)
        unmapped = [r for r in rows if not r.get("maps")]
        notin = [r for r in rows if r.get("state") in ("not_in_place", "partial") and r.get("maps")]
        L += [f"## 5. {model.client}'s existing controls\n",
              f"{len(rows)} controls were imported from {model.client}'s control register: {st['in_place']} reported in place, "
              f"{st['partial']} partly, {st['not_in_place']} not in place, {st['unknown']} with no status. "
              f"{len(rows) - len(unmapped)} map to {fw} requirements.\n",
              "### Reported as not fully in place\n",
              _table(["Control", "Status", "Requirements", "Owner"],
                     [[f"{r.get('ref') + ' ' if r.get('ref') else ''}{r.get('name')}", r.get("status") or "", ", ".join(r.get("maps") or []),
                       r.get("owner") or ""] for r in notin]),
              f"### Not mapped to {fw}\n",
              (f"These controls name no {fw} requirement. Some may support it (an analyst maps them by editing "
               "`maps` in `existing-controls.yaml`); others belong to other frameworks or none.\n" if unmapped else ""),
              _table(["Control", "Status", "Other references"],
                     [[f"{r.get('ref') + ' ' if r.get('ref') else ''}{r.get('name')}", r.get("status") or "",
                       ", ".join(r.get("unrecognized") or [])] for r in unmapped]), ""]
    else:
        L += [f"## 5. {model.client}'s existing controls\n",
              "No control register has been imported. To include one, upload the export from your GRC tool or your control "
              "spreadsheet to the intake folder.\n", ""]
    # 6. roadmap
    phase_rows = []
    by_phase = collections.defaultdict(list)
    from .model import to_date
    ids = {str(ph.get("id")) for ph in model.phases}
    labels = {str(ph.get("label") or "").lower(): str(ph.get("id")) for ph in model.phases}

    def when(g):
        p = str(g.get("phase") or "")
        if p in ids:
            return p
        if p.lower() in labels:
            return labels[p.lower()]
        try:
            due = to_date(g.get("due")) if g.get("due") else None
        except (TypeError, ValueError):
            due = None
        for ph in model.phases:      # no phase: the phase whose dates hold its due date
            try:
                if due and to_date(ph.get("start")) <= due <= to_date(ph.get("end")):
                    return str(ph.get("id"))
            except (TypeError, ValueError):
                continue
        return ""
    for g in gaps:
        by_phase[when(g)].append(g)
    for ph in model.phases:
        pid = str(ph.get("id"))
        items = by_phase.pop(pid, [])
        phase_rows.append([ph.get("label") or pid, f"{ph.get('start') or ''} – {ph.get('end') or ''}".strip(" –"),
                           model.fmt(str(ph.get("objective") or "")),
                           ", ".join(str(g.get("id")) for g in items) or "—"])
    left = [g for k, v in by_phase.items() for g in v]
    L += ["## 6. Remediation roadmap\n", _table(["Phase", "Dates", "Objective", "Gaps planned"], phase_rows),
          (f"\nNot yet scheduled: {', '.join(str(g.get('id')) for g in left)}. Each gets a phase and a due date when its "
           "owner agrees the plan.\n" if left else ""), ""]
    # 7. basis
    src = _sources(model)
    L += ["## 7. Basis and limits\n",
          "- What a control register, policy or earlier report says is a statement, not proof. A requirement is "
          "**Verified** only when the engagement team has seen it documented, in use, with records, and tested.",
          "- Earlier audit reports cover their own period and scope, which may differ from this one.",
          "- Mappings between the client's controls and the requirements were read from the client's own register; "
          "an analyst checks them.",
          "", "Information reviewed:", *(f"- {s}" for s in src or ["(none recorded)"]), ""]
    return "\n".join(x for x in L if x is not None)


def report(model: Engagement, out: Path, with_docx: bool = False) -> list[tuple[str, str, str]]:
    md = markdown(model)
    (out / "gap-assessment.md").write_text(md, encoding="utf-8")
    link = "gap-assessment.md"
    desc = "Client-facing: how far the existing setup goes, the gaps to close and the roadmap"
    if with_docx:
        from .render_docx import render_markdown
        render_markdown(model, md, out / "gap-assessment.docx", f"{model.client} — gap assessment", model.today)
        desc += " ([Word](gap-assessment.docx?raw=1))"
    return [("Gap assessment", link, desc)]
