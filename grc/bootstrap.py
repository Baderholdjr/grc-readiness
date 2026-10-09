"""Write the thin client-repository skeleton (workflow wrappers, engine pin, README).

    python -m grc bootstrap --dir ../acme-grc --engine-repo Baderholdjr/grc-readiness

A client repo holds only its engagement record. Workflows are thin wrappers that
call the engine repo's reusable workflows at engine-v<MAJOR>; the engine itself is
pinned in requirements.txt at engine-v<VERSION>. Existing files are kept unless
--force. Run `grc new-engagement` (or the New engagement workflow) afterwards.
"""
from __future__ import annotations

from pathlib import Path

from . import __version__
from .model import ENGINE

SKELETON = ENGINE / "client"
# Packaging drops dot-directories, so the skeleton stores them as dot-<name>.


def _target_path(rel: Path) -> Path:
    return Path(*[("." + p[4:]) if p.startswith("dot-") else p for p in rel.parts])


def render(text: str, engine_repo: str, version: str) -> str:
    return (text.replace("__ENGINE_REPO__", engine_repo)
                .replace("__ENGINE_VERSION__", version)
                .replace("__ENGINE_MAJOR__", version.split(".")[0])
                .replace("__REPO_OWNER__", engine_repo.split("/")[0]))


def write(target: Path, engine_repo: str, version: str | None = None, force: bool = False) -> list[str]:
    version = version or __version__
    log = []
    for src in sorted(p for p in SKELETON.rglob("*") if p.is_file()):
        rel = _target_path(src.relative_to(SKELETON))
        dst = target / rel
        if dst.exists() and not force:
            log.append(f"kept     {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(render(src.read_text(encoding="utf-8"), engine_repo, version), encoding="utf-8")
        log.append(f"wrote    {rel}")
    return log
