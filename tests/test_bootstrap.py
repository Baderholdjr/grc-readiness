"""Thin client skeleton: placeholders rendered, wrappers mirror the engine repo's own."""
import re
from pathlib import Path

import yaml

from grc import __version__, bootstrap
from grc.cli import main
from grc.model import ENGINE, load

ROOT = Path(__file__).resolve().parent.parent
WRAPPED = ["audit", "collect", "docs", "hours", "impact", "freshness", "ingest", "new-engagement", "portal", "publish-reports", "release", "review", "sync-issues"]


def _on(path):
    data = yaml.safe_load(path.read_text())
    return data.get("on", data.get(True)), data.get("permissions")


def test_client_wrappers_match_engine_repo_wrappers():
    for name in WRAPPED:
        local = ROOT / ".github" / "workflows" / f"{name}.yml"
        client = ENGINE / "client" / "dot-github" / "workflows" / f"{name}.yml"
        assert _on(local) == _on(client), f"{name}: triggers/permissions differ between engine repo and client skeleton"
        assert f"grc-{name}.yml@engine-v__ENGINE_MAJOR__" in client.read_text()
        assert (ROOT / ".github" / "workflows" / f"grc-{name}.yml").exists()


def test_every_reusable_workflow_is_callable():
    for path in (ROOT / ".github" / "workflows").glob("grc-*.yml"):
        on = _on(path)[0]
        assert "workflow_call" in on, path.name


def test_bootstrap_renders_everything(tmp_path):
    assert main(["bootstrap", "--dir", str(tmp_path), "--engine-repo", "acme/engine", "--version", "1.4.2"]) == 0
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files and not any("__ENGINE" in p.read_text() or "__REPO_OWNER" in p.read_text() for p in files)
    req = (tmp_path / "requirements.txt").read_text()
    assert "git+https://github.com/acme/engine@engine-v1.4.2" in req
    wf = (tmp_path / ".github" / "workflows" / "validate.yml").read_text()
    assert "uses: acme/engine/.github/workflows/grc-validate.yml@engine-v1" in wf
    assert "* @acme" in (tmp_path / ".github" / "CODEOWNERS").read_text()
    assert (tmp_path / ".gitignore").exists() and not (tmp_path / "dot-github").exists()
    # second run keeps edits unless --force
    (tmp_path / "README.md").write_text("mine")
    log = bootstrap.write(tmp_path, "acme/engine", "1.4.2")
    assert "kept     README.md" in log and (tmp_path / "README.md").read_text() == "mine"


def test_thin_repo_works_end_to_end(tmp_path):
    """A bootstrapped repo + new engagement validates and builds with no engine files in it."""
    bootstrap.write(tmp_path, "acme/engine")
    edir = tmp_path / "engagement"
    assert main(["--engagement", str(edir), "new-engagement", "--client", "Thin Co", "--start", "2026-11-02",
                 "--stage1", "2027-03-15", "--stage2", "2027-05-10", "--intake", str(tmp_path / "intake"),
                 "--confirm-reset"]) == 0
    assert not (tmp_path / "frameworks").exists() and not (tmp_path / "grc").exists()
    assert main(["--engagement", str(edir), "validate"]) == 0
    assert main(["--engagement", str(edir), "build", "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "brief.md").exists()
    cfg = yaml.safe_load((edir / "collectors.yaml").read_text())
    assert cfg["checks"][0]["params"]["required_checks"] == ["validate / validate"]


def test_repo_override_of_playbook(tmp_path):
    bootstrap.write(tmp_path, "acme/engine")
    edir = tmp_path / "engagement"
    main(["--engagement", str(edir), "new-engagement", "--client", "X", "--start", "2026-11-02", "--stage1",
          "2027-03-15", "--stage2", "2027-05-10", "--intake", str(tmp_path / "intake"), "--confirm-reset"])
    pb = yaml.safe_load((ENGINE / "frameworks" / "iso42001" / "playbook.yaml").read_text())
    pb["title_suffix"] = "Custom Brief Title"
    (tmp_path / "frameworks" / "iso42001").mkdir(parents=True)
    (tmp_path / "frameworks" / "iso42001" / "playbook.yaml").write_text(yaml.safe_dump(pb))
    assert load(edir).playbook["title_suffix"] == "Custom Brief Title"
    assert len(load(edir).requirements) == 65  # catalog still from the engine


def test_versions_agree():
    import tomllib
    assert tomllib.load(open(ROOT / "pyproject.toml", "rb"))["project"]["version"] == __version__


def test_skeleton_has_no_hidden_paths():
    """Packaging silently drops dot-files/dirs; the skeleton must not rely on them."""
    hidden = [p for p in (ENGINE / "client").rglob("*") if any(part.startswith(".") for part in p.relative_to(ENGINE).parts)]
    assert hidden == []
