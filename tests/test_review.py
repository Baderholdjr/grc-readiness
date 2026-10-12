"""Management review (9.3)."""
import datetime as dt
import hashlib
import shutil
from pathlib import Path

import yaml

from grc import issues, review
from grc.cli import main
from grc.model import load
from grc.render_md import render_all
from grc.rules import metrics, validate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)
INPUTS = ["previous_actions", "context_changes", "interested_parties", "performance", "risks_and_impacts",
          "improvement", "resources"]


def setup(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    return edir


def m(edir, today=TODAY):
    return load(edir, today=today)


def findings(edir, today=TODAY, code=None, severity=None):
    return [f for f in validate(m(edir, today)) if (code is None or f.code == code) and (severity is None or f.severity == severity)]


def rpath(edir, rid="MR-2026-01"):
    return edir / "reviews" / f"{rid}.yaml"


def edit(edir, fn, rid="MR-2026-01"):
    p = rpath(edir, rid)
    d = yaml.safe_load(p.read_text())
    fn(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def hold(d, on="2026-10-06"):
    d.update(status="held", held_on=on, chair="Chief Executive Officer", attendees=["CTO", "Head of Responsible AI"])
    for i in d["inputs"]:
        i["notes"] = f"Discussed {i['id']}."
    d["decisions"] = [{"id": "D-01", "about": "resources", "decision": "Fund an ML evaluation engineer."}]
    d["actions"] = [{"id": "A-01", "action": "Hire ML evaluation engineer", "owner": "CTO", "due": "2026-12-01", "status": "open"}]


def held(tmp_path, planned=dt.date(2026, 10, 6)):
    edir = setup(tmp_path)
    review.new(m(edir, dt.date(2026, 10, 1)), planned)
    review.pack(m(edir, dt.date(2026, 10, 5)), "MR-2026-01")
    edit(edir, hold)
    return edir


def cite(edir, rid="MR-2026-01", leg="evidenced"):
    p = edir / "controls" / "9.3.yaml"
    d = yaml.safe_load(p.read_text())
    d["owner"] = d.get("owner") or "CEO"
    d["test"]["implemented"] = {"status": "verified", "evidence": [rid]}
    d["test"][leg] = {"status": "verified", "evidence": [rid]}
    p.write_text(yaml.safe_dump(d, sort_keys=False))


# ---------------------------------------------------------------- schedule and pack
def test_new_numbers_and_validates(tmp_path):
    edir = setup(tmp_path)
    assert review.new(m(edir), dt.date(2026, 11, 2))[0].startswith("MR-2026-01")
    assert review.new(m(edir), dt.date(2026, 12, 2))[0].startswith("MR-2026-02")
    d = yaml.safe_load(rpath(edir).read_text())
    assert [i["id"] for i in d["inputs"]] == INPUTS and d["status"] == "planned"
    assert not findings(edir, severity="error") and not findings(edir, code="W150")
    assert findings(edir, today=dt.date(2026, 11, 3), code="W150")


def test_pack_is_generated_frozen_and_fingerprinted(tmp_path):
    edir = setup(tmp_path)
    review.new(m(edir), dt.date(2026, 11, 2))
    review.pack(m(edir), "MR-2026-01")
    pk = edir / "reviews" / "MR-2026-01-pack.md"
    text = pk.read_text()
    for n, title in enumerate(["Status of actions", "Changes in external", "interested parties", "AIMS performance",
                               "impact assessments", "continual improvement", "Adequacy of resources"], start=1):
        assert f"## {n}. " in text and title in text
    d = yaml.safe_load(rpath(edir).read_text())
    assert d["pack"]["sha256"] == hashlib.sha256(pk.read_bytes()).hexdigest() and d["pack"]["as_of"] == "2026-10-08"
    assert rpath(edir).read_text().startswith("# Management review")   # header comment kept
    review.pack(m(edir, TODAY + dt.timedelta(days=1)), "MR-2026-01")     # refresh allowed before the meeting
    edit(edir, hold)
    try:
        review.pack(m(edir), "MR-2026-01")
        raise AssertionError
    except ValueError as exc:
        assert "frozen" in str(exc)


# ---------------------------------------------------------------- held / closed
def test_held_review_completeness(tmp_path):
    edir = held(tmp_path)
    assert not findings(edir, severity="error")
    assert review.is_sound(m(edir), "MR-2026-01")
    edit(edir, lambda d: (d["inputs"][2].update(notes=""), d.update(chair="", decisions=[], held_on="2026-10-20")))
    msg = " ".join(f.message for f in findings(edir, code="E051"))
    assert "interested_parties" in msg and "no chair" in msg and "no decisions" in msg and "future" in msg


def test_pack_tampering_and_late_pack(tmp_path):
    edir = held(tmp_path)
    pk = edir / "reviews" / "MR-2026-01-pack.md"
    pk.write_text(pk.read_text().replace("Readiness", "Readyness"))
    assert any("changed after it was generated" in f.message for f in findings(edir, code="E051"))
    edir2 = held(tmp_path / "b")
    edit(edir2, lambda d: d.update(held_on="2026-10-04"))   # pack as of 10-05, meeting 10-04
    assert any("after the meeting" in f.message for f in findings(edir2, code="E051"))


def test_closing_needs_minutes_and_finished_actions(tmp_path):
    edir = held(tmp_path)
    edit(edir, lambda d: d.update(status="closed"))
    msgs = " ".join(f.message for f in findings(edir, severity="error"))
    assert "minutes not approved" in msgs and "open actions" in msgs
    edit(edir, lambda d: (d.update(minutes_approved_by="Chief Executive Officer", minutes_approved_on="2026-10-07"),
                          d["actions"][0].update(status="done")))
    assert any("done without closed_on and evidence" in f.message for f in findings(edir, code="E052"))
    edit(edir, lambda d: d["actions"][0].update(closed_on="2026-10-07", evidence=["EV-999"]))
    assert findings(edir, code="E006")
    ev = yaml.safe_load((edir / "evidence" / "index.yaml").read_text())["evidence"][0]["id"]
    edit(edir, lambda d: d["actions"][0].update(evidence=[ev]))
    assert not findings(edir, severity="error")


def test_action_rules_and_issues(tmp_path):
    edir = held(tmp_path)
    edit(edir, lambda d: d["actions"].append({"id": "A-01", "action": "dup", "status": "open"}))
    msgs = " ".join(f.message for f in findings(edir, severity="error"))
    assert "used more than once" in msgs and "without owner, due" in msgs
    edir = held(tmp_path / "b")
    assert findings(edir, today=dt.date(2026, 12, 2), code="W152")
    items = [i for i in issues.tracked_items(m(edir)) if i["kind"] == "review"]
    assert items and items[0]["id"] == "MR-2026-01/A-01" and items[0]["open"] and "<!-- grc:MR-2026-01/A-01 -->" in items[0]["body"]
    assert metrics(m(edir, dt.date(2026, 12, 2)))["mr_actions_overdue"] == 1


# ---------------------------------------------------------------- evidence and cadence
def test_review_as_evidence_for_9_3(tmp_path):
    edir = held(tmp_path)
    cite(edir)
    assert any("management review" in f.message for f in findings(edir, code="E015"))   # minutes not approved yet
    edit(edir, lambda d: d.update(minutes_approved_by="Chief Executive Officer", minutes_approved_on="2026-10-07"))
    assert not findings(edir, code="E015") and not findings(edir, code="W153")
    later = dt.date(2027, 10, 10)
    assert findings(edir, today=later, code="E007") and findings(edir, today=later, code="W151")


def test_cadence_warnings(tmp_path):
    edir = setup(tmp_path)
    stage1 = dt.date.fromisoformat(str(yaml.safe_load((edir / "engagement.yaml").read_text())["dates"]["stage1"]))
    assert findings(edir, today=stage1 - dt.timedelta(days=30), code="W151")
    assert not findings(edir, today=stage1 - dt.timedelta(days=90), code="W151")
    p = edir / "controls" / "9.3.yaml"
    d = yaml.safe_load(p.read_text())
    d["owner"] = "CEO"
    d["test"]["implemented"] = {"status": "verified", "evidence": []}
    d["test"]["evidenced"] = {"status": "verified", "evidence": []}
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert findings(edir, code="W153")


def test_previous_actions_carry_into_next_pack(tmp_path):
    edir = held(tmp_path)
    edit(edir, lambda d: d.update(minutes_approved_by="CEO", minutes_approved_on="2026-10-07"))
    review.new(m(edir), dt.date(2027, 3, 1))
    review.pack(m(edir, dt.date(2027, 2, 20)), "MR-2027-01")
    text = (edir / "reviews" / "MR-2027-01-pack.md").read_text()
    assert "MR-2026-01/A-01" in text and "Hire ML evaluation engineer" in text and "MR-2026-01 on 2026-10-06" in text


# ---------------------------------------------------------------- robustness and reports
def test_malformed_review_is_reported(tmp_path):
    edir = setup(tmp_path)
    (edir / "reviews").mkdir()
    (edir / "reviews" / "MR-2026-01.yaml").write_text("id: [unclosed\n")
    (edir / "reviews" / "MR-2026-02.yaml").write_text("id: MR-2026-09\nstatus: held\nplanned_on: 2026-10-01\n"
                                                      "inputs: 5\ndecisions: [x]\nactions: [{id: A-1}]\n")
    fs = findings(edir)
    assert {"MR-2026-01", "MR-2026-02"} <= {f.ref for f in fs if f.code == "E001"}
    assert not [f for f in fs if f.code == "E000"]
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(tmp_path / "o"), "--force"]) == 0


