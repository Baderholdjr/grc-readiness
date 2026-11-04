"""Program layer: common control catalog, governance calendar, owner certification, scorecard."""
import datetime as dt
import json

import yaml

from grc import program as P
from grc import program_report
from grc.cli import main

TODAY = dt.date(2026, 11, 4)


def _repo(tmp_path):
    root = tmp_path / "repo"
    for fw, name, extra in (("iso27001", "engagement", []), ("soc2", "engagement-soc2", ["--categories", "privacy"])):
        intake = root / ("intake" + name[len("engagement"):])
        assert main(["--engagement", str(root / name), "new-engagement", "--client", "Acme", "--start", "2026-01-05",
                     "--stage1", "2027-03-15", "--stage2", "2027-05-15", "--framework", fw, "--intake", str(intake),
                     *extra, "--confirm-reset"]) == 0
    ev = {"evidence": [{"id": "EV-001", "title": "Access review Q3", "type": "record", "location": "drive://x",
                        "owner": "CISO", "collected": "2026-10-02", "valid_for_days": 120}]}
    (root / "engagement" / "evidence" / "index.yaml").write_text(yaml.safe_dump(ev))
    (root / "program").mkdir()
    (root / "program" / "owners.yaml").write_text(yaml.safe_dump({"owners": [
        {"role": "CISO", "github": ["alice"]}, {"role": "IT Manager", "github": ["bob"]}]}))
    _controls(root, [
        {"id": "CTL-ACC-01", "title": "Access review", "owner": "CISO", "frequency": "quarterly", "type": "manual",
         "evidence": ["iso27001:EV-001"], "maps": {"iso27001": ["A.5.18", "A.8.2"], "soc2": ["CC6.2"], "nist80053": ["AC-2"]}},
        {"id": "CTL-CHG-01", "title": "Change approval", "owner": "IT Manager", "type": "automated",
         "maps": {"iso27001": ["A.8.32"], "soc2": ["CC8.1"]}},
    ])
    return root


def _controls(root, ctls):
    (root / "program" / "controls.yaml").write_text(yaml.safe_dump({"controls": ctls}, sort_keys=False))


def _calendar(root, obs):
    (root / "program" / "calendar.yaml").write_text(yaml.safe_dump({"obligations": obs}, sort_keys=False))


def codes(root, today=TODAY):
    return [f.code for f in P.validate(P.load_program(root, today=today))]


# ------------------------------------------------------------------ catalog
def test_reference_catalog_has_nist_baselines():
    prog = P.Program(root=P.Path("."), today=TODAY)
    idx = prog.requirement_index("nist80053")
    assert len(idx) > 1000 and idx["AC-2"]["title"] == "Account Management"
    assert sum("M" in r.get("baselines", []) for r in idx.values()) == 287       # SP 800-53B moderate
    assert idx["AC-2(3)"]["enhances"] == "AC-2"


def test_clean_catalog_and_coverage(tmp_path):
    root = _repo(tmp_path)
    c = codes(root)
    assert not [x for x in c if x.startswith("P10") and x not in ("P107", "P109")], c
    prog = P.load_program(root, today=TODAY)
    cov = {x["framework"]: x for x in P.coverage(prog)}
    assert cov["iso27001"]["covered"] == 3 and cov["soc2"]["covered"] == 2
    assert cov["nist80053"]["record"] is None
    assert "P107" in c                      # most requirements still have no common control


def test_bad_mappings_are_errors(tmp_path):
    root = _repo(tmp_path)
    _controls(root, [
        {"id": "C1", "title": "x", "owner": "CISO", "maps": {"iso27001": ["A.9.9"]}},
        {"id": "C1", "title": "y", "owner": "Nobody", "maps": {"nofw": ["1"]}, "evidence": ["iso27001:EV-404"]},
        {"id": "C2", "title": "z", "owner": "CISO", "maps": {"soc2": ["A1.1"]}, "evidence": ["iso42001:EV-001"]},
    ])
    c = codes(root)
    assert {"P104", "P102", "P106", "P103", "P105", "P108"} <= set(c), c


def test_schema_error(tmp_path):
    root = _repo(tmp_path)
    _controls(root, [{"id": "C1", "title": "x", "owner": "CISO"}])     # no maps
    assert "P101" in codes(root)


