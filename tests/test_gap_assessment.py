"""Gap analysis of a client's existing setup: control register import (GRC tool exports, own sheets), prior audit
reports in AI ingest, and the client-facing gap assessment."""
import csv
import datetime as dt

import yaml

from grc import gap_assessment, ingest
from grc.cli import main
from grc.ingest import ai, register
from grc.model import load
from grc.rules import validate

TODAY = dt.date(2026, 11, 20)


def _new(tmp_path, fw="soc2", categories=None, name="engagement"):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / name), "new-engagement", "--client", "Larch & Finch", "--start", "2026-11-09",
            "--stage1", "2027-02-01", "--stage2", "2027-06-01", "--framework", fw,
            "--intake", str(root / ("intake" + name[len("engagement"):])), "--confirm-reset"]
    if categories:
        args[-1:-1] = ["--categories", categories]
    assert main(args) == 0
    return root / name, root / ("intake" + name[len("engagement"):])


# a fictional export in the shape GRC tools use: a title line, then the header; mappings in one column
TOOL_EXPORT = [
    ["Larch & Finch controls export", "", "", "", "", ""],
    [],
    ["Control ID", "Control Name", "Description", "Owner", "Status", "Framework Mappings"],
    ["LF-01", "Quarterly access reviews", "Managers review user access each quarter", "Ana Ortiz", "Implemented",
     "SOC 2: CC6.2, CC6.3; ISO 27001:2022: A.5.18"],
    ["LF-02", "Annual penetration test", "External test of the platform", "Bo Lind", "Not implemented",
     "SOC 2: CC4.1 | ISO 27001: Annex A 8.8"],
    ["LF-03", "Information security policy", "Approved policy set", "Cy Park", "In progress", "ISO 27001: 5.2, A.5.1"],
    ["LF-04", "Badge access to the office", "", "Di Wu", "", "GDPR Art. 32(1)(b)"],
    ["LF-05", "Change approvals", "Pull requests need an approval", "", "Passing", "SOC2 CC8.1"],
]


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)


def test_register_is_recognised_and_ids_read_as_tools_write_them():
    assert register.detect(TOOL_EXPORT) and register.find_header(TOOL_EXPORT) == 2
    assert not register.detect([["area", "finding", "requirements"]])        # an intake template, not a register
    soc = {"CC6.2", "CC6.3", "CC4.1", "CC8.1"}
    d, rows, notes = register.to_draft(TOOL_EXPORT, "export.csv", "soc2", soc)
    assert [r["maps"] for r in rows] == [["CC6.2", "CC6.3"], ["CC4.1"], [], [], ["CC8.1"]]
    assert [r["state"] for r in rows] == ["in_place", "not_in_place", "partial", "unknown", "in_place"]
    assert {(c["requirement"], c["leg"]) for c in d["claims"]} == {
        ("CC6.2", "documented"), ("CC6.2", "implemented"), ("CC6.3", "documented"), ("CC6.3", "implemented"),
        ("CC8.1", "documented"), ("CC8.1", "implemented")}
    assert [(g["requirements"], g["severity"]) for g in d["gaps"]] == [(["CC4.1"], "high")]
    assert "2 of 5 control(s) map to no soc2 requirement" in notes[0]   # no label given: the id
    # the same register, read for ISO 27001: other frameworks' pieces are skipped, clauses and Annex A both found
    iso = {"A.5.18", "A.8.8", "5.2", "A.5.1"}
    _, rows, _ = register.to_draft(TOOL_EXPORT, "export.csv", "iso27001", iso)
    assert [r["maps"] for r in rows] == [["A.5.18"], ["A.8.8"], ["A.5.1", "5.2"], [], []]


