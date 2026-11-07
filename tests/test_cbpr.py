"""Global CBPR / Global PRP: catalog, certifications, conditional requirements, documents, mappings."""
import collections
import datetime as dt
import re

import yaml

from grc import documents
from grc.cli import main
from grc.model import ENGINE, load
from grc.render_md import applicability_rows
from grc.rules import validate

FW = ENGINE / "frameworks" / "cbpr"
TODAY = dt.date(2026, 11, 20)
OTHER_WORDS = re.compile(r"Annex A|Stage [12]\b|Statement of Applicability|\bISMS\b|\bAIMS\b|certification body|"
                         r"Trust Services|[Ss]ervice auditor|[Oo]bservation period|ePHI|HIPAA|covered entity|business associate|"
                         r"GDPR|TX-RAMP|FedRAMP|data subject|supervisory authority|\bDPO\b")


def _new(tmp_path, categories="cbpr", name="engagement-cbpr"):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / name), "new-engagement", "--client", "Larch & Finch", "--start", "2026-11-09",
            "--stage1", "2027-02-01", "--stage2", "2027-04-01", "--framework", "cbpr",
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
    assert ids == [f"PR{i}" for i in range(1, 58)] + [f"PRP{i}" for i in range(1, 19)]
    assert collections.Counter(r["category"] for r in reqs) == {"cbpr": 57, "prp": 18}
    assert {r["id"] for r in reqs if r["kind"] == "conditional"} == {
        "PR1", "PR3", "PR9", "PR14", "PR15", "PR16", "PR17", "PR18", "PR22", "PR30", "PR31", "PR32", "PR41", "PR42",
        "PR53", "PR54", "PR55", "PR56", "PR57", "PRP8", "PRP15", "PRP16", "PRP17"}
    assert cat["choose_at_least_one"] == ["cbpr", "prp"]
    assert all(r["intent"] and r["evidence_examples"] for r in reqs)
    # the sub-parts the Accountability Agent checks one by one are named in the intent
    by = {r["id"]: r for r in reqs}
    assert all(f"(6{x})" in by["PR6"]["intent"] for x in "abcdef")
    assert all(f"(44{x})" in by["PR44"]["intent"] for x in "abcde")


def test_documents_cover_each_requirement_once_in_one_certification():
    cat = {r["id"]: r["category"] for r in yaml.safe_load((FW / "catalog.yaml").read_text())["requirements"]}
    pb = yaml.safe_load((FW / "playbook.yaml").read_text())
    lib = pb["documents"]["library"]
    covered = collections.Counter(r for e in lib for r in e["satisfies"])
    assert set(covered) == set(cat) and set(covered.values()) == {1}
    for e in lib:
        assert len({cat[r] for r in e["satisfies"]}) == 1, e["id"]
        text = (FW / "documents" / e["template"]).read_text()
        assert text.splitlines()[0] == "# {{title}}"
        assert re.findall(r"^## (.+)$", text, re.M) == e["sections"], e["id"]
        assert not OTHER_WORDS.search(text), e["template"]
        assert "{{doc_review_days}}" in text
        assert not [r for r in e["satisfies"] if not re.search(rf"\b{r}\b", text)], e["id"]
    for key in ("internal_audit_ref", "corrective_ref", "review_ref", "record_control_ref", "scope_ref", "objectives_ref", "risk_ref"):
        ids = pb["terms"][key]
        assert set(ids) <= set(cat) and {cat[i] for i in ids} == {"cbpr", "prp"}, key


def test_certifications_decide_scope(tmp_path):
    m = load(_new(tmp_path / "none", categories=None), today=TODAY)
    assert len(m.controls) == 0 and "W113" in codes(m)
    m = load(_new(tmp_path / "prp", categories="prp"), today=TODAY)
    assert len(m.controls) == 18 and not m.is_applicable("PR44")
    assert m.term("internal_audit_ref") == "PRP11" and m.term("risk_ref") == "PRP2"
    e = _new(tmp_path / "both", categories="cbpr,prp")
    m = load(e, today=TODAY)
    assert len(m.controls) == 75 and m.term("internal_audit_ref") == "PR46"
    assert [f for f in validate(m) if f.severity == "error"] == []
    assert '"PR46:' in (e / "collectors.yaml").read_text()
    documents.new(m, "all", mode="templates")
    assert len(list((e / "documents").glob("DOC-*.md"))) == 16
    c = load(_new(tmp_path / "cbpr"), today=TODAY)
    assert sorted(documents.library(c)) == sorted(d for d in documents.library(m) if d.startswith("DOC-CBPR-"))


def test_conditional_requirements_need_a_reason_and_others_cannot_be_excluded(tmp_path):
    edir = _new(tmp_path)

    def setc(rid, **kw):
        f = edir / "controls" / f"{rid}.yaml"
        d = yaml.safe_load(f.read_text())
        d.update(kw)
        f.write_text(yaml.safe_dump(d, sort_keys=False))
    setc("PR22", applicable=False)
    assert "E004" in codes(load(edir, today=TODAY))
    setc("PR22", applicable=False, justification="No direct marketing: customers are businesses contacted only about their accounts.")
    m = load(edir, today=TODAY)
    assert "E004" not in codes(m)
    row = next(r for r in applicability_rows(m) if r[0] == "PR22")
    assert row[2] == "No" and row[3].startswith("No direct marketing")
    setc("PR44", applicable=False, justification="Nobody asks.")
    e4 = [f.message for f in validate(load(edir, today=TODAY)) if f.code == "E004"]
    assert e4 == ["Program requirement PR44 is mandatory and cannot be excluded."]


def test_reports_use_cbpr_terms(tmp_path):
    edir = _new(tmp_path)
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    soa = (out / "soa.md").read_text()
    assert soa.startswith("# Larch & Finch — Global CBPR Applicability Statement")
    matrix = (out / "control-matrix.md").read_text()
    assert "| PR44 | Access to information | Requirement |" in matrix
    assert "| PR22 | Opting out of direct marketing | Conditional |" in matrix
    for f in ("soa.md", "control-matrix.md", "brief.md", "client-view.md"):
        assert not OTHER_WORDS.search((out / f).read_text()), f


def test_mappings_are_proposed_and_never_equivalent():
    cb = {str(r["id"]) for r in yaml.safe_load((FW / "catalog.yaml").read_text())["requirements"]}
    for other in ("gdpr", "iso27001"):
        data = yaml.safe_load((ENGINE / "mappings" / f"cbpr__{other}.yaml").read_text())
        ids = {str(r["id"]) for r in yaml.safe_load((ENGINE / "frameworks" / other / "catalog.yaml").read_text())["requirements"]}
        assert data["frameworks"] == ["cbpr", other]
        for m in data["mappings"]:
            assert m["cbpr"] in cb and str(m[other]) in ids and m["relationship"] != "equivalent" and not m["reviewed_by"]


def test_timesheets_find_cbpr_ids():
    from grc.hours import CBPR_REF
    assert CBPR_REF.findall("Drafted PR6 statement; PRP17 sub-processor terms; not PR-6 or APR2026") == ["PR6", "PRP17"]
