"""TX-RAMP (Texas DIR Security Controls Baselines 2.0): catalog, levels, documents, program and NIST mapping."""
import collections
import datetime as dt
import re

import yaml

from grc import documents
from grc import program as P
from grc.cli import main
from grc.model import ENGINE, load
from grc.rules import validate

FW = ENGINE / "frameworks" / "txramp"
TODAY = dt.date(2026, 11, 20)
OTHER_WORDS = re.compile(r"Annex A|Stage [12]|Statement of Applicability|\bISMS\b|\bAIMS\b|certification body|"
                         r"Trust Services|[Ss]ervice auditor|[Oo]bservation period|ePHI|HIPAA")


def _new(tmp_path, categories="level_2", name="engagement-txramp"):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / name), "new-engagement", "--client", "Larch & Finch", "--start", "2026-11-09",
            "--stage1", "2027-03-01", "--stage2", "2027-05-01", "--framework", "txramp",
            "--intake", str(root / ("intake" + name[len("engagement"):])), "--confirm-reset"]
    if categories:
        args[-1:-1] = ["--categories", categories]
    assert main(args) == 0
    return root / name


def test_catalog_is_the_baseline_with_nist_ids():
    cat = yaml.safe_load((FW / "catalog.yaml").read_text())
    reqs = cat["requirements"]
    assert len(reqs) == len({r["id"] for r in reqs}) == 223
    assert collections.Counter(r["category"] for r in reqs) == {"core": 117, "level_2": 106}
    nist = {str(r["id"]) for r in yaml.safe_load((ENGINE / "reference" / "nist80053.yaml").read_text())["requirements"]}
    assert {r["id"] for r in reqs} <= nist
    assert len({r["group"] for r in reqs}) == 17 and all(r["intent"] and r["evidence_examples"] for r in reqs)
    assert {r["id"] for r in reqs if r["category"] == "core"} >= {"AC-1", "AC-2", "IA-2", "RA-5", "SI-2"}


def test_documents_cover_every_control_once_and_refs_exist():
    cat = {r["id"] for r in yaml.safe_load((FW / "catalog.yaml").read_text())["requirements"]}
    pb = yaml.safe_load((FW / "playbook.yaml").read_text())
    lib = pb["documents"]["library"]
    covered = collections.Counter(r for e in lib for r in e["satisfies"])
    assert set(covered) == cat and set(covered.values()) == {1} and len(lib) == 17
    for e in lib:
        text = (FW / "documents" / e["template"]).read_text()
        assert re.findall(r"^## (.+)$", text, re.M) == e["sections"], e["id"]
        assert not OTHER_WORDS.search(text), e["template"]
    for key in ("internal_audit_ref", "corrective_ref", "review_ref", "record_control_ref", "scope_ref",
                "objectives_ref", "risk_ref"):
        assert pb["terms"][key] in cat, key


def test_level_1_and_level_2_records(tmp_path):
    e1 = _new(tmp_path / "l1", categories=None)
    m = load(e1, today=TODAY)
    assert m.categories_in_scope == {"core"} and len(m.controls) == 117
    assert m.is_applicable("AC-2") and not m.is_applicable("AC-2(3)")
    e2 = _new(tmp_path / "l2")
    m = load(e2, today=TODAY)
    assert len(m.controls) == 223 and m.is_applicable("AC-2(3)")
    assert [f.code for f in validate(m) if f.severity == "error"] == []
    documents.new(m, "all", mode="templates")
    assert len(list((e2 / "documents").glob("DOC-TXR-*.md"))) == 17
    out = tmp_path / "out"
    assert main(["--engagement", str(e2), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
    soa = (out / "soa.md").read_text()
    assert soa.startswith("# Larch & Finch — TX-RAMP Control Applicability")
    matrix = (out / "control-matrix.md").read_text()
    assert "| AC-2(3) | Account Management: Disable Accounts | Level 2 |" in matrix
    for f in ("soa.md", "control-matrix.md", "brief.md", "client-view.md"):
        assert not OTHER_WORDS.search((out / f).read_text()), f
    assert "Assessment submission" in (out / "client-view.md").read_text()


def test_a_nist_mapped_program_control_counts_for_txramp(tmp_path):
    edir = _new(tmp_path, name="engagement")
    root = edir.parent
    (root / "program").mkdir()
    (root / "program" / "controls.yaml").write_text(yaml.safe_dump({"controls": [
        {"id": "CTL-ACCT", "title": "Account management", "owner": "IT Lead", "maps": {"nist80053": ["AC-2", "AC-2(3)", "PM-1"]}}]}))
    prog = P.load_program(root, today=TODAY)
    assert prog.control_index["CTL-ACCT"]["maps"]["txramp"] == ["AC-2", "AC-2(3)"]
    assert {c["framework"]: c["covered"] for c in P.coverage(prog)}["txramp"] == 2
    assert not [f for f in P.validate(prog) if f.code == "P104"]


def test_timesheets_find_nist_ids():
    from grc.hours import NIST_REF
    assert NIST_REF.findall("AC-2(3) disable accounts; reviewed RA-5 and SI-2.") == ["AC-2(3)", "RA-5", "SI-2"]
