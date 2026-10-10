"""Policies and procedures (5.2, 7.5; the Documented leg)."""
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml

from grc import documents
from grc.cli import main
from grc.model import load, resource
from grc.render_md import render_all
from grc.rules import metrics, validate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)


def setup(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    (edir / "inventory.yaml").write_text(yaml.safe_dump({"items": [
        {"id": "INV-001", "name": "Triage chatbot", "kind": "ai_system", "owner": "Data Scientist", "risk_tier": "High"},
        {"id": "INV-002", "name": "Azure OpenAI", "kind": "supplier_service", "owner": "CTO"}]}))
    return edir


def m(edir, today=TODAY):
    return load(edir, today=today)


def findings(edir, today=TODAY, code=None, severity=None):
    return [f for f in validate(m(edir, today)) if (code is None or f.code == code) and (severity is None or f.severity == severity)]


def path(edir, did="DOC-AI-POLICY"):
    return edir / "documents" / f"{did}.md"


def edit(edir, did="DOC-AI-POLICY", meta=None, body=None):
    p = path(edir, did)
    md, b, err = documents.parse(p.read_text())
    assert err is None
    if meta:
        meta(md)
    if body:
        b = body(b)
    p.write_text(documents.dump(md, b))


def complete(edir, did="DOC-AI-POLICY"):
    """Resolve every TODO and set owner/author, as the analyst would."""
    edit(edir, did, meta=lambda d: d.update(owner="CTO", author="Engagement Lead"),
         body=lambda b: documents.TODO.sub("Decided", b))


def approved(tmp_path, did="DOC-AI-POLICY"):
    edir = setup(tmp_path)
    documents.new(m(edir), did, mode="templates")
    complete(edir, did)
    documents.approve(m(edir), did, "Chief Executive Officer")
    return edir


def cite(edir, rid="5.2", did="DOC-AI-POLICY", status="verified"):
    p = edir / "controls" / f"{rid}.yaml"
    d = yaml.safe_load(p.read_text())
    d["test"]["documented"] = {"status": status, "evidence": [did]}
    p.write_text(yaml.safe_dump(d, sort_keys=False))


# ---------------------------------------------------------------- library and templates
def test_library_covers_every_requirement_once_and_templates_have_sections(tmp_path):
    model = m(setup(tmp_path))
    lib = documents.config(model)["library"]
    covered = [r for e in lib for r in e["satisfies"]]
    assert sorted(covered) == sorted(r["id"] for r in model.requirements)
    ctx = documents.context(model)
    for e in lib:
        text = resource(model.root, "frameworks", "iso42001", "documents", e["template"]).read_text()
        assert not set(documents.PLACEHOLDER.findall(text)) - set(ctx) - {"title", "doc_id"}, e["id"]
        body = documents.render_template(text, {**ctx, "title": e["title"]})
        assert not [s for s in e["sections"] if s.casefold() not in documents.headings(body)], e["id"]


def test_new_all_drafts_every_document_once(tmp_path):
    edir = setup(tmp_path)
    assert findings(edir, code="W140")
    log = documents.new(m(edir), "all", mode="templates")
    assert len([l for l in log if l.startswith("DOC-")]) == 17
    assert not findings(edir, code="W140") and len(findings(edir, code="W141")) == 17
    assert not findings(edir, severity="error")
    text = path(edir, "DOC-IMPACT").read_text()
    assert "Triage chatbot" in text and "every 180 days" in text and "{{" not in text
    assert "Azure OpenAI" in path(edir, "DOC-THIRDPARTY").read_text()
    meta, _, _ = documents.parse(path(edir, "DOC-AI-POLICY").read_text())
    assert meta["status"] == "draft" and meta["satisfies"][:2] == ["5.1", "5.2"]
    before = path(edir).read_text()
    assert all("already exists" in l for l in documents.new(m(edir), "all", mode="templates"))
    assert path(edir).read_text() == before
    try:
        documents.new(m(edir), "DOC-NOPE")
        raise AssertionError
    except ValueError as exc:
        assert "not in the document library" in str(exc)


# ---------------------------------------------------------------- approval
def test_approve_refuses_incomplete_documents(tmp_path):
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-AI-POLICY", mode="templates")
    for fix, msg in ((None, "unresolved [[TODO]]"),):
        try:
            documents.approve(m(edir), "DOC-AI-POLICY", "CEO")
            raise AssertionError
        except ValueError as exc:
            assert msg in str(exc) and "no author" in str(exc)
    complete(edir)
    for approver in ("Engagement Lead", "engagement lead"):
        try:
            documents.approve(m(edir), "DOC-AI-POLICY", approver)
            raise AssertionError
        except ValueError as exc:
            assert "is the author" in str(exc)
    edit(edir, body=lambda b: b.replace("## Commitments", "## Promises"))
    try:
        documents.approve(m(edir), "DOC-AI-POLICY", "CEO")
        raise AssertionError
    except ValueError as exc:
        assert "missing section(s): Commitments" in str(exc)
    try:
        documents.approve(m(edir), "DOC-AI-POLICY", "CEO", on=TODAY + dt.timedelta(days=3))
        raise AssertionError
    except ValueError as exc:
        assert "future" in str(exc)


def test_approved_document_is_documented_evidence(tmp_path):
    edir = approved(tmp_path)
    meta, body, _ = documents.parse(path(edir).read_text())
    assert meta["status"] == "approved" and meta["approved_hash"] == documents.fingerprint(documents.coerce(meta), body)
    assert meta["history"][0]["approver"] == "Chief Executive Officer"
    assert documents.is_effective(m(edir), "DOC-AI-POLICY")
    w143 = findings(edir, code="W143")
    assert w143 and "5.2" in w143[0].message
    cite(edir)
    assert not findings(edir, severity="error")
    assert "5.2" not in findings(edir, code="W143")[0].message
    assert metrics(m(edir))["docs_approved"] == 1


def test_changing_approved_text_is_caught(tmp_path):
    edir = approved(tmp_path)
    cite(edir)
    edit(edir, body=lambda b: b.replace("Accountability", "Accountability (mostly)"))
    assert any("changed after approval" in f.message for f in findings(edir, code="E042"))
    assert any("DOC-AI-POLICY" in f.message for f in findings(edir, code="E015"))
    # whitespace-only changes don't count
    edir2 = approved(tmp_path / "b")
    edit(edir2, body=lambda b: b.replace("\n", "   \n"))
    assert not findings(edir2, code="E042")


def test_marking_approved_by_hand_is_caught(tmp_path):
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-AI-POLICY", mode="templates")
    complete(edir)
    edit(edir, meta=lambda d: d.update(status="approved", approver="CEO", approved_on="2026-10-01"))
    assert any("without an approval fingerprint" in f.message for f in findings(edir, code="E042"))
    cite(edir)
    assert findings(edir, code="E015")


def test_reapproval_needs_a_new_version(tmp_path):
    edir = approved(tmp_path)
    edit(edir, meta=lambda d: d.update(status="draft"), body=lambda b: b + "\nAdded clause.\n")
    try:
        documents.approve(m(edir), "DOC-AI-POLICY", "CEO")
        raise AssertionError
    except ValueError as exc:
        assert "bump `version`" in str(exc)
    edit(edir, meta=lambda d: d.update(version="1.1"))
    documents.approve(m(edir), "DOC-AI-POLICY", "CEO")
    meta, _, _ = documents.parse(path(edir).read_text())
    assert [h["version"] for h in meta["history"]] == ["0.1", "1.1"]
    assert not findings(edir, severity="error")


def test_review_cycle_and_explicit_next_review(tmp_path):
    edir = approved(tmp_path)
    cite(edir)
    later = TODAY + dt.timedelta(days=400)
    assert findings(edir, today=later, code="W142") and findings(edir, today=later, code="E007")
    edit(edir, meta=lambda d: d.update(next_review="2099-01-01"))
    meta, _, _ = documents.parse(path(edir).read_text())
    assert documents.next_review(m(edir), meta) == TODAY + dt.timedelta(days=365)


def test_draft_document_cannot_close_a_gap_or_finding(tmp_path):
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-AI-POLICY", mode="templates")
    gaps = yaml.safe_load((edir / "gaps.yaml").read_text())
    gaps["gaps"][0].update(status="closed", closure_evidence=["DOC-AI-POLICY"])
    (edir / "gaps.yaml").write_text(yaml.safe_dump(gaps, sort_keys=False))
    assert any("DOC-AI-POLICY" in f.message for f in findings(edir, code="E013"))
    (edir / "findings.yaml").write_text(yaml.safe_dump({"findings": [{
        "id": "OFI-001", "source": "other", "grade": "ofi", "description": "t", "requirement": "5.2",
        "status": "open", "raised_on": "2026-09-01", "evidence": ["DOC-AI-POLICY"]}]}))
    assert any("document DOC-AI-POLICY" in f.message for f in findings(edir, code="E024"))


def test_malformed_documents_are_reported_not_fatal(tmp_path):
    edir = setup(tmp_path)
    (edir / "documents").mkdir()
    (edir / "documents" / "DOC-BAD.md").write_text("# no front matter\n")
    (edir / "documents" / "DOC-WORSE.md").write_text("---\n- a list\n---\nbody\n")
    (edir / "documents" / "DOC-ODD.md").write_text("---\nid: DOC-OTHER\ntitle: x\nkind: policy\nversion: 1\nstatus: weird\n"
                                                    "satisfies: [9.9]\n---\nbody\n")
    fs = findings(edir)
    assert {f.ref for f in fs if f.code == "E001"} >= {"DOC-BAD", "DOC-WORSE", "DOC-ODD"}
    assert any("satisfies unknown requirement 9.9" in f.message for f in fs if f.code == "E040")
    assert any("its id is 'DOC-OTHER'" in f.message for f in fs if f.code == "E040")
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out), "--force"]) == 0


