"""Changes proposed from the client site: what the engine offers, and the Worker's YAML edits checked against
Python's YAML parser and `grc validate` on records the engine itself wrote."""
import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from grc import portal
from grc.cli import main
from grc.model import load
from grc.rules import validate

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
EDIT_JS = (ROOT / "grc" / "resources" / "portal" / "yamledit.js").as_uri()


def _new(tmp_path, fw="soc2", cats=None):
    root = tmp_path / "repo"
    args = ["--engagement", str(root / "engagement"), "new-engagement", "--client", "Larch & Finch", "--start",
            "2026-11-09", "--stage1", "2027-02-01", "--stage2", "2027-06-01", "--framework", fw,
            "--intake", str(root / "intake"), "--confirm-reset"]
    if cats:
        args[-1:-1] = ["--categories", cats]
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(args) == 0
    return root / "engagement"


def test_client_site_offers_only_allowed_changes(tmp_path):
    edir = _new(tmp_path)
    d = portal.data(load(edir))
    assert d["edits"] == ["implementation", "owner_email", "evidence"]
    reqs = [x for a in d["frameworks"][0]["areas"] for x in a["requirements"]]
    assert reqs and all(r["edit"]["path"].startswith("engagement/controls/") and len(r["key"]) == 12 for r in reqs)
    assert len({r["key"] for r in reqs}) == len(reqs)
    assert all(r["edit"] is None for r in d["frameworks"][0]["requests"] if r["kind"] != "Requirement")
    assert d["owners"]["path"] == "engagement/owners.yaml"
    assert [r["role"] for r in d["owners"]["roles"]] == []          # only the engagement lead so far: ours, not offered
    (edir / "owners.yaml").write_text("owners:\n  - role: Engagement Lead\n    github: []\n  - role: Head of IT\n    github: []\n"
                                      "  - role: Platform\n    github: [plat-lead]\n")
    assert [r["role"] for r in portal.data(load(edir))["owners"]["roles"]] == ["Head of IT"]
    f = edir / "engagement.yaml"
    e = yaml.safe_load(f.read_text())
    e.setdefault("portal", {})["edits"] = ["evidence", "status"]           # "status" isn't something the engine allows
    f.write_text(yaml.safe_dump(e, sort_keys=False))
    assert any(x.severity == "error" for x in validate(load(edir)))          # the schema refuses it
    e["portal"]["edits"] = ["evidence"]
    f.write_text(yaml.safe_dump(e, sort_keys=False))
    d = portal.data(load(edir))
    assert d["edits"] == ["evidence"] and d["owners"] is None
    r = d["frameworks"][0]["areas"][0]["requirements"][0]
    assert r["edit"] == {"path": None, "implementation": None, "evidence": True}


