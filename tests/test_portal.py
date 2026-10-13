"""Client site: data built from the record, answers recorded as reviewed submissions, Worker behaviour."""
import datetime as dt
import json
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest
import yaml

from grc import portal
from grc.cli import main
from grc.model import load
from grc.rules import validate

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
TODAY = dt.date(2026, 10, 8)
NODE = shutil.which("node")


def setup(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    return edir


def m(edir, today=TODAY):
    return load(edir, today=today)


def open_gap(edir, **kw):
    gaps = yaml.safe_load((edir / "gaps.yaml").read_text())
    gaps["gaps"][0].update(status="open", owner="CTO", **kw)
    (edir / "gaps.yaml").write_text(yaml.safe_dump(gaps, sort_keys=False))
    return gaps["gaps"][0]["id"]


def gap_request(model, gid):
    return next(r for f in portal.data(model)["frameworks"] for r in f["requests"] if r["ref"] == gid)


def write_sub(edir, sid="SUB-20261001-abcdef", **over):
    model = m(edir)
    gid = next(g["id"] for g in model.gaps if g.get("status") in ("open", "in_progress"))
    req = gap_request(model, gid)
    sub = {"id": sid, "request": {"key": req["key"], "kind": "Gap", "ref": gid, "title": req["title"], "framework": "iso42001"},
           "submitted_by": "jane@client.example", "submitted_at": "2026-10-01T10:00:00Z", "answer": "Policy is on SharePoint.",
           "links": ["https://sp.example/p"], "no_sensitive_data": True, "status": "received"}
    sub.update(over)
    (edir / "submissions").mkdir(exist_ok=True)
    (edir / "submissions" / f"{sid}.yaml").write_text(yaml.safe_dump(sub, sort_keys=False))
    return sub


def codes(model):
    return [f.code for f in validate(model)]


# ------------------------------------------------------------------ data
def test_data_is_plain_language_and_leaves_out_internal_numbers(tmp_path):
    edir = setup(tmp_path)
    gid = open_gap(edir, due="2026-09-01")
    d = portal.data(m(edir))
    text = json.dumps(d)
    for internal in ("hours_total", "hours_used", "budget", "W1", "E0"):
        assert internal not in text
    f = d["frameworks"][0]
    assert f["key"] == "iso42001" and f["applicable"] > 0 and f["areas"]
    r = gap_request(m(edir), gid)
    assert r["overdue"] and r["action"] and r["answerable"] and r["why"]
    agg = [x for x in f["requests"] if x["kind"] == "Requirements"]
    assert all(not x["answerable"] and not x["action"] for x in agg)
    assert f["requests"][0]["overdue"]          # overdue first
    assert {"phases", "stages", "upcoming"} <= set(f["path"])
    assert not any(u["text"].startswith("Phase starts") for u in f["path"]["upcoming"])


def test_request_keys_are_stable_and_distinct(tmp_path):
    edir = setup(tmp_path)
    open_gap(edir)
    a = [r["key"] for r in portal.data(m(edir))["frameworks"][0]["requests"]]
    b = [r["key"] for r in portal.data(m(edir, TODAY + dt.timedelta(days=3)))["frameworks"][0]["requests"]]
    assert a == b and len(set(a)) == len(a)
    assert portal.request_key("iso42001", "Gap", "GAP-01") != portal.request_key("iso27001", "Gap", "GAP-01")


def test_submission_status_reaches_the_site(tmp_path):
    edir = setup(tmp_path)
    gid = open_gap(edir)
    write_sub(edir, status="needs_more", note="Please link the approved version.", reviewed_by="Bernard")
    write_sub(edir, sid="SUB-20260901-000001", submitted_at="2026-09-01T10:00:00Z", status="withdrawn", reviewed_by="B")   # older one is ignored
    r = gap_request(m(edir), gid)
    assert r["submission"] == {"status": "needs_more", "at": "2026-10-01", "note": "Please link the approved version."}
    assert "W171" not in codes(m(edir))


def test_several_frameworks_become_tabs(tmp_path):
    edir = setup(tmp_path)
    other = tmp_path / "second" / "engagement"
    shutil.copytree(FIXTURE, other)
    out = tmp_path / "site"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "portal", "--out", str(out), "--repo", "acme/x",
                 "--also", str(other)]) == 0
    d = json.loads((out / "public" / "portal.json").read_text())
    assert len(d["frameworks"]) == 2