# ---------------------------------------------------------------- AI fill
def _transport(fills, questions=()):
    seen = {}

    def t(body):
        seen["body"] = body
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(
            {"fills": fills, "open_questions": list(questions)})}]}
    return t, seen


def test_ai_fill_only_replaces_markers_and_sanitises(tmp_path):
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-AI-POLICY", mode="templates")
    before = path(edir).read_text()
    n = len(documents.todos(before))
    t, seen = _transport([
        {"n": 1, "text": "Information Security Policy | v4", "source": "intake/isp.pdf"},   # table cell: pipe neutralised
        {"n": 2, "text": "## Injected heading\nline two [[TODO]] {{client}}", "source": "engagement"},
        {"n": 3, "text": "No source given", "source": ""},                                 # dropped
        {"n": 999, "text": "Out of range", "source": "engagement"},                       # ignored
    ], ["Who decides precedence?"])
    log = documents.fill(m(edir), ["DOC-AI-POLICY"], transport=t)
    after = path(edir).read_text()
    assert "AI filled 2 of" in log[0] and any("Who decides" in l for l in log)
    assert "Information Security Policy / v4" in after
    assert "Injected heading line two TODO client" in after and "## Injected" not in after
    assert len(documents.todos(after)) == n - 2
    # everything outside the markers is unchanged
    strip = lambda s: documents.TODO.sub("", s.split("---\n", 2)[2])
    assert re.sub(r"Information Security Policy / v4|Injected heading line two TODO client", "", strip(after)) == strip(before)
    assert "[[TODO#1:" in seen["body"]["messages"][0]["content"]
    assert after.split("---\n", 2)[1] == before.split("---\n", 2)[1]   # front matter byte-for-byte unchanged