def test_expired_evidence_warns(tmp_path):
    root = _repo(tmp_path)
    assert "P110" in codes(root, today=dt.date(2027, 3, 1))           # 2026-10-02 + 120 days


def test_suggestions_from_crosswalks(tmp_path):
    root = _repo(tmp_path)
    _controls(root, [{"id": "C1", "title": "x", "owner": "CISO", "maps": {"iso27001": ["A.8.32"]}}])
    sug = P.suggestions(P.load_program(root, today=TODAY))
    assert any(s["to_fw"] == "soc2" and s["to"] == "CC8.1" and not s["reviewed"] for s in sug)


# ------------------------------------------------------------------ calendar
def test_calendar_occurrences_and_rules(tmp_path):
    root = _repo(tmp_path)
    _calendar(root, [
        {"id": "OBL-1", "title": "Access review", "owner": "CISO", "every": "quarterly", "first_due": "2026-01-15",
         "controls": ["CTL-ACC-01"],
         "done": [{"period": "2026-01-15", "completed": "2026-01-10", "evidence": ["iso27001:EV-001"]},
                  {"period": "2026-04-15", "completed": "2026-04-20", "evidence": ["iso27001:EV-001"]},
                  {"period": "2026-10-15", "completed": "2026-10-02"}]},          # no evidence: P204
        {"id": "OBL-2", "title": "Bad", "owner": "Ghost", "every": "annual", "first_due": "2026-03-31",
         "controls": ["CTL-NOPE"],
         "done": [{"period": "2026-03-30", "completed": "2027-01-01", "evidence": ["soc2:EV-999"]}]},
    ])
    prog = P.load_program(root, today=TODAY)
    st = {o["due"].isoformat(): o["status"] for o in P.occurrences(prog, prog.obligations[0])}
    assert st == {"2026-01-15": "done_on_time", "2026-04-15": "done_late", "2026-07-15": "overdue",
                  "2026-10-15": "done_on_time"}
    c = codes(root)
    assert {"P204", "P206", "P207", "P208", "P203", "P209", "P205"} <= set(c), c


def test_month_end_due_dates_clamp():
    ob = {"every": "monthly", "first_due": "2026-01-31"}
    assert [d.isoformat() for d in P.due_dates(ob, dt.date(2026, 4, 30))] == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_obligation_issue_items(tmp_path):
    root = _repo(tmp_path)
    _calendar(root, [{"id": "OBL-1", "title": "Access review", "owner": "CISO", "every": "quarterly",
                      "first_due": "2026-08-15", "done": [{"period": "2026-08-15", "completed": "2026-08-10",
                                                           "evidence": ["iso27001:EV-001"]}]}])
    items = P.obligation_items(P.load_program(root, today=dt.date(2026, 11, 5)))
    by = {i["key"]: i for i in items}
    assert by["OBL-1@2026-11-15"]["open"] and "Due 2026-11-15" in by["OBL-1@2026-11-15"]["title"]
    assert not by["OBL-1@2026-08-15"]["open"]
    assert "<!-- grc:obligation:OBL-1@2026-11-15 -->" in by["OBL-1@2026-11-15"]["body"]
    assert P.sync_obligation_issues(P.load_program(root, today=dt.date(2026, 11, 5)), None, None)[0].startswith("[dry-run]")


# ------------------------------------------------------------------ certification
def _cert(root, owner_slug, **kw):
    p = root / "program" / "certifications" / "2026-Q3" / f"{owner_slug}.yaml"
    d = yaml.safe_load(p.read_text())
    for k, v in kw.items():
        if k == "responses":
            for c in d["controls"]:
                c.update(v.get(c["id"], {"response": "operating"}))
        else:
            d[k] = v
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_certify_open_and_sign(tmp_path):
    root = _repo(tmp_path)
    prog = P.load_program(root, today=dt.date(2026, 10, 1))
    created = P.certify_open(prog)
    assert sorted(p.name for p in created) == ["ciso.yaml", "it-manager.yaml"]
    assert not P.certify_open(P.load_program(root, today=dt.date(2026, 10, 1)))      # never overwritten
    d = yaml.safe_load(created[0].read_text())
    assert d["period"] == "2026-Q3" and d["due"] == "2026-10-30" and d["controls"][0]["response"] == "pending"
    assert "P306" in codes(root)                                                      # due 2026-10-30, unsigned
    _cert(root, "ciso", certified_by="alice", certified_on="2026-10-05")
    assert "P303" in codes(root)                                                      # signed while pending
    _cert(root, "ciso", responses={"CTL-ACC-01": {"response": "exception", "note": ""}})
    assert {"P304", "P307"} <= set(codes(root))
    _cert(root, "ciso", responses={"CTL-ACC-01": {"response": "exception", "note": "late", "follow_up": "GAP-01"}})
    c = codes(root)
    assert not {"P303", "P304", "P307", "P305"} & set(c), c
    _cert(root, "ciso", certified_by="bob")                                           # not the owner
    assert "P305" in codes(root)
    _cert(root, "ciso", certified_by="alice", certified_on="2026-09-20")             # before the quarter ended
    assert "P309" in codes(root)


