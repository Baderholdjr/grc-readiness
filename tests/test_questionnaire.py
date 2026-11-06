"""Security questionnaires (HECVAT 4): definition, import, draft, validation, fill, learn.

The real HECVAT workbook is EDUCAUSE's and isn't in this repository. These tests build a small workbook with
the same layout (sheets, columns, dropdowns, formulas). Set GRC_HECVAT_WORKBOOK to a real HECVAT 4 workbook to
also run the import against it.
"""
import datetime as dt
import os
import re
import zipfile
from pathlib import Path

import openpyxl
import pytest
import yaml
from openpyxl.worksheet.datavalidation import DataValidation

from grc import program as P
from grc import questionnaire as Q
from grc.cli import main
from grc.model import ENGINE

TODAY = dt.date(2026, 11, 6)
DEF = ENGINE / "questionnaires" / "hecvat-4.yaml"
SHEETS = ["START HERE", "Organization", "Product", "Infrastructure", "IT Accessibility", "Case-Specific", "AI", "Privacy"]
# id, sheet, our own made-up question text, compliant answer
ROWS = [
    ("GNRL-01", "START HERE", "Provider name", "Not scored"),
    ("GNRL-02", "START HERE", "Product name", "Not scored"),
    ("REQU-01", "START HERE", "Cloud offering?", "Not scored"),
    ("REQU-06", "START HERE", "Card data?", "Not scored"),
    ("COMP-03", "START HERE", "No outages last year?", "Yes"),
    ("PPPR-08", "Organization", "Written security policy?", "Yes"),
    ("CHNG-01", "Organization", "Tell customers about big changes?", "Yes"),
    ("DATA-01", "Product", "Public IP addresses on data hosts?", "No"),
    ("PCID-01", "Case-Specific", "Card industry attestation?", "Yes"),
]


def make_workbook(path: Path) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for s in SHEETS:
        wb.create_sheet(s)
    q = wb.create_sheet("Questions")
    ar = wb.create_sheet("Auto Responses")
    ar["A36"] = "Version 4.1.4"
    for i, v in enumerate(["Yes", "No", "N/A"], start=3):
        ar[f"J{i}"] = v
    q["A2"], q["B2"], q["O2"], q["U2"] = "New ID", "Question", "Standard Guidance", "Compliant Response"
    for i, (qid, _, text, comp) in enumerate(ROWS, start=3):
        q[f"A{i}"], q[f"B{i}"], q[f"O{i}"], q[f"U{i}"] = qid, text, "Some guidance.", comp
    dv = {s: DataValidation(type="list", formula1="'Auto Responses'!$J$3:$J$5", allow_blank=True) for s in SHEETS}
    rownum = {s: 13 for s in SHEETS}
    for qid, sheet, _, _ in ROWS:
        ws = wb[sheet]
        r = rownum[sheet]
        ws[f"A{r}"] = qid
        ws[f"B{r}"] = f'=VLOOKUP($A{r},Questions!$A$2:$X$333,2,0)&""'
        if not qid.startswith("GNRL"):
            dv[sheet].add(f"C{r}")
        rownum[sheet] += 1
    org = wb["Organization"]           # the general questions repeat on each tab, filled from START HERE
    org["A40"], org["C40"] = "GNRL-01", "=VLOOKUP($A40,'START HERE'!$A$13:$C$21,3,0)&\"\""
    for s in SHEETS:
        if dv[s].sqref:
            wb[s].add_data_validation(dv[s])
    wb.save(path)
    return path


def _ev(edir, eid="EV-001"):
    (edir / "evidence" / "index.yaml").write_text(yaml.safe_dump({"evidence": [
        {"id": eid, "title": "Information security policy, approved", "type": "record", "location": "drive://x",
         "collected": "2026-11-01", "approved_by": "CISO", "approved_on": "2026-11-01", "valid_for_days": 365}]}))