def test_ai_fill_never_touches_approved_documents(tmp_path):
    edir = approved(tmp_path)
    before = path(edir).read_text()
    t, _ = _transport([{"n": 1, "text": "x", "source": "engagement"}])
    log = documents.fill(m(edir), ["DOC-AI-POLICY"], transport=t)
    assert "only drafts are filled" in log[0] and path(edir).read_text() == before


def test_sandbox_fill_uses_canned_file(tmp_path):
    edir = setup(tmp_path)
    sb = tmp_path / "sandbox"
    sb.mkdir()
    (sb / "ai_docs.json").write_text(json.dumps({"DOC-USE": {"fills": [{"n": 1, "text": "No PHI in unapproved tools", "source": "engagement"}],
                                                            "open_questions": []}}))
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["sandbox"] = {"enabled": True, "dir": "sandbox"}
    eng["ingest"] = {"ai_drafting": True}
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    log = documents.new(m(edir), "DOC-USE", mode="auto")
    assert any("[SANDBOX] AI filled 1" in l for l in log)
    assert "No PHI in unapproved tools" in path(edir, "DOC-USE").read_text()


def test_fill_without_ai_enabled(tmp_path):
    edir = setup(tmp_path)
    log = documents.new(m(edir), "DOC-USE", mode="auto")
    assert any("templates only" in l for l in log)
    assert main(["--engagement", str(edir), "docs", "fill", "DOC-USE"]) == 2


