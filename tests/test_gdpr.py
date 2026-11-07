"""GDPR (Regulation (EU) 2016/679): catalog, roles, conditional obligations, documents, mappings."""
import collections
import datetime as dt
import re

import yaml

from grc import documents
from grc.cli import main
from grc.model import ENGINE, load
from grc.render_md import applicability_rows
from grc.rules import validate

FW = ENGINE / "frameworks" / "gdpr"
TODAY = dt.date(2026, 11, 20)
OTHER_WORDS = re.compile(r"Annex A|Stage [12]\b|Statement of Applicability|\bISMS\b|\bAIMS\b|certification body|"
                         r"Trust Services|[Ss]ervice auditor|[Oo]bservation period|ePHI|HIPAA|covered entity|business associate")


def _new(tmp_path, categories="controller", name="engagement-gdpr"):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / name), "new-engagement", "--client", "Larch & Finch", "--start", "2026-11-09",
            "--stage1", "2027-02-01", "--stage2", "2027-04-01", "--framework", "gdpr",
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
    assert len(ids) == len(set(ids)) == 59 and all(re.fullmatch(r"Art\d{1,2}(\(\d+\))?(\([a-z]\))?", i) for i in ids)
    assert collections.Counter(r["category"] for r in reqs) == {
        "controller": 31, "processor": 10, "core": 7, "transfers": 4, "dpo": 3, "special_categories": 2,
        "children": 1, "representative": 1}
    assert {r["id"] for r in reqs if r["kind"] == "conditional"} == {
        "Art7", "Art20", "Art22", "Art26", "Art36", "Art45", "Art46", "Art49"}
    assert cat["choose_at_least_one"] == ["controller", "processor"]
    assert all(r["intent"] and r["evidence_examples"] for r in reqs)


def test_documents_cover_each_requirement_once_in_one_category():
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
    for key in ("internal_audit_ref", "corrective_ref", "review_ref", "record_control_ref", "scope_ref",
                "objectives_ref", "risk_ref"):
        assert pb["terms"][key] in cat, key
    # the refs the engine leans on (audit, records collector) are in the core, so every client has them
    assert all(cat[pb["terms"][k]] == "core" for k in ("internal_audit_ref", "record_control_ref", "risk_ref"))


def test_roles_decide_scope(tmp_path):
    m = load(_new(tmp_path / "none", categories=None), today=TODAY)
    assert m.categories_in_scope == {"core"} and len(m.controls) == 7 and "W113" in codes(m)
    m = load(_new(tmp_path / "proc", categories="processor"), today=TODAY)
    assert len(m.controls) == 17 and m.is_applicable("Art28(3)(a)") and not m.is_applicable("Art15")
    assert "W113" not in codes(m)
    e = _new(tmp_path / "both", categories="controller,processor,transfers,dpo")
    m = load(e, today=TODAY)
    assert len(m.controls) == 55 and m.is_applicable("Art46") and not m.is_applicable("Art8")
    assert [f for f in validate(m) if f.severity == "error"] == []
    documents.new(m, "all", mode="templates")
    drafted = sorted(p.stem for p in (e / "documents").glob("DOC-GDPR-*.md"))
    assert len(drafted) == 13 and "DOC-GDPR-CHILDREN" not in drafted and "DOC-GDPR-PROCESSOR" in drafted


def test_conditional_obligations_need_a_reason_and_mandatory_ones_cannot_be_excluded(tmp_path):
    edir = _new(tmp_path)

    def setc(rid, **kw):
        f = edir / "controls" / f"{rid}.yaml"
        d = yaml.safe_load(f.read_text())
        d.update(kw)
        f.write_text(yaml.safe_dump(d, sort_keys=False))
    setc("Art22", applicable=False)
    assert "E004" in codes(load(edir, today=TODAY))
    setc("Art22", applicable=False, justification="No decisions are made solely by automated means.")
    m = load(edir, today=TODAY)
    assert "E004" not in codes(m)
    row = next(r for r in applicability_rows(m) if r[0] == "Art22")
    assert row[2] == "No" and row[3].startswith("No decisions")
    setc("Art15", applicable=False, justification="We never get requests.")
    e4 = [f.message for f in validate(load(edir, today=TODAY)) if f.code == "E004"]
    assert e4 == ["Obligation Art15 is mandatory and cannot be excluded."]


def test_reports_use_gdpr_terms(tmp_path):
    edir = _new(tmp_path)
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    soa = (out / "soa.md").read_text()
    assert soa.startswith("# Larch & Finch — GDPR Applicability Statement")
    assert "| Art8 | Child's consent for online services | No | Children is not in the scope" in soa
    matrix = (out / "control-matrix.md").read_text()
    assert "| Art32(1)(a) | Pseudonymisation and encryption | Obligation |" in matrix
    assert "| Art22 | Automated individual decision-making | Conditional |" in matrix
    for f in ("soa.md", "control-matrix.md", "brief.md", "client-view.md"):
        assert not OTHER_WORDS.search((out / f).read_text()), f


def test_mappings_are_proposed_and_never_equivalent():
    for other in ("iso27001", "soc2"):
        data = yaml.safe_load((ENGINE / "mappings" / f"gdpr__{other}.yaml").read_text())
        ids = {str(r["id"]) for r in yaml.safe_load((ENGINE / "frameworks" / other / "catalog.yaml").read_text())["requirements"]}
        gd = {str(r["id"]) for r in yaml.safe_load((FW / "catalog.yaml").read_text())["requirements"]}
        assert data["frameworks"] == ["gdpr", other]
        for m in data["mappings"]:
            assert m["gdpr"] in gd and str(m[other]) in ids and m["relationship"] != "equivalent" and not m["reviewed_by"]


def test_timesheets_find_gdpr_ids():
    from grc.hours import GDPR_REF
    assert GDPR_REF.findall("Drafted Art30(1) ROPA; Art32(1)(a) encryption; see Art 5 later") == ["Art30(1)", "Art32(1)(a)"]
