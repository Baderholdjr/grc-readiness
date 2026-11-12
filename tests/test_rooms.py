"""Read-only rooms: the executive dashboard carries summary numbers only, the auditor room carries the auditor
package and its window, both bundles fail closed until configured, and the pages render without errors."""
import contextlib
import datetime as dt
import io
import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
import yaml

from grc import rooms
from grc.cli import main
from grc.model import load
from grc.rules import validate

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
TODAY = dt.date(2026, 11, 12)
MARK = "ZQX-CONFIDENTIAL-TEXT"


def _new(tmp_path):
    root = tmp_path / "repo"
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["--engagement", str(root / "engagement"), "new-engagement", "--client", "Larch & Finch", "--start",
                     "2026-11-09", "--stage1", "2027-02-01", "--stage2", "2027-06-01", "--framework", "soc2",
                     "--intake", str(root / "intake"), "--confirm-reset"]) == 0
    return root / "engagement"


def _gaps(edir, gaps):
    (edir / "gaps.yaml").write_text(yaml.safe_dump({"gaps": gaps}, sort_keys=False))


def _set_rooms(edir, rooms_cfg):
    f = edir / "engagement.yaml"
    d = yaml.safe_load(f.read_text())
    d["rooms"] = rooms_cfg
    f.write_text(yaml.safe_dump(d, sort_keys=False))


def _gap(i, sev, due, area="Access reviews", status="open"):
    return {"id": f"GAP-{i:02d}", "area": area, "finding": f"{MARK} finding {i}", "requirements": ["CC6.1"],
            "owner": f"{MARK} owner", "severity": sev, "due": due, "status": status}


def test_executive_summary_has_numbers_not_record_text(tmp_path):
    edir = _new(tmp_path)
    _gaps(edir, [_gap(1, "low", "2026-12-01"), _gap(2, "high", "2026-11-01"), _gap(3, "medium", "2026-11-20"),
                 _gap(4, "high", "2027-01-15", status="in_progress"), _gap(5, "low", "2026-12-02", status="closed")])
    c = edir / "controls" / "CC6.1.yaml"
    d = yaml.safe_load(c.read_text())
    d["implementation"] = f"{MARK} implementation"
    c.write_text(yaml.safe_dump(d, sort_keys=False))
    out = tmp_path / "rooms"
    assert rooms.build_executive(load(edir, today=TODAY), out / "executive")
    raw = (out / "executive" / "public" / "data.json").read_text()
    assert MARK not in raw and "CC6.1" not in raw            # no finding, owner, implementation or requirement ids
    s = json.loads(raw)
    assert (s["gaps_open"], s["gaps_overdue"]) == (4, 1)
    assert s["gaps_by_severity"] == {"high": 2, "medium": 1, "low": 1, "unrated": 0}
    assert [g["severity"] for g in s["top_gaps"]] == ["high", "high", "medium", "low"]
    assert s["top_gaps"][0] == {"area": "Access reviews", "severity": "high", "due": "2026-11-01", "status": "open", "overdue": True}
    assert (s["days_to_stage1"], s["days_to_stage2"]) == (81, 201)
    assert s["ready_pct"] == 0 and s["applicable"] > 0
    toml = (out / "executive" / "wrangler.toml").read_text()
    assert 'ROOM = "executive"' in toml and 'ACCESS_AUD = ""' in toml   # fails closed until the AUD is set
    assert "run_worker_first = true" in toml


