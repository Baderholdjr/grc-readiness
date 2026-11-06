"""HIPAA (Security Rule and Breach Notification Rule): catalog, categories, wording, documents, mappings."""
import collections
import datetime as dt
import json
import re

import yaml

from grc import documents
from grc.cli import main
from grc.model import ENGINE, load
from grc.rules import leg_effective, validate

FW = ENGINE / "frameworks" / "hipaa"
TODAY = dt.date(2026, 11, 20)
OTHER_WORDS = re.compile(r"Annex A|Stage [12]|Statement of Applicability|\bISMS\b|\bAIMS\b|certification body|clause 9\.\d|"
                         r"Trust Services|[Ss]ervice auditor|[Oo]bservation period")


def codes(m):
    return [f.code for f in validate(m)]


def _new(tmp_path, categories="breach", name="engagement-hipaa"):
    root = tmp_path / "repo"
    edir = root / name
    args = ["--engagement", str(edir), "new-engagement", "--client", "Calloway Clinics", "--start", "2026-11-09",
            "--stage1", "2027-03-15", "--stage2", "2027-05-03", "--framework", "hipaa",
            "--intake", str(root / ("intake" + name[len("engagement"):])), "--confirm-reset"]
    if categories:
        args[-1:-1] = ["--categories", categories]
    assert main(args) == 0
    return edir


def _set(edir, rid, **kw):
    p = edir / "controls" / f"{rid}.yaml"
    d = yaml.safe_load(p.read_text())
    d.update(kw)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


# ------------------------------------------------------------------ catalog and playbook
def test_catalog_follows_the_rule():
    cat = yaml.safe_load((FW / "catalog.yaml").read_text())
    reqs = cat["requirements"]
    ids = [r["id"] for r in reqs]
    assert len(ids) == len(set(ids)) == 74
    kinds = collections.Counter(r["kind"] for r in reqs)
    # the Security Rule's 22 standards plus 164.306(a)/(e) and 7 Breach Notification sections; its 36
    # implementation specifications in 164.308-312 (14 required, 22 addressable) plus 7 required in 164.314/316
    assert kinds == {"standard": 31, "required": 21, "addressable": 22}
    spec = [r for r in reqs if r["id"].split("(")[0] in ("164.308", "164.310", "164.312") and r["kind"] != "standard"]
    assert collections.Counter(r["kind"] for r in spec) == {"required": 14, "addressable": 22}
    assert {r["category"] for r in reqs} == {"security", "breach", "clearinghouse", "group_health_plan", "government"}
    groups = {g["id"] for g in cat["groups"]}
    assert all(r["group"] in groups and r["intent"] and r["evidence_examples"] for r in reqs)
    assert cat["kinds"]["addressable"]["mandatory"] is False and cat["kinds"]["required"]["mandatory"] is True
    assert all(re.fullmatch(r"164\.\d{3}(\([a-z0-9A-Z]+\))*", i) for i in ids)


def test_document_library_covers_every_requirement_once():
    cat = yaml.safe_load((FW / "catalog.yaml").read_text())
    pb = yaml.safe_load((FW / "playbook.yaml").read_text())
    lib = pb["documents"]["library"]
    covered = collections.Counter(r for e in lib for r in e["satisfies"])
    assert set(covered) == {r["id"] for r in cat["requirements"]} and set(covered.values()) == {1}
    cats = {r["id"]: r["category"] for r in cat["requirements"]}
    for e in lib:
        assert len({cats[r] for r in e["satisfies"]}) == 1, e["id"]
        text = (FW / "documents" / e["template"]).read_text()
        heads = re.findall(r"^## (.+)$", text, re.M)
        assert [h for h in heads if h in e["sections"]] == e["sections"], e["id"]
        assert not OTHER_WORDS.search(text), e["template"]
    for key in ("internal_audit_ref", "corrective_ref", "review_ref", "record_control_ref", "scope_ref",
                "objectives_ref", "risk_ref"):
        assert pb["terms"][key] in cats, key
    assert pb["impact_assessment"]["required_for_kinds"] == []


