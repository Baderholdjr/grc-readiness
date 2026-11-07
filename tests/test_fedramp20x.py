"""FedRAMP 20x (FedRAMP Consolidated Rules for 2026): catalog, classes, SHOULD rules, documents, reports."""
import collections
import datetime as dt
import json
import re

import yaml

from grc import documents
from grc.cli import main
from grc.model import ENGINE, load
from grc.render_md import applicability_rows
from grc.rules import validate

FW = ENGINE / "frameworks" / "fedramp20x"
TODAY = dt.date(2026, 11, 20)
OTHER_WORDS = re.compile(r"Annex A|Stage [12]\b|Statement of Applicability|\bISMS\b|\bAIMS\b|certification body|"
                         r"Trust Services|[Ss]ervice auditor|[Oo]bservation period|ePHI|HIPAA|covered entity|business associate|"
                         r"GDPR|TX-RAMP")
ID = re.compile(r"[A-Z]{3}-[A-Z]{3}-[A-Z]{3}")


def _new(tmp_path, categories="class_b,class_c", name="engagement-fedramp"):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / name), "new-engagement", "--client", "Larch & Finch", "--start", "2026-11-09",
            "--stage1", "2027-03-01", "--stage2", "2027-05-01", "--framework", "fedramp20x",
            "--intake", str(root / ("intake" + name[len("engagement"):])), "--confirm-reset"]
    if categories:
        args[-1:-1] = ["--categories", categories]
    assert main(args) == 0
    return root / name


def codes(m):
    return [f.code for f in validate(m)]


def test_catalog_shape():
    cat = yaml.safe_load((FW / "catalog.yaml").read_text())
    reqs = cat["requirements"]
    ids = [r["id"] for r in reqs]
    assert len(ids) == len(set(ids)) == 187 and all(ID.fullmatch(i) for i in ids)
    assert collections.Counter(r["kind"] for r in reqs) == {"rule": 96, "indicator": 46, "recommendation": 45}
    assert collections.Counter(r["category"] for r in reqs) == {"class_b": 116, "core": 57, "class_c": 10, "class_a": 4}
    ksi = [r for r in reqs if r["id"].startswith("KSI-")]
    assert len(ksi) == 46 and {r["kind"] for r in ksi} == {"indicator"}
    assert {r["id"] for r in ksi if r["category"] == "class_c"} == {
        "KSI-CNA-EIS", "KSI-MLA-ALA", "KSI-SVC-PRR", "KSI-SVC-RUD", "KSI-SVC-VCM"}
    assert all(r["intent"] and r["evidence_examples"] and "**" not in r["intent"] for r in reqs)
    assert cat["framework"]["version"] and cat["choose_at_least_one"] == ["class_a", "class_b"]
    # FedRAMP's own NIST SP 800-53 mappings are kept, in the engine's id form
    nist = {str(r["id"]) for r in yaml.safe_load((ENGINE / "reference" / "nist80053.yaml").read_text())["requirements"]}
    assert all(set(r.get("nist80053", [])) <= nist for r in reqs)
    by = {r["id"]: r for r in reqs}
    assert "AC-6" in by["KSI-IAM-ELP"]["nist80053"]
    # per-class timeframes are kept, and classes with the same text share it
    assert "Class C:" in by["VDR-TFR-PDD"]["intent"] and "every 14 days" in by["VDR-TFR-PDD"]["intent"]
    assert "N5: 2 days (internet-reachable and likely exploitable)" in by["VDR-TFR-PVR"]["intent"]
    assert by["IEC-CSO-FIR"]["intent"].startswith("Classes A and B: Providers MUST")