def test_reports(tmp_path):
    edir = held(tmp_path)
    digests = []
    for run in ("a", "b"):
        out = tmp_path / run
        assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
        digests.append(hashlib.sha256((out / "mr-MR-2026-01-pack.docx").read_bytes()).hexdigest())
    out = tmp_path / "a"
    reg = (out / "management-reviews.md").read_text()
    assert "MR-2026-01" in reg and "1 open" in reg
    page = (out / "mr-MR-2026-01.md").read_text()
    assert "Fund an ML evaluation engineer" in page and "Discussed performance" in page
    assert (out / "mr-MR-2026-01-pack.md").exists() and digests[0] == digests[1]
    assert "Management review" in (out / "README.md").read_text()


def test_cli(tmp_path):
    edir = setup(tmp_path)
    rep = tmp_path / "r.md"
    assert main(["--engagement", str(edir), "review", "new", "2026-11-02", "--report", str(rep)]) == 0
    assert "MR-2026-01" in rep.read_text()
    assert main(["--engagement", str(edir), "review", "pack"]) == 2
    assert main(["--engagement", str(edir), "review", "pack", "MR-2026-01"]) == 0
    assert main(["--engagement", str(edir), "review", "pack", "MR-2099-01"]) == 2


# ---------------------------------------------------------------- review regressions
def test_minutes_dates_are_checked_for_held_reviews_too(tmp_path):
    for on in ("2099-01-01", "2020-01-01", None):
        edir = held(tmp_path / str(on))
        cite(edir)
        edit(edir, lambda d, o=on: d.update(minutes_approved_by="Board", minutes_approved_on=o))
        assert findings(edir, code="E015"), on
        assert review.evidence_entries(m(edir))["MR-2026-01"]["result"] == "fail"


