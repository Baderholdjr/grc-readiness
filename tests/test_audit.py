"""Internal audit (9.2) and corrective actions (10.2)."""
import datetime as dt
import json
import shutil
from pathlib import Path

import yaml

from grc import audit
from grc.cli import main
from grc.model import load
from grc.rules import validate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)  # the fixture's evidence is current on this date


def setup(tmp_path, scope=("A.6.2.5", "A.6.2.4", "9.2"), auditors=("Internal Auditor",), populations=None):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    (edir / "audit").mkdir()
    prog = {"audits": [{"id": "AUD-2027-01", "title": "Full AIMS", "scope": list(scope), "auditors": list(auditors),
                        "planned": {"start": "2027-01-11", "end": "2027-01-29"}, "status": "planned",
                        "populations": populations or {}}]}
    (edir / "audit" / "program.yaml").write_text(yaml.safe_dump(prog, sort_keys=False))
    return edir


def errors(edir, today=TODAY, code=None):
    fs = [f for f in validate(load(edir, today=today)) if f.severity == "error"]
    return [f for f in fs if code is None or f.code == code]


def wp_path(edir, wid):
    return edir / "audit" / "AUD-2027-01" / "workpapers" / f"{wid}.yaml"


def edit_wp(edir, wid, fn):
    p = wp_path(edir, wid)
    d = yaml.safe_load(p.read_text())
    fn(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_sample_size_table():
    assert [audit.default_sample_size(n) for n in (0, 1, 3, 10, 40, 200, 1000)] == [0, 1, 2, 3, 5, 15, 25]


def test_draw_is_deterministic_and_order_independent():
    items = [f"#{i}" for i in range(1, 101)]
    a = audit.draw(items, 10, "AUD-2027-01/WP-01")
    b = audit.draw(list(reversed(items)) + items[:5], 10, "AUD-2027-01/WP-01")
    assert a == b and len(a) == 10
    assert audit.draw(items, 10, "AUD-2027-01/WP-02") != a
    assert audit.draw(items[:3], 10, "x") == ["#1", "#2", "#3"]


def test_scope_by_group_and_exclude(tmp_path):
    edir = setup(tmp_path, scope=("A.6",))
    m = load(edir)
    a = m.audits[0]
    assert all(r.startswith("A.6.") for r in audit.in_scope(m, a)) and len(audit.in_scope(m, a)) == 9
    a["exclude"] = ["A.6.2"]
    assert audit.in_scope(m, a) == ["A.6.1.2", "A.6.1.3"]


def test_plan_writes_workpapers_once(tmp_path):
    edir = setup(tmp_path)
    log = audit.plan(load(edir, today=TODAY), "AUD-2027-01")
    assert len(log) == 3
    wps = load(edir).workpapers["AUD-2027-01"]
    assert sorted(wp["requirement"] for wp in wps.values()) == ["9.2", "A.6.2.4", "A.6.2.5"]
    assert any("owner" in step.lower() for step in wps["WP-01"]["procedure"])
    assert audit.plan(load(edir), "AUD-2027-01") == ["All in-scope requirements already have workpapers."]
    assert not errors(edir)


def test_independence(tmp_path):
    edir = setup(tmp_path, auditors=("Head of Platform",))  # owns A.6.2.4 / A.6.2.5 in the fixture
    assert errors(edir, code="E020")
    (edir / "owners.yaml").write_text(yaml.safe_dump({"owners": [{"role": "Head of Platform", "github": ["alice"]}]}))
    edir2 = setup(tmp_path / "b", auditors=("alice",))
    (edir2 / "owners.yaml").write_text(yaml.safe_dump({"owners": [{"role": "Head of Platform", "github": ["alice"]}]}))
    assert errors(edir2, code="E020")  # GitHub user of the owner role


def _snapshot(edir, ev, n):
    d = edir / "evidence" / "collected"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ev}.json").write_text(json.dumps({"collected_at": "2027-01-10T00:00:00+00:00",
                                              "details": {"items": [{"id": f"#{i}"} for i in range(1, n + 1)]}}))


def test_sampling_from_collector_population(tmp_path):
    edir = setup(tmp_path, scope=("A.6.2.5",))
    _snapshot(edir, "EV-111", 40)
    (edir / "collectors.yaml").write_text(yaml.safe_dump({"enabled": True, "checks": [
        {"evidence": "EV-111", "title": "PRs", "collector": "github.pr_reviews", "params": {"repo": "o/r"},
         "supports": ["A.6.2.5:evidenced"]}]}))
    audit.plan(load(edir), "AUD-2027-01")
    wp = load(edir).workpapers["AUD-2027-01"]["WP-01"]
    assert wp["population"] == "EV-111"
    log = audit.sample(load(edir, today=TODAY), "AUD-2027-01")
    wp = load(edir).workpapers["AUD-2027-01"]["WP-01"]
    assert len(wp["sample"]) == 5 and wp["sampling"]["population_size"] == 40 and len(wp["sampling"]["population_sha256"]) == 64
    first = [s["item"] for s in wp["sample"]]
    assert "already sampled" in audit.sample(load(edir), "AUD-2027-01")[0]
    audit.sample(load(edir), "AUD-2027-01", force=True)
    assert [s["item"] for s in load(edir).workpapers["AUD-2027-01"]["WP-01"]["sample"]] == first  # reproducible
    edit_wp(edir, "WP-01", lambda d: d["sample"][0].update(result="pass"))
    assert "NOT redrawn" in audit.sample(load(edir), "AUD-2027-01", force=True)[0]


