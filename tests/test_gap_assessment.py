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
    assert register.ids_in("164.308 (a)(1)(ii)(A) and §164.312(e)", "hipaa", {"164.308(a)(1)(ii)(A)", "164.312(e)(1)"})[0] == ["164.308(a)(1)(ii)(A)"]
    assert register.ids_in("Article 28(3)(a); Art 30", "gdpr", {"Art28(3)(a)", "Art30(1)"})[0] == ["Art28(3)(a)"]
    assert register.ids_in("AC-2 (3), AC-02, SI-4(99)", "txramp", {"AC-2(3)", "AC-2", "SI-4"}) == (["AC-2(3)", "AC-2", "SI-4"], [])
    assert register.ids_in("KSI-IAM-ELP", "fedramp20x", {"KSI-IAM-ELP"})[0] == ["KSI-IAM-ELP"]
    assert register.ids_in("PR 44, PRP7", "cbpr", {"PR44", "PRP7"})[0] == ["PR44", "PRP7"]
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