# ------------------------------------------------------------------ an engagement end to end
def test_new_hipaa_engagement_validates_builds_and_speaks_hipaa(tmp_path):
    edir = _new(tmp_path)
    m = load(edir, today=TODAY)
    assert m.categories_in_scope == {"security", "breach"}
    assert len(m.controls) == 70 and not m.uses_impact_assessments and m.system_abbrev == "ePHI environment"
    assert not m.is_applicable("164.308(a)(4)(ii)(A)") and m.is_applicable("164.404")
    assert (edir / "controls" / "164.308(a)(1)(ii)(A).yaml").exists()
    assert codes(m) == ["W140"]
    assert "164.308(a)(8)" in (edir / "audit" / "program.yaml").read_text()

    documents.new(m, "all", mode="templates")
    drafted = sorted(p.stem for p in (edir / "documents").glob("DOC-*.md"))
    assert len(drafted) == 14 and "DOC-HIPAA-BREACH" in drafted and "DOC-HIPAA-GHP" not in drafted
    assert all("{{" not in (edir / "documents" / f"{d}.md").read_text() for d in drafted)

    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    soa = (out / "soa.md").read_text()
    assert soa.startswith("# Calloway Clinics — Security Rule Applicability and Addressable Decisions")
    assert "| 164.312(a)(2)(iv) | Encryption and decryption | Yes |" in soa
    assert "| 164.308(a)(1)(ii)(A) |" not in soa                 # required: never an applicability decision
    matrix = (out / "control-matrix.md").read_text()
    assert "## TEC 164.312 Technical safeguards" in matrix and "| 164.308(a)(1)(ii)(A) | Risk analysis |" in matrix
    for f in ("soa.md", "control-matrix.md", "brief.md", "client-view.md", "internal-audit.md", "README.md"):
        assert not OTHER_WORDS.search((out / f).read_text()), f
    cv = (out / "client-view.md").read_text()
    assert "Readiness assessment" in cv and "Independent assessment" in cv
    assert "HIPAA Security Rule readiness and gap closure" in (out / "brief.md").read_text()

    site = tmp_path / "site"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "portal", "--out", str(site), "--repo", "a/b"]) == 0
    data = json.loads((site / "public" / "portal.json").read_text())
    assert any(g["term"] == "Required and addressable" for g in data["frameworks"][0]["glossary"])

    dist = tmp_path / "dist"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "package", "--out", str(dist)]) == 0
    idx = next(dist.glob("*/00-auditor-index.md")).read_text()
    assert "| Independent HIPAA assessor | TBD |" in idx and not OTHER_WORDS.search(idx)


def test_addressable_needs_a_documented_decision_and_required_cannot_be_dropped(tmp_path):
    edir = _new(tmp_path)
    _set(edir, "164.312(a)(2)(iv)", applicable=False)
    e4 = [f for f in validate(load(edir, today=TODAY)) if f.code == "E004"]
    assert len(e4) == 1 and "164.312(a)(2)(iv)" in e4[0].message
    _set(edir, "164.312(a)(2)(iv)", applicable=False,
         justification="Not reasonable for the legacy lab analyser; equivalent measure: isolated VLAN, physical lock, "
                       "replacement by 2027-06 (risk RA-14).")
    m = load(edir, today=TODAY)
    assert "E004" not in codes(m) and not m.is_applicable("164.312(a)(2)(iv)")
    # a required specification can't be excluded, justification or not
    _set(edir, "164.312(a)(2)(i)", applicable=False, justification="We share accounts.")
    e4 = [f.message for f in validate(load(edir, today=TODAY)) if f.code == "E004"]
    assert e4 == ["Required implementation specification 164.312(a)(2)(i) is mandatory and cannot be excluded."]


def test_categories_drop_out_of_scope_requirements(tmp_path):
    edir = _new(tmp_path, categories=None)
    m = load(edir, today=TODAY)
    assert m.categories_in_scope == {"security"} and not m.is_applicable("164.404") and len(m.controls) == 63


