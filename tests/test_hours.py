"""Hours tracking: timesheet import (Toggl, Harvest, Clockify, generic), logging, burn, forecast, rules."""
import datetime as dt
import shutil
from pathlib import Path

import yaml

from grc import hours
from grc.cli import main
from grc.model import load
from grc.render_md import render_all
from grc.rules import metrics, validate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)

TOGGL = """User,Email,Client,Project,Task,Description,Billable,Start date,Start time,End date,End time,Duration,Tags
Ana,ana@x.com,Larkspur,ISO 42001,,Kickoff workshop with CTO,Yes,2026-09-14,09:00:00,2026-09-14,11:30:00,02:30:00,kickoff
Ana,ana@x.com,Larkspur,ISO 42001,,Drafted AI policy (A.2.2 GAP-01),Yes,2026-09-15,13:00:00,2026-09-15,17:00:00,04:00:00,
Ana,ana@x.com,Other Co,Website,,unrelated,Yes,2026-09-15,09:00:00,2026-09-15,10:00:00,01:00:00,
"""
HARVEST = """Date,Client,Project,Project Code,Task,Notes,Hours,Billable?,First Name,Last Name
2026-09-21,Larkspur,ISO 42001,LK1,Interviews,Release owner walkthrough,1.5,Yes,Ben,Ortiz
2026-09-22,Larkspur,ISO 42001,LK1,Internal Audit,Sampled release approvals,3.25,Yes,Ben,Ortiz
"""
CLOCKIFY = """Project,Client,Description,Task,User,Group,Email,Tags,Billable,Start Date,Start Time,End Date,End Time,Duration (h),Duration (decimal)
ISO 42001,Larkspur,Evidence review of collectors,,Ana,,ana@x.com,,Yes,09/29/2026,10:00 AM,09/29/2026,12:00 PM,02:00:00,2.00
"""


def setup(tmp_path, budget=100):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["budget"] = {"hours_total": budget}
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    (edir / "hours.yaml").write_text("entries: []\n")
    return edir


def m(edir, today=TODAY):
    return load(edir, today=today)


def findings(edir, today=TODAY, code=None, severity=None):
    return [f for f in validate(m(edir, today)) if (code is None or f.code == code) and (severity is None or f.severity == severity)]


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_import_formats_filter_and_idempotence(tmp_path):
    edir = setup(tmp_path)
    files = [write(tmp_path, "toggl.csv", TOGGL), write(tmp_path, "harvest.csv", HARVEST), write(tmp_path, "clockify.csv", CLOCKIFY)]
    log = hours.import_files(m(edir), files, match="larkspur")
    files_log = [l for l in log if l.endswith(")") or "added so far" in l]
    assert "toggl" in files_log[0] and "1 skipped (other client/project)" in files_log[0]
    assert any("(harvest)" in l for l in log) and any("(clockify)" in l for l in log)
    assert any("client/project filter: 'larkspur'" in l for l in log)
    es = {e["note"][:12]: e for e in m(edir).hours}
    assert es["Kickoff work"]["hours"] == 2.5 and es["Kickoff work"]["activity"] == "kickoff"
    assert es["Drafted AI p"]["activity"] == "documentation" and es["Drafted AI p"]["refs"] == ["A.2.2", "GAP-01"]
    assert es["Sampled rele"]["person"] == "Ben Ortiz" and es["Sampled rele"]["activity"] == "internal_audit"
    assert es["Evidence rev"]["date"] == "2026-09-29" and es["Evidence rev"]["hours"] == 2.0
    assert hours.total(m(edir)) == 13.25
    again = hours.import_files(m(edir), files, match="larkspur")
    assert "already imported" in again[0] and hours.total(m(edir)) == 13.25
    assert not findings(edir, severity="error")


def test_log_entry_and_validation(tmp_path):
    edir = setup(tmp_path)
    hours.log_entry(m(edir), 2, "interviews", "ana", note="walkthrough", refs=["A.6.2.5"])
    hours.log_entry(m(edir), 2, "interviews", "ana", note="walkthrough", refs=["A.6.2.5"])  # same day, second entry
    assert len(m(edir).hours) == 2 and len({e["id"] for e in m(edir).hours}) == 2
    for bad in ((0, "interviews", None), (3, "golf", None), (3, "other", TODAY + dt.timedelta(days=1))):
        try:
            hours.log_entry(m(edir), bad[0], bad[1], "ana", on=bad[2])
            raise AssertionError(bad)
        except ValueError:
            pass
    d = yaml.safe_load((edir / "hours.yaml").read_text())
    d["entries"].append({**d["entries"][0], "id": "H-0000000000", "hours": 13, "refs": ["GAP-99"], "activity": "golf"})
    d["entries"].append({**d["entries"][0]})
    (edir / "hours.yaml").write_text(yaml.safe_dump(d))
    msgs = " | ".join(f.message for f in findings(edir, code="E060"))
    assert "appears more than once" in msgs and "unknown activity 'golf'" in msgs and "GAP-99" in msgs and "more than 14" in msgs


