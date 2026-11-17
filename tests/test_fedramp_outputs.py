"""FedRAMP 20x outputs in FedRAMP's JSON formats: built from the record, validated against FedRAMP's schemas."""
import contextlib
import datetime as dt
import hashlib
import io
import json

import pytest
import yaml

from grc import fedramp
from grc.cli import main
from grc.model import load
from grc.rules import validate

TODAY = dt.date(2026, 11, 20)


def _new(tmp_path, categories="class_b,class_c", fw="fedramp20x"):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / "engagement"), "new-engagement", "--client", "Larch & Finch", "--start", "2026-11-09",
            "--stage1", "2027-03-01", "--stage2", "2027-05-01", "--framework", fw,
            "--intake", str(root / "intake"), "--confirm-reset"]
    if categories:
        args[-1:-1] = ["--categories", categories]
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(args) == 0
    return root / "engagement"


def _model(edir, today=TODAY):
    return load(edir, today=today)


def _write(edir, name, data):
    (edir / "fedramp").mkdir(exist_ok=True)
    (edir / "fedramp" / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))


VULNS = {"vulnerabilities": [
    {"id": "VULN-1", "detected": "2026-10-03T14:20:00Z", "source": "Image scan", "description": "Old OpenSSL in the API image",
     "evaluated": "2026-10-04T09:00:00Z", "internet_reachable": True, "likely_exploitable": False, "rating": 2,
     "next_reduction": {"by": "2026-11-30", "rating": 1}, "reductions": [{"on": "2026-10-20", "rating": 2}]},
    {"id": "VULN-2", "detected": "2026-02-01", "source": "Penetration test", "description": "Legacy cipher on an internal port",
     "evaluated": "2026-02-02", "internet_reachable": False, "likely_exploitable": False, "rating": 1,
     "accepted": {"rationale": "Vendor appliance; replaced in Q2 2027", "on": "2026-09-01"}},
    {"id": "VULN-3", "detected": "2026-03-01", "source": "Bug bounty", "description": "Verbose error page",
     "evaluated": "2026-03-02", "internet_reachable": True, "likely_exploitable": False, "rating": 1},
    {"id": "VULN-4", "detected": "2026-06-01", "source": "Image scan", "description": "Fixed long ago",
     "evaluated": "2026-06-02", "rating": 1, "disposition": "Remediated", "closed": "2026-06-10"},
]}
INCIDENTS = {"incidents": [
    {"id": "INC-1", "description": "Credential stuffing against the login page", "started": "2026-10-10T01:00:00Z",
     "detected": "2026-10-10T01:20:00Z", "source": "WAF alert", "rating": 2, "root_cause": "Reused passwords",
     "resolved": "2026-10-12T08:00:00Z", "lessons": ["Turned on bot protection for login"]},
    {"id": "INC-2", "description": "Suspicious admin login", "detected": "2026-11-18T02:00:00Z"},
]}
CHANGES = {"changes": [
    {"id": "SCN-1", "date": "2026-10-15", "type": "Transformative", "description": "Move to a new cloud region",
     "reason": "Capacity", "plan": {"summary": "Phased move with rollback", "start": "2026-12-01",
                                    "milestones": [{"description": "Pilot tenant moved", "date": "2026-12-10"}]},
     "requirements": ["KSI-CNA-RNT"]},
]}
REPORTS = {"reports": [{"from": "2026-08-01", "to": "2026-10-31", "data_changes": ["Updated the secure configuration guide"],
                        "recommendations": ["Use phishing-resistant MFA for agency administrators"]}]}


def _full(tmp_path):
    edir = _new(tmp_path)
    m = _model(edir)
    fedramp.init(m)
    _write(edir, "vulnerabilities", VULNS)
    _write(edir, "incidents", INCIDENTS)
    _write(edir, "changes", CHANGES)
    _write(edir, "reports", REPORTS)
    return edir


def test_vendored_schemas_are_fedramps_unchanged():
    lines = (fedramp.SCHEMA_DIR / "SHA256SUMS").read_text().split("\n")
    sums = dict(reversed(line.split("  ")) for line in lines if line.strip())
    files = sorted(p.name for p in fedramp.SCHEMA_DIR.glob("*.json"))
    assert sorted(sums) == files and len(files) == 11
    for name in files:
        assert hashlib.sha256((fedramp.SCHEMA_DIR / name).read_bytes()).hexdigest() == sums[name], name
    for kind in fedramp.DOCS:                     # every schema we build against is there and readable
        assert fedramp.schema(kind)["$schema"].endswith("2020-12/schema")


