"""ISO/IEC 27001:2022: catalog, playbook, document library, and a full engagement run end to end."""
import collections
import datetime as dt
import json
import re
from pathlib import Path

import yaml

from grc import client_view, documents, portal, review
from grc.cli import main
from grc.model import ENGINE, load
from grc.rules import validate

FW = ENGINE / "frameworks" / "iso27001"
TODAY = dt.date(2026, 11, 20)


def test_catalog_shape():
    cat = yaml.safe_load((FW / "catalog.yaml").read_text())
    reqs = cat["requirements"]
    kinds = collections.Counter(r["kind"] for r in reqs)
    assert kinds == {"clause": 25, "control": 93}
    groups = collections.Counter(r["group"] for r in reqs if r["kind"] == "control")
    assert groups == {"A.5": 37, "A.6": 8, "A.7": 14, "A.8": 34}
    ids = [r["id"] for r in reqs]
    assert len(set(ids)) == len(ids)
    assert {g["id"] for g in cat["groups"]} >= {r["group"] for r in reqs}
    assert all(r.get("intent") and r.get("evidence_examples") for r in reqs)
    assert cat["framework"]["management_system"].endswith("(ISMS)")


def test_document_library_covers_every_requirement_once_and_templates_have_their_sections():
    cat = yaml.safe_load((FW / "catalog.yaml").read_text())
    pb = yaml.safe_load((FW / "playbook.yaml").read_text())
    lib = pb["documents"]["library"]
    covered = collections.Counter(r for e in lib for r in e["satisfies"])
    assert set(covered) == {r["id"] for r in cat["requirements"]} and set(covered.values()) == {1}
    for e in lib:
        text = (FW / "documents" / e["template"]).read_text()
        heads = re.findall(r"^## (.+)$", text, re.M)
        assert [h for h in heads if h in e["sections"]] == e["sections"], e["id"]
        assert "AIMS" not in text and " AI " not in text, e["template"]
    assert pb["impact_assessment"]["required_for_kinds"] == []


def _new(tmp_path):
    root = tmp_path / "repo"
    edir = root / "engagement-27001"
    assert main(["--engagement", str(edir), "new-engagement", "--client", "Acme Health", "--start", "2026-11-02",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--framework", "iso27001",
                 "--intake", str(root / "intake-27001"), "--confirm-reset"]) == 0
    return edir


def test_new_iso27001_engagement_validates_builds_and_drafts(tmp_path):
    edir = _new(tmp_path)
    m = load(edir, today=TODAY)
    assert m.engagement["framework"] == "iso27001" and len(m.controls) == 118
    assert m.system_abbrev == "ISMS" and not m.uses_impact_assessments
    prog = yaml.safe_load((edir / "audit" / "program.yaml").read_text())["audits"][0]
    assert prog["title"] == "ISO 27001 internal audit - full ISMS" and prog["criteria"][0] == "ISO/IEC 27001:2022"
    assert [f.code for f in validate(m) if f.severity in ("error", "warning")] == ["W140"]

    # the whole document library drafts, with every placeholder filled or marked
    log = documents.new(m, "all", mode="templates")
    assert len(list((edir / "documents").glob("DOC-*.md"))) == 20, log
    for p in (edir / "documents").glob("DOC-*.md"):
        assert "{{" not in p.read_text(), p.name

    # reports, review pack, client view and site carry no AI-specific content
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    brief = (out / "brief.md").read_text()
    assert "## 2. Information and Systems in Scope" in brief and "AI Usage" not in brief
    assert not (out / "impact-assessments.md").exists()
    assert "AI systems" not in (out / "client-view.md").read_text()
    rid = next(iter(review.reviews(load(edir, today=TODAY))))
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "review", "pack", rid]) == 0
    pack = next((edir / "reviews").glob("*-pack.md")).read_text()
    assert "AI " not in pack and "Feedback from interested parties" in pack and "DOC-IS-OBJECTIVES" in pack
    assert all("AI" not in a for _, a in client_view.overview(load(edir, today=TODAY)))
    d = portal.data(load(edir, today=TODAY))
    assert d["frameworks"][0]["name"] == "ISO 27001" and len(d["frameworks"][0]["areas"]) == 11