def test_certification_of_someone_elses_control(tmp_path):
    root = _repo(tmp_path)
    P.certify_open(P.load_program(root, today=dt.date(2026, 10, 1)))
    p = root / "program" / "certifications" / "2026-Q3" / "ciso.yaml"
    d = yaml.safe_load(p.read_text())
    d["controls"].append({"id": "CTL-CHG-01", "response": "operating"})
    p.write_text(yaml.safe_dump(d))
    assert "P308" in codes(root)


def test_quarters():
    assert P.previous_quarter(dt.date(2026, 10, 1)) == "2026-Q3"
    assert P.previous_quarter(dt.date(2026, 1, 3)) == "2025-Q4"
    assert P.quarter_end("2026-Q1") == dt.date(2026, 3, 31) and P.quarter_end("2026-Q4") == dt.date(2026, 12, 31)


# ------------------------------------------------------------------ reports and CLI
def test_reports_and_scorecard(tmp_path):
    root = _repo(tmp_path)
    _calendar(root, [{"id": "OBL-1", "title": "Access review", "owner": "CISO", "every": "quarterly",
                      "first_due": "2026-08-15", "done": [{"period": "2026-08-15", "completed": "2026-08-10",
                                                           "evidence": ["iso27001:EV-001"]}]}])
    out = tmp_path / "out"
    assert main(["--today", "2026-11-04", "program", "report", "--root", str(root), "--out", str(out)]) == 0
    names = {p.name for p in out.iterdir()}
    assert {"program.md", "control-catalog.md", "coverage.md", "governance-calendar.md", "governance-calendar.ics",
            "certifications.md", "common-control-matrix.xlsx", "scorecard.json"} <= names
    sc = json.loads((out / "scorecard.json").read_text())
    assert sc["controls"] == 2 and sc["requirements_mapped"] == 6 and sc["multi_framework_controls"] == 2
    assert sc["obligations_on_time_pct"] == 100 and sc["automated_controls_pct"] == 50
    ics = (out / "governance-calendar.ics").read_text()
    assert "BEGIN:VEVENT" in ics and "DTSTART;VALUE=DATE:20261115" in ics
    from openpyxl import load_workbook
    wb = load_workbook(out / "common-control-matrix.xlsx")
    assert wb.sheetnames == ["Controls", "Mapping", "Coverage", "Calendar"]
    assert "Access review" in program_report.catalog_md(P.load_program(root, today=TODAY))


def test_cli_validate_exit_codes(tmp_path):
    root = _repo(tmp_path)
    assert main(["--today", "2026-11-04", "program", "validate", "--root", str(root)]) == 0
    _controls(root, [{"id": "C1", "title": "x", "owner": "CISO", "maps": {"iso27001": ["A.9.9"]}}])
    assert main(["--today", "2026-11-04", "program", "validate", "--root", str(root)]) == 1
    assert main(["program", "validate", "--root", str(tmp_path / "empty")]) == 0                 # no program/: nothing to do


def test_cli_certify(tmp_path):
    root = _repo(tmp_path)
    assert main(["--today", "2026-10-01", "program", "certify", "--root", str(root)]) == 0
    assert (root / "program" / "certifications" / "2026-Q3" / "it-manager.yaml").exists()
    assert main(["--today", "2026-10-01", "program", "certify", "--root", str(root), "--period", "2026-Q2"]) == 0
    assert (root / "program" / "certifications" / "2026-Q2" / "ciso.yaml").exists()
