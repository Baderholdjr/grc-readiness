"""Auditor package (PDF exports, auditor index, checksums, reproducible zip)."""
import datetime as dt
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import yaml
from pypdf import PdfReader

from grc import documents, package
from grc.cli import main
from grc.model import load
from grc.render_pdf import inline, render

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)


def setup(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    documents.new(load(edir, today=TODAY), "DOC-USE", mode="templates")
    return edir


def build(edir, out, label="stage1"):
    return package.build(load(edir, today=TODAY), out, label=label)


def test_package_layout_index_and_checksums(tmp_path):
    edir = setup(tmp_path)
    log = build(edir, tmp_path / "dist")
    root = next(p for p in (tmp_path / "dist").iterdir() if p.is_dir())
    assert root.name.endswith("-stage1-2026-10-08")
    for f in ("00-auditor-index.pdf", "00-auditor-index.md", "manifest.json", "SHA256SUMS",
              "02-applicability/soa.pdf", "02-applicability/soa.csv", "02-applicability/control-matrix.pdf",
              "03-documented-information/documents.pdf", "03-documented-information/doc-DOC-USE.pdf",
              "03-documented-information/doc-DOC-USE.docx", "05-evidence/evidence-index.pdf",
              "08-source-record/engagement/engagement.yaml"):
        assert (root / f).exists(), f
    assert not list(root.rglob("README.pdf"))
    # every file listed with a correct checksum
    sums = dict(reversed(line.split("  ", 1)) for line in (root / "SHA256SUMS").read_text().splitlines())
    files = [p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"]
    assert len(sums) == len(files)
    for p in files:
        assert sums[p.relative_to(root).as_posix()] == hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["as_of"] == "2026-10-08" and "02-applicability/soa.pdf" in manifest["files"]
    idx = (root / "00-auditor-index.md").read_text()
    assert "Requirement → evidence traceability" in idx and "| 5.2 |" in idx and "SHA-256" in idx
    text = PdfReader(str(root / "00-auditor-index.pdf")).pages[0].extract_text()
    assert "auditor package" in text and "How to read this package" in text
    assert any("archive:" in l for l in log)


def test_package_is_reproducible(tmp_path):
    edir = setup(tmp_path)
    build(edir, tmp_path / "a")
    build(edir, tmp_path / "b")
    za, zb = next((tmp_path / "a").glob("*.zip")), next((tmp_path / "b").glob("*.zip"))
    assert za.read_bytes() == zb.read_bytes()
    with zipfile.ZipFile(za) as z:
        names = z.namelist()
        assert names == sorted(names) and all(n.startswith(za.stem + "/") for n in names)


def test_cited_evidence_points_into_the_package(tmp_path):
    edir = setup(tmp_path)
    m = load(edir, today=TODAY)
    md, b, _ = documents.parse((edir / "documents" / "DOC-USE.md").read_text())
    (edir / "documents" / "DOC-USE.md").write_text(documents.dump(
        {**md, "owner": "CTO", "author": "Analyst"}, documents.TODO.sub("Decided", b)))
    documents.approve(load(edir, today=TODAY), "DOC-USE", "CEO")
    p = edir / "controls" / "A.9.2.yaml"
    d = yaml.safe_load(p.read_text())
    d["owner"] = "CTO"
    d["test"]["documented"] = {"status": "verified", "evidence": ["DOC-USE"]}
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    build(edir, tmp_path / "dist")
    idx = next((tmp_path / "dist").glob("*/00-auditor-index.md")).read_text()
    assert "verified: DOC-USE" in idx and "03-documented-information/doc-DOC-USE.pdf" in idx


def test_package_refuses_invalid_record(tmp_path):
    edir = setup(tmp_path)
    p = edir / "controls" / "5.2.yaml"
    d = yaml.safe_load(p.read_text())
    d["owner"] = "CTO"
    d["test"]["documented"] = {"status": "verified", "evidence": ["EV-999"]}
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "package", "--out", str(tmp_path / "d")]) == 1
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "package", "--out", str(tmp_path / "d"),
                 "--force", "--label", "../draft x"]) == 0
    root = next(p for p in (tmp_path / "d").iterdir() if p.is_dir())
    assert "-draft-x-" in root.name or "---draft-x-" in root.name   # label sanitised: no path traversal
    assert "E006" in (root / "00-auditor-index.md").read_text()