def test_two_frameworks_in_one_repository_show_as_two_tabs(tmp_path):
    e27 = _new(tmp_path)
    root = e27.parent
    e42 = root / "engagement"
    assert main(["--engagement", str(e42), "new-engagement", "--client", "Acme Health", "--start", "2026-11-02",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--intake", str(root / "intake"), "--confirm-reset"]) == 0
    out = tmp_path / "site"
    assert main(["--engagement", str(e42), "--today", TODAY.isoformat(), "portal", "--out", str(out), "--repo", "a/b",
                 "--also", str(e27)]) == 0
    d = json.loads((out / "public" / "portal.json").read_text())
    assert [f["key"] for f in d["frameworks"]] == ["iso42001", "iso27001"]
    keys = [r["key"] for f in d["frameworks"] for r in f["requests"]]
    assert len(keys) == len(set(keys))


def test_second_record_is_namespaced_in_issues_and_linked_from_reports(tmp_path):
    import os
    from grc import issues
    from grc.model import discover
    e27 = _new(tmp_path)
    root = e27.parent
    e42 = root / "engagement"
    assert main(["--engagement", str(e42), "new-engagement", "--client", "Acme Health", "--start", "2026-11-02",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--intake", str(root / "intake"), "--confirm-reset"]) == 0
    assert [p.name for p in discover(root)] == ["engagement", "engagement-27001"]
    gaps = {"gaps": [{"id": "GAP-01", "area": "Access", "finding": "No access reviews.", "requirements": ["A.5.18"],
                      "owner": "CTO", "due": "2026-12-01", "phase": "governance", "severity": "high", "status": "open"}]}
    (e27 / "gaps.yaml").write_text(yaml.safe_dump(gaps))
    m27 = load(e27, today=TODAY)
    assert m27.namespace == "iso27001" and load(e42).namespace == ""
    it = issues.tracked_items(m27)[0]
    assert it["id"] == "iso27001:GAP-01" and it["gid"] == "GAP-01"
    assert it["title"].startswith("[ISO 27001] [GAP-01]") and "<!-- grc:iso27001:GAP-01 -->" in it["body"]
    assert "`engagement/" not in it["body"]
    out = tmp_path / "out"
    assert main(["--engagement", str(e42), "--today", TODAY.isoformat(), "build", "--out", str(out), "--no-docx"]) == 0
    assert "engagement-27001/README.md" in (out / "README.md").read_text()
    # dispatch workflows pick the record from $GRC_ENGAGEMENT
    old = os.environ.get("GRC_ENGAGEMENT")
    os.environ["GRC_ENGAGEMENT"] = str(e27)
    try:
        assert main(["--today", TODAY.isoformat(), "validate"]) == 0
    finally:
        if old is None:
            os.environ.pop("GRC_ENGAGEMENT")
        else:
            os.environ["GRC_ENGAGEMENT"] = old


def test_record_wide_workflows_loop_over_every_record_and_scripts_parse():
    import shutil
    import subprocess
    wf = Path(__file__).resolve().parent.parent / ".github" / "workflows"
    for name in ("grc-validate.yml", "grc-publish-reports.yml", "grc-collect.yml", "grc-freshness.yml",
                 "grc-sync-issues.yml", "grc-release.yml"):
        assert "python -m grc engagements" in (wf / name).read_text(), name
    for name in ("grc-audit.yml", "grc-docs.yml", "grc-review.yml", "grc-impact.yml", "grc-new-engagement.yml"):
        text = (wf / name).read_text()
        assert "GRC_ENGAGEMENT: ${{ inputs.engagement }}" in text and "engagement(-[a-z0-9]+)?$" in text, name
    bash = shutil.which("bash")
    if not bash:
        return
    for path in wf.glob("grc-*.yml"):
        for job in (yaml.safe_load(path.read_text()).get("jobs") or {}).values():
            for step in job.get("steps") or []:
                if isinstance(step.get("run"), str):
                    script = step["run"].replace("${{", "__").replace("}}", "__")
                    r = subprocess.run([bash, "-n"], input=script, capture_output=True, text=True)
                    assert r.returncode == 0, f"{path.name}: {step.get('name')}: {r.stderr}"


# ------------------------------------------------------------------ cross-framework reuse
def _two_records(tmp_path):
    e27 = _new(tmp_path)
    root = e27.parent
    e42 = root / "engagement"
    assert main(["--engagement", str(e42), "new-engagement", "--client", "Acme Health", "--start", "2026-11-02",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--intake", str(root / "intake"), "--confirm-reset"]) == 0
    (e42 / "evidence" / "index.yaml").write_text(yaml.safe_dump({"evidence": [
        {"id": "EV-001", "title": "Document Control Procedure v2", "type": "document", "location": "sharepoint://dc",
         "collected": "2026-11-01", "approved_by": "COO", "approved_on": "2026-10-30", "valid_for_days": 365}]}))
    return root, e42, e27


def _set_leg(edir, rid, leg, status, evidence, owner="COO"):
    p = edir / "controls" / f"{rid}.yaml"
    d = yaml.safe_load(p.read_text())
    d["owner"] = owner
    d["test"][leg] = {"status": status, "evidence": evidence}
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def _review_mapping(root, rows):
    src = yaml.safe_load((ENGINE / "mappings" / "iso27001__iso42001.yaml").read_text())
    for m in src["mappings"]:
        if (m["iso27001"], m["iso42001"]) in rows:
            m.update(reviewed_by="Bernard Aderhold", reviewed_on="2026-11-03")
    (root / "mappings").mkdir(exist_ok=True)
    (root / "mappings" / "iso27001__iso42001.yaml").write_text(yaml.safe_dump(src, sort_keys=False))


def codes(m):
    return [f.code for f in validate(m)]


def test_evidence_counts_across_records_only_with_a_reviewed_equivalent_mapping(tmp_path):
    root, e42, e27 = _two_records(tmp_path)
    _set_leg(e27, "7.5", "documented", "verified", ["iso42001:EV-001"])
    m27 = load(e27, today=TODAY)
    assert "E080" in codes(m27)                       # engine mapping is only proposed
    _review_mapping(root, {("7.5", "7.5")})
    m27 = load(e27, today=TODAY)
    c = codes(m27)
    assert "E080" not in c and "E006" not in c and "E012" not in c
    from grc.rules import leg_effective
    assert leg_effective(m27, m27.controls["7.5"]["test"]["documented"]) == "verified"
    # a related mapping never lets evidence count twice
    _set_leg(e27, "5.2", "documented", "verified", ["iso42001:EV-001"])
    _review_mapping(root, {("7.5", "7.5"), ("5.2", "5.2")})
    assert any(f.code == "E080" and "5.2" in f.message for f in validate(load(e27, today=TODAY)))
    # expiry still applies to borrowed evidence
    assert "E007" in codes(load(e27, today=dt.date(2027, 12, 1)))


def test_unknown_record_and_bad_mapping_file_are_reported(tmp_path):
    root, e42, e27 = _two_records(tmp_path)
    _set_leg(e27, "7.5", "documented", "verified", ["soc2:EV-001"])
    assert any(f.code == "E080" and "no soc2 record" in f.message for f in validate(load(e27, today=TODAY)))
    (root / "mappings").mkdir()
    (root / "mappings" / "iso27001__iso42001.yaml").write_text(yaml.safe_dump({
        "frameworks": ["iso27001", "iso42001"],
        "mappings": [{"iso27001": "9.9", "iso42001": "7.5", "relationship": "same"}]}))
    c = [f for f in validate(load(e27, today=TODAY)) if f.code == "E081"]
    assert any("9.9" in f.message for f in c) and any("relationship" in f.message for f in c)


def test_reuse_opportunities_report_and_shared_requests(tmp_path):
    root, e42, e27 = _two_records(tmp_path)
    _review_mapping(root, {("7.5", "7.5")})
    _set_leg(e42, "7.5", "documented", "verified", ["EV-001"])
    _set_leg(e27, "7.5", "documented", "not_started", [])
    m27 = load(e27, today=TODAY)
    hint = [f for f in validate(m27) if f.code == "I180"]
    assert hint and "iso42001:EV-001" in hint[0].message
    out = tmp_path / "out27"
    assert main(["--engagement", str(e27), "--today", TODAY.isoformat(), "build", "--out", str(out), "--no-docx"]) == 0
    text = (out / "cross-framework.md").read_text()
    assert "Bernard Aderhold" in text and "proposed" in text
    # both records ask about 7.5: the site shows it once, on the first tab, marked for both
    _set_leg(e42, "7.5", "documented", "not_started", [])
    d = portal.data(load(e42, today=TODAY), [load(e27, today=TODAY)])
    r42 = [r for r in d["frameworks"][0]["requests"] if r["kind"] == "Requirement" and r["ref"] == "7.5"]
    assert r42 and r42[0]["also"] == ["ISO 27001 7.5"]
    assert not [r for r in d["frameworks"][1]["requests"] if r["kind"] == "Requirement" and r["ref"] == "7.5"]