# ------------------------------------------------------------------ rules
def test_submission_rules(tmp_path):
    edir = setup(tmp_path)
    open_gap(edir)
    write_sub(edir)
    assert "W171" in codes(m(edir))                                    # waiting 7 days > 5
    assert "W171" not in codes(m(edir, dt.date(2026, 10, 3)))
    write_sub(edir, status="accepted", reviewed_by="Bernard", evidence=["EV-999"])
    c = codes(m(edir))
    assert "W172" in c and "W171" not in c
    write_sub(edir, id="SUB-20261001-000000")
    assert "E070" in codes(m(edir))


def test_submission_schema_guards(tmp_path):
    edir = setup(tmp_path)
    open_gap(edir)
    for over in ({"status": "needs_more", "reviewed_by": "B"},              # needs a note for the client
                 {"status": "accepted"},                                     # needs reviewed_by
                 {"status": "verified"},
                 {"no_sensitive_data": False},
                 {"links": ["http://insecure.example"]},
                 {"answer": "x" * 4001},
                 {"submitted_by": "not-an-email"}):
        shutil.rmtree(edir / "submissions", ignore_errors=True)
        write_sub(edir, **over)
        assert "E001" in codes(m(edir)), over
    shutil.rmtree(edir / "submissions")
    (edir / "submissions").mkdir()
    (edir / "submissions" / "SUB-20261001-badbad.yaml").write_text("id: [unclosed\n")
    assert "E001" in codes(m(edir))


def test_closed_request_is_noted(tmp_path):
    edir = setup(tmp_path)
    open_gap(edir)
    write_sub(edir)
    gaps = yaml.safe_load((edir / "gaps.yaml").read_text())
    gaps["gaps"][0]["status"] = "risk_accepted"
    (edir / "gaps.yaml").write_text(yaml.safe_dump(gaps, sort_keys=False))
    assert "W170" in codes(m(edir))


# ------------------------------------------------------------------ bundle
def test_bundle_and_wrangler_config(tmp_path):
    edir = setup(tmp_path)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["client"]["name"] = 'Acme "Quote" \\ Health (fictional)'
    eng["portal"] = {"enabled": True, "access_team": "acme-grc", "access_aud": "f" * 64, "allowed_email_domains": ["acme.example"]}
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    assert "E001" not in codes(m(edir))
    out = tmp_path / "site"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "portal", "--out", str(out), "--repo", "acme/client"]) == 0
    for f in ("public/index.html", "public/app.js", "public/app.css", "public/portal.json", "worker.js", "wrangler.toml"):
        assert (out / f).is_file(), f
    cfg = tomllib.loads((out / "wrangler.toml").read_text())
    assert cfg["name"] == "grc-portal-acme-quote-health"
    assert cfg["assets"]["run_worker_first"] is True
    assert cfg["vars"]["ACCESS_TEAM"] == "acme-grc" and cfg["vars"]["ALLOWED_EMAIL_DOMAINS"] == "acme.example"
    assert cfg["vars"]["GITHUB_REPO"] == "acme/client"
    html = (out / "public" / "index.html").read_text()
    assert "http" not in html.replace("http-equiv", "")          # no third-party resources
    js = (out / "public" / "app.js").read_text()
    assert "innerHTML" not in js and "eval(" not in js


def test_portal_settings_are_validated(tmp_path):
    edir = setup(tmp_path)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["portal"] = {"access_aud": "not-hex", "worker_name": "Bad Name"}
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    assert codes(m(edir)).count("E001") >= 2