def setup_repo(tmp_path, with_program=True) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    if with_program:
        e = root / "engagement"
        assert main(["--engagement", str(e), "new-engagement", "--client", "Larch & Finch", "--start", "2026-11-02",
                     "--stage1", "2027-02-01", "--stage2", "2027-04-01", "--framework", "iso27001",
                     "--intake", str(root / "intake"), "--confirm-reset"]) == 0
        _ev(e)
        (root / "program").mkdir()
        (root / "program" / "controls.yaml").write_text(yaml.safe_dump({"controls": [
            {"id": "CTL-POL", "title": "Security policy set", "owner": "CISO",
             "description": "Policies are approved by leadership and reviewed every year.",
             "evidence": ["iso27001:EV-001"], "maps": {"iso27001": ["A.5.1"], "nist80053": ["PM-1"]}},
            {"id": "CTL-NET", "title": "Network segmentation", "owner": "Head of Platform",
             "maps": {"iso27001": ["A.8.22"]}}]}))
    wbk = make_workbook(tmp_path / "received.xlsx")
    assert main(["--today", TODAY.isoformat(), "questionnaire", "import", "--root", str(root), "--workbook", str(wbk),
                 "--name", "hecvat-fsu", "--requester", "Fictional State University", "--due", "2026-11-30"]) == 0
    return root


def _q(root):
    return Q.load_questionnaire(root, "hecvat-fsu")


def _set(root, qid, **kw):
    p = root / "questionnaires" / "hecvat-fsu" / "answers.yaml"
    d = yaml.safe_load(p.read_text())
    for a in d["answers"]:
        if a["id"] == qid:
            a.update(kw)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _codes(root, today=TODAY):
    return [f.code for f in Q.validate(root, P.load_program(root, today=today), today)]


def _draft(root, today=TODAY):
    assert main(["--today", today.isoformat(), "questionnaire", "draft", "--root", str(root)]) == 0
    return {a["id"]: a for a in _q(root).answers}


# ------------------------------------------------------------------ the definition
def test_hecvat_definition_maps_real_requirements_and_never_copies_the_questions():
    d = yaml.safe_load(DEF.read_text())
    qs = d["questions"]
    assert len(qs) == 331 and all(re.fullmatch(r"[A-Z]{4}-\d{2}", k) for k in qs)
    ids = {}
    for fw in ("iso27001", "soc2", "hipaa", "iso42001"):
        ids[fw] = {str(r["id"]) for r in yaml.safe_load((ENGINE / "frameworks" / fw / "catalog.yaml").read_text())["requirements"]}
    ids["nist80053"] = {str(r["id"]) for r in yaml.safe_load((ENGINE / "reference" / "nist80053.yaml").read_text())["requirements"]}
    for qid, v in qs.items():
        assert v["topic"] and len(v["topic"]) <= 60 and v["answer"] in ("yes_no", "text", "choice"), qid
        for fw, refs in (v.get("maps") or {}).items():
            assert refs and set(map(str, refs)) <= ids[fw], (qid, fw, refs)
    assert sum(1 for v in qs.values() if v.get("maps")) >= 200
    assert {g["question"] for g in d["gates"]} == {f"REQU-0{i}" for i in range(1, 9)}
    assert set(d["profile"]) == {f"GNRL-0{i}" for i in range(1, 10)} and set(d["profile"]) <= set(qs)