def _node(script: str, payload: dict) -> dict:
    r = subprocess.run([NODE, "--input-type=module", "-e", script], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


SCRIPT = f"""
import * as Y from "{EDIT_JS}";
let raw = ""; for await (const c of process.stdin) raw += c;
const p = JSON.parse(raw), out = {{}};
for (const [k, t] of Object.entries(p.controls)) out[k] = Y.setImplementation(t, p.value);
out.owners = {{}};
for (const role of p.roles) out.owners[role] = Y.setOwnerEmail(p.owners, role, "pat@client.example");
out.evidence = Y.addEvidence(p.evidence, {{ title: p.value.slice(0, 60), type: "record", location: "https://x.example/a?b=c#d",
  collected: "2026-11-13", notes: "Added from the client site", requirements: [p.req] }});
process.stdout.write(JSON.stringify(out));
"""

NASTY = 'Line one: "quoted" & \'single\'\n- looks like a list\n  # not a comment\n{not: a map} *anchor &x !tag %pct @at `tick` ✓'


@pytest.mark.skipif(not NODE, reason="node not installed")
@pytest.mark.parametrize("fw,cats", [("soc2", None), ("iso27001", None), ("hipaa", "covered_entity"), ("gdpr", "controller"),
                                     ("fedramp20x", "class_a"), ("iso42001", None)])
def test_edits_parse_back_exactly_and_the_record_still_validates(tmp_path, fw, cats):
    edir = _new(tmp_path, fw, cats)
    m = load(edir)
    before = {f.code for f in validate(m) if f.severity == "error"}
    ctl = {cid: p.read_text() for cid, p in m.control_files.items()}
    roles = [o["role"] for o in m.owners]
    first = next(iter(ctl))
    out = _node(SCRIPT, {"controls": ctl, "value": NASTY, "roles": roles, "owners": (edir / "owners.yaml").read_text(),
                         "evidence": (edir / "evidence" / "index.yaml").read_text(), "req": first})
    for cid, text in ctl.items():
        old, new = yaml.safe_load(text), yaml.safe_load(out[cid])
        assert new.pop("implementation") == NASTY
        old.pop("implementation", None)
        assert new == old, cid                                   # nothing else changed
        assert [ln for ln in text.splitlines() if ln.startswith("#")] == [ln for ln in out[cid].splitlines() if ln.startswith("#")]
    for role, text in out["owners"].items():
        owners = yaml.safe_load(text)["owners"]
        assert [o.get("email") for o in owners if o["role"] == role] == ["pat@client.example"]
        assert [o for o in owners if o["role"] != role] == [o for o in yaml.safe_load((edir / "owners.yaml").read_text())["owners"] if o["role"] != role]
    ev_old = yaml.safe_load((edir / "evidence" / "index.yaml").read_text())["evidence"] or []
    ev_new = yaml.safe_load(out["evidence"]["text"])["evidence"]
    assert ev_new[:-1] == ev_old and ev_new[-1]["id"] == out["evidence"]["id"] and ev_new[-1]["requirements"] == [first]
    # write them all back: the record still loads and validates with no new errors
    for cid, p in m.control_files.items():
        p.write_text(out[cid])
    (edir / "owners.yaml").write_text(out["owners"][roles[0]])
    (edir / "evidence" / "index.yaml").write_text(out["evidence"]["text"])
    after = {f.code for f in validate(load(edir)) if f.severity == "error"}
    assert after <= before, after - before


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_edit_worker_unit_tests():
    r = subprocess.run([NODE, "--test", str(ROOT / "tests" / "portal" / "edit.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_change_pages_in_a_browser(tmp_path):
    import socket
    import time
    sync_api = pytest.importorskip("playwright.sync_api")
    edir = _new(tmp_path)
    (edir / "owners.yaml").write_text("owners:\n  - role: Engagement Lead\n    github: []\n  - role: Head of IT\n    github: []\n")
    site = tmp_path / "site"
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["--engagement", str(edir), "portal", "--out", str(site), "--repo", "acme/client-repo"]) == 0
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    state = tmp_path / "state.json"
    srv = subprocess.Popen([NODE, str(ROOT / "tests" / "portal" / "harness.mjs"), "serve", str(site), str(port),
                            "dana@client.example", str(state), str(edir.parent)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    errs = []
    try:
        time.sleep(1.2)
        with sync_api.sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 390, "height": 844})
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://localhost:{port}/#/progress")
            pg.click("details.area summary")
            pg.click("ul.reqs a >> nth=0")
            pg.fill("#impl", "Okta SSO; quarterly access reviews.")
            pg.click("form:has(#impl) button.primary")
            assert "no patient or personal data" in pg.inner_text("form:has(#impl) .msg")      # confirmation needed
            pg.check("#nophi-impl")
            pg.click("form:has(#impl) button.primary")
            pg.wait_for_selector("text=Update sent")
            pg.goto(f"http://localhost:{port}/#/owners")
            assert pg.locator(".owner-row").count() == 1 and "Head of IT" in pg.inner_text(".owner-row")
            pg.fill(".owner-row input[type=email]", "it@client.example")
            pg.check(".owner-row input[type=checkbox]")
            pg.click(".owner-row button")
            pg.wait_for_selector("text=Sent. It changes")
            assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            b.close()
    finally:
        srv.terminate()
    assert not errs, errs
    st = json.loads(state.read_text())
    assert [x["title"] for x in st["pulls"]] == ["Client change: implementation statement for CC1.1",
                                                 "Client change: email for the Head of IT owner"]
    files = {k.split(":", 1)[1]: v for k, v in st["files"].items()}
    assert yaml.safe_load(files["engagement/controls/CC1.1.yaml"])["implementation"] == "Okta SSO; quarterly access reviews."
    assert yaml.safe_load(files["engagement/owners.yaml"])["owners"][1]["email"] == "it@client.example"