# ------------------------------------------------------------------ Worker (Node)
@pytest.mark.skipif(not NODE, reason="node not installed")
def test_worker_unit_tests():
    r = subprocess.run([NODE, "--test", str(ROOT / "tests" / "portal" / "worker.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_worker_yaml_passes_the_engine_schema(tmp_path):
    """What the Worker writes, with hostile text, loads and validates in the engine."""
    edir = setup(tmp_path)
    gid = open_gap(edir)
    req = gap_request(m(edir), gid)
    script = tmp_path / "gen.mjs"
    script.write_text(f"""
import {{ loadWorker }} from {json.dumps((ROOT / 'tests' / 'portal' / 'harness.mjs').as_uri())};
const W = await loadWorker();
const nasty = 'a\\r\\nb\\u2028"q" \\\\ \\u0000\\u202E x\\ud800 😀\\nstatus: accepted\\n--- \\n# c';
process.stdout.write(W.submissionYaml({{ id: "SUB-20261007-0a0b0c", request: {{ key: {json.dumps(req['key'])}, kind: "Gap",
  ref: {json.dumps(gid)}, title: W.cleanText('Title: with "colon"', 300), framework: "iso42001" }},
  submitted_by: "o'neil@client.example", submitted_at: "2026-10-07T09:08:07Z",
  answer: W.cleanText(nasty, 4000), links: [W.cleanLink("https://x.example/a?b='1'&c=\\"2\\"")] }}));
""")
    r = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    (edir / "submissions").mkdir()
    (edir / "submissions" / "SUB-20261007-0a0b0c.yaml").write_text(r.stdout, encoding="utf-8")
    model = m(edir)
    s = model.submissions["SUB-20261007-0a0b0c"]
    assert s["status"] == "received" and s["answer"].startswith('a\nb\n"q" \\') and "😀" in s["answer"]
    assert "status: accepted" in s["answer"]       # stayed inside the answer
    assert not [f for f in validate(model) if f.severity == "error"], [f.message for f in validate(model) if f.severity == "error"]
    assert gap_request(model, gid)["submission"]["status"] == "received"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_browser_end_to_end(tmp_path):
    """Sign in, open a request, send an answer; the pull request's file validates in the engine."""
    sync_api = pytest.importorskip("playwright.sync_api")
    edir = setup(tmp_path)
    gid = open_gap(edir, due="2026-10-30")
    out = tmp_path / "site"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "portal", "--out", str(out), "--repo", "acme/client-repo"]) == 0
    port, state = _free_port(), tmp_path / "gh.json"
    srv = subprocess.Popen([NODE, str(ROOT / "tests" / "portal" / "harness.mjs"), "serve", str(out), str(port), "jane@client.example", str(state)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    errors = []
    try:
        for _ in range(50):
            if state.exists():
                break
            time.sleep(0.1)
        with sync_api.sync_playwright() as p:
            try:
                b = p.chromium.launch()
            except Exception as exc:  # no browser available here
                pytest.skip(f"chromium unavailable: {exc}")
            pg = b.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://localhost:{port}/")
            pg.wait_for_selector("h1")
            assert "Stage 1" in pg.inner_text("h1") or "readiness" in pg.inner_text("h1")
            assert "jane@client.example" in pg.inner_text("#me")
            pg.goto(f"http://localhost:{port}/#/request/{gap_request(m(edir), gid)['key']}")
            pg.fill("#ans", "Policy v1 on SharePoint")
            pg.click("button.primary")
            assert "patient" in pg.inner_text(".msg")          # must confirm no personal data first
            pg.check("#nophi")
            pg.click("button.primary")
            pg.wait_for_selector(".done-panel")
            pg.goto(f"http://localhost:{port}/#/requests")
            pg.click("text=Sent")
            assert "Sent, waiting for review" in pg.inner_text("main")
            b.close()
    finally:
        srv.terminate()
    assert not errors, errors
    files = json.loads(state.read_text())["files"]
    assert len(files) == 1
    (name, text), = files.items()
    sid = name.rsplit("/", 1)[1][:-5]
    (edir / "submissions").mkdir()
    (edir / "submissions" / f"{sid}.yaml").write_text(text)
    model = m(edir)
    assert not [f for f in validate(model) if f.severity == "error"]
    assert model.submissions[sid]["submitted_by"] == "jane@client.example"


def test_analyst_report_lists_waiting_first_and_stays_out_of_the_auditor_package(tmp_path):
    from grc import package
    edir = setup(tmp_path)
    open_gap(edir)
    write_sub(edir, sid="SUB-20261002-aaaaaa", status="accepted", reviewed_by="B", submitted_at="2026-10-02T00:00:00Z")
    write_sub(edir, sid="SUB-20261001-bbbbbb")
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "build", "--out", str(out), "--no-docx", "--force"]) == 0
    text = (out / "submissions.md").read_text()
    assert text.index("SUB-20261001-bbbbbb") < text.index("SUB-20261002-aaaaaa") and "1 waiting" in text
    assert "submissions.md" in (out / "README.md").read_text()
    assert "submissions.md" in package.SKIP


def test_withdrawn_duplicate_does_not_hide_accepted_answer(tmp_path):
    edir = setup(tmp_path)
    gid = open_gap(edir)
    write_sub(edir, sid="SUB-20261001-aaaaaa", status="accepted", reviewed_by="B")
    write_sub(edir, sid="SUB-20261002-bbbbbb", status="withdrawn", reviewed_by="B", submitted_at="2026-10-02T00:00:00Z")
    assert gap_request(m(edir), gid)["submission"]["status"] == "accepted"


def test_answers_to_a_second_framework_are_read_from_the_main_engagement(tmp_path):
    edir = setup(tmp_path)
    other = tmp_path / "second" / "engagement"
    shutil.copytree(FIXTURE, other)
    eng = yaml.safe_load((other / "engagement.yaml").read_text())
    eng["framework"] = "iso42001b"
    (other / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False))
    shutil.copytree(ROOT / "grc" / "resources" / "frameworks" / "iso42001", tmp_path / "second" / "frameworks" / "iso42001b")
    open_gap(other)
    second = m(other)
    gid = next(g["id"] for g in second.gaps if g.get("status") == "open")
    req = next(r for r in portal.framework_data(second)["requests"] if r["ref"] == gid)
    (edir / "submissions").mkdir()
    (edir / "submissions" / "SUB-20261007-cccccc.yaml").write_text(yaml.safe_dump({
        "id": "SUB-20261007-cccccc", "request": {"key": req["key"], "kind": "Gap", "ref": gid, "framework": "iso42001b"},
        "submitted_by": "a@b.example", "submitted_at": "2026-10-07T00:00:00Z", "answer": "x", "links": [],
        "no_sensitive_data": True, "status": "accepted", "reviewed_by": "B"}))
    d = portal.data(m(edir), [second])
    r2 = next(r for r in d["frameworks"][1]["requests"] if r["ref"] == gid)
    assert r2["submission"]["status"] == "accepted"
    (edir / "submissions" / "SUB-20261007-cccccc.yaml").write_text(
        (edir / "submissions" / "SUB-20261007-cccccc.yaml").read_text().replace("status: accepted", "status: received"))
    assert "W170" not in codes(m(edir))