def test_closed_with_open_actions_is_not_sound(tmp_path):
    edir = held(tmp_path)
    edit(edir, lambda d: d.update(status="closed", minutes_approved_by="CEO", minutes_approved_on="2026-10-07"))
    assert not review.is_sound(m(edir), "MR-2026-01")
    assert review.evidence_entries(m(edir))["MR-2026-01"]["result"] == "fail"


def test_malformed_fields_do_not_crash_or_hide_checks(tmp_path):
    edir = held(tmp_path)
    review.new(m(edir), dt.date(2026, 11, 1))
    edit(edir, lambda d: d.update(attendees=5, chair=""), "MR-2026-01")
    edit(edir, lambda d: d.update(actions=[{"id": "A-01", "action": "x", "owner": "o", "due": "2026-12-01",
                                            "status": "open", "evidence": [1]}]), "MR-2026-02")
    fs = findings(edir)
    assert any(f.code == "E001" for f in fs) and any(f.code == "E051" for f in fs)   # review checks still run
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "validate", "--summary", str(tmp_path / "s.md")]) == 1
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(tmp_path / "o"), "--force"]) == 0


def test_pack_rewrites_the_record_cleanly(tmp_path):
    edir = setup(tmp_path)
    review.new(m(edir), dt.date(2026, 11, 2))
    p = rpath(edir)
    p.write_text(p.read_text().replace("pack:\n  as_of: null\n  sha256: null\n", "pack: null  # to do\n# a note\n"))
    review.pack(m(edir), "MR-2026-01")
    text = p.read_text()
    assert text.count("\npack:") == 1 and text.startswith("# Management review")
    d = yaml.safe_load(text)
    assert d["pack"]["sha256"] and d["planned_on"] == "2026-11-02"
    assert not findings(edir, severity="error")


def test_playbook_without_review_section_still_works(tmp_path):
    edir = setup(tmp_path)
    fw = tmp_path / "frameworks" / "iso42001"
    fw.mkdir(parents=True)
    pb = yaml.safe_load((Path(review.__file__).parent / "resources" / "frameworks" / "iso42001" / "playbook.yaml").read_text())
    pb.pop("management_review")
    (fw / "playbook.yaml").write_text(yaml.safe_dump(pb))
    review.new(m(edir), dt.date(2026, 11, 2))
    review.pack(m(edir), "MR-2026-01")
    assert "## 7. Adequacy of resources" in (edir / "reviews" / "MR-2026-01-pack.md").read_text()
    edit(edir, lambda d: (hold(d), [i.update(notes="") for i in d["inputs"]]))
    assert any("no notes for input(s)" in f.message for f in findings(edir, code="E051"))
