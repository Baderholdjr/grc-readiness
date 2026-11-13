"""The consultant workspace: its settings, the bundle, the vendored YAML parser, the Worker's own tests, and the
pages in a browser against a fake GitHub (signing in, editing a requirement, opening a pull request)."""
import contextlib
import hashlib
import io
import json
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from grc import workspace
from grc.cli import main

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
VENDOR = ROOT / "grc" / "resources" / "workspace" / "vendor"


def _cfg(tmp_path, text):
    p = tmp_path / "workspace.yaml"
    p.write_text(text)
    return p


def test_settings_are_checked(tmp_path):
    ok = workspace.load_config(_cfg(tmp_path, "github_client_id: Iv23liEXAMPLE0001\nconsultants: [Baderholdjr, sam-x]\n"))
    assert ok == {"github_client_id": "Iv23liEXAMPLE0001", "consultants": ["Baderholdjr", "sam-x"],
                  "worker_name": "seshat-workspace", "base_branch": "main"}
    for bad, msg in [("consultants: [a]\n", "github_client_id"), ("github_client_id: Iv23liEXAMPLE0001\n", "consultants"),
                     ("github_client_id: Iv23liEXAMPLE0001\nconsultants: ['a b']\n", "consultants"),
                     ("github_client_id: Iv23liEXAMPLE0001\nconsultants: [a]\nbase_branch: ../x\n", "base_branch"),
                     ("github_client_id: Iv23liEXAMPLE0001\nconsultants: [a]\nworker_name: Bad_Name\n", "worker_name")]:
        with pytest.raises(workspace.WorkspaceError, match=msg):
            workspace.load_config(_cfg(tmp_path, bad))


def test_bundle_has_no_secrets(tmp_path, capsys):
    p = _cfg(tmp_path, "github_client_id: Iv23liEXAMPLE0001\nconsultants: [Baderholdjr]\n")
    assert main(["workspace", "--config", str(p), "--out", str(tmp_path / "b")]) == 0
    toml = (tmp_path / "b" / "wrangler.toml").read_text()
    assert 'GITHUB_CLIENT_ID = "Iv23liEXAMPLE0001"' in toml and 'CONSULTANTS = "Baderholdjr"' in toml
    assert "GITHUB_CLIENT_SECRET =" not in toml and "SESSION_KEY =" not in toml
    for f in ("worker.js", "access.js", "yamledit.js", "js-yaml.mjs", "public/index.html", "public/app.js", "public/icon.svg"):
        assert (tmp_path / "b" / f).exists(), f
    assert "set the Worker secrets" in capsys.readouterr().out


def test_vendored_parser_is_the_reviewed_file():
    readme = (VENDOR / "README.md").read_text()
    want = re.search(r"`([0-9a-f]{64})`", readme).group(1)
    assert hashlib.sha256((VENDOR / "js-yaml.mjs").read_bytes()).hexdigest() == want
    assert (VENDOR / "js-yaml.mjs").read_text().lstrip().startswith("/*! js-yaml 4.1.1 ")
    assert "MIT" in (VENDOR / "js-yaml-LICENSE.txt").read_text()


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_workspace_worker_unit_tests():
    r = subprocess.run([NODE, "--test", str(ROOT / "tests" / "portal" / "workspace.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


CONTROL = ("# A.5.15 Access control\nid: A.5.15\nowner: Head of IT\ntest:\n  documented:\n    status: verified\n"
           "    evidence: [\"EV-001\"]\n  implemented:\n    status: not_started\n    evidence: []\n  evidenced:\n"
           "    status: not_started\n    evidence: []\n  tested:\n    status: not_started\n    evidence: []\n")


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_workspace_in_a_browser(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    p = _cfg(tmp_path, "github_client_id: Iv23liEXAMPLE0001\nconsultants: [dana-lead]\n")
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["workspace", "--config", str(p), "--out", str(tmp_path / "b")]) == 0
    (tmp_path / "control.yaml").write_text(CONTROL)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = subprocess.Popen([NODE, str(ROOT / "tests" / "portal" / "harness.mjs"), "serve-workspace", str(tmp_path / "b"), str(port),
                            str(tmp_path / "control.yaml")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    errs = []
    try:
        time.sleep(1.2)
        with sync_api.sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 390, "height": 844})
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.goto(f"http://localhost:{port}/")
            pg.wait_for_selector("text=Sign in with GitHub")                     # no session yet
            pg.goto(f"http://localhost:{port}/__test/session")
            pg.goto(f"http://localhost:{port}/")
            pg.wait_for_selector("text=Signed in as dana-lead")
            pg.click("text=test-larch-grc")
            pg.wait_for_selector("details.req")
            pg.click("details.req summary")
            assert pg.inner_text(".leg >> nth=0").count("Verified by a reviewer") == 1   # no control to change it
            pg.select_option(".leg >> nth=1 >> select", "claimed")
            pg.click(".leg >> nth=1 >> text=Save status")
            pg.wait_for_selector("text=opened. The record changes when it's merged.")
            assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            state = json.loads(pg.goto(f"http://localhost:{port}/__test/state").text())
            b.close()
    finally:
        srv.terminate()
    assert not [e for e in errs if "401" not in e], errs                          # the 401 before sign-in is expected
    assert [x["title"] for x in state["pulls"]] == ["Workspace: implemented check of A.5.15: claimed"]
    assert '  implemented:\n    status: "claimed"' in state["files"]["engagement/controls/A.5.15.yaml"]
