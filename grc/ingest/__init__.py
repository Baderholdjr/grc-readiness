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
EXCLUDE_DIRS = {"timesheets"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pending(intake: Path, force: bool = False) -> list[Path]:
    ledger = yaml.safe_load((intake / LEDGER).read_text()) if (intake / LEDGER).exists() else {}
    ledger = ledger or {}
    files = []
    for p in sorted(intake.rglob("*")):
        if not p.is_file() or p.name in SKIP or p.name.startswith("~$"):
            continue
        if p.relative_to(intake).parts[0] in EXCLUDE_DIRS:   # handled by other commands (e.g. `grc hours`)
            continue
        rel = str(p.relative_to(intake))
        if not force and (ledger.get(rel) or {}).get("sha256") == _sha(p):
            continue
        files.append(p)
    return files


BATCH_DOCS = 4               # documents per model call
BATCH_CHARS = 60_000         # and at most this much text per call (a larger single document goes alone)


def _batches(items: list[tuple]) -> list[list[tuple]]:
    out, cur, size = [], [], 0
    for it in items:
        n = len(it[1] or "")
        if cur and (len(cur) >= BATCH_DOCS or size + n > BATCH_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        out.append(cur)
    return out


def run(engagement_dir: str | Path, intake_dir: str | Path = "intake", mode: str = "auto",
        force: bool = False, transport=None, files: list[Path] | None = None) -> str:
    """mode: auto (templates + AI if enabled), templates, ai."""
    intake = Path(intake_dir)
    model: Engagement = load(engagement_dir)
    from .. import sandbox
    sandbox.configure(model)
    todo = files if files is not None else pending(intake, force)
    if not todo:
        return f"No new or changed files in {intake.name}/.\n"
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

    from .. import sandbox
    if for_ai:
        catalog = [r for r in model.requirements if model.in_category_scope(r["id"])]
        failed: list[tuple[str, str]] = []

        def read(batch):
            """One call per batch; a batch whose answer doesn't fit is split in half and tried again."""
            nonlocal combined
            try:
                result = ai.draft([(n, t) for n, t, _ in batch], catalog, model.gaps, model.client,
                                  model=settings.get("model"), transport=transport, framework=model.framework_name)
            except ai.AIUnavailable as exc:
                if len(batch) > 1 and "truncated" in str(exc):
                    half = len(batch) // 2
                    read(batch[:half])
                    read(batch[half:])
                    return
                failed.extend((n, str(exc)) for n, _, _ in batch)
                return
            combined = draft.merge(combined, result)
            for n, _, p in batch:
                notes.append(f"`{n}`: " + ("sandbox AI draft (canned, sandbox/ai_draft.json)" if sandbox.active()
                             else f"drafted by Claude ({settings.get('model') or ai.DEFAULT_MODEL})"))
                ledger_updates[n] = {"sha256": _sha(p), "mode": "ai"}

        for batch in _batches(for_ai):
            if failed and not any("truncated" in why for _, why in failed):
                failed.extend((n, failed[0][1]) for n, _, _ in batch)   # out of credit, bad key: don't keep calling
                continue
            read(batch)
        if failed:
            notes.insert(0, f"**{len(failed)} document(s) not read: {failed[0][1]}.** Spreadsheets in the intake "
                            "template format are imported regardless; the rest are read on the next run.")
            notes += [f"`{n}`: not processed ({why})" for n, why in failed]

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
    if sandbox.active():
        report = ("> ⚠️ **SANDBOX MODE.** AI drafting returned canned test output from `sandbox/ai_draft.json`; "
                  "no document was sent to the Anthropic API.\n\n") + report
    return report + "\n### Files\n" + "\n".join(f"- {n}" for n in notes) + "\n"