def test_pdf_renderer_handles_symbols_markup_and_is_deterministic(tmp_path):
    md = ("# Title ✅\n\n> **SANDBOX** banner\n\n| A | B ≥ 12 → x |\n|---|---|\n| `DOC-1` | [link](https://e.x) & <b>raw</b> |\n\n"
          "- one\n  - nested\n1. first\n2. second\n\n```\ncode ⚠️\n```\n\n<details>\n<summary>More</summary>\n\ntext _it_\n")
    a = render(md, tmp_path / "a.pdf", "T", "footer")
    b = render(md, tmp_path / "b.pdf", "T", "footer")
    assert a.read_bytes() == b.read_bytes()
    text = "".join(pg.extract_text() for pg in PdfReader(str(a)).pages)
    assert "[OK]" in text and ">= 12 -> x" in text and "DOC-1" in text
    assert inline("a & b <x> **c**") == "a &amp; b &lt;x&gt; <b>c</b>"


# ---------------------------------------------------------------- review regressions
def test_renderer_survives_hostile_markdown(tmp_path):
    md = ("| A | B |\n|---|---|\n| x | " + "long text " * 600 + " |\n\n"
          "**a _b** c_ and x **[a](https://e.com/**) b** and [**x](https://x.com) y**\n\n"
          "[q](https://x.com/?a=1&b=2) price < 5 and > 3, line<br>break\n")
    out = render(md, tmp_path / "h.pdf", "T", "f")
    text = "".join(pg.extract_text() for pg in PdfReader(str(out)).pages)
    assert "price < 5 and > 3" in text and "truncated in the PDF" in text
    raw = out.read_bytes()
    assert b"a=1&b=2" in raw and b"&amp;amp;" not in raw


def test_tall_cells_split_across_pages(tmp_path):
    import grc.render_pdf as rp
    saved, rp.MAX_CELL = rp.MAX_CELL, 10 ** 6   # no truncation: the row itself must split
    try:
        md = "| A | B |\n|---|---|\n| x | " + "word " * 6000 + " |\n"
        out = render(md, tmp_path / "t.pdf", "T", "f")
        assert len(PdfReader(str(out)).pages) >= 2
    finally:
        rp.MAX_CELL = saved


def test_brief_stays_in_overview_and_manifest_lists_index(tmp_path):
    edir = setup(tmp_path)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["client"]["name"] = "MR Holdings"
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    log = build(edir, tmp_path / "dist")
    root = next(p for p in (tmp_path / "dist").iterdir() if p.is_dir())
    assert (root / "01-overview" / "mr-holdings-iso42001-brief.docx").exists()
    manifest = json.loads((root / "manifest.json").read_text())
    assert "00-auditor-index.pdf" in manifest["files"] and "reportlab" in manifest
    assert (tmp_path / "dist" / f"{root.name}-auditor-index.pdf").exists()
    assert not [p for p in (tmp_path / "dist").iterdir() if p.name.startswith(".")]


def test_source_record_skips_symlinks_and_hidden_files(tmp_path):
    edir = setup(tmp_path)
    (tmp_path / "secret.yaml").write_text("api_key: SUPERSECRET\n")
    (edir / "notes.yaml").symlink_to(tmp_path / "secret.yaml")
    (edir / ".cache").mkdir()
    (edir / ".cache" / "token.json").write_text("{}")
    build(edir, tmp_path / "dist")
    z = next((tmp_path / "dist").glob("*.zip"))
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert not [n for n in names if n.endswith("notes.yaml") or ".cache" in n]
        assert not any(b"SUPERSECRET" in zf.read(n) for n in names)


def test_failed_build_leaves_no_debris(tmp_path):
    import grc.render_pdf as rp
    edir = setup(tmp_path)
    build(edir, tmp_path / "dist")
    before = sorted(p.name for p in (tmp_path / "dist").iterdir())
    orig = rp.render

    def boom(md, out, title, *a, **k):
        if "soa" in str(out):
            raise RuntimeError("layout")
        return orig(md, out, title, *a, **k)
    rp.render = boom
    try:
        try:
            build(edir, tmp_path / "dist")
            raise AssertionError
        except ValueError as exc:
            assert "soa.md" in str(exc)
    finally:
        rp.render = orig
    left = sorted(p.name for p in (tmp_path / "dist").iterdir())
    assert not [n for n in left if n.startswith(".")]
