"""Ingest client documents from intake/ into the engagement record.

  CSV/XLSX in the intake template format -> imported deterministically
  Anything else (docx, pdf, xlsx, md, txt) -> drafted by Claude (if enabled)

Processed files are recorded with their sha256 in intake/.processed.yaml so
re-runs only handle new or changed files.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import yaml

from ..model import Engagement, load
from . import ai, apply, draft, extract, templates

LEDGER = ".processed.yaml"
SKIP = {"README.md", LEDGER, ".gitkeep"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pending(intake: Path, force: bool = False) -> list[Path]:
    ledger = yaml.safe_load((intake / LEDGER).read_text()) if (intake / LEDGER).exists() else {}
    ledger = ledger or {}
    files = []
    for p in sorted(intake.rglob("*")):
        if not p.is_file() or p.name in SKIP or p.name.startswith("~$"):
            continue
        rel = str(p.relative_to(intake))
        if not force and (ledger.get(rel) or {}).get("sha256") == _sha(p):
            continue
        files.append(p)
    return files


def run(engagement_dir: str | Path, intake_dir: str | Path = "intake", mode: str = "auto",
        force: bool = False, transport=None, files: list[Path] | None = None) -> str:
    """mode: auto (templates + AI if enabled), templates, ai."""
    intake = Path(intake_dir)
    model: Engagement = load(engagement_dir)
    todo = files if files is not None else pending(intake, force)
    if not todo:
        return "No new or changed files in intake/.\n"
    settings = model.engagement.get("ingest", {}) or {}
    ai_allowed = mode in ("auto", "ai") and settings.get("ai_drafting", False)

    combined, notes, for_ai, ledger_updates = draft.empty(), [], [], {}
    for p in todo:
        rel = str(p.relative_to(intake)) if p.is_relative_to(intake) else p.name
        if p.suffix.lower() not in extract.SUPPORTED:
            notes.append(f"`{rel}`: unsupported file type, skipped")
            continue
        table = extract.rows(p)
        kind = templates.detect(table[0]) if table else None
        if kind and mode in ("auto", "templates"):
            _, d, problems = templates.to_draft(table, rel)
            combined = draft.merge(combined, d)
            notes.append(f"`{rel}`: imported as **{kind}** template")
            notes += [f"`{rel}`: {x}" for x in problems]
            ledger_updates[rel] = {"sha256": _sha(p), "mode": f"template:{kind}"}
        elif ai_allowed:
            for_ai.append((rel, extract.text(p), p))
        else:
            reason = "AI drafting is disabled (set `ingest: {ai_drafting: true}` in engagement.yaml)" \
                if mode != "templates" else "not an intake template"
            notes.append(f"`{rel}`: not processed — {reason}")

    if for_ai:
        try:
            result = ai.draft([(n, t) for n, t, _ in for_ai], model.requirements, model.gaps, model.client,
                              model=settings.get("model"), transport=transport)
            combined = draft.merge(combined, result)
            for n, _, p in for_ai:
                notes.append(f"`{n}`: drafted by Claude ({settings.get('model') or ai.DEFAULT_MODEL})")
                ledger_updates[n] = {"sha256": _sha(p), "mode": "ai"}
        except ai.AIUnavailable as exc:
            notes += [f"`{n}`: not processed — {exc}" for n, _, _ in for_ai]

    label = ", ".join(sorted(ledger_updates)) or "intake"
    report = apply.apply(model, combined, label, files=sorted(ledger_updates))
    if ledger_updates:
        lp = intake / LEDGER
        ledger = (yaml.safe_load(lp.read_text()) if lp.exists() else {}) or {}
        today = dt.date.today().isoformat()
        for k, v in ledger_updates.items():
            ledger[k] = {**v, "ingested": today}
        lp.write_text("# Files already ingested (sha256). Delete an entry to re-ingest.\n"
                      + yaml.safe_dump(ledger, sort_keys=True), encoding="utf-8")
    return report + "\n### Files\n" + "\n".join(f"- {n}" for n in notes) + "\n"
