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
