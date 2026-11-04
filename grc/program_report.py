"""Program reports: control catalog, coverage, scorecard, matrix workbook and the governance calendar (.ics).

    python -m grc program report --out out/program

Writes:
  program.md                   scorecard (the KPIs for the quarterly report to security leadership)
  control-catalog.md           every common control, its owner, evidence and the requirements it satisfies
  coverage.md                  per framework: in-scope requirements with and without a common control,
                               and mappings the crosswalks suggest
  governance-calendar.md       obligations, the next due date and what is overdue
  governance-calendar.ics      the next 12 months of due dates, for Outlook / Google Calendar
  certifications.md            quarterly owner certifications and the exceptions owners reported
  common-control-matrix.xlsx   Controls, Mapping, Coverage and Calendar sheets
  scorecard.json               the same KPIs, machine-readable (one file per quarter on the reports branch
                               gives the trend)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import program as P
from .rules import Finding


def _md_table(head: list[str], rows: list[list]) -> str:
    esc = lambda v: str("" if v is None else v).replace("|", "\\|").replace("\n", " ")
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]) + "\n"


def _pct(v) -> str:
    return "–" if v is None else f"{v}%"


def scorecard_md(prog: P.Program, sc: dict, findings: list[Finding]) -> str:
    errs = sum(f.severity == "error" for f in findings)
    warns = sum(f.severity == "warning" for f in findings)
    cert = sc["certification"]
    lines = [f"# Compliance program scorecard", "", f"As of {sc['as_of']}. Validation: {errs} error(s), {warns} warning(s).", "",
             "## Controls", "",
             _md_table(["Measure", "Value"], [
                 ["Common controls", sc["controls"]],
                 ["Requirement mappings (one control can satisfy many)", sc["requirements_mapped"]],
                 ["Average requirements satisfied per control", sc["avg_requirements_per_control"]],
                 ["Controls serving two or more of the frameworks in scope", sc["multi_framework_controls"]],
                 ["Automated controls", _pct(sc["automated_controls_pct"])],
                 ["Cited evidence that is current", _pct(sc["evidence_current_pct"])],
                 ["Controls with no evidence cited", sc["controls_without_evidence"]]]),
             "## Coverage by framework", "",
             _md_table(["Framework", "Record", "In scope", "With a common control", "Coverage"],
                       [[c["name"], (c["record"] + "/") if c["record"] else "reference only", c["in_scope"] if c["in_scope"] is not None else "–",
                         c["covered"], _pct(c["pct"])] for c in sc["coverage"]]),
             "## Governance calendar", "",
             _md_table(["Measure", "Value"], [
                 ["Recurring obligations", sc["obligations"]],
                 ["Due in the last 90 days", sc["obligations_due_90d"]],
                 ["Completed on time (last 90 days)", _pct(sc["obligations_on_time_pct"])],
                 ["Overdue now", sc["obligations_overdue"]]]),
             f"## Owner certification ({cert['period']})", "",
             _md_table(["Measure", "Value"], [
                 ["Control owners", cert["owners"]],
                 ["Certifications opened", cert["opened"]],
                 ["Signed", f"{cert['certified']} ({_pct(sc['certification_pct'])})"],
                 ["Controls reported as exception or not operating", cert["exceptions"]]]),
             "## Findings and gaps (all records)", "",
             _md_table(["Measure", "Value"], [
                 ["Open findings", sc["open_findings"]],
                 ["Open findings older than 90 days", sc["findings_over_90d"]],
                 ["Average days to close a finding", sc["avg_days_to_close_finding"] if sc["avg_days_to_close_finding"] is not None else "–"],
                 ["Open gaps", sc["open_gaps"]]])]
    if findings:
        lines += ["## Validation", "", _md_table(["Severity", "Code", "Message"],
                                                  [[f.severity, f.code, f.message] for f in findings if f.severity != "info"])]
    return "\n".join(lines)


def catalog_md(prog: P.Program) -> str:
    fws = sorted({fw for c in prog.controls for fw in (c.get("maps") or {})},
                 key=lambda fw: (fw not in prog.records, fw))
    rows = []
    for c in sorted(prog.controls, key=lambda c: c["id"]):
        maps = c.get("maps") or {}
        rows.append([c["id"], c.get("title", ""), c.get("owner", ""), c.get("frequency", ""), c.get("type", ""),
                     len(c.get("evidence") or []), P.reuse(c)] + [", ".join(maps.get(fw, [])) for fw in fws])
    head = ["Control", "Title", "Owner", "Frequency", "Type", "Evidence", "Requirements"] + [prog.framework_name(fw) for fw in fws]
    out = ["# Common control catalog", "",
           f"{len(prog.controls)} controls. Each is run and evidenced once and satisfies the requirements listed "
           "against it in every framework. A mapping is the program's claim; each record still tests the "
           "requirement against its evidence.", "", _md_table(head, rows)]
    detail = []
    for c in sorted(prog.controls, key=lambda c: c["id"]):
        detail += [f"### {c['id']} {c.get('title', '')}", ""]
        if c.get("description"):
            detail += [c["description"].strip(), ""]
        detail.append(f"Owner: {c.get('owner', '')}. Frequency: {c.get('frequency', '–')}. Type: {c.get('type', '–')}.")
        detail.append("")
        for fw, rids in (c.get("maps") or {}).items():
            idx = prog.requirement_index(fw)
            detail.append(f"- **{prog.framework_name(fw)}:** " + "; ".join(f"{r} {idx.get(r, {}).get('title', '?')}" for r in rids))
        for ref in c.get("evidence") or []:
            rec, ev = prog.evidence(ref)
            state = "not found" if ev is None else ("current" if rec.evidence_is_current(ev) else "expired or failing")
            detail.append(f"- Evidence `{ref}`: {(ev or {}).get('title', '')} ({state})")
        detail.append("")
    return "\n".join(out + ["## Controls in detail", ""] + detail)


def coverage_md(prog: P.Program) -> str:
    out = ["# Coverage by framework", "",
           "In-scope requirements of each record, and whether a common control satisfies them. Requirements "
           "with no control are either covered by something the program doesn't track yet, or a gap.", ""]
    for cv in P.coverage(prog):
        if not cv["record"]:
            continue
        rec = prog.records[cv["framework"]]
        out += [f"## {cv['name']} ({cv['record']}/): {cv['covered']} of {cv['in_scope']} ({cv['pct']}%)", ""]
        if cv["unmapped"]:
            out += ["Not mapped to any common control:", "",
                    _md_table(["Requirement", "Title"], [[r, rec.requirement_index[r]["title"]] for r in cv["unmapped"]])]
        else:
            out += ["Every in-scope requirement maps to at least one common control.", ""]
    sug = P.suggestions(prog)
    out += ["## Mappings the crosswalks suggest", "",
            "From the framework crosswalks in mappings/ (the engine's are proposals until someone reviews them). "
            "Add a suggestion to the control's `maps` only after checking the control really meets it.", ""]
    out += [_md_table(["Control", "Because it maps to", "Suggested", "Relationship", "Crosswalk reviewed"],
                      [[s["control"], s["from"], f"{prog.framework_name(s['to_fw'])} {s['to']}", s["relationship"],
                        "yes" if s["reviewed"] else "no (proposed)"] for s in sug])] if sug else ["None.", ""]
    return "\n".join(out)


def calendar_md(prog: P.Program) -> str:
    rows = []
    for ob in sorted(prog.obligations, key=lambda o: o["id"]):
        occ = P.occurrences(prog, ob, horizon_days=400)
        nxt = next((o for o in occ if o["status"] in ("due_soon", "upcoming")), None)
        overdue = [o["due"].isoformat() for o in occ if o["status"] == "overdue"]
        last = max((o for o in occ if o["done"]), key=lambda o: o["due"], default=None)
        rows.append([ob["id"], ob.get("title", ""), ob.get("owner", ""), ob.get("every", ""),
                     (f"{last['done'].get('completed')} for {last['due']} "
                      f"({'on time' if last['status'] == 'done_on_time' else 'late'})" if last else "–"),
                     nxt["due"].isoformat() if nxt else "–", ", ".join(overdue) or "–", ob.get("source", "")])
    return "\n".join(["# Governance calendar", "",
                      f"As of {prog.today}. Each obligation has an owner, due dates and evidence of completion. "
                      "Subscribe to governance-calendar.ics to see the due dates in your calendar.", "",
                      _md_table(["Obligation", "Title", "Owner", "Every", "Last completed", "Next due", "Overdue", "Source"], rows)])


def ics(prog: P.Program, months: int = 12) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    until = P.add_months(prog.today, months)
    esc = lambda s: str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//grc-readiness//governance calendar//EN", "CALSCALE:GREGORIAN",
           "X-WR-CALNAME:Governance calendar"]
    for ob in prog.obligations:
        for d in P.due_dates(ob, until):
            if d < prog.today - dt.timedelta(days=31):
                continue
            nxt = d + dt.timedelta(days=1)
            desc = f"Owner: {ob.get('owner', '')}\nEvidence: {ob.get('evidence_expected', '')}\nSource: {ob.get('source', '')}"
            out += ["BEGIN:VEVENT", f"UID:{ob['id']}-{d.isoformat()}@grc-readiness", f"DTSTAMP:{stamp}",
                    f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{nxt.strftime('%Y%m%d')}",
                    f"SUMMARY:{esc('Due: ' + ob.get('title', ob['id']))}", f"DESCRIPTION:{esc(desc)}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


def certifications_md(prog: P.Program) -> str:
    out = ["# Owner certifications", "",
           "Each quarter every control owner confirms, in a pull request, that their controls operated as "
           "described, or reports what didn't.", ""]
    for period in sorted(prog.certifications, reverse=True):
        st = P.certification_status(prog, period)
        out += [f"## {period}: {st['certified']} of {st['owners']} owners signed, {st['exceptions']} exception(s)", ""]
        rows, exc = [], []
        for s, d in sorted(prog.certifications[period].items()):
            ctl = [x for x in d.get("controls") or [] if isinstance(x, dict)]
            rows.append([d.get("owner", s), len(ctl), sum(1 for x in ctl if x.get("response") == "pending"),
                         d.get("certified_by") or "–", d.get("certified_on") or "–", d.get("due") or "–"])
            exc += [[d.get("owner", s), x.get("id"), x.get("response"), x.get("note", ""), x.get("follow_up", "")]
                    for x in ctl if x.get("response") in ("exception", "not_operating", "not_applicable")]
        out.append(_md_table(["Owner", "Controls", "Pending", "Certified by", "On", "Due"], rows))
        if exc:
            out += ["Reported by owners:", "", _md_table(["Owner", "Control", "Response", "Note", "Follow-up"], exc)]
    if not prog.certifications:
        out.append("No certifications yet. Run **Actions → Compliance program** with `certify` (or `grc program certify`).")
    return "\n".join(out)


def workbook(prog: P.Program, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    head_fill, bold = PatternFill("solid", fgColor="183B4E"), Font(bold=True, color="FFFFFF")

    def sheet(ws, head, rows, widths):
        ws.append(head)
        for c in ws[1]:
            c.font, c.fill = bold, head_fill
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")

    fws = sorted({fw for c in prog.controls for fw in (c.get("maps") or {})}, key=lambda fw: (fw not in prog.records, fw))
    ws = wb.active
    ws.title = "Controls"
    sheet(ws, ["Control", "Title", "Owner", "Frequency", "Type", "Evidence", "Requirements"] + [prog.framework_name(f) for f in fws],
          [[c["id"], c.get("title", ""), c.get("owner", ""), c.get("frequency", ""), c.get("type", ""),
            "\n".join(c.get("evidence") or []), P.reuse(c)] + ["\n".join((c.get("maps") or {}).get(f, [])) for f in fws]
           for c in sorted(prog.controls, key=lambda c: c["id"])],
          [14, 36, 22, 12, 11, 22, 13] + [22] * len(fws))
    rows = []
    for c in sorted(prog.controls, key=lambda c: c["id"]):
        for fw, rids in (c.get("maps") or {}).items():
            idx = prog.requirement_index(fw)
            rows += [[c["id"], c.get("title", ""), prog.framework_name(fw), r, idx.get(r, {}).get("title", "")] for r in rids]
    sheet(wb.create_sheet("Mapping"), ["Control", "Control title", "Framework", "Requirement", "Requirement title"], rows,
          [14, 36, 18, 14, 50])
    m = P.mapped(prog)
    rows = []
    for fw, rec in prog.records.items():
        for rid in P.in_scope(rec):
            rows.append([prog.framework_name(fw), rid, rec.requirement_index[rid]["title"], ", ".join(m.get(fw, {}).get(rid, [])) or "NOT MAPPED"])
    sheet(wb.create_sheet("Coverage"), ["Framework", "Requirement", "Title", "Common controls"], rows, [18, 14, 50, 30])
    rows = []
    for ob in prog.obligations:
        for o in P.occurrences(prog, ob, horizon_days=366):
            e = o["done"] or {}
            rows.append([ob["id"], ob.get("title", ""), ob.get("owner", ""), o["due"], o["status"].replace("_", " "),
                         e.get("completed", ""), "\n".join(e.get("evidence") or [])])
    sheet(wb.create_sheet("Calendar"), ["Obligation", "Title", "Owner", "Due", "Status", "Completed on", "Evidence"], rows,
          [14, 36, 22, 12, 14, 13, 24])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_all(prog: P.Program, findings: list[Finding], out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    sc = P.scorecard(prog)
    files = {"program.md": scorecard_md(prog, sc, findings), "scorecard.json": json.dumps(sc, indent=2, default=str) + "\n"}
    if prog.controls:
        files["control-catalog.md"] = catalog_md(prog)
        files["coverage.md"] = coverage_md(prog)
    if prog.obligations:
        files["governance-calendar.md"] = calendar_md(prog)
        files["governance-calendar.ics"] = ics(prog)
    files["certifications.md"] = certifications_md(prog)
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="" if name.endswith(".ics") else None)
    names = sorted(files)
    if prog.controls or prog.obligations:
        workbook(prog, out / "common-control-matrix.xlsx")
        names.append("common-control-matrix.xlsx")
    return names
