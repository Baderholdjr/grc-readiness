"""new-engagement, owners/CODEOWNERS, issue assignment + overdue reminders, evidence linking, sandbox."""
import datetime as dt
import json
import shutil
from pathlib import Path

import yaml

from grc import codeowners, collect, issues, newengagement, sandbox
from grc.cli import main
from grc.model import load
from grc.rules import validate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
D = dt.date


def copy(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    return edir


# ------------------------------------------------------------ new engagement
def test_phases_are_contiguous_and_end_after_stage2():
    ph = newengagement.compute_phases(D(2026, 11, 2), D(2027, 3, 15), D(2027, 5, 10))
    assert [p["id"] for p in ph] == ["validate", "governance", "implement", "test", "stage1", "stage2"]
    for a, b in zip(ph, ph[1:]):
        assert b["start"] == a["end"] + dt.timedelta(days=1)
    assert ph[4]["label"] == "MAR 2027" and ph[-1]["end"] >= D(2027, 5, 10)


def test_phases_reject_bad_dates():
    for args in [(D(2027, 1, 1), D(2026, 12, 1), D(2027, 2, 1)), (D(2026, 11, 1), D(2026, 12, 15), D(2027, 2, 1))]:
        try:
            newengagement.compute_phases(*args)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_new_engagement_resets_and_validates(tmp_path):
    edir, intake = copy(tmp_path), tmp_path / "intake"
    intake.mkdir()
    (intake / "README.md").write_text("keep")
    (intake / "old.csv").write_text("x")
    assert main(["--engagement", str(edir), "new-engagement", "--client", "Acme", "--start", "2026-11-02",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--intake", str(intake)]) == 2  # needs confirm
    assert (intake / "old.csv").exists()
    assert main(["--engagement", str(edir), "new-engagement", "--client", "Acme", "--start", "2026-11-02",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--intake", str(intake), "--confirm-reset"]) == 0
    assert sorted(p.name for p in intake.iterdir()) == ["README.md"]
    m = load(edir)
    assert m.client == "Acme" and m.gaps == [] and m.evidence == [] and len(m.controls) == 65
    assert not [f for f in validate(m) if f.severity in ("error", "warning")]


# ------------------------------------------------------------------- owners
def _owners(edir, mapping):
    (edir / "owners.yaml").write_text(yaml.safe_dump({"owners": [{"role": r, "github": u} for r, u in mapping.items()]}))


def test_unknown_owner_warns(tmp_path):
    edir = copy(tmp_path)
    _owners(edir, {"Head of Platform": ["alice"]})
    codes = [f for f in validate(load(edir, today=D(2026, 10, 8))) if f.code == "W111"]
    assert codes and any("VP Engineering" in f.message for f in codes)
    assert not any("Head of Platform" in f.message for f in codes)


def test_codeowners_block_is_managed_and_idempotent(tmp_path):
    edir = copy(tmp_path)
    _owners(edir, {"Head of Platform": ["alice", "org/platform"], "VP Engineering": ["bob"]})
    co = tmp_path / "CODEOWNERS"
    co.write_text("* @lead\n")
    m = load(edir)
    changed, missing = codeowners.update(m, co)
    text = co.read_text()
    assert changed and text.startswith("* @lead\n")
    assert "/controls/A.6.2.4.yaml @alice @org/platform" in text and "/controls/5.2.yaml @bob" in text
    assert any("Legal" in x for x in missing)
    assert codeowners.update(m, co) == (False, missing)
    co.write_text(text + "\n# trailing rule\n/docs/ @writer\n")
    codeowners.update(m, co)
    assert co.read_text().count(codeowners.BEGIN) == 1 and "/docs/ @writer" in co.read_text()


class FakeGH:
    def __init__(self, existing=None, comments=None, reject_assignees=False):
        self.calls, self.existing, self.comments, self.reject = [], existing or [], comments or {}, reject_assignees

    def call(self, method, path, body=None):
        import urllib.error
        self.calls.append((method, path, body))
        if path.startswith("/labels") or path.startswith("/milestones?"):
            return [] if method == "GET" else {"number": 1}
        if path == "/milestones":
            return {"number": len(self.calls)}
        if path.startswith("/issues?"):
            return self.existing if "page=1" in path else []
        if path.endswith("/comments?per_page=100"):
            return self.comments.get(path.split("/")[2], [])
        if self.reject and body and body.get("assignees"):
            raise urllib.error.HTTPError(path, 422, "invalid assignee", {}, None)
        if method == "POST" and path == "/issues":
            return {"number": 100 + sum(1 for c in self.calls if c[:2] == ("POST", "/issues"))}
        return {}

    def paged(self, path):
        sep = "&" if "?" in path else "?"
        yield from (self.call("GET", f"{path}{sep}per_page=100&page=1") or [])


def _sync(model, gh):
    real = issues.GitHub
    issues.GitHub = lambda repo, token: gh
    try:
        return issues.sync(model, "o/r", "t", dry_run=False)
    finally:
        issues.GitHub = real


def test_issues_assigned_and_overdue_reminder_once(tmp_path):
    edir = copy(tmp_path)
    _owners(edir, {"VP Engineering": ["bob"], "Legal": ["org/legal"]})
    m = load(edir, today=D(2026, 12, 1))  # GAP-01 (due 2026-11-20, VP Engineering) is overdue
    gh = FakeGH()
    log = _sync(m, gh)
    gap01 = next(c for c in gh.calls if c[:2] == ("POST", "/issues") and "[GAP-01]" in c[2]["title"])
    assert gap01[2]["assignees"] == ["bob"]
    legal = next(c for c in gh.calls if c[:2] == ("POST", "/issues") and "[GAP-07]" in c[2]["title"])
    assert "assignees" not in legal[2]  # teams can't be assignees
    reminders = [c for c in gh.calls if c[0] == "POST" and c[1].endswith("/comments")]
    assert any("@bob" in c[2]["body"] and "2026-11-20" in c[2]["body"] for c in reminders)
    # second run: issue exists and already has the reminder -> no new comment
    marker = issues.overdue_marker("GAP-01", "2026-11-20")
    existing = [{"number": 101, "body": "<!-- grc:GAP-01 -->"}]
    gh2 = FakeGH(existing=existing, comments={"101": [{"body": marker}]})
    _sync(m, gh2)
    assert not [c for c in gh2.calls if c[1] == "/issues/101/comments"]


def test_invalid_assignee_falls_back(tmp_path):
    edir = copy(tmp_path)
    _owners(edir, {"VP Engineering": ["ghost"]})
    gh = FakeGH(reject_assignees=True)
    log = _sync(load(edir, today=D(2026, 10, 8)), gh)
    assert any("could not assign ghost" in x for x in log)


# --------------------------------------------------------- evidence linking
def _linking_engagement(tmp_path, owner="Head of Platform"):
    edir = copy(tmp_path)
    (edir / "collectors.yaml").write_text(yaml.safe_dump({"enabled": True, "checks": [
        {"evidence": "EV-150", "title": "Gate runs", "collector": "github.workflow_runs",
         "params": {"repo": "o/r", "workflow": "g.yml"}, "type": "record",
         "supports": ["A.6.2.2:implemented", "A.6.2.4:evidenced", "Z.1:implemented"]}]}))
    p = edir / "controls" / "A.6.2.2.yaml"
    c = yaml.safe_load(p.read_text())
    c["owner"] = owner
    p.write_text("# header kept\n" + yaml.safe_dump(c, sort_keys=False))
    return edir


def _fake_gate(conclusion="success"):
    from grc.collectors import http
    real = http.request
    http.request = lambda *a, **k: {"workflow_runs": [{"conclusion": conclusion}]}
    return lambda: setattr(http, "request", real)


def test_passing_evidence_is_linked_never_verified(tmp_path):
    import os
    os.environ["GH_COLLECTOR_TOKEN"] = "x"
    edir = _linking_engagement(tmp_path)
    restore = _fake_gate()
    try:
        _, report = collect.run(load(edir, today=D(2026, 10, 8)))
    finally:
        restore()
    m = load(edir, today=D(2026, 10, 8))
    leg = m.controls["A.6.2.2"]["test"]["implemented"]
    assert leg["status"] == "partial" and leg["evidence"] == ["EV-150"] and "Auto:" in leg["note"]
    assert (edir / "controls" / "A.6.2.2.yaml").read_text().startswith("# header kept")
    ev = m.controls["A.6.2.4"]["test"]["evidenced"]  # already verified: cited, still verified, not downgraded
    assert ev["status"] == "verified" and "EV-150" in ev["evidence"]
    assert "Linked to controls" in report and "Z.1:implemented" in report
    assert not [f for f in validate(m) if f.severity == "error"]


def test_no_owner_means_cite_only(tmp_path):
    import os
    os.environ["GH_COLLECTOR_TOKEN"] = "x"
    edir = _linking_engagement(tmp_path, owner="")
    restore = _fake_gate()
    try:
        _, report = collect.run(load(edir, today=D(2026, 10, 8)))
    finally:
        restore()
    leg = load(edir).controls["A.6.2.2"]["test"]["implemented"]
    assert leg["status"] == "claimed" and leg["evidence"] == ["EV-150"]  # cited, status untouched
    assert "no owner yet" in report


def test_failing_evidence_is_not_linked(tmp_path):
    import os
    os.environ["GH_COLLECTOR_TOKEN"] = "x"
    edir = _linking_engagement(tmp_path)
    restore = _fake_gate("failure")
    try:
        collect.run(load(edir, today=D(2026, 10, 8)))
    finally:
        restore()
    assert load(edir).controls["A.6.2.2"]["test"]["implemented"]["evidence"] == []


# ------------------------------------------------------------------ sandbox
def _sandbox(tmp_path):
    import grc.model as gm
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root / "engagement")
    sb = root / "sandbox"
    sb.mkdir()
    (sb / "drata.yaml").write_text(yaml.safe_dump({
        "/policies": {"pages": [[{"name": "AI Policy", "status": "ACTIVE", "approvedAt": "2026-09-01", "renewalDate": "2027-09-01"}],
                                [{"name": "Vendor Management Policy", "status": "ACTIVE", "approvedAt": "2026-01-01", "renewalDate": "2026-06-01"}]]},
        "/personnel-search": {"by_param": "aiAwarenessTrainingStatus[]", "responses": {
            "PASS": {"pagination": {"totalCount": 38}}, "FAIL": {"pagination": {"totalCount": 2}}},
            "default": {"pagination": {"totalCount": 0}}}}))
    (sb / "aws.yaml").write_text(yaml.safe_dump({"s3": {"ml": {"encryption": "aws:kms", "versioning": "Enabled",
        "public_access_block": dict.fromkeys(["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"], True)}}}))
    (sb / "ai_draft.json").write_text(json.dumps({"client_overview": [], "ai_usage": [], "scope_statement": "", "in_place": [],
        "inventory": [], "gaps": [], "evidence": [], "claims": [], "open_questions": ["sandbox question"]}))
    e = root / "engagement" / "engagement.yaml"
    e.write_text(e.read_text() + "\nsandbox:\n  enabled: true\n  dir: sandbox\n")
    (root / "engagement" / "collectors.yaml").write_text(yaml.safe_dump({"enabled": True, "checks": [
        {"evidence": "EV-160", "title": "Policies", "collector": "drata.policies", "params": {"names": ["AI Policy", "Vendor Management"]}},
        {"evidence": "EV-161", "title": "Training", "collector": "drata.training", "params": {"min_pass_rate": 0.9}},
        {"evidence": "EV-162", "title": "Bucket", "collector": "aws.s3_bucket", "params": {"bucket": "ml"}}]}))
    return root, lambda: None  # repo root is derived from the engagement directory


def test_sandbox_runs_collectors_without_credentials(tmp_path):
    import os
    os.environ.pop("DRATA_API_KEY", None)
    root, restore = _sandbox(tmp_path)
    try:
        model = load(root / "engagement", today=D(2026, 10, 8))
        results, report = collect.run(model)
    finally:
        restore()
        sandbox._DIR = None
        sandbox._uninstall_cloud_fakes()
    r = {x["evidence"]: x for x in results}
    assert r["EV-160"]["result"] == "fail" and "renewal was due" in " ".join(r["EV-160"]["findings"])  # pages followed
    assert r["EV-161"]["result"] == "pass" and "38/40" in r["EV-161"]["summary"]
    assert r["EV-162"]["result"] == "pass"
    assert "SANDBOX MODE" in report
    snap = json.loads((root / "engagement" / "evidence" / "collected" / "EV-161.json").read_text())
    assert snap["sandbox"] is True
    assert "[SANDBOX]" in (root / "engagement" / "evidence" / "collected.yaml").read_text()


def test_sandbox_ai_draft(tmp_path):
    from grc import ingest
    import docx
    root, restore = _sandbox(tmp_path)
    try:
        e = root / "engagement" / "engagement.yaml"
        e.write_text(e.read_text() + "ingest:\n  ai_drafting: true\n")
        intake = root / "intake"
        intake.mkdir()
        d = docx.Document()
        d.add_paragraph("memo")
        d.save(str(intake / "memo.docx"))
        report = ingest.run(root / "engagement", intake)
    finally:
        restore()
        sandbox._DIR = None
        sandbox._uninstall_cloud_fakes()
    assert "SANDBOX MODE" in report and "sandbox question" in report


def test_failing_check_flags_contradicted_claim(tmp_path):
    import os
    os.environ["GH_COLLECTOR_TOKEN"] = "x"
    edir = copy(tmp_path)
    (edir / "collectors.yaml").write_text(yaml.safe_dump({"enabled": True, "checks": [
        {"evidence": "EV-150", "title": "Gate", "collector": "github.workflow_runs",
         "params": {"repo": "o/r", "workflow": "g.yml"}, "supports": ["A.6.2.2:implemented"]}]}))
    # fixture: A.6.2.2 implemented is 'claimed'
    restore = _fake_gate("failure")
    try:
        _, report = collect.run(load(edir, today=D(2026, 10, 8)))
    finally:
        restore()
    section = report.split("Evidence contradicts a client claim", 1)[1].split("###", 1)[0]
    assert "A.6.2.2·implemented" in section and "EV-150" in section


def test_sandbox_label_only_on_simulated_collectors(tmp_path):
    import os
    os.environ["GH_COLLECTOR_TOKEN"] = "x"
    root, restore = _sandbox(tmp_path)
    (root / "engagement" / "collectors.yaml").write_text(yaml.safe_dump({"enabled": True, "checks": [
        {"evidence": "EV-150", "title": "Gate", "collector": "github.workflow_runs", "params": {"repo": "o/r", "workflow": "g.yml"}},
        {"evidence": "EV-162", "title": "Bucket", "collector": "aws.s3_bucket", "params": {"bucket": "ml"}}]}))
    gate = _fake_gate()
    try:
        collect.run(load(root / "engagement", today=D(2026, 10, 8)))
    finally:
        gate()
        restore()
        sandbox._DIR = None
        sandbox._uninstall_cloud_fakes()
    ev = {e["id"]: e for e in yaml.safe_load((root / "engagement" / "evidence" / "collected.yaml").read_text())["evidence"]}
    assert not ev["EV-150"]["notes"].startswith("[SANDBOX]") and ev["EV-162"]["notes"].startswith("[SANDBOX]")