def test_burn_plan_forecast_and_warnings(tmp_path):
    edir = setup(tmp_path, budget=40)
    model = m(edir)
    phases = [p["id"] for p in hours.phases(model)]
    first = hours.phases(model)[0]
    start = dt.date.fromisoformat(str(first["start"]))
    # 4 weeks of 6 hours each, ending before TODAY's week
    wk = hours.week_of(TODAY)
    for i in range(1, 5):
        hours.log_entry(m(edir), 6, "documentation", "ana", on=wk - dt.timedelta(weeks=i))
    model = m(edir)
    f = hours.forecast(model)
    assert f["rate_per_week"] == 6 and f["used"] == 24 and f["projected_total"] > 40
    assert findings(edir, code="W161") and not findings(edir, code="W106")   # 24 of 40 = 60%
    plan = hours.planned(model)
    assert set(plan) <= set(phases) and abs(sum(plan.values()) - 40) < 1
    by_phase = hours.by(model, lambda e: hours.phase_for(model, e))
    over = [ph for ph, h in by_phase.items() if ph in plan and h > plan[ph]]
    assert bool(over) == bool(findings(edir, code="W160"))
    assert metrics(model)["hours_used"] == 24
    hours.log_entry(m(edir), 9, "documentation", "ben", on=wk)
    assert findings(edir, code="W106")   # 33 of 40 = 82%


def test_manual_hours_used_conflict_and_untracked(tmp_path):
    edir = setup(tmp_path)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["budget"]["hours_used"] = 50
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    assert findings(edir, code="W163")
    (edir / "hours.yaml").unlink()
    assert hours.hours_used(m(edir)) == 50 and not findings(edir, code="W163")


def test_report_and_cli(tmp_path):
    edir = setup(tmp_path)
    csvf = write(tmp_path, "h.csv", "date,person,hours,activity,note\n2026-09-30,Ana,3,interviews,Walkthrough GAP-01\n")
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "hours", "import", str(csvf)]) == 0
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "hours", "log", "--hours", "1.5",
                 "--activity", "project_management", "--person", "ben", "--refs", "GAP-01"]) == 0
    assert main(["--engagement", str(edir), "hours", "log", "--hours", "1"]) == 2
    out = tmp_path / "out"
    model = m(edir)
    render_all(model, validate(model), out)
    text = (out / "hours.md").read_text()
    assert "By phase" in text and "Interviews and walkthroughs" in text and "GAP-01" in text and "4.5" in text
    assert (out / "hours.csv").read_text().count("\n") == 3
    assert "Hours and budget" in (out / "README.md").read_text()


def test_timesheets_are_not_ingested(tmp_path):
    from grc.ingest import pending
    intake = tmp_path / "intake"
    (intake / "timesheets").mkdir(parents=True)
    (intake / "timesheets" / "t.csv").write_text(TOGGL)
    (intake / "policy.md").write_text("x")
    assert [p.name for p in pending(intake)] == ["policy.md"]


# ---------------------------------------------------------------- review regressions
def test_date_order_detected_per_file_and_flagged_when_ambiguous(tmp_path):
    edir = setup(tmp_path)
    eu = write(tmp_path, "eu.csv", "date,person,hours\n13/09/2026,ana,1\n05/09/2026,ana,1\n")
    us = write(tmp_path, "amb.csv", "date,person,hours\n05/09/2026 09:00,ben,1\n")
    log = hours.import_files(m(edir), [eu, us])
    dates = sorted(e["date"] for e in m(edir).hours)
    assert dates == ["2026-05-09", "2026-09-05", "2026-09-13"]
    assert any("could be day/month" in l and "amb.csv" in l for l in log) and not any("eu.csv" in l and "could be" in l for l in log)
    edir2 = setup(tmp_path / "b")
    hours.import_files(m(edir2), [us], order="DMY")
    assert m(edir2).hours[0]["date"] == "2026-09-05"


def test_identical_rows_kept_and_renamed_exports_not_duplicated(tmp_path):
    edir = setup(tmp_path)
    text = HARVEST + "2026-09-21,Larkspur,ISO 42001,LK1,Interviews,Release owner walkthrough,1.5,Yes,Ben,Ortiz\n"
    hours.import_files(m(edir), [write(tmp_path, "sept.csv", text)])
    assert hours.total(m(edir)) == 6.25            # 1.5 + 3.25 + 1.5: the repeated row is real work
    hours.import_files(m(edir), [write(tmp_path, "q3-cumulative.csv", text + "2026-09-30,Larkspur,ISO 42001,LK1,Interviews,x,2,Yes,Ben,Ortiz\n")])
    assert hours.total(m(edir)) == 8.25            # only the new row added