@pytest.mark.skipif(not os.environ.get("GRC_HECVAT_WORKBOOK"), reason="set GRC_HECVAT_WORKBOOK to a real HECVAT 4 workbook")
def test_import_a_real_hecvat_workbook(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    Q.import_workbook(root, Path(os.environ["GRC_HECVAT_WORKBOOK"]), "real", today=TODAY)
    qn = _q_named(root, "real")
    assert len(qn.questions) == 331 and qn.meta["version"] == "4.1.4"
    assert {q["id"] for q in qn.questions} == set(yaml.safe_load(DEF.read_text())["questions"])


def _q_named(root, name):
    return Q.load_questionnaire(root, name)


# ------------------------------------------------------------------ import
def test_import_reads_questions_answer_cells_and_dropdowns(tmp_path):
    root = setup_repo(tmp_path, with_program=False)
    qn = _q(root)
    assert qn.meta["version"] == "4.1.4" and qn.meta["requester"] == "Fictional State University"
    assert (root / "questionnaires" / "hecvat-fsu" / "received.xlsx").exists()
    by = qn.qindex
    assert len(by) == len(ROWS)                              # the repeated GNRL-01 on Organization is a formula: skipped
    assert by["GNRL-01"]["sheet"] == "START HERE" and by["GNRL-01"]["allowed"] is None
    assert by["PPPR-08"] == {**by["PPPR-08"], "sheet": "Organization", "answer_cell": "C13", "detail_cell": "D13",
                             "allowed": ["Yes", "No", "N/A"], "question": "Written security policy?", "compliant": "Yes"}
    # importing again over it needs --force, and keeps the answers
    with pytest.raises(SystemExit):
        Q.import_workbook(root, tmp_path / "received.xlsx", "hecvat-fsu", today=TODAY)
    _draft(root)
    _set(root, "COMP-03", answer="Yes", source="person")
    Q.import_workbook(root, tmp_path / "received.xlsx", "hecvat-fsu", today=TODAY, force=True)
    assert _q(root).aindex["COMP-03"]["answer"] == "Yes" and _q(root).meta["due"] == "2026-11-30"


# ------------------------------------------------------------------ draft
def test_draft_proposes_from_controls_profile_and_gates_and_never_approves(tmp_path):
    root = setup_repo(tmp_path)
    (root / "questionnaires" / "profile.yaml").write_text("provider_name: Larch & Finch (fictional)\n")
    a = _draft(root)
    assert not [x for x in a.values() if x["status"] == "approved"]
    # PPPR-08 maps to A.5.1: CTL-POL has current evidence -> the compliant answer, with the control's words
    assert a["PPPR-08"]["status"] == "proposed" and a["PPPR-08"]["answer"] == "Yes" and a["PPPR-08"]["support"] == "supported"
    assert a["PPPR-08"]["detail"] == "Policies are approved by leadership and reviewed every year." and a["PPPR-08"]["owner"] == "CISO"
    assert any(b.startswith("program:CTL-POL") for b in a["PPPR-08"]["basis"])
    # DATA-01 maps to A.8.22: the control has no evidence -> partial, nothing proposed
    assert a["DATA-01"]["status"] == "needs_answer" and a["DATA-01"]["support"] == "partial"
    assert a["DATA-01"]["owner"] == "Head of Platform"
    assert a["GNRL-01"]["answer"] == "Larch & Finch (fictional)" and a["GNRL-01"]["source"] == "profile:provider_name"
    assert a["GNRL-02"]["status"] == "needs_answer"
    assert a["PCID-01"]["status"] == "needs_answer"
    # a person answers the card-data gate No: the PCI section is switched off
    _set(root, "REQU-06", answer="No", source="person")
    a = _draft(root)
    assert a["PCID-01"]["status"] == "not_applicable" and a["PCID-01"]["source"] == "gate:REQU-06"
    assert a["REQU-06"]["answer"] == "No"                    # a person's answer is kept by draft


def test_draft_marks_open_gaps_and_validation_warns_on_unsupported_claims(tmp_path):
    root = setup_repo(tmp_path)
    (root / "engagement" / "gaps.yaml").write_text(yaml.safe_dump({"gaps": [
        {"id": "GAP-001", "area": "Policy", "finding": "Policy set not approved.", "requirements": ["A.5.1"],
         "owner": "CISO", "due": "2027-01-15", "severity": "high", "status": "open"}]}))
    a = _draft(root)
    assert a["PPPR-08"]["support"] == "partial" and "open gap iso27001:GAP-001" in a["PPPR-08"]["basis"]
    assert a["PPPR-08"]["status"] == "needs_answer"
    # nothing at all behind it (no evidence, gap open): a "Yes" approved anyway is flagged
    (root / "program" / "controls.yaml").write_text(yaml.safe_dump({"controls": [
        {"id": "CTL-NET", "title": "Network segmentation", "owner": "Head of Platform", "maps": {"iso27001": ["A.8.22"]}}]}))
    _draft(root)
    _set(root, "PPPR-08", answer="Yes", status="approved", approved_by="CISO", approved_on="2026-11-06", support="gap")
    assert "Q104" in _codes(root)


# ------------------------------------------------------------------ validation
def test_validation_rules(tmp_path):
    root = setup_repo(tmp_path)
    _draft(root)
    assert _codes(root) == []
    _set(root, "COMP-03", answer="Maybe")
    assert "Q102" in _codes(root)
    _set(root, "COMP-03", answer=True, status="approved")             # unquoted Yes in YAML is read as true
    codes = _codes(root)
    assert "Q102" not in codes and codes.count("Q103") == 1           # Yes is fine; no approver is not
    _set(root, "COMP-03", approved_by="CISO", approved_on="2026-11-06")
    assert "Q103" not in _codes(root)
    p = root / "questionnaires" / "hecvat-fsu" / "answers.yaml"
    d = yaml.safe_load(p.read_text())
    d["answers"].append({"id": "ZZZZ-99", "status": "needs_answer"})
    d["answers"].append({"id": "COMP-03", "status": "needs_answer"})
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert _codes(root).count("Q108") == 2
    d["answers"] = d["answers"][:-2]
    d["answers"][0]["status"] = "done"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert "Q101" in _codes(root)
    d["answers"][0]["status"] = "needs_answer"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert "Q107" in _codes(root, today=dt.date(2026, 11, 27))     # due in 3 days, answers still open
    assert "Q107" in _codes(root, today=dt.date(2026, 12, 2))      # overdue
    # an approved answer in a section the gate switched off
    _set(root, "REQU-06", answer="No", source="person", status="approved", approved_by="CISO", approved_on="2026-11-06")
    _set(root, "PCID-01", answer="Yes", source="person", status="approved", approved_by="CISO", approved_on="2026-11-06")
    assert "Q109" in _codes(root)


# ------------------------------------------------------------------ fill
def test_fill_writes_only_approved_answers_and_keeps_the_workbook_intact(tmp_path):
    root = setup_repo(tmp_path)
    (root / "questionnaires" / "profile.yaml").write_text("provider_name: Larch & Finch <fictional>\n")
    _draft(root)
    _set(root, "GNRL-01", status="approved", approved_by="CISO", approved_on="2026-11-06")
    _set(root, "PPPR-08", status="approved", approved_by="CISO", approved_on="2026-11-06")
    out = tmp_path / "filled.xlsx"
    assert main(["--today", TODAY.isoformat(), "questionnaire", "fill", "--root", str(root), "--out", str(out)]) == 0
    src = root / "questionnaires" / "hecvat-fsu" / "received.xlsx"
    a, b = zipfile.ZipFile(src), zipfile.ZipFile(out)
    assert a.namelist() == b.namelist()
    changed = {n for n in a.namelist() if a.read(n) != b.read(n)}
    assert changed <= {"xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"}
    for n in changed - {"xl/workbook.xml"}:                           # dropdowns survive
        assert a.read(n).count(b"<dataValidation ") == b.read(n).count(b"<dataValidation ") > 0
    assert b'fullCalcOnLoad="1"' in b.read("xl/workbook.xml")
    wb = openpyxl.load_workbook(out)
    assert wb["START HERE"]["C13"].value == "Larch & Finch <fictional>"     # escaped in XML, read back intact
    assert wb["START HERE"]["C3"].value == "2026-11-06"
    assert wb["Organization"]["C13"].value == "Yes"
    assert wb["Organization"]["D13"].value == "Policies are approved by leadership and reviewed every year."
    assert wb["Organization"]["C40"].value.startswith("=VLOOKUP")       # formulas untouched
    assert wb["Product"]["C13"].value is None                             # not approved: left blank
    assert len(wb["Organization"].data_validations.dataValidation) == 1
    # a draft for internal review marks what isn't approved
    _set(root, "COMP-03", answer="Yes", source="person", status="proposed")
    draft = tmp_path / "draft.xlsx"
    assert main(["--today", TODAY.isoformat(), "questionnaire", "fill", "--root", str(root), "--draft", "--out", str(draft)]) == 0
    wb = openpyxl.load_workbook(draft)
    assert wb["START HERE"]["C17"].value == "Yes" and wb["START HERE"]["D17"].value.startswith("[DRAFT - not approved]")


def test_set_cell_handles_existing_missing_and_empty_rows():
    xml = ('<sheetData><row r="5"><c r="A5" t="s"><v>1</v></c><c r="C5" s="21"/><c r="F5"><v>2</v></c></row>'
           '<row r="6" spans="1:3"/><row r="7"><c r="A7"><v>3</v></c></row></sheetData>')
    x = Q._set_cell(xml, "C5", "Yes & no")
    assert '<c r="C5" s="21" t="inlineStr"><is><t xml:space="preserve">Yes &amp; no</t></is></c><c r="F5">' in x
    x = Q._set_cell(x, "D5", "x")
    assert x.index('r="D5"') < x.index('r="F5"')
    x = Q._set_cell(x, "C6", "y")
    assert '<row r="6" spans="1:3"><c r="C6" t="inlineStr">' in x
    x = Q._set_cell(x, "D7", "z")
    assert x.index('r="A7"') < x.index('r="D7"')
    x = Q._set_cell(x, "C9", "new")
    assert x.endswith('<row r="9"><c r="C9" t="inlineStr"><is><t xml:space="preserve">new</t></is></c></row></sheetData>')
    x = Q._set_cell(x, "B2", "first")
    assert x.startswith('<sheetData><row r="2"><c r="B2"')


# ------------------------------------------------------------------ the library
def test_learn_builds_a_library_the_next_questionnaire_reuses(tmp_path):
    root = setup_repo(tmp_path)
    _draft(root)
    _set(root, "COMP-03", answer="Yes", detail="No unplanned outages in the last 12 months.", source="person",
         status="approved", approved_by="CISO", approved_on="2026-11-06")
    assert main(["questionnaire", "learn", "--root", str(root), "--name", "hecvat-fsu"]) == 0
    lib = yaml.safe_load((root / "questionnaires" / "library.yaml").read_text())["answers"]
    assert lib == [{"id": "ANS-COMP-03", "questions": ["hecvat-4:COMP-03"], "topic": "Recent unplanned service outages",
                    "answer": "Yes", "detail": "No unplanned outages in the last 12 months.", "owner": None,
                    "approved_by": "CISO", "approved_on": "2026-11-06", "review_every_days": 365}]
    assert _codes(root) == []
    # the next questionnaire starts from it
    assert main(["--today", TODAY.isoformat(), "questionnaire", "import", "--root", str(root), "--workbook",
                 str(tmp_path / "received.xlsx"), "--name", "hecvat-next"]) == 0
    assert main(["--today", TODAY.isoformat(), "questionnaire", "draft", "--root", str(root), "--name", "hecvat-next"]) == 0
    nxt = Q.load_questionnaire(root, "hecvat-next").aindex["COMP-03"]
    assert nxt["status"] == "proposed" and nxt["source"] == "library:ANS-COMP-03" and nxt["answer"] == "Yes"
    # a year later the library answer is stale: not proposed, and flagged for review
    later = dt.date(2027, 11, 7)
    assert "Q106" in _codes(root, today=later)
    assert main(["--today", later.isoformat(), "questionnaire", "draft", "--root", str(root), "--name", "hecvat-next"]) == 0
    assert Q.load_questionnaire(root, "hecvat-next").aindex["COMP-03"]["status"] == "needs_answer"
    # a library entry naming a question that doesn't exist
    lib.append({"id": "ANS-X", "questions": ["hecvat-4:NOPE-01"], "answer": "Yes", "approved_by": "CISO",
                "approved_on": "2026-11-06"})
    (root / "questionnaires" / "library.yaml").write_text(yaml.safe_dump({"answers": lib}))
    assert "Q105" in _codes(root)


def test_report_lists_open_questions_by_owner(tmp_path):
    root = setup_repo(tmp_path)
    _draft(root)
    text = Q.report_md(_q(root))
    assert text.startswith("# HECVAT 4 for Fictional State University")
    assert "| Proposed, waiting for approval | 1 |" in text
    assert "| DATA-01 | Data hosts on public IP space | needs_answer |  | Head of Platform | partial |" in text
