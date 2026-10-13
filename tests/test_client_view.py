"""Client view: plain-language progress, dates and requests by owner; no internal economics."""
import datetime as dt
import shutil
from pathlib import Path

import yaml

from grc import client_view, hours, package
from grc.cli import main
from grc.model import load

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)


def setup(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    return edir


def m(edir):
    return load(edir, today=TODAY)


def test_items_by_owner_overdue_first_and_unowned_collapsed(tmp_path):
    edir = setup(tmp_path)
    gaps = yaml.safe_load((edir / "gaps.yaml").read_text())
    gaps["gaps"][0].update(owner="CTO", due="2026-09-01", status="open")
    gaps["gaps"][1].update(status="risk_accepted")
    (edir / "gaps.yaml").write_text(yaml.safe_dump(gaps, sort_keys=False))
    for rid in ("5.2", "A.6.2.5"):
        p = edir / "controls" / f"{rid}.yaml"
        d = yaml.safe_load(p.read_text())
        d["owner"] = ""
        d["test"] = {k: {"status": "not_started", "evidence": []} for k in ("documented", "implemented", "evidenced", "tested")}
        p.write_text(yaml.safe_dump(d, sort_keys=False))
    its = client_view.items(m(edir))
    assert its[0]["overdue"] and its[0]["ref"] == gaps["gaps"][0]["id"]
    assert gaps["gaps"][1]["id"] not in {i["ref"] for i in its}
    unowned = [i for i in its if i["kind"] == "Requirements"]
    assert len(unowned) == 1 and unowned[0]["owner"] == client_view.UNASSIGNED and "without an owner" in unowned[0]["ref"]
    assert "5.2 " in unowned[0]["ask"][1] and "A.6.2.5 " in unowned[0]["ask"][1]
    assert not [i for i in its if i["kind"] == "Requirement" and i["owner"] == client_view.UNASSIGNED]
    owned = [i for i in its if i["kind"] == "Requirement"]
    assert owned and all(any(a.startswith(("Documented", "In use", "Records", "Tested")) for a in i["ask"]) for i in owned)


def test_html_is_self_contained_escaped_and_excludes_internal_numbers(tmp_path):
    edir = setup(tmp_path)
    gaps = yaml.safe_load((edir / "gaps.yaml").read_text())
    gaps["gaps"][0].update(owner="CTO", finding='<script>alert(1)</script> & "quotes"', status="open")
    (edir / "gaps.yaml").write_text(yaml.safe_dump(gaps, sort_keys=False))
    (edir / "hours.yaml").write_text("entries: []\n")
    hours.log_entry(m(edir), 7, "interviews", "ana", on=TODAY - dt.timedelta(days=1))
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["client_view"] = {"intro": "Weekly status for the AIMS working group.", "contact": "Bernard (engagement lead)"}
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out), "--no-docx"]) == 0
    page = (out / "client-view.html").read_text()
    assert "<script>alert(1)" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "default-src 'none'" in page and "http" not in page.split("<script>")[0].replace("http-equiv", "")
    assert "Weekly status for the AIMS working group." in page and "Bernard (engagement lead)" in page
    for internal in ("hours", "budget:", "hours_total", "W10", "E00", "working rule"):
        assert internal.lower() not in page.lower(), internal
    md = (out / "client-view.md").read_text()
    assert "## What we need from you" in md and "## Coming up" in md
    assert "Client view" in (out / "README.md").read_text()


def test_client_view_is_not_in_the_auditor_package(tmp_path):
    edir = setup(tmp_path)
    package.build(m(edir), tmp_path / "dist")
    root = next(p for p in (tmp_path / "dist").iterdir() if p.is_dir())
    assert not list(root.rglob("client-view*"))


def test_milestones_are_future_and_sorted(tmp_path):
    ms = client_view.milestones(m(setup(tmp_path)))
    assert ms == sorted(ms) and all(d >= TODAY for d, _ in ms)


# ---------------------------------------------------------------- review regressions
def _set(edir, rid, owner="CTO", **legs):
    p = edir / "controls" / f"{rid}.yaml"
    d = yaml.safe_load(p.read_text())
    d["owner"] = owner
    for k, (st, ev) in legs.items():
        d["test"][k] = {"status": st, "evidence": ev}
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_partial_legs_never_drop_a_requirement(tmp_path):
    edir = setup(tmp_path)
    ev = yaml.safe_load((edir / "evidence" / "index.yaml").read_text())["evidence"][0]["id"]
    _set(edir, "7.4", implemented=("partial", [ev]))
    its = [i for i in client_view.items(m(edir)) if i["ref"] == "7.4"]
    assert its and any("being reviewed" in a for a in its[0]["ask"])


def test_lapsed_document_milestones_and_markdown_escaping(tmp_path):
    from grc import documents
    edir = setup(tmp_path)
    documents.new(m(edir), "DOC-AI-POLICY", mode="templates")
    md_, body, _ = documents.parse((edir / "documents" / "DOC-AI-POLICY.md").read_text())
    (edir / "documents" / "DOC-AI-POLICY.md").write_text(documents.dump({**md_, "status": "approved", "approved_on": "2024-01-01"}, body))
    _set(edir, "5.2", owner="CTO")
    asks = [a for i in client_view.items(m(edir)) if i["ref"] == "5.2" for a in i["ask"]]
    assert any("due for review" in a for a in asks) and not any("complete and approve" in a for a in asks)
    ms = client_view.milestones(load(edir, today=dt.date(2026, 1, 1)))
    assert any("Stage 1" in t for _, t in ms) and any("Stage 2" in t for _, t in ms)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["client"]["name"] = "Acme | Co\n# Not a title"
    eng["client_view"] = {"contact": "<img src=https://evil.example/x.png>"}
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    _set(edir, "5.3", owner="Ops | Team\n## injected")
    out = client_view.render_md(m(edir), tmp_path / "cv.md").read_text()
    assert "<img" not in out and "\n# Not a title" not in out and "\n## injected" not in out and "Acme \\| Co" in out


def test_owner_case_is_merged_and_review_action_not_duplicated(tmp_path):
    edir = setup(tmp_path)
    _set(edir, "5.2", owner="CTO")
    _set(edir, "5.3", owner="cto")
    owners = {i["owner"] for i in client_view.items(m(edir)) if i["ref"] in ("5.2", "5.3")}
    assert len(owners) == 1