def test_trend_reads_the_record_from_git_history(tmp_path):
    edir = _new(tmp_path)
    repo = edir.parent
    git = lambda *a, date=None: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                                               env={"GIT_AUTHOR_DATE": date or "", "GIT_COMMITTER_DATE": date or "",
                                                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                                                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
                                                    "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path)})
    git("init", "-q")
    _gaps(edir, [_gap(1, "high", "2026-12-01"), _gap(2, "low", "2026-12-01")])
    git("add", "-A")
    git("commit", "-qm", "two gaps", date="2026-10-20T10:00:00Z")
    _gaps(edir, [_gap(1, "high", "2026-12-01")])
    git("commit", "-qam", "one closed", date="2026-11-03T10:00:00Z")
    pts = rooms.trend(load(edir, today=TODAY), weeks=4)
    assert [p["week"] for p in pts] == ["2026-10-22", "2026-10-29", "2026-11-05", "2026-11-12"]
    assert [p["gaps_open"] for p in pts] == [2, 2, 1, 1]
    assert rooms.trend(load(_new(tmp_path / "nogit"), today=TODAY)) == []      # no history: no trend, no error


def test_auditor_room_bundle_carries_the_package_and_its_window(tmp_path):
    edir = _new(tmp_path)
    _set_rooms(edir, {"auditor": {"enabled": True, "opens": "2027-01-25", "closes": "2027-02-12",
                                  "auditors": ["Ann@Audit.example", "bo@audit.example"], "access_aud": "c" * 64}})
    m = load(edir, today=TODAY)
    assert not [f for f in validate(m) if f.code in ("W180", "W181") or f.severity == "error"]
    out = tmp_path / "rooms" / "auditor"
    rooms.build_auditor(m, out)
    toml = (out / "wrangler.toml").read_text()
    assert 'AUDITORS = "ann@audit.example,bo@audit.example"' in toml
    assert 'ROOM_OPENS = "2027-01-25"' in toml and 'ROOM_CLOSES = "2027-02-12"' in toml and 'ROOM = "auditor"' in toml
    d = json.loads((out / "public" / "room.json").read_text())
    z = out / "public" / "files" / d["package"]["name"]
    assert z.exists() and z.stat().st_size == d["package"]["bytes"]
    import hashlib
    assert hashlib.sha256(z.read_bytes()).hexdigest() == d["package"]["sha256"]
    paths = {f["path"] for f in d["files"]}
    assert "00-auditor-index.pdf" in paths and any(p.startswith("09-oscal/") for p in paths)
    for f in d["files"][:10]:                  # every listed file is served, with the manifest's checksum
        p = out / "public" / "files" / d["folder"] / f["path"]
        assert hashlib.sha256(p.read_bytes()).hexdigest() == f["sha256"]


def test_auditor_window_warnings(tmp_path):
    edir = _new(tmp_path)
    codes = lambda: {f.code for f in validate(load(edir, today=TODAY))}
    _set_rooms(edir, {"auditor": {"enabled": True}})
    assert "W180" in codes()
    _set_rooms(edir, {"auditor": {"enabled": True, "opens": "2027-02-12", "closes": "2027-01-25", "auditors": ["a@x.example"]}})
    assert "W180" in codes()
    _set_rooms(edir, {"auditor": {"enabled": True, "opens": "2027-01-01", "closes": "2027-12-31", "auditors": ["a@x.example"]}})
    assert "W181" in codes()
    _set_rooms(edir, {"auditor": {"enabled": True, "opens": "2027-01-01", "closes": "2027-01-31", "auditors": ["not-an-email"]}})
    assert any(f.severity == "error" for f in validate(load(edir, today=TODAY)))


def test_rooms_command(tmp_path, capsys):
    edir = _new(tmp_path)
    assert main(["--engagement", str(edir), "--today", TODAY.isoformat(), "rooms", "--out", str(tmp_path / "r")]) == 0
    out = capsys.readouterr().out
    assert "executive dashboard written" in out and "auditor room written" in out
    assert "refuses everyone" in out
    for room in ("executive", "auditor"):
        b = tmp_path / "r" / room
        assert (b / "worker.js").exists() and (b / "access.js").exists() and (b / "public" / "index.html").exists()


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_rooms_worker_unit_tests():
    r = subprocess.run([NODE, "--test", str(ROOT / "tests" / "portal" / "rooms.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(not NODE, reason="node not installed")
@pytest.mark.parametrize("room", ["executive", "auditor"])
def test_room_pages_render_without_errors(tmp_path, room):
    sync_api = pytest.importorskip("playwright.sync_api")
    edir = _new(tmp_path)
    _gaps(edir, [_gap(1, "high", "2026-11-01", area='<img src=x onerror="alert(1)">')])
    today = dt.date.today()
    _set_rooms(edir, {"auditor": {"enabled": True, "opens": (today - dt.timedelta(days=1)).isoformat(),
                                  "closes": (today + dt.timedelta(days=1)).isoformat(), "auditors": ["ann@audit.example"]}})
    out = tmp_path / "r"
    with contextlib.redirect_stdout(io.StringIO()):
        assert main(["--engagement", str(edir), "rooms", "--room", room, "--out", str(out)]) == 0
    port = _free_port()
    srv = subprocess.Popen([NODE, str(ROOT / "tests" / "portal" / "harness.mjs"), "serve-room", str(out / room), str(port),
                            "ann@audit.example"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    errors = []
    try:
        time.sleep(1.0)
        with sync_api.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 390, "height": 844})
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: (errors.append("dialog: " + d.message), d.dismiss()))
            page.goto(f"http://localhost:{port}/")
            page.wait_for_selector("h1")
            stamp = page.inner_text("#stamp")
            assert "Viewed by ann@audit.example" in stamp
            if room == "executive":
                assert page.inner_text(".hero .big") == "0%"
                assert '<img src=x onerror="alert(1)">' in page.inner_text("table")      # shown as text
            else:
                link = page.get_attribute("a.btn", "href")
                assert link.startswith("files/") and link.endswith(".zip")
                assert page.locator("td a").count() > 5
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")   # no sideways scroll
            b.close()
    finally:
        srv.terminate()
    assert not errors, errors
