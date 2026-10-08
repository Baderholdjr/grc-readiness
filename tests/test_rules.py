"""Rule tests: each mutates a copy of the example engagement and checks the finding."""
import datetime as dt
import shutil
from pathlib import Path

import pytest
import yaml

from grc.model import load
from grc.rules import metrics, requirement_state, validate

ROOT = Path(__file__).resolve().parent.parent
# Engine tests run against a frozen copy so editing the live engagement never breaks them.
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)


@pytest.fixture
def eng(tmp_path):
    dst = tmp_path / "engagement"
    shutil.copytree(FIXTURE, dst)
    return dst


def codes(edir, today=TODAY, severity=None):
    return {f.code for f in validate(load(edir, today=today)) if severity is None or f.severity == severity}


def edit_control(edir, cid, fn):
    p = edir / "controls" / f"{cid}.yaml"
    data = yaml.safe_load(p.read_text())
    fn(data)
    p.write_text(yaml.safe_dump(data, sort_keys=False))


def test_example_is_valid():
    errors = [f for f in validate(load(FIXTURE, today=TODAY)) if f.severity == "error"]
    assert errors == []


def test_codification_gap_detected():
    assert "W102" in codes(FIXTURE)


def test_verified_without_evidence(eng):
    edit_control(eng, "5.2", lambda d: d["test"]["documented"].update(status="verified", evidence=[]))
    assert "E005" in codes(eng, severity="error")


def test_documented_needs_approved_document(eng):
    # EV-001 is an unapproved draft
    edit_control(eng, "4.3", lambda d: d["test"]["documented"].update(status="verified", evidence=["EV-001"]))
    assert "E012" in codes(eng)


def test_tested_needs_test_evidence(eng):
    edit_control(eng, "A.6.2.5", lambda d: d["test"]["tested"].update(status="verified", evidence=["EV-011"]))
    assert "E012" in codes(eng)


def test_stale_evidence_blocks_verified(eng):
    edit_control(eng, "A.6.1.2", lambda d: d["test"]["documented"].update(status="verified"))
    assert "E007" in codes(eng)


def test_evidence_expires_with_time():
    later = dt.date(2027, 3, 1)  # EV-010 (90 days from 2026-09-28) has expired
    found = codes(FIXTURE, today=later)
    assert "E007" in found


def test_unknown_evidence_reference(eng):
    edit_control(eng, "A.6.2.6", lambda d: d["test"]["evidenced"].update(evidence=["EV-999"]))
    assert "E006" in codes(eng)


def test_leg_order(eng):
    edit_control(eng, "A.6.2.6", lambda d: d["test"]["tested"].update(status="verified", evidence=["EV-022"]))
    assert "E008" in codes(eng)


def test_owner_required(eng):
    edit_control(eng, "A.6.2.6", lambda d: d.update(owner=""))
    assert "E009" in codes(eng)


def test_exclusion_needs_justification(eng):
    edit_control(eng, "A.10.4", lambda d: d.update(applicable=False, justification=""))
    assert "E004" in codes(eng)


def test_clause_cannot_be_excluded(eng):
    edit_control(eng, "9.2", lambda d: d.update(applicable=False, justification="nope"))
    assert "E004" in codes(eng)


def test_missing_control_file(eng):
    (eng / "controls" / "9.3.yaml").unlink()
    assert "E002" in codes(eng)


def test_closed_gap_needs_evidence(eng):
    p = eng / "gaps.yaml"
    data = yaml.safe_load(p.read_text())
    data["gaps"][0]["status"] = "closed"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    assert "E013" in codes(eng)


def test_schema_rejects_bad_status(eng):
    edit_control(eng, "4.4", lambda d: d["test"]["tested"].update(status="done"))
    assert "E001" in codes(eng)


def test_ready_state(eng):
    def make_ready(d):
        d["test"] = {
            "documented": {"status": "verified", "evidence": ["EV-013"]},
            "implemented": {"status": "verified", "evidence": ["EV-014"]},
            "evidenced": {"status": "verified", "evidence": ["EV-014"]},
            "tested": {"status": "verified", "evidence": ["EV-022"]},
        }
    edit_control(eng, "10.2", make_ready)
    model = load(eng, today=TODAY)
    assert requirement_state(model, "10.2") == "Ready"
    assert metrics(model)["requirements_ready"] == 1
    assert not [f for f in validate(model) if f.severity == "error"]