def test_ids_in_each_framework():
    assert register.ids_in("164.308 (a)(1)(ii)(A) and §164.312(e)", "hipaa", {"164.308(a)(1)(ii)(A)", "164.312(e)(1)"})[0] == [
        "164.308(a)(1)(ii)(A)", "164.312(e)(1)"]                         # a parent citation means its parts
    assert register.ids_in("Article 28(3)(a); Art 30", "gdpr", {"Art28(3)(a)", "Art30(1)"})[0] == ["Art28(3)(a)", "Art30(1)"]
    assert register.ids_in("AC-2 (3), AC-02, SI-4(99)", "txramp", {"AC-2(3)", "AC-2", "SI-4"}) == (["AC-2(3)", "AC-2", "SI-4"], [])
    assert register.ids_in("KSI-IAM-ELP", "fedramp20x", {"KSI-IAM-ELP"})[0] == ["KSI-IAM-ELP"]
    assert register.ids_in("PR 44, PRP7", "cbpr", {"PR44", "PRP7"}, hinted=True)[0] == ["PR44", "PRP7"]
    # a reference written for this framework that the catalog doesn't have is reported, not mapped
    assert register.ids_in("ISO 27001: A.9.2.1", "iso27001", {"A.5.18"}) == ([], ["A.9.2.1"])
    assert register.state_of("Needs remediation") == "not_in_place" and register.state_of("Draft") == "partial"


def test_ingest_imports_a_register_and_the_assessment_reports_on_it(tmp_path):
    edir, intake = _new(tmp_path)
    _write_csv(intake / "vanta-export.csv", TOOL_EXPORT)
    report = ingest.run(edir, intake, mode="templates")
    assert "imported as a **control register** (5 controls, 3 mapped to SOC 2)" in report
    m = load(edir, today=TODAY)
    assert len(m.existing_controls) == 5 and m.existing_controls[0]["source"] == "vanta-export.csv row 4"
    assert m.controls["CC6.2"]["test"]["implemented"]["status"] == "claimed"
    assert m.controls["CC6.2"]["test"]["tested"]["status"] == "not_started"          # never further than claimed
    assert any(g["requirements"] == ["CC4.1"] and g["severity"] == "high" for g in m.gaps)
    assert [f for f in validate(m) if f.severity == "error"] == []
    cov = gap_assessment.coverage(m)
    assert cov["CC6.2"] == "Reported in place" and cov["CC4.1"] == "Gap" and cov["CC1.1"] == "No existing control"
    md = gap_assessment.markdown(m)
    assert "| LF-03 Information security policy | In progress |  |" in md            # mapped to nothing in SOC 2
    assert "`vanta-export.csv` (control register" in md
    # re-importing a changed register replaces its rows instead of adding to them
    rows = TOOL_EXPORT[:4]
    _write_csv(intake / "vanta-export.csv", rows)
    ingest.run(edir, intake, mode="templates")
    assert len(load(edir, today=TODAY).existing_controls) == 1


def test_bad_mapping_in_existing_controls_is_a_warning(tmp_path):
    edir, intake = _new(tmp_path)
    _write_csv(intake / "export.csv", TOOL_EXPORT)
    ingest.run(edir, intake, mode="templates")
    p = edir / "existing-controls.yaml"
    data = yaml.safe_load(p.read_text())
    data["controls"][2]["maps"] = ["CC99.9"]
    p.write_text(yaml.safe_dump(data))
    w = [f for f in validate(load(edir, today=TODAY)) if f.code == "W116"]
    assert len(w) == 1 and "CC99.9" in w[0].message


def test_build_writes_the_gap_assessment(tmp_path):
    edir, _ = _new(tmp_path, fw="cbpr", categories="cbpr")
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    md = (out / "gap-assessment.md").read_text()
    assert md.startswith("# Larch & Finch — Global CBPR gap assessment")
    assert "**57** requirements of Global CBPR apply" in md and "| No existing control | 57 | 100% |" in md
    assert (out / "gap-assessment.docx").exists()
    assert "[Gap assessment](gap-assessment.md)" in (out / "README.md").read_text()
    for word in ("hours", "budget", "Working rule"):
        assert word not in md