# ---------------------------------------------------------------- reports
def test_reports_and_word_files_are_reproducible(tmp_path):
    edir = approved(tmp_path)
    documents.new(m(edir), "DOC-USE", mode="templates")
    digests = []
    for run in ("a", "b"):
        out = tmp_path / run
        assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out)]) == 0
        digests.append(hashlib.sha256((out / "doc-DOC-AI-POLICY.docx").read_bytes()).hexdigest())
    out = tmp_path / "a"
    reg = (out / "documents.md").read_text()
    assert "DOC-AI-POLICY" in reg and "not started" in reg and "approved ✅" in reg
    assert "DRAFT" in (out / "doc-DOC-USE.md").read_text()
    assert (out / "doc-DOC-USE.docx").exists() and digests[0] == digests[1]
    assert "Policies and procedures" in (out / "README.md").read_text()


def test_cli_approve(tmp_path):
    edir = setup(tmp_path)
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "docs", "new", "DOC-IMPROVE", "--mode", "templates"]) == 0
    edit(edir, "DOC-IMPROVE", meta=lambda d: d.update(owner="CTO", author="Analyst"))
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "docs", "approve", "DOC-IMPROVE"]) == 2
    rep = tmp_path / "r.md"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "docs", "approve", "DOC-IMPROVE",
                 "--approver", "CEO", "--report", str(rep)]) == 0
    assert "approved by CEO" in rep.read_text()


# ---------------------------------------------------------------- review regressions
def test_front_matter_edits_after_approval_are_caught(tmp_path):
    edir = approved(tmp_path)
    cite(edir)
    for change in (lambda d: d.update(approved_on="2026-10-07"), lambda d: d.update(approver="Someone Else"),
                   lambda d: d.update(satisfies=["5.2", "9.3"]), lambda d: d.update(title="Different"),
                   lambda d: d.update(version="9.9")):
        edir2 = approved(tmp_path / str(id(change)))
        cite(edir2)
        edit(edir2, meta=change)
        assert findings(edir2, code="E042") and findings(edir2, code="E015")
    # a per-document review cycle is not allowed (it could stretch validity)
    edit(edir, meta=lambda d: d.update(review_every_days=100000))
    assert findings(edir, code="E001")


def test_bad_metadata_in_one_document_does_not_silence_other_checks(tmp_path):
    edir = setup(tmp_path)
    cite(edir, did="EV-999")
    base = {f.code for f in findings(edir, severity="error")}
    assert "E006" in base
    documents.new(m(edir), "DOC-USE", mode="templates")
    edit(edir, "DOC-USE", meta=lambda d: d.update(author=["x"], approver={"a": 1}, approved_on=dt.datetime(2026, 10, 8, 10),
                                                   status="approved", satisfies="A.9.2", history=5))
    codes = {f.code for f in findings(edir, severity="error")}
    assert "E006" in codes and "E001" in codes and "E000" not in codes
    assert not [f for f in findings(edir) if "unknown requirement" in f.message and "DOC-USE" in f.message]
    # approve doesn't crash on malformed history; it reports what's wrong
    try:
        documents.approve(m(edir), "DOC-USE", "CEO")
    except ValueError:
        pass
    (edir / "documents" / "DOC-BIN.md").write_bytes(b"\xff\xfe\x00bad")
    (edir / "documents" / "DOC-NULL.md").write_text("﻿---\nid: DOC-NULL\ntitle: t\nkind: policy\nversion: 1.10\nstatus: null\n---\nx\n")
    fs = findings(edir)
    assert {"DOC-BIN", "DOC-NULL"} <= {f.ref for f in fs if f.code == "E001"}
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(tmp_path / "o"), "--force"]) == 0