def test_generator_reproduces_the_catalog(tmp_path):
    """The catalog is generated; the generator's own logic is checked on a tiny dataset."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fr20x", ENGINE.parent.parent / "tools" / "fedramp20x.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    d = {"info": {"version": "x", "default_artifacts": {"FRR": ["Explain"], "KSI": ["Measures"]}},
         "FRR": {"ABC": {"info": {"name": "Alpha", "subsets": {"CSO": {}}}, "data": {"all": {"CSO": {
             "ABC-CSO-ONE": {"name": "One", "statement": "Providers MUST do **one**.", "force": "MUST", "affects": ["Providers"],
                             "controls": ["ac-2.3"]},
             "ABC-CSO-TWO": {"name": "Two", "affects": ["Providers"], "varies_by_class": {
                 "a": {"statement": "Providers with Class A Certifications MAY do two.", "force": "MAY"},
                 "b": {"statement": "Providers with Class B Certifications SHOULD do two.", "force": "SHOULD"},
                 "c": {"statement": "Providers with Class C Certifications MUST do two.", "force": "MUST"}}},
             "ABC-CSO-AGY": {"name": "Agencies", "statement": "Agencies MUST x.", "force": "MUST", "affects": ["Agencies"]}}}}},
             "AGU": {"info": {"name": "skip"}, "data": {}}},
         "KSI": {"XYZ": {"name": "Theme", "indicators": {"KSI-XYZ-ONE": {"name": "Ind", "statement": "It is done.",
                                                                          "varies_by_class": {"a": {"statement": "Optional: x"}}}}}}}
    g = gen.generate(d)
    by = {r["id"]: r for r in g["reqs"]}
    assert set(by) == {"ABC-CSO-ONE", "ABC-CSO-TWO", "KSI-XYZ-ONE"}
    assert by["ABC-CSO-ONE"] == {"id": "ABC-CSO-ONE", "kind": "rule", "category": "core", "group": "ABC", "title": "One",
                                      "intent": "Providers MUST do one.", "evidence_examples": ["Explain"], "nist80053": ["AC-2(3)"]}
    assert by["ABC-CSO-TWO"]["kind"] == "rule" and by["ABC-CSO-TWO"]["category"] == "class_c"
    assert by["ABC-CSO-TWO"]["intent"] == "Class B: Providers SHOULD do two. Class C: Providers MUST do two."
    assert by["KSI-XYZ-ONE"]["category"] == "class_b" and by["KSI-XYZ-ONE"]["evidence_examples"] == ["Measures"]


def test_documents_cover_each_requirement_once():
    ids = {r["id"] for r in yaml.safe_load((FW / "catalog.yaml").read_text())["requirements"]}
    pb = yaml.safe_load((FW / "playbook.yaml").read_text())
    lib = pb["documents"]["library"]
    covered = collections.Counter(r for e in lib for r in e["satisfies"])
    assert set(covered) == ids and set(covered.values()) == {1}
    for e in lib:
        text = (FW / "documents" / e["template"]).read_text()
        assert text.splitlines()[0] == "# {{title}}"
        assert re.findall(r"^## (.+)$", text, re.M) == e["sections"], e["id"]
        assert not OTHER_WORDS.search(text), e["template"]
        assert "{{doc_review_days}}" in text
        assert not [r for r in e["satisfies"] if r not in text], e["id"]
    for key in ("internal_audit_ref", "corrective_ref", "review_ref", "record_control_ref", "scope_ref", "objectives_ref", "risk_ref"):
        refs = pb["terms"][key] if isinstance(pb["terms"][key], list) else [pb["terms"][key]]
        assert set(refs) <= ids, key


def test_class_decides_scope(tmp_path):
    m = load(_new(tmp_path / "none", categories=None), today=TODAY)
    assert m.categories_in_scope == {"core"} and len(m.controls) == 57 and "W113" in codes(m)
    m = load(_new(tmp_path / "a", categories="class_a"), today=TODAY)
    assert len(m.controls) == 61 and m.is_applicable("FRC-CLA-MFR") and not m.is_applicable("VDR-CSO-DET")
    assert m.term("scope_ref") == "FRC-CSO-PKG"
    m = load(_new(tmp_path / "b", categories="class_b"), today=TODAY)
    assert len(m.controls) == 173 and not m.is_applicable("KSI-CNA-EIS") and m.term("scope_ref") == "MAS-CSO-IIR"
    e = _new(tmp_path / "c")
    m = load(e, today=TODAY)
    assert len(m.controls) == 183 and m.is_applicable("KSI-CNA-EIS")
    assert [f for f in validate(m) if f.severity == "error"] == [] and "W115" not in codes(m)
    assert '"KSI-CMT-LMC:' in (e / "collectors.yaml").read_text()
    documents.new(m, "all", mode="templates")
    assert len(list((e / "documents").glob("DOC-FR-*.md"))) == 18
    a = load(_new(tmp_path / "a2", categories="class_a"), today=TODAY)
    assert len(documents.library(a)) == 12 and "DOC-FR-TRUST" not in documents.library(a)


def test_class_combinations_are_warned(tmp_path):
    w = [f.message for f in validate(load(_new(tmp_path / "c", categories="class_c"), today=TODAY)) if f.code == "W115"]
    assert w == ["scope.categories: 'class_c' adds to class_b; choose class_b as well, or its requirements are left out."]
    w = [f.message for f in validate(load(_new(tmp_path / "ab", categories="class_a,class_b"), today=TODAY)) if f.code == "W115"]
    assert w == ["scope.categories: 'class_a' can't be combined with class_b; choose one."]


def test_should_rules_can_be_set_aside_with_a_reason_but_must_rules_cannot(tmp_path):
    edir = _new(tmp_path)

    def setc(rid, **kw):
        f = edir / "controls" / f"{rid}.yaml"
        d = yaml.safe_load(f.read_text())
        d.update(kw)
        f.write_text(yaml.safe_dump(d, sort_keys=False))
    setc("SCG-ENH-API", applicable=False, justification="Settings are managed only in the console; risk accepted (SDR-007).")
    setc("VDR-CSO-DET", applicable=False, justification="We scan by hand.")
    setc("KSI-IAM-ELP", applicable=False, justification="Not needed.")
    m = load(edir, today=TODAY)
    e4 = sorted(f.message for f in validate(m) if f.code == "E004")
    assert e4 == ["FedRAMP rule (MUST) VDR-CSO-DET is mandatory and cannot be excluded.",
                  "Key Security Indicator KSI-IAM-ELP is mandatory and cannot be excluded."]
    row = next(r for r in applicability_rows(m) if r[0] == "SCG-ENH-API")
    assert row[2] == "No" and row[3].startswith("Settings are managed")


def test_reports_use_fedramp_terms(tmp_path):
    edir = _new(tmp_path)
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    soa = (out / "soa.md").read_text()
    assert soa.startswith("# Larch & Finch — FedRAMP 20x Applicability Statement")
    matrix = (out / "control-matrix.md").read_text()
    assert "| KSI-IAM-ELP | Ensuring Least Privilege | KSI |" in matrix
    assert "| SCG-ENH-API | API Capability | Should |" in matrix
    for f in ("soa.md", "control-matrix.md", "brief.md", "client-view.md"):
        assert not OTHER_WORDS.search((out / f).read_text()), f


def test_timesheets_find_fedramp_ids():
    from grc.hours import FEDRAMP_REF
    assert FEDRAMP_REF.findall("Wired KSI-IAM-ELP evidence; VDR-TFR-PDD scan cycle; DOC-FR-VULN draft") == ["KSI-IAM-ELP", "VDR-TFR-PDD"]