def test_population_from_csv(tmp_path):
    edir = setup(tmp_path, scope=("A.8.4",), populations={"incidents": {"file": "populations/incidents.csv", "key": "ticket"}})
    (edir / "audit" / "populations").mkdir()
    (edir / "audit" / "populations" / "incidents.csv").write_text("ticket,title\n" + "".join(f"INC-{i},x\n" for i in range(1, 8)))
    audit.plan(load(edir), "AUD-2027-01")
    edit_wp(edir, "WP-01", lambda d: d.update(population="incidents"))
    audit.sample(load(edir, today=TODAY), "AUD-2027-01")
    wp = load(edir).workpapers["AUD-2027-01"]["WP-01"]
    assert len(wp["sample"]) == 3 and all(s["item"].startswith("INC-") for s in wp["sample"])


def _conclude(d, conclusion="effective", by="Internal Auditor", **extra):
    d.update(conclusion=conclusion, summary="Tested per procedure.", performed_by=by, performed_on="2027-01-15", **extra)
    for s in d.get("sample", []):
        s["result"] = s.get("result") if s.get("result") != "not_tested" else "pass"


def test_workpaper_conclusion_rules(tmp_path):
    edir = setup(tmp_path, scope=("A.6.2.5",))
    audit.plan(load(edir), "AUD-2027-01")
    edit_wp(edir, "WP-01", lambda d: d.update(sample=[{"item": "#1", "result": "exception", "note": "no approval"},
                                                      {"item": "#2", "result": "not_tested"}], conclusion="effective"))
    codes = {f.message.split(" ", 1)[1][:30] for f in errors(edir, code="E022")}
    assert len(errors(edir, code="E022")) >= 3  # no performer, untested item, no summary, exceptions w/o rationale
    edit_wp(edir, "WP-01", lambda d: _conclude(d, "not_effective"))
    assert any("raises no finding" in f.message for f in errors(edir, code="E022"))
    edit_wp(edir, "WP-01", lambda d: d.update(findings=["NC-001"]))
    assert errors(edir, code="E025")  # finding not in register
    edit_wp(edir, "WP-01", lambda d: d.update(reviewed_by="Internal Auditor"))
    assert any("reviewed by the person who performed" in f.message for f in errors(edir, code="E022"))


def test_workpaper_is_test_evidence_only_when_reviewed(tmp_path):
    edir = setup(tmp_path, scope=("A.6.2.5",))
    audit.plan(load(edir), "AUD-2027-01")
    edit_wp(edir, "WP-01", lambda d: _conclude(d))
    p = edir / "controls" / "A.6.2.5.yaml"
    c = yaml.safe_load(p.read_text())
    c["test"]["tested"] = {"status": "verified", "evidence": ["AUD-2027-01/WP-01"]}
    p.write_text(yaml.safe_dump(c, sort_keys=False))
    assert any("not concluded effective and independently reviewed" in f.message for f in errors(edir, code="E015"))
    edit_wp(edir, "WP-01", lambda d: d.update(reviewed_by="Engagement Lead", reviewed_on="2027-01-18"))
    assert not errors(edir)


def _findings(edir, items):
    (edir / "findings.yaml").write_text(yaml.safe_dump({"findings": items}, sort_keys=False))


BASE = {"id": "NC-001", "source": "internal_audit", "audit": "AUD-2027-01", "requirement": "A.6.2.5", "grade": "minor",
        "description": "2 of 5 promotions merged without independent approval.", "raised_on": "2027-01-15", "status": "open"}