def test_starter_record_exports_every_document_and_each_matches_fedramps_schema(tmp_path):
    edir = _full(tmp_path)
    out = tmp_path / "out"
    written = fedramp.export(_model(edir), out)
    names = [n for n, _, _ in written]
    assert names[:6] == ["certification-package-overview.json", "security-decision-record.json",
                         "ongoing-certification-report-2026-08-01_2026-10-31.json",
                         "vulnerability-detail-report-2026-08-01_2026-10-31.json",
                         "accepted-vulnerability-info-2026-08-01_2026-10-31.json", "historical-vulnerability-activity.json"]
    assert names[6:] == ["incidents/INC-1.json", "incidents/INC-2.json", "significant-changes/SCN-1.json"]
    for n, _, errs in written:
        assert errs == [], n
        doc = json.loads((out / n).read_text())
        assert fedramp.validate(doc) == [], n               # the kind is recognised from the document itself
        md = (out / n).with_suffix(".md").read_text()
        assert "GRC readiness engine" in md and md.startswith("# Example Provider (fictional): ")
    assert main(["fedramp", "validate", *[str(out / n) for n in names]]) == 0


def test_sdr_statuses_come_only_from_verified_legs(tmp_path):
    edir = _full(tmp_path)
    m = _model(edir)
    sdr = fedramp.build_sdr(m, fedramp.load(m)["package"])
    ksi = sdr["keySecurityIndicators"]
    frr = sdr["fedRampRequirements"]
    assert len(ksi) == 46 and len(ksi) + len(frr) == 183          # Class C: every requirement in scope
    assert {k["ksiImplementationStatus"] for k in ksi} == {"Not Implemented"}
    assert all(k["ksiAssessment"] == [] for k in ksi)
    assert sdr["metadata"]["updateSource"].startswith("GRC readiness engine")


def test_ready_indicator_is_implemented_with_its_evidence(tmp_path):
    edir = _full(tmp_path)
    (edir / "evidence" / "index.yaml").write_text(yaml.safe_dump({"evidence": [
        {"id": "EV-901", "title": "Network architecture standard", "type": "document", "location": "https://example.invalid/std",
         "owner": "CISO", "collected": "2026-11-01", "approved_by": "CEO"},
        {"id": "EV-902", "title": "Firewall rule export", "type": "config", "location": "https://example.invalid/fw",
         "owner": "CISO", "collected": "2026-11-01", "sensitivity": "restricted"},
        {"id": "EV-903", "title": "Segmentation test", "type": "test", "location": "https://example.invalid/t",
         "owner": "CISO", "collected": "2026-11-02"}]}, sort_keys=False))
    f = edir / "controls" / "KSI-CNA-RNT.yaml"
    d = yaml.safe_load(f.read_text())
    d["owner"] = "CISO"
    d["implementation"] = "Network traffic is restricted to what each service needs."
    d["test"] = {"documented": {"status": "verified", "evidence": ["EV-901"]},
                 "implemented": {"status": "verified", "evidence": ["EV-902"]},
                 "evidenced": {"status": "verified", "evidence": ["EV-902"]},
                 "tested": {"status": "verified", "evidence": ["EV-903"]}}
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    m = _model(edir, today=dt.date(2026, 11, 9))
    assert [x for x in validate(m) if x.severity == "error"] == []
    k = next(x for x in fedramp.build_sdr(m, fedramp.load(m)["package"])["keySecurityIndicators"] if x["ksiId"] == "KSI-CNA-RNT")
    assert k["ksiImplementationStatus"] == "Implemented"
    assert k["ksiImplementation"] == ["Network traffic is restricted to what each service needs."]
    assert k["ksiAssessment"][0].startswith("Readiness review by the engagement team (not an independent assessment)")
    assert k["ksiTests"] == ["Segmentation test (test)"]
    ev = {e["evidenceDescription"]: e for e in k["ksiEvidence"]}
    assert ev["Network architecture standard"]["evidenceType"] == "Policy"
    assert "evidenceLocation" not in ev["Firewall rule export"]          # restricted: no location shared
    assert ev["Segmentation test"]["evidenceLocation"] == "https://example.invalid/t"


def test_claimed_only_is_not_implemented_and_says_so(tmp_path):
    edir = _full(tmp_path)
    f = edir / "controls" / "KSI-CNA-RNT.yaml"
    d = yaml.safe_load(f.read_text())
    d["owner"] = "CISO"
    d["test"] = {"implemented": {"status": "claimed"}}
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    m = _model(edir)
    k = next(x for x in fedramp.build_sdr(m, fedramp.load(m)["package"])["keySecurityIndicators"] if x["ksiId"] == "KSI-CNA-RNT")
    assert k["ksiImplementationStatus"] == "Not Implemented"
    assert k["ksiValidation"] == ["Implemented: claimed by the provider, not yet verified."]


