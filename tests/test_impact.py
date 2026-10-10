"""AI system impact assessments (6.1.4, 8.4, A.5.2-A.5.5)."""
import datetime as dt
import shutil
from pathlib import Path

import yaml

from grc import impact
from grc.cli import main
from grc.model import load
from grc.render_md import render_all
from grc.rules import validate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)
CATS = ["safety", "health", "fairness", "privacy", "autonomy", "transparency", "security",
        "economic", "information", "environment", "rights"]

INVENTORY = {"items": [
    {"id": "INV-001", "name": "Triage chatbot", "kind": "ai_system", "risk_tier": "High",
     "description": "Suggests an urgency level for patient messages."},
    {"id": "INV-002", "name": "Claims scorer", "kind": "ai_system", "risk_tier": "Medium"},
    {"id": "INV-003", "name": "Copilot", "kind": "sdlc_tool"},
    {"id": "INV-004", "name": "Retired model", "kind": "ai_system", "in_scope": False},
]}


def setup(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    (edir / "inventory.yaml").write_text(yaml.safe_dump(INVENTORY, sort_keys=False))
    return edir


def findings(edir, today=TODAY, code=None, severity=None):
    fs = validate(load(edir, today=today))
    return [f for f in fs if (code is None or f.code == code) and (severity is None or f.severity == severity)]


def ia_path(edir, iid="IA-001"):
    return edir / "impact" / f"{iid}.yaml"


def edit(edir, fn, iid="IA-001"):
    p = ia_path(edir, iid)
    d = yaml.safe_load(p.read_text())
    fn(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def complete(d, residual=(2, 2)):
    """A complete, independently approved assessment with one relevant category."""
    d["context"].update(intended_use="Triage", affected_parties=["patients"])
    d["screening"] = [{"category": c, "relevant": c == "health", "rationale": "considered"} for c in CATS]
    d["impacts"] = [{"id": "I-01", "category": "health", "area": "individuals", "description": "Under-triage",
                     "likelihood": 4, "severity": 5, "mitigations": ["clinician review"],
                     "residual_likelihood": residual[0], "residual_severity": residual[1]}]
    d.update(conclusion="Acceptable with oversight", decision="approve", status="approved",
             assessor="Data Scientist", assessed_on="2026-09-01", approver="Head of Responsible AI",
             approved_on="2026-09-10")


def started(tmp_path):
    edir = setup(tmp_path)
    assert impact.new(load(edir, today=TODAY), "INV-001")[0].startswith("IA-001  INV-001")
    return edir


# ---------------------------------------------------------------- new
def test_new_all_creates_one_per_in_scope_ai_system_and_numbers_by_file(tmp_path):
    edir = setup(tmp_path)
    assert len(findings(edir, code="W130")) == 2  # INV-001, INV-002 (not the tool, not the retired one)
    log = impact.new(load(edir, today=TODAY), "all")
    assert [l.split()[:2] for l in log] == [["IA-001", "INV-001"], ["IA-002", "INV-002"]]
    d = yaml.safe_load(ia_path(edir).read_text())
    assert d["context"]["intended_use"].startswith("Suggests") and d["status"] == "draft"
    assert [s["category"] for s in d["screening"]] == CATS and all(s["relevant"] is None for s in d["screening"])
    assert ia_path(edir).read_text().startswith("# AI system impact assessment")
    # idempotent: nothing new, nothing overwritten
    assert impact.new(load(edir, today=TODAY), "all") == ["Every AI system in scope already has an impact assessment."]
    assert not findings(edir, code="W130") and len(findings(edir, code="W131")) == 2
    assert not findings(edir, severity="error")


def test_new_rejects_unknown_or_non_ai(tmp_path):
    edir = setup(tmp_path)
    m = load(edir, today=TODAY)
    for target, msg in (("INV-003", "sdlc_tool"), ("INV-999", "not in")):
        try:
            impact.new(m, target)
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert msg in str(exc)
    assert main(["--engagement", str(edir), "impact", "new", "INV-003"]) == 2


def test_superseded_frees_the_system_and_numbering_continues(tmp_path):
    edir = started(tmp_path)
    edit(edir, lambda d: d.update(status="superseded"))
    assert impact.new(load(edir, today=TODAY), "INV-001")[0].startswith("IA-002")
    # two active assessments for one system is an error
    edit(edir, lambda d: d.update(status="draft"))
    assert findings(edir, code="E030")


# ---------------------------------------------------------------- approval rules
def test_complete_approval_passes(tmp_path):
    edir = started(tmp_path)
    edit(edir, complete)
    assert not findings(edir, severity="error")
    assert impact.is_effective(load(edir, today=TODAY), yaml.safe_load(ia_path(edir).read_text()))


def test_approval_completeness(tmp_path):
    edir = started(tmp_path)
    edit(edir, lambda d: d.update(status="approved"))
    msgs = " ".join(f.message for f in findings(edir, code="E031"))
    assert "affected_parties" in msgs and "approver" in msgs and "unscreened" in msgs

    edir2 = started(tmp_path / "b")
    def broken(d):
        complete(d)
        d["screening"][2]["rationale"] = ""   # fairness: no rationale
        d["screening"][0]["relevant"] = True  # safety relevant but no impact
        d["decision"] = "approve_with_conditions"
    edit(edir2, broken)
    msgs = " ".join(f.message for f in findings(edir2, code="E031"))
    assert "without a rationale" in msgs and "no assessed impact" in msgs and "no conditions" in msgs


def test_approver_must_be_independent_of_assessor(tmp_path):
    edir = started(tmp_path)
    edit(edir, lambda d: (complete(d), d.update(approver="data scientist")))
    assert any("own assessor" in f.message for f in findings(edir, code="E031"))
    assert not impact.is_effective(load(edir, today=TODAY), yaml.safe_load(ia_path(edir).read_text()))


def test_residual_thresholds_and_acceptance(tmp_path):
    edir = started(tmp_path)
    edit(edir, lambda d: complete(d, residual=(3, 4)))  # 12: needs acceptance
    assert any("needs acceptance" in f.message for f in findings(edir, code="E032"))

    edit(edir, lambda d: d["impacts"][0].update(acceptance={"accepted_by": "Data Scientist", "accepted_on": "2026-09-10",
                                                            "rationale": "benefit outweighs"}))
    assert any("accepted by the assessor" in f.message for f in findings(edir, code="E032"))

    edit(edir, lambda d: d["impacts"][0]["acceptance"].update(accepted_by="CEO"))
    assert not findings(edir, severity="error")

    edit(edir, lambda d: d["impacts"][0].update(residual_likelihood=4, residual_severity=5))  # 20: unacceptable
    assert any("unacceptable" in f.message for f in findings(edir, code="E032"))
    edit(edir, lambda d: d.update(decision="reject"))
    assert not findings(edir, code="E032")

    edit(edir, lambda d: d["impacts"][0].update(residual_likelihood=None))
    assert any("without a residual" in f.message for f in findings(edir, code="E032"))


def test_residual_higher_than_inherent_warns(tmp_path):
    edir = started(tmp_path)
    edit(edir, lambda d: (complete(d), d["impacts"][0].update(likelihood=1, severity=1)))
    assert findings(edir, code="W133")


def test_review_cycle_by_risk_tier_and_expiry(tmp_path):
    edir = started(tmp_path)
    edit(edir, complete)
    m = load(edir, today=TODAY)
    assert impact.next_review(m, m.impacts["IA-001"]) == dt.date(2026, 9, 10) + dt.timedelta(days=180)  # High tier
    later = dt.date(2027, 3, 10)
    assert findings(edir, today=later, code="W132")
    assert not impact.is_effective(load(edir, today=later), m.impacts["IA-001"])


# ---------------------------------------------------------------- evidence
def _cite(edir):
    p = edir / "controls" / "A.5.2.yaml"
    d = yaml.safe_load(p.read_text())
    d["test"]["implemented"] = {"status": "verified", "evidence": ["IA-001"]}
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_assessment_as_evidence(tmp_path):
    edir = started(tmp_path)
    _cite(edir)
    assert any("not approved" in f.message for f in findings(edir, code="E015"))  # draft
    edit(edir, complete)
    assert not findings(edir, code="E015") and not findings(edir, code="E006")
    # past review: the record goes stale like any expired evidence
    assert findings(edir, today=dt.date(2027, 3, 10), code="E007")
    # self-approved: not citable
    edit(edir, lambda d: d.update(approver="Data Scientist"))
    assert findings(edir, code="E015")


# ---------------------------------------------------------------- reports
def test_reports_and_metrics(tmp_path):
    edir = setup(tmp_path)
    impact.new(load(edir, today=TODAY), "all")
    edit(edir, complete)
    m = load(edir, today=TODAY)
    out = tmp_path / "out"
    summary = render_all(m, validate(m), out)
    reg = (out / "impact-assessments.md").read_text()
    assert "IA-001" in reg and "IA-002" in reg and "Triage chatbot" in reg
    page = (out / "ia-IA-001.md").read_text()
    assert "Under-triage" in page and "Head of Responsible AI" in page
    assert "1 of 2" in summary


def test_cli_report_and_docx_slug(tmp_path):
    edir = setup(tmp_path)
    rep = tmp_path / "r.md"
    assert main(["--engagement", str(edir), "impact", "new", "all", "--report", str(rep)]) == 0
    assert "IA-002" in rep.read_text()
    eng = edir / "engagement.yaml"
    d = yaml.safe_load(eng.read_text())
    d["client"]["name"] = "Larkspur Health (fictional)"
    eng.write_text(yaml.safe_dump(d, sort_keys=False))
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out), "--force"]) == 0
    assert (out / "larkspur-health-fictional-iso42001-brief.docx").exists()