def test_finding_lifecycle(tmp_path):
    edir = setup(tmp_path, scope=("A.6.2.5",))
    _findings(edir, [{**BASE, "status": "action_planned"}])
    assert any("without owner, due, root_cause, corrective_action" in f.message for f in errors(edir, code="E024"))
    plan_ok = {**BASE, "owner": "Head of Platform", "due": "2027-02-15", "root_cause": "Admins could bypass rules",
               "corrective_action": "Remove bypass; require 1 approval", "status": "implemented"}
    _findings(edir, [plan_ok])
    assert any("without implementation evidence" in f.message for f in errors(edir, code="E024"))
    _findings(edir, [{**plan_ok, "evidence": ["EV-011"], "status": "closed"}])
    assert any("without an effectiveness review" in f.message for f in errors(edir, code="E024"))
    eff = {"reviewed_on": "2027-02-20", "reviewed_by": "Head of Platform", "effective": True, "evidence": ["EV-011"]}
    _findings(edir, [{**plan_ok, "evidence": ["EV-011"], "status": "closed", "effectiveness": eff}])
    assert any("reviewed by the action owner" in f.message for f in errors(edir, code="E024"))
    _findings(edir, [{**plan_ok, "evidence": ["EV-011"], "status": "closed", "effectiveness": {**eff, "reviewed_by": "Internal Auditor"}}])
    assert not errors(edir)


def test_major_nc_blocks_verified_tested_and_cannot_be_accepted(tmp_path):
    edir = setup(tmp_path, scope=("A.6.2.5",))
    _findings(edir, [{**BASE, "grade": "major", "status": "accepted"}])
    assert errors(edir, code="E024")
    p = edir / "controls" / "A.6.2.5.yaml"
    c = yaml.safe_load(p.read_text())
    c["test"]["tested"] = {"status": "verified", "evidence": ["EV-022"]}
    p.write_text(yaml.safe_dump(c, sort_keys=False))
    _findings(edir, [{**BASE, "grade": "major"}])
    assert errors(edir, code="E026")


def test_audit_status_gates(tmp_path):
    edir = setup(tmp_path, scope=("A.6.2.5",))
    audit.plan(load(edir), "AUD-2027-01")
    prog = edir / "audit" / "program.yaml"
    d = yaml.safe_load(prog.read_text())
    d["audits"][0]["status"] = "closed"
    prog.write_text(yaml.safe_dump(d, sort_keys=False))
    msgs = " ".join(f.message for f in errors(edir, code="E021"))
    assert "not concluded" in msgs and "report.issued" in msgs
    edit_wp(edir, "WP-01", lambda w: _conclude(w))
    d["audits"][0]["report"] = {"issued": "2027-01-29", "approved_by": "Engagement Lead"}
    prog.write_text(yaml.safe_dump(d, sort_keys=False))
    assert any("lack review" in f.message for f in errors(edir, code="E021"))
    edit_wp(edir, "WP-01", lambda w: w.update(reviewed_by="Engagement Lead", reviewed_on="2027-01-28"))
    assert not errors(edir)


def test_reports_and_cli(tmp_path):
    edir = setup(tmp_path, scope=("A.6.2.5", "9.2"))
    assert main(["--engagement", str(edir), "audit", "plan", "AUD-2027-01"]) == 0
    assert main(["--engagement", str(edir), "audit", "plan", "AUD-9999-01"]) == 2
    _findings(edir, [{**BASE, "owner": "Head of Platform", "due": "2026-10-01"}])
    edit_wp(edir, "WP-01", lambda w: _conclude(w, "not_effective", findings=["NC-001"]))
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", "2026-10-08", "build", "--out", str(out)]) == 0
    idx = (out / "README.md").read_text()
    assert "(internal-audit.md)" in idx and "(corrective-actions.md)" in idx and "Open nonconformities:** 0 major · 1 minor" in idx
    rep = (out / "audit-AUD-2027-01.md").read_text()
    assert "NC-001" in rep and "❌ not effective" in rep
    assert "NC-001" in (out / "corrective-actions.md").read_text()
    assert any(f.code == "W120" for f in validate(load(edir, today=TODAY)))  # NC past due


def test_findings_become_issues(tmp_path):
    from grc import issues
    edir = setup(tmp_path, scope=("A.6.2.5",))
    _findings(edir, [{**BASE, "owner": "Head of Platform"}, {**BASE, "id": "OFI-001", "grade": "ofi"}])
    items = {i["id"]: i for i in issues.tracked_items(load(edir))}
    assert items["NC-001"]["labels"] == ["grc-finding", "grade:minor"] and items["NC-001"]["open"]
    assert "<!-- grc:NC-001 -->" in items["NC-001"]["body"] and "Effectiveness reviewed" in items["NC-001"]["body"]
    assert "no corrective action is required" in items["OFI-001"]["body"]
    assert "GAP-01" in items


def test_new_engagement_schedules_an_audit(tmp_path):
    edir, intake = tmp_path / "engagement", tmp_path / "intake"
    main(["--engagement", str(edir), "new-engagement", "--client", "A", "--start", "2026-11-02", "--stage1",
          "2027-03-15", "--stage2", "2027-05-10", "--intake", str(intake), "--confirm-reset"])
    m = load(edir)
    a = m.audits[0]
    test = m.phase_index["test"]
    assert a["id"] == "AUD-2027-01" and str(a["planned"]["start"]) == str(test["start"]) and m.findings == []
    assert not [f for f in validate(m) if f.severity == "error"]