def test_record_with_errors_is_refused_unless_drafted(tmp_path):
    edir = _full(tmp_path)
    f = edir / "controls" / "KSI-CNA-RNT.yaml"
    d = yaml.safe_load(f.read_text())
    d["test"] = {k: {"status": "verified"} for k in ("documented", "implemented", "evidenced", "tested")}  # no evidence: E005
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    m = _model(edir)
    with pytest.raises(fedramp.FedrampError, match="validation error"):
        fedramp.export(m, tmp_path / "o")
    assert not (tmp_path / "o").exists()
    fedramp.export(m, tmp_path / "o", force=True)
    sdr = json.loads((tmp_path / "o" / "security-decision-record.json").read_text())
    k = next(x for x in sdr["keySecurityIndicators"] if x["ksiId"] == "KSI-CNA-RNT")
    assert k["ksiImplementationStatus"] == "Partially Implemented"     # never Implemented while flagged


def test_vulnerability_reports_split_accepted_and_flag_the_192_day_rule(tmp_path):
    edir = _full(tmp_path)
    m = _model(edir)
    files = fedramp.load(m)
    vulns = json.loads(json.dumps(fedramp.jsonable(files["vulnerabilities"]["vulnerabilities"])))
    pkg = files["package"]
    start, end = dt.date(2026, 8, 1), dt.date(2026, 10, 31)
    vdr = fedramp.build_vdr(m, pkg, vulns, start, end)
    assert [v["providerTrackingId"] for v in vdr["vulnerabilities"]] == ["VULN-1", "VULN-3"]   # VULN-4 closed in June
    v3 = vdr["vulnerabilities"][1]
    assert v3["overdueStatus"]["isOverdue"] is True and "VER-TFR-MAV" in v3["overdueStatus"]["explanation"]
    assert vdr["vulnerabilities"][0]["overdueStatus"] == {"isOverdue": False}
    assert vdr["reportPeriod"] == {"from": "2026-08-01T00:00:00Z", "to": "2026-10-31T23:59:59Z"}
    avi = fedramp.build_avi(m, pkg, vulns, start, end)
    assert [a["vulnerabilityDetail"]["providerTrackingId"] for a in avi["acceptedVulnerabilities"]] == ["VULN-2"]
    hist = fedramp.build_history(m, pkg, vulns)
    assert len(hist["activeVulnerabilities"]) == 3 and len(hist["acceptedVulnerabilities"]) == 1
    w183 = [f for f in validate(m) if f.code == "W183"]
    assert [f.ref for f in w183] == ["VULN-3"]


def test_incident_stage_and_ocr_contents(tmp_path):
    edir = _full(tmp_path)
    out = tmp_path / "o"
    fedramp.export(_model(edir), out)
    inc1 = json.loads((out / "incidents" / "INC-1.json").read_text())
    inc2 = json.loads((out / "incidents" / "INC-2.json").read_text())
    assert inc1["reportType"] == "Final" and inc1["resolvedAt"] == "2026-10-12T08:00:00Z"
    assert inc2["reportType"] == "Initial"
    ocr = json.loads((out / "ongoing-certification-report-2026-08-01_2026-10-31.json").read_text())
    assert ocr["certificationDataChanges"] == ["Updated the secure configuration guide"]
    assert ocr["transformativeChanges"] == ["SCN-1 (2026-10-15): Move to a new cloud region"]
    assert [i["summary"] for i in ocr["reportableIncidents"]["incidents"]] == ["Credential stuffing against the login page"]
    assert ocr["acceptedVulnerabilities"].startswith("1 accepted vulnerability with activity in this period (VULN-2)")
    assert ocr["plannedCertificationDataChanges"]["planningHorizonThrough"] == "2027-01-31"
    cpo = json.loads((out / "certification-package-overview.json").read_text())
    assert cpo["serviceProperties"]["nextOngoingCertificationReportDate"] == "2027-01-31"
    scn = json.loads((out / "significant-changes" / "SCN-1.json").read_text())
    assert scn["changeType"] == "Transformative" and scn["impactedControls"] == ["KSI-CNA-RNT"]


def test_explicit_period(tmp_path):
    edir = _full(tmp_path)
    names = [n for n, _, _ in fedramp.export(_model(edir), tmp_path / "o", dt.date(2026, 11, 1), dt.date(2026, 11, 20))]
    assert "ongoing-certification-report-2026-11-01_2026-11-20.json" in names
    with pytest.raises(fedramp.FedrampError, match="starts"):
        fedramp.export(_model(edir), tmp_path / "p", dt.date(2026, 11, 20), dt.date(2026, 11, 1))