def test_early_burn_rate_uses_weeks_since_start(tmp_path):
    edir = setup(tmp_path)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    start = hours.week_of(TODAY) - dt.timedelta(weeks=1)
    eng["dates"]["start"] = start.isoformat()
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    hours.log_entry(m(edir), 10, "kickoff", "ana", on=start)
    hours.log_entry(m(edir), 10, "kickoff", "ben", on=start + dt.timedelta(days=1))
    f = hours.forecast(m(edir))
    assert f["rate_per_week"] == 20 and f["weeks"] == 1


def test_malformed_entries_do_not_hide_other_checks(tmp_path):
    edir = setup(tmp_path)
    (edir / "hours.yaml").write_text(yaml.safe_dump({"entries": [
        {"id": "H-aaaaaaaaaa", "date": "2026-09-01", "person": "ana", "hours": 8, "activity": "other", "refs": 5},
        {"id": "H-bbbbbbbbbb", "date": "2026-09-01", "person": 7, "hours": "x", "activity": "other", "refs": "A.6.2.5"},
        {"id": "H-cccccccccc", "date": "2026-09-02", "person": "ana", "hours": 9, "activity": "other", "refs": [9.3]},
        {"id": "H-cccccccccc", "date": "2026-09-02", "person": "ana", "hours": 9, "activity": "other"}]}))
    fs = findings(edir)
    msgs = " | ".join(f.message for f in fs if f.code == "E060")
    assert "appears more than once" in msgs and "not a number" in msgs and "more than 14" in msgs
    assert not [f for f in fs if f.code == "E000"] and "A, ." not in msgs
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out), "--force", "--no-docx"]) == 0


def test_bad_duration_skips_row_and_classification_edges(tmp_path):
    edir = setup(tmp_path)
    toggl = TOGGL.replace("02:30:00", "1:xx")
    log = hours.import_files(m(edir), [write(tmp_path, "t.csv", toggl)], match="larkspur")
    assert "no date or hours" in log[0] and len(m(edir).hours) == 1
    model = m(edir)
    assert hours.classify(model, "", "", "Call at 2pm about fixtures") == "other"
    assert hours.classify(model, "", "", "Reviewed gaps with owners") == "remediation"
    assert hours.classify(model, "", "", "Spent 2.5 hours") == "other"


def test_note_numbers_are_not_clause_refs_aliases_and_ignored(tmp_path):
    edir = setup(tmp_path)
    (edir / "hours.yaml").write_text(yaml.safe_dump({"aliases": {"Ana Lopez": "ana"}, "entries": []}))
    csvf = write(tmp_path, "g.csv", "date,person,hours,note,refs\n2026-09-30,Ana Lopez,2.5,Spent 6.2 h on GAP-01,9.3\n")
    hours.import_files(m(edir), [csvf])
    e = m(edir).hours[0]
    assert e["person"] == "ana" and e["refs"] == ["9.3", "GAP-01"]
    d = yaml.safe_load((edir / "hours.yaml").read_text())
    assert d["aliases"] == {"Ana Lopez": "ana"}
    d["ignored"] = [e["id"]]
    d["entries"] = []
    (edir / "hours.yaml").write_text(yaml.safe_dump(d))
    hours.import_files(m(edir), [csvf])
    assert m(edir).hours == [] and not findings(edir, severity="error")


def test_timesheet_stays_out_of_the_auditor_package(tmp_path):
    from grc import package
    edir = setup(tmp_path)
    hours.log_entry(m(edir), 2, "interviews", "ana")
    package.build(m(edir), tmp_path / "dist")
    root = next(p for p in (tmp_path / "dist").iterdir() if p.is_dir())
    assert not list(root.glob("01-overview/hours*")) and not (root / "08-source-record" / "engagement" / "hours.yaml").exists()


def test_match_is_forgiving_and_explains_itself(tmp_path):
    for typed in ('"Larkspur"', " Larkspur ", "HOURS_MATCH=Larkspur", "acme, larkspur", "\u201cLarkspur\u201d"):
        edir = setup(tmp_path / str(abs(hash(typed))))
        hours.import_files(m(edir), [write(tmp_path, "t.csv", TOGGL)], match=typed)
        assert len(m(edir).hours) == 2, typed
    edir = setup(tmp_path / "none")
    log = hours.import_files(m(edir), [write(tmp_path, "t.csv", TOGGL)], match="Larkspur Health (fictional)")
    assert any("skipped every row" in l and "Larkspur / ISO 42001 (2)" in l for l in log)
