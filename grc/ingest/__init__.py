"""Ingest client documents from intake/ into the engagement record.

  CSV/XLSX in the intake template format -> imported deterministically
  CSV/XLSX control register (GRC tool export or own sheet) -> imported deterministically (register.py)
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
from .. import safety
from . import ai, apply, draft, extract, register, templates

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
        if p.is_symlink():          # never followed; listed so the report says it was refused
            if p.name not in SKIP:
                files.append(p)
            continue
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


class _Record:
    """One record's share of an ingest run: what was imported, what goes to Claude, and the notes."""

    def __init__(self, engagement_dir, intake_dir, mode, force, files):
        from .. import sandbox
        self.intake = Path(intake_dir)
        self.model: Engagement = load(engagement_dir)
        sandbox.configure(self.model)
        self.todo = files if files is not None else pending(self.intake, force)
        self.settings = self.model.engagement.get("ingest", {}) or {}
        self.mode = mode
        self.combined, self.notes, self.for_ai, self.ledger_updates = draft.empty(), [], [], {}
        self.register_rows: dict[str, list[dict]] = {}
        ai_allowed = mode in ("auto", "ai") and self.settings.get("ai_drafting", False)
        for p in self.todo:
            rel = str(p.relative_to(self.intake)) if p.is_relative_to(self.intake) else p.name
            if p.suffix.lower() not in extract.SUPPORTED:
                self.notes.append(f"`{rel}`: unsupported file type, skipped")
                continue
            try:
                safety.check_upload(p, self.intake)
                table = extract.rows(p)
            except safety.UnsafeFile as exc:
                self.notes.append(f"`{rel}`: **not processed**, because {exc}")
                continue
            except Exception as exc:  # a damaged or hostile file is reported, never a crash
                self.notes.append(f"`{rel}`: **not processed**, it could not be read ({type(exc).__name__})")
                continue
            kind = templates.detect(table[0]) if table else None
            try:
                reg = None if kind or mode not in ("auto", "templates") else \
                    next(((sheet, t) for sheet, t in extract.tables(p) if register.detect(t)), None)
            except Exception:  # damaged workbook: fall through to the other readers
                reg = None
            if kind and mode in ("auto", "templates"):
                _, d, problems = templates.to_draft(table, rel)
                self.combined = draft.merge(self.combined, d)
                self.notes.append(f"`{rel}`: imported as **{kind}** template")
                self.notes += [f"`{rel}`: {x}" for x in problems]
                self.ledger_updates[rel] = {"sha256": _sha(p), "mode": f"template:{kind}"}
            elif reg:
                sheet, t = reg
                known = {str(r["id"]) for r in self.catalog()}
                name = register.register_name(rel)
                d, rows, problems = register.to_draft(t, rel + (f" sheet {sheet}" if sheet and p.suffix.lower() == ".xlsx" else ""),
                                                      self.framework, known, self.model.catalog["framework"]["short_name"], name)
                self.combined = draft.merge(self.combined, d)
                self.register_rows[name] = self.register_rows.get(name, []) + rows
                mapped = sum(1 for r in rows if r["maps"])
                self.notes.append(f"`{rel}`: imported as a **control register** ({len(rows)} controls, {mapped} mapped to "
                                  f"{self.model.catalog['framework']['short_name']})")
                self.notes += [f"`{rel}`: {x}" for x in problems]
                self.ledger_updates[rel] = {"sha256": _sha(p), "mode": "register"}
            elif ai_allowed:
                try:
                    self.for_ai.append((rel, extract.text(p), p))
                except Exception as exc:
                    self.notes.append(f"`{rel}`: **not processed**, its text could not be read ({type(exc).__name__})")
            else:
                reason = "AI drafting is disabled (set `ingest: {ai_drafting: true}` in engagement.yaml)" \
                    if mode != "templates" else "not an intake template"
                self.notes.append(f"`{rel}`: not processed — {reason}")

    @property
    def framework(self) -> str:
        return str(self.model.engagement.get("framework") or "iso42001")

    def catalog(self) -> list[dict]:
        return [r for r in self.model.requirements if self.model.in_category_scope(r["id"])]

    def drafted(self, names: list[str], how: str):
        from .. import sandbox
        for n, _, p in [x for x in self.for_ai if x[0] in names]:
            self.notes.append(f"`{n}`: " + ("sandbox AI draft (canned, sandbox/ai_draft.json)" if sandbox.active() else how))
            self.ledger_updates[n] = {"sha256": _sha(p), "mode": "ai"}

    def failed(self, failures: list[tuple[str, str]]):
        if failures:
            self.notes.insert(0, f"**{len(failures)} document(s) not read: {failures[0][1]}.** Spreadsheets in the "
                                 "intake template format are imported regardless; the rest are read on the next run.")
            self.notes += [f"`{n}`: not processed ({why})" for n, why in failures]

    def finish(self) -> str:
        from .. import sandbox
        if not self.todo:
            return f"No new or changed files in {self.intake.name}/.\n"
        label = ", ".join(sorted(self.ledger_updates)) or "intake"
        report = apply.apply(self.model, self.combined, label, files=sorted(self.ledger_updates))
        if self.register_rows:
            register.save(self.model.engagement_dir, self.register_rows)
            stale = register.stale_gaps(load(self.model.engagement_dir).gaps, self.register_rows)
            if stale:
                report += ("\n### Gaps the re-imported register no longer supports\n"
                           "Not closed automatically: confirm with evidence, then close (closure_evidence).\n\n"
                           + "\n".join(f"- {s}" for s in stale) + "\n")
        if self.ledger_updates:
            lp = self.intake / LEDGER
            ledger = (yaml.safe_load(lp.read_text()) if lp.exists() else {}) or {}
            today = dt.date.today().isoformat()
            for k, v in self.ledger_updates.items():
                ledger[k] = {**v, "ingested": today}
            lp.write_text("# Files already ingested (sha256). Delete an entry to re-ingest.\n"
                          + yaml.safe_dump(ledger, sort_keys=True), encoding="utf-8")
        if sandbox.active():
            report = ("> ⚠️ **SANDBOX MODE.** AI drafting returned canned test output from `sandbox/ai_draft.json`; "
                      "no document was sent to the Anthropic API.\n\n") + report
        return report + "\n### Files\n" + "\n".join(f"- {n}" for n in self.notes) + "\n"