# ------------------------------------------------------------------ mappings, references, collectors
def test_mappings_name_real_requirements_and_share_evidence_only_when_reviewed(tmp_path):
    cat = {r["id"] for r in yaml.safe_load((FW / "catalog.yaml").read_text())["requirements"]}
    for other in ("iso27001", "soc2"):
        src = yaml.safe_load((ENGINE / "mappings" / f"hipaa__{other}.yaml").read_text())
        ids = {r["id"] for r in yaml.safe_load((ENGINE / "frameworks" / other / "catalog.yaml").read_text())["requirements"]}
        assert src["frameworks"] == ["hipaa", other]
        assert all(m["hipaa"] in cat and m[other] in ids and not m["reviewed_by"] for m in src["mappings"])
        assert {m["relationship"] for m in src["mappings"]} <= {"equivalent", "subset", "superset", "related"}

    eh = _new(tmp_path)
    root = eh.parent
    e27 = root / "engagement"
    assert main(["--engagement", str(e27), "new-engagement", "--client", "Calloway Clinics", "--start", "2026-11-09",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--framework", "iso27001",
                 "--intake", str(root / "intake"), "--confirm-reset"]) == 0
    (e27 / "evidence" / "index.yaml").write_text(yaml.safe_dump({"evidence": [
        {"id": "EV-001", "title": "Backup configuration and restore report", "type": "record", "location": "drive://x",
         "collected": "2026-11-01", "approved_by": "CTO", "approved_on": "2026-11-01", "valid_for_days": 365}]}))
    q = e27 / "controls" / "A.8.13.yaml"
    d = yaml.safe_load(q.read_text())
    d["owner"] = "CTO"
    d["test"]["implemented"] = {"status": "verified", "evidence": ["EV-001"]}
    q.write_text(yaml.safe_dump(d, sort_keys=False))
    p = eh / "controls" / "164.308(a)(7)(ii)(A).yaml"
    d = yaml.safe_load(p.read_text())
    d["owner"] = "CTO"
    d["test"]["implemented"] = {"status": "verified", "evidence": ["iso27001:EV-001"]}
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert "E080" in codes(load(eh, today=TODAY))                   # proposed only
    src = yaml.safe_load((ENGINE / "mappings" / "hipaa__iso27001.yaml").read_text())
    for mp in src["mappings"]:
        if (mp["hipaa"], mp["iso27001"]) == ("164.308(a)(7)(ii)(A)", "A.8.13"):
            mp.update(reviewed_by="Bernard Aderhold", reviewed_on="2026-11-05")
    (root / "mappings").mkdir()
    (root / "mappings" / "hipaa__iso27001.yaml").write_text(yaml.safe_dump(src, sort_keys=False))
    m = load(eh, today=TODAY)
    assert "E080" not in codes(m)
    assert leg_effective(m, m.controls["164.308(a)(7)(ii)(A)"]["test"]["implemented"]) == "verified"


def test_timesheets_and_collectors_accept_hipaa_ids(tmp_path):
    from grc.hours import HIPAA_REF
    assert HIPAA_REF.findall("164.308(a)(1)(ii)(A) risk analysis; 164.312(b) logging, 164.402.") == [
        "164.308(a)(1)(ii)(A)", "164.312(b)", "164.402"]
    text = (ENGINE / "schemas" / "collectors.schema.json").read_text()
    pat = re.compile(re.search(r'"pattern": "(\^\[0-9A-Za-z\.\(\)\]\+:[^"]+)"', text).group(1).replace("\\\\", "\\"))
    assert pat.match("164.312(a)(2)(iv):implemented") and pat.match("CC8.1:implemented")


def test_program_layer_maps_to_hipaa(tmp_path):
    from grc import program as P
    edir = _new(tmp_path, name="engagement")
    root = edir.parent
    (root / "program").mkdir()
    (root / "program" / "controls.yaml").write_text(yaml.safe_dump({"controls": [
        {"id": "CTL-BKP", "title": "Backups", "owner": "CTO",
         "maps": {"hipaa": ["164.308(a)(7)(ii)(A)"], "nist80053": ["CP-9"]}}]}))
    prog = P.load_program(root, today=TODAY)
    assert not [f for f in P.validate(prog) if f.code == "P104"]
    assert {c["framework"]: c["covered"] for c in P.coverage(prog)}["hipaa"] == 1