def test_incomplete_package_is_refused_with_what_is_missing(tmp_path):
    edir = _new(tmp_path)
    m = _model(edir)
    with pytest.raises(fedramp.FedrampError, match="package.yaml is missing"):
        fedramp.export(m, tmp_path / "o")
    assert "W182" in [f.code for f in validate(m)]
    fedramp.init(m)
    pkg = yaml.safe_load((edir / "fedramp" / "package.yaml").read_text())
    del pkg["overview_url"]
    pkg["contacts"] = [c for c in pkg["contacts"] if c["type"] != "Sales"]
    _write(edir, "package", pkg)
    m = _model(edir)
    w = [f.message for f in validate(m) if f.code == "W182"]
    assert w and "overview_url" in w[0] and "a Sales contact" in w[0]
    with pytest.raises(fedramp.FedrampError, match="overview_url"):
        fedramp.export(m, tmp_path / "o")


def test_schema_mismatch_writes_nothing(tmp_path, monkeypatch):
    edir = _full(tmp_path)
    monkeypatch.setattr(fedramp, "build_scn", lambda pkg, c: {"certificationPackageOverviewUri": "x", "changeType": "Routine",
                                                               "changeDescription": "d"})
    with pytest.raises(fedramp.FedrampError, match="FedRAMP's schema"):
        fedramp.export(_model(edir), tmp_path / "o")
    assert not (tmp_path / "o").exists()


def test_input_files_are_checked(tmp_path):
    edir = _full(tmp_path)
    data = json.loads(json.dumps(VULNS))
    data["vulnerabilities"].append(dict(data["vulnerabilities"][0]))        # duplicate id
    data["vulnerabilities"][0]["rating"] = 9                                 # out of range
    _write(edir, "vulnerabilities", data)
    ch = json.loads(json.dumps(CHANGES))
    ch["changes"][0]["requirements"] = ["KSI-NOT-REAL"]
    _write(edir, "changes", ch)
    (edir / "fedramp" / "incidents.yaml").write_text("incidents: [\n")       # not YAML
    found = [(f.code, f.message) for f in validate(_model(edir))]
    assert any(c == "E001" and "rating" in msg for c, msg in found)
    assert any(c == "E092" and "VULN-1 appears twice" in msg for c, msg in found)
    assert any(c == "E092" and "KSI-NOT-REAL" in msg for c, msg in found)
    assert any(c == "E001" and "incidents.yaml: not valid YAML" in msg for c, msg in found)


def test_other_frameworks_are_untouched(tmp_path):
    edir = _new(tmp_path, categories=None, fw="soc2")
    m = _model(edir)
    assert not fedramp.applies(m) and fedramp.check(m) == []
    with pytest.raises(fedramp.FedrampError, match="not fedramp20x"):
        fedramp.export(m, tmp_path / "o")


def test_class_a_scope(tmp_path):
    edir = _new(tmp_path, categories="class_a")
    m = _model(edir)
    fedramp.init(m)
    sdr = fedramp.build_sdr(m, fedramp.load(m)["package"])
    assert len(sdr["keySecurityIndicators"]) == 7 and len(sdr["keySecurityIndicators"]) + len(sdr["fedRampRequirements"]) == 44


def test_cli(tmp_path):
    edir = _full(tmp_path)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["--engagement", str(edir), "--today", "2026-11-20", "fedramp", "export", "--out", str(tmp_path / "o")]) == 0
    assert "matches FedRAMP's schema" in out.getvalue()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"changeType": "Routine"}))
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["fedramp", "validate", str(bad)]) == 1
        assert main(["--engagement", str(edir), "fedramp", "init"]) == 0       # nothing to do: files exist


def test_auditor_package_carries_the_20x_documents(tmp_path):
    edir = _full(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["--engagement", str(edir), "--today", "2026-11-20", "package", "--out", str(tmp_path / "dist"),
                     "--label", "stage1"]) == 0
    root = next(p for p in (tmp_path / "dist").iterdir() if p.is_dir())
    assert (root / "10-fedramp20x" / "security-decision-record.json").exists()
    assert (root / "10-fedramp20x" / "security-decision-record.md").exists()
    idx = (root / "00-auditor-index.md").read_text()
    assert "FedRAMP 20x, in FedRAMP's JSON formats" in idx
    sums = (root / "SHA256SUMS").read_text()
    assert "10-fedramp20x/certification-package-overview.json" in sums


def test_auditor_package_says_why_20x_documents_are_missing(tmp_path):
    edir = _new(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["--engagement", str(edir), "--today", "2026-11-20", "package", "--out", str(tmp_path / "dist"),
                     "--label", "stage1"]) == 0
    root = next(p for p in (tmp_path / "dist").iterdir() if p.is_dir())
    assert not (root / "10-fedramp20x").exists()
    assert "FedRAMP 20x JSON documents:** not included: " in (root / "00-auditor-index.md").read_text()
