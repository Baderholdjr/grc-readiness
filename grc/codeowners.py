"""Generate a managed block in .github/CODEOWNERS from owners.yaml.

Each control file gets its owner's GitHub users as required reviewers, so a
client owner must approve changes to their own controls. Lines outside the
managed block are left alone. GitHub uses the LAST matching rule, so the block
is appended after hand-written rules.
"""
from __future__ import annotations

from pathlib import Path

from .model import Engagement

BEGIN = "# >>> grc-managed: control owners (python -m grc codeowners) >>>"
END = "# <<< grc-managed <<<"


def render_block(model: Engagement) -> tuple[str, list[str]]:
    lines, missing = [BEGIN, "# Generated from engagement/owners.yaml. Do not edit inside this block."], []
    base = model.engagement_dir.relative_to(model.root) if model.engagement_dir.is_relative_to(model.root) else Path("engagement")
    for r in model.requirements:
        c = model.controls.get(r["id"])
        if not c or not c.get("owner"):
            continue
        users = model.github_users(c["owner"])
        if not users:
            missing.append(f"{r['id']} ({c['owner']})")
            continue
        lines.append(f"/{base.as_posix()}/controls/{r['id']}.yaml " + " ".join(f"@{u}" for u in users))
    lines.append(END)
    return "\n".join(lines) + "\n", missing


def update(model: Engagement, path: Path) -> tuple[bool, list[str]]:
    block, missing = render_block(model)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        tail = rest.split(END, 1)[1].lstrip("\n")
        new = head.rstrip("\n") + "\n\n" + block + (("\n" + tail) if tail.strip() else "")
    else:
        new = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    changed = new != text
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    return changed, missing