def test_ai_prompt_treats_prior_reports_as_statements():
    rule = ai.SYSTEM.split("10.")[1]
    assert "prior audit" in rule and "exception" in rule and "`tested` leg only when the report" in rule


# ------------------------------------------------------------------ review cases
def test_every_row_not_in_place_gets_its_own_gap(tmp_path):
    edir, intake = _new(tmp_path)
    rows = [["Control ID", "Control Name", "Status", "SOC 2"]] + [
        [f"LF-{i}", f"Control {i}", s, rid] for i, (s, rid) in enumerate(
            [("Not implemented", "CC7.1"), ("Not implemented", "CC6.2"), ("Failing", "CC6.6"),
             ("In progress", "CC8.1"), ("Draft", "CC2.1"), ("Implemented", "CC6.1")])]
    _write_csv(intake / "reg.csv", rows)
    ingest.run(edir, intake, mode="templates")
    m = load(edir, today=TODAY)
    assert sorted((g["requirements"][0], g["severity"]) for g in m.gaps if g.get("register")) == [
        ("CC2.1", "medium"), ("CC6.2", "high"), ("CC6.6", "high"), ("CC7.1", "high"), ("CC8.1", "medium")]
    assert {gap_assessment.coverage(m)[r] for r in ("CC7.1", "CC6.2", "CC6.6")} == {"Gap"}


def test_reimport_finds_its_gaps_lists_stale_ones_and_survives_a_new_file_name(tmp_path):
    edir, intake = _new(tmp_path)
    head = ["Control ID", "Control Name", "Status", "SOC 2"]
    _write_csv(intake / "reg-2026-11-01.csv", [head, ["LF-1", "Pen test", "Not implemented", "CC4.1"],
                                               ["LF-6", "MFA", "Implemented", "CC6.1"]])
    ingest.run(edir, intake, mode="templates")
    (intake / "reg-2026-11-01.csv").unlink()
    _write_csv(intake / "reg-2026-11-20.csv", [head, ["LF-1", "Pen test", "Implemented", "CC4.1"],
                                               ["LF-6", "MFA", "Failing", "CC6.1"]])
    report = ingest.run(edir, intake, mode="templates")
    m = load(edir, today=TODAY)
    assert len(m.existing_controls) == 2 and {r["register"] for r in m.existing_controls} == {"reg"}
    assert "no longer supports" in report and "reg/LF-1" in report             # listed, not closed
    assert [g["status"] for g in m.gaps if g.get("register") == "reg/LF-1"] == ["open"]
    assert [g["severity"] for g in m.gaps if g.get("register") == "reg/LF-6"] == ["high"]
    assert gap_assessment.coverage(m)["CC6.1"] == "Gap"
    # the same file again: nothing new
    before = len(load(edir).gaps)
    ingest.run(edir, intake, mode="templates", force=True)
    assert len(load(edir).gaps) == before


def test_status_words():
    s = register.state_of
    assert [s(x) for x in ("Configured", "Deferred", "Retired", "Not Applicable", "N/A", "Exception", "Accepted risk",
                           "Planned", "Credit card controls", "Out of scope", "Needs remediation", "")] == [
        "in_place", "planned", "not_applicable", "not_applicable", "not_applicable", "partial", "not_in_place",
        "planned", "unknown", "not_applicable", "not_in_place", "unknown"]
    assert s("Yes", applicable="No") == "not_applicable"
    d, rows, _ = register.to_draft([["Control", "Status", "SOC 2"], ["Risk accepted for legacy VPN", "Accepted risk", "CC6.6"],
                                    ["Fax policy", "N/A", "CC6.7"]], "r.csv", "soc2", {"CC6.6", "CC6.7"})
    assert [(g["severity"], g["requirements"]) for g in d["gaps"]] == [("medium", ["CC6.6"])] and not d["claims"]