def test_unclosed_or_odd_markers(tmp_path):
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-AI-POLICY", mode="templates")
    edit(edir, body=lambda b: b.replace("## Commitments", "Owner: [[TODO: name\n\n## Commitments", 1))
    t, _ = _transport([{"n": i, "text": "x", "source": "engagement"} for i in range(1, 60)])
    documents.fill(m(edir), ["DOC-AI-POLICY"], transport=t)
    assert "## Commitments" in path(edir).read_text()
    edir2 = setup(tmp_path / "b")
    documents.new(m(edir2), "DOC-AI-POLICY", mode="templates")
    complete(edir2)
    for odd in ("[[TODO - decide]]", "[[todo: x]]", "[[ something ]]"):
        edit(edir2, body=lambda b, o=odd: b + f"\n{o}\n")
        try:
            documents.approve(m(edir2), "DOC-AI-POLICY", "CEO")
            raise AssertionError(odd)
        except ValueError as exc:
            assert "unresolved" in str(exc)
        edit(edir2, body=lambda b, o=odd: b.replace(f"\n{o}\n", ""))


def test_fill_text_cannot_inject_markup(tmp_path):
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-USE", mode="templates")
    edit(edir, "DOC-USE", body=lambda b: b + "\n[[TODO: line start]]\n\n[[TODO: another]]\n\n# comment kept\n")
    raw = path(edir, "DOC-USE").read_text().replace("status: draft", "status: draft  # keep me", 1)
    path(edir, "DOC-USE").write_text(raw)
    n = len(documents.todos(documents.parse(raw)[1]))
    t, _ = _transport([{"n": 1, "text": "ok [{{[TODO: x]{{] and {[[{client}]]} <!-- `code`", "source": 5},
                       {"n": n - 1, "text": "```text", "source": "engagement"},
                       {"n": n, "text": "1. numbered", "source": "engagement"}])
    documents.fill(m(edir), ["DOC-USE"], transport=t)
    after = path(edir, "DOC-USE").read_text()
    assert "status: draft  # keep me" in after                       # front matter untouched
    assert "ok TODO: x and client !-- code" in after and "{{" not in after.split("---", 2)[2]
    assert "```" not in after and "\ntext\n" in after
    assert "\n1\\. numbered\n" in after


def test_periodic_reapproval_and_stale_next_review(tmp_path):
    edir = approved(tmp_path)
    edit(edir, meta=lambda d: d.update(next_review="2026-12-01"))
    later = dt.date(2027, 3, 1)
    assert not documents.is_effective(m(edir, later), "DOC-AI-POLICY")
    log = documents.approve(m(edir, later), "DOC-AI-POLICY", "CEO")   # same version, same text: periodic review
    assert "approved by CEO" in log[0]
    meta, _, _ = documents.parse(path(edir).read_text())
    assert "next_review" not in meta and len(meta["history"]) == 2
    assert documents.is_effective(m(edir, later), "DOC-AI-POLICY")
    assert "not due for review" in documents.approve(m(edir, later), "DOC-AI-POLICY", "CEO")[0]


def test_draft_word_file_is_the_same_on_different_days(tmp_path):
    from grc.render_docx import render_document
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-USE", mode="templates")
    a = render_document(m(edir, TODAY), "DOC-USE", tmp_path / "a.docx").read_bytes()
    b = render_document(m(edir, TODAY + dt.timedelta(days=1)), "DOC-USE", tmp_path / "b.docx").read_bytes()
    assert a == b