def _read_batches(items: list[tuple], call, on_result) -> list[tuple[str, str]]:
    """Send items (name, text, ...) in batches; split a batch whose answer is truncated; stop calling after a
    failure that isn't about size (no credit, bad key). Returns (name, reason) for every item not read."""
    failed: list[tuple[str, str]] = []

    def read(batch):
        try:
            result = call(batch)
        except ai.AIUnavailable as exc:
            if len(batch) > 1 and "truncated" in str(exc):
                half = len(batch) // 2
                read(batch[:half])
                read(batch[half:])
                return
            failed.extend((it[0], str(exc)) for it in batch)
            return
        on_result(batch, result)

    for batch in _batches(items):
        if failed and not any("truncated" in why for _, why in failed):
            failed.extend((it[0], failed[0][1]) for it in batch)
            continue
        read(batch)
    return failed


def run(engagement_dir: str | Path, intake_dir: str | Path = "intake", mode: str = "auto",
        force: bool = False, transport=None, files: list[Path] | None = None) -> str:
    """mode: auto (templates + AI if enabled), templates, ai."""
    rec = _Record(engagement_dir, intake_dir, mode, force, files)
    if not rec.todo:
        return rec.finish()
    if rec.for_ai:
        model_name = rec.settings.get("model") or ai.DEFAULT_MODEL
        names = [n for n, _, _ in rec.for_ai]

        def call(batch):
            # gaps drafted from earlier batches count as existing, so a later batch doesn't raise them again
            known = rec.model.gaps + [{"id": "(drafted in this run)", "area": g.get("area", ""), "finding": g.get("finding", "")}
                                      for g in rec.combined.get("gaps") or [] if isinstance(g, dict)]
            return ai.draft([(n, t) for n, t, _ in batch], rec.catalog(), known, rec.model.client,
                            model=rec.settings.get("model"), transport=transport, framework=rec.model.framework_name,
                            others=[n for n in names if n not in {b[0] for b in batch}])

        def done(batch, result):
            rec.combined = draft.merge(rec.combined, result)
            rec.drafted([b[0] for b in batch], f"drafted by Claude ({model_name})")
        rec.failed(_read_batches(rec.for_ai, call, done))
    return rec.finish()


# ------------------------------------------------------------------ one read for several records
def _owner(source: str, names: list[str]) -> list[str]:
    """The documents an item's `source` names (longest name first, so 'a/b.docx' beats 'b.docx')."""
    s = str(source or "")
    hit = [n for n in sorted(names, key=len, reverse=True) if n and (n in s or Path(n).name in s)]
    return hit[:1] or names