def test_requirement_request_gets_a_new_key_when_the_ask_changes(tmp_path):
    a = {"kind": "Requirement", "ref": "5.2", "ask": ["Documented: x"]}
    b = {"kind": "Requirement", "ref": "5.2", "ask": ["Records: y"]}
    g = {"kind": "Gap", "ref": "GAP-01", "ask": ["one"]}
    assert portal.item_key("f", a) != portal.item_key("f", b)
    assert portal.item_key("f", g) == portal.item_key("f", dict(g, ask=["changed wording"]))


def test_wrangler_toml_survives_unusual_values(tmp_path):
    edir = setup(tmp_path)
    eng = yaml.safe_load((edir / "engagement.yaml").read_text())
    eng["client"]["name"] = "Café 😀 Health\nInc"
    (edir / "engagement.yaml").write_text(yaml.safe_dump(eng, sort_keys=False, allow_unicode=True))
    cfg = tomllib.loads(portal.wrangler_toml(m(edir), "acme/x 😀"))
    assert cfg["vars"]["GITHUB_REPO"] == "acme/x 😀" and cfg["name"].startswith("grc-portal-caf")


def test_indented_review_lines_get_a_helpful_message(tmp_path):
    edir = setup(tmp_path)
    open_gap(edir)
    write_sub(edir)
    f = edir / "submissions" / "SUB-20261001-abcdef.yaml"
    f.write_text(f.read_text() + "   reviewed_by: B\n   note: x\n")
    msg = [x.message for x in validate(m(edir)) if x.code == "E001"][0]
    assert "line" in msg and "left edge" in msg