def test_iso_annex_numbers_and_prose():
    k = {"A.5.1", "A.8.1", "A.7.4", "A.5.15", "A.8.10", "5.2", "8.1", "9.2", "7.5.1"}
    assert register.mapped_ids([("ISO 27001 Annex A", "5.1, 8.1, 7.4, 5.15, 8.10")], "iso27001", k)[0] == [
        "A.5.1", "A.8.1", "A.7.4", "A.5.15", "A.8.10"]
    assert register.mapped_ids([("ISO 27001 clauses", "5.2, 8.1")], "iso27001", k)[0] == ["5.2", "8.1"]
    assert register.mapped_ids([("References", "Review takes 7.5 hours; version 6.2, section 8.1")], "iso27001", k)[0] == []
    assert register.mapped_ids([("Frameworks", "ISO 42001 9.2, ISO 27001 A.5.1")], "iso27001", k)[0] == ["A.5.1"]
    assert register.mapped_ids([("Frameworks", "ISO 42001 9.2, ISO 27001 A.5.1")], "iso42001", {"9.2", "A.5.1"})[0] == ["9.2"]
    assert register.ids_in("PR 12 merged", "cbpr", {"PR12"})[0] == [] and register.ids_in("PR 12", "cbpr", {"PR12"}, hinted=True)[0] == ["PR12"]
    # a parent reference means all of it
    assert register.ids_in("Article 32", "gdpr", {"Art32(1)(a)", "Art32(2)", "Art33"})[0] == ["Art32(1)(a)", "Art32(2)"]


def test_headers_and_sheets(tmp_path):
    t = [["CONTROL #", "control title", "Status", "SOC 2"], ["C-1", "Access reviews", "Implemented", "CC6.2"],
         ["C-2", "", "Not implemented", "CC6.3"]]
    _, rows, notes = register.to_draft(t, "r.csv", "soc2", {"CC6.2", "CC6.3"})
    assert [(r["ref"], r["name"]) for r in rows] == [("C-1", "Access reviews"), ("C-2", "C-2")]
    assert not register.detect([["Title", "Version", "Owner", "Reference", "Approved"]])     # a policy index
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.title = "Cover"
    wb.active.append(["Larch & Finch control register"])
    ws = wb.create_sheet("Controls")
    ws.append(["Control ID", "Control Name", "Status", "ISO 27001 Annex A"])
    ws.append([])
    ws.append(["LF-1", "Clock sync", "Implemented", 8.17])
    ws.append(["LF-2", "Deletion", "Implemented", 8.1])
    ws["D4"].number_format = "0.00"
    ws["D4"] = 8.1
    edir, intake = _new(tmp_path, fw="iso27001")
    wb.save(intake / "register.xlsx")
    ingest.run(edir, intake, mode="templates")
    m = load(edir, today=TODAY)
    assert [(r["source"], r["maps"]) for r in m.existing_controls] == [
        ("register.xlsx sheet Controls row 3", ["A.8.17"]), ("register.xlsx sheet Controls row 4", ["A.8.10"])]


def test_pipes_and_malformed_files_do_not_break_reports(tmp_path):
    edir, intake = _new(tmp_path)
    _write_csv(intake / "reg.csv", [["Control", "Status", "SOC 2"], ["Vendor risk | review", "Not implemented", "CC9.2"]])
    ingest.run(edir, intake, mode="templates")
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    import docx
    tables = docx.Document(str(out / "gap-assessment.docx")).tables
    assert any(c.text == "Vendor risk / review" for t in tables for r in t.rows for c in r.cells)
    (edir / "existing-controls.yaml").write_text("- name: x\n  maps: CC6.1\n")
    m = load(edir, today=TODAY)
    assert any(f.code == "E001" and "existing-controls" in str(f.file) for f in validate(m))
    assert gap_assessment.markdown(m)