def _for_framework(result: dict, fw: str, docs: set[str], names: list[str]) -> dict:
    """The part of a shared read that belongs to one record: its documents, its framework's ids (unprefixed)."""
    pre = fw + ":"

    def mine(item) -> bool:
        return bool(set(_owner(item.get("source", ""), names)) & docs) if isinstance(item, dict) else True

    def ids(lst):
        return [str(x)[len(pre):] for x in lst or [] if str(x).startswith(pre)]
    out = draft.empty()
    out["client_overview"] = list(result.get("client_overview") or [])
    out["ai_usage"] = list(result.get("ai_usage") or [])
    out["open_questions"] = list(result.get("open_questions") or [])
    out["scope_statement"] = next((s.get("statement", "") for s in result.get("scope_statements") or []
                                   if isinstance(s, dict) and str(s.get("framework", "")).lower() == fw), "")
    for key in ("inventory", "evidence"):
        out[key] = [x for x in result.get(key) or [] if mine(x)]
    for key in ("gaps", "in_place"):
        for x in result.get(key) or []:
            if not mine(x):
                continue
            had = x.get("requirements") or []
            own = ids(had)
            if had and not own:
                continue                      # it is about another framework only
            out[key].append({**x, "requirements": own})
    for c in result.get("claims") or []:
        if mine(c) and str(c.get("requirement", "")).startswith(pre):
            out["claims"].append({**c, "requirement": str(c["requirement"])[len(pre):]})
    return out


def run_many(records: list[tuple[str | Path, str | Path]], mode: str = "auto", force: bool = False,
             transport=None) -> dict[str, str]:
    """Ingest several records (engagement/, engagement-27001/, ...) together. A document that more than one
    record has (the same file in intake/ and intake-27001/) is sent to Claude once, with every record's
    catalog, and the draft is split per record. Returns {engagement dir: report}."""
    recs = [_Record(e, i, mode, force, None) for e, i in records]
    sharing = [r for r in recs if r.for_ai]
    fws = [r.framework for r in sharing]
    if len(sharing) < 2 or len(set(fws)) != len(fws):      # nothing to share, or two records of one framework
        if not sharing:
            return {str(e): r.finish() for (e, _), r in zip(records, recs)}
        return {str(e): run(e, i, mode, force, transport) for e, i in records}
    # unique documents by content
    docs: dict[str, list] = {}
    for r in sharing:
        for n, text, p in r.for_ai:
            key = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
            entry = docs.setdefault(key, [n, text, []])
            entry[2].append((r, n))
    items = [(v[0], v[1], v[2]) for v in docs.values()]
    all_names = [v[0] for v in docs.values()]
    catalog = [{"id": f"{r.framework}:{q['id']}", "title": q["title"]} for r in sharing for q in r.catalog()]
    known_all = [{"id": f"{r.framework}:{g.get('id')}", "area": g.get("area", ""), "finding": g.get("finding", "")}
                 for r in sharing for g in r.model.gaps if isinstance(g, dict)]
    first = sharing[0]
    model_name = first.settings.get("model") or ai.DEFAULT_MODEL
    drafted: list[dict] = []
    labels = [r.model.framework_name for r in sharing]

    def call(batch):
        known = known_all + [{"id": "(drafted in this run)", "area": g.get("area", ""), "finding": g.get("finding", "")}
                             for res in drafted for g in res.get("gaps") or [] if isinstance(g, dict)]
        return ai.draft([(n, t) for n, t, _ in batch], catalog, known, first.model.client, model=first.settings.get("model"),
                        transport=transport, framework=" and ".join(labels),
                        others=[n for n in all_names if n not in {b[0] for b in batch}],
                        frameworks=[f"{r.framework} ({r.model.framework_name})" for r in sharing])

    def done(batch, result):
        drafted.append(result)
        names = [b[0] for b in batch]
        for r in sharing:
            # a record's own name for each document in this batch (the same file can sit in two intake folders)
            own = {n_r: n for n, _, owners in batch for rr, n_r in owners if rr is r}
            if not own:
                continue
            part = _for_framework(result, r.framework, set(own.values()), names)
            for key in ("inventory", "evidence", "gaps", "in_place", "claims"):
                for x in part[key]:
                    hit = _owner(x.get("source", ""), names)[0]
                    mine = next((k for k, v in own.items() if v == hit), None)
                    if mine and mine != hit:
                        x["source"] = str(x.get("source", "")).replace(hit, mine, 1)
            r.combined = draft.merge(r.combined, part)
            others = len({id(rr) for _, _, owners in batch for rr, _ in owners}) - 1
            r.drafted(list(own), f"drafted by Claude ({model_name})"
                      + (f", read once for this and {others} other record(s)" if others else ""))
    failed = _read_batches(items, call, done)
    for r in sharing:
        mine = {n for n, _, _ in r.for_ai}
        names_by_doc = {v[0]: [n_r for rr, n_r in v[2] if rr is r] for v in docs.values()}
        r.failed([(own, why) for n, why in failed for own in names_by_doc.get(n, []) if own in mine])
    return {str(e): r.finish() for (e, _), r in zip(records, recs)}
