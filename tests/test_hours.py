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
    assert "toggl" in log[0] and "1 skipped (other client/project)" in log[0] and "harvest" in log[1] and "clockify" in log[2]
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
