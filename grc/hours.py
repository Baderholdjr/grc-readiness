"""Hours tracking: a timesheet in the repo, burn against budget and phase plans, and a forecast.

    engagement/hours.yaml          entries: date, person, hours, activity, phase, refs, note
    python -m grc hours import intake/timesheets/toggl.csv --match "Larkspur"
    python -m grc hours log --hours 2.5 --activity interviews --note "Release-owner walkthrough" --refs A.6.2.5

Imports recognise Toggl, Harvest and Clockify exports (and any CSV with date/hours columns). Each entry
gets a stable id from its source row, so re-importing the same export never double-counts.
When hours.yaml exists, it replaces the hand-typed budget.hours_used.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import hashlib
import io
import re
from pathlib import Path

import yaml

from .model import Engagement, to_date

DEFAULT = {"warn_at": 0.8, "forecast_weeks": 4, "max_per_person_day": 14, "phase_split": {}, "activities": [{"id": "other"}],
           "date_order": None}
HEADER = ("# Timesheet (engagement/hours.yaml). Imported by `grc hours import` (Toggl, Harvest, Clockify or CSV)\n"
          "# or added with `grc hours log`. Edit through PRs like everything else; ids keep re-imports idempotent.\n")


def method(model: Engagement) -> dict:
    return {**DEFAULT, **(model.playbook.get("hours") or {})}


def safe_date(v) -> dt.date | None:
    try:
        return to_date(v)
    except (TypeError, ValueError, OverflowError):
        return None


def _clean(e: dict, aliases: dict) -> dict:
    e = dict(e)
    refs = e.get("refs")
    e["refs"] = [str(r) for r in refs] if isinstance(refs, list) else ([str(refs)] if isinstance(refs, (str, int, float)) else [])
    who = str(e.get("person") or "").strip()
    e["person"] = aliases.get(who.lower(), who)
    return e


def aliases(model: Engagement) -> dict[str, str]:
    """hours.yaml `aliases: {"Ana Lopez": ana}` - one person, several spellings (tracker name, GitHub user)."""
    a = model.hours_meta.get("aliases") if isinstance(model.hours_meta.get("aliases"), dict) else {}
    return {str(k).strip().lower(): str(v).strip() for k, v in a.items()}


def ignored(model: Engagement) -> set[str]:
    """hours.yaml `ignored: [H-...]` - entries deliberately removed, so re-imports don't bring them back."""
    v = model.hours_meta.get("ignored")
    return {str(x) for x in v} if isinstance(v, list) else set()


def entries(model: Engagement) -> list[dict]:
    al = aliases(model)
    return [_clean(e, al) for e in model.hours if isinstance(e, dict)]


def tracked(model: Engagement) -> bool:
    """True when the engagement keeps a timesheet (then it is the source of hours used)."""
    return (model.engagement_dir / "hours.yaml").exists()


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def total(model: Engagement) -> float:
    return round(sum(_num(e.get("hours")) for e in entries(model)), 2)


def hours_used(model: Engagement) -> float:
    if tracked(model):
        return total(model)
    return _num((model.engagement.get("budget") or {}).get("hours_used"))


def phases(model: Engagement) -> list[dict]:
    return [p for p in model.engagement.get("phases") or [] if isinstance(p, dict) and p.get("id")]


def phase_for(model: Engagement, e: dict) -> str | None:
    if e.get("phase"):
        return str(e["phase"])
    d = safe_date(e.get("date"))
    for p in phases(model):
        if d and safe_date(p.get("start")) and safe_date(p.get("end")) and safe_date(p["start"]) <= d <= safe_date(p["end"]):
            return str(p["id"])
    return None


def planned(model: Engagement) -> dict[str, float]:
    """Planned hours per phase: explicit `hours` on the phase, else the playbook split of the budget."""
    budget = _num((model.engagement.get("budget") or {}).get("hours_total"))
    split = method(model).get("phase_split") or {}
    out = {}
    for p in phases(model):
        if p.get("hours") is not None:
            out[str(p["id"])] = _num(p["hours"])
        elif split.get(p["id"]) is not None:
            out[str(p["id"])] = round(budget * _num(split[p["id"]]), 1)
    return out


def by(model: Engagement, key) -> dict[str, float]:
    acc: dict[str, float] = collections.defaultdict(float)
    for e in entries(model):
        acc[str(key(e) or "—")] += _num(e.get("hours"))
    return {k: round(v, 2) for k, v in sorted(acc.items())}


def week_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def weekly(model: Engagement) -> dict[dt.date, float]:
    acc: dict[dt.date, float] = collections.defaultdict(float)
    for e in entries(model):
        d = safe_date(e.get("date"))
        if d:
            acc[week_of(d)] += _num(e.get("hours"))
    return dict(sorted(acc.items()))


def forecast(model: Engagement) -> dict:
    """Burn rate over the last N full weeks, projected to the end of the last phase (or Stage 2)."""
    cfg = method(model)
    n = int(cfg.get("forecast_weeks") or 4)
    this_week = week_of(model.today)
    w = weekly(model)
    starts = [d for d in [safe_date((model.engagement.get("dates") or {}).get("start"))] + list(w) if d]
    first = min(starts) if starts else None
    full_weeks = max(0, (this_week - week_of(first)).days // 7) if first else 0
    span = max(1, min(n, full_weeks))
    weeks = [this_week - dt.timedelta(weeks=i) for i in range(1, span + 1)]
    rate = round(sum(w.get(x, 0.0) for x in weeks) / span, 2) if full_weeks else 0.0
    ends = [safe_date(p.get("end")) for p in phases(model)] + [safe_date((model.engagement.get("dates") or {}).get("stage2"))]
    end = max([d for d in ends if d] or [model.today])
    remaining_weeks = max((end - model.today).days, 0) / 7
    used = hours_used(model)
    projected = round(used + rate * remaining_weeks, 1)
    budget = _num((model.engagement.get("budget") or {}).get("hours_total"))
    start = safe_date((model.engagement.get("dates") or {}).get("start"))
    elapsed = (min(1.0, max(0.0, (model.today - start).days / max((end - start).days, 1)))) if start else None
    return {"rate_per_week": rate, "weeks": span if full_weeks else 0, "end": end, "projected_total": projected, "budget": budget,
            "used": used, "elapsed_share": round(elapsed, 3) if elapsed is not None else None,
            "budget_share": round(used / budget, 3) if budget else None}


# ------------------------------------------------------------------ classification
def classify(model: Engagement, *texts: str) -> str:
    text = " ".join(t for t in texts if t).lower()
    acts = method(model)["activities"]
    ids = {a["id"] for a in acts}
    for t in texts:
        if t and t.strip().lower().replace(" ", "_") in ids:
            return t.strip().lower().replace(" ", "_")
    best, score = "other", 0
    for a in acts:
        for k in a.get("keywords") or []:
            if re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}(?:s|es)?(?![a-z0-9])", text) and len(k) > score:
                best, score = a["id"], len(k)
    return best if best in ids else ("other" if "other" in ids else sorted(ids)[0])


def entry_id(*parts) -> str:
    return "H-" + hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ import
def _duration(v: str) -> float | None:
    v = (v or "").strip()
    if not v:
        return None
    if ":" in v:   # h:mm or h:mm:ss
        try:
            parts = [float(x or 0) for x in v.split(":")]
        except ValueError:
            return None
        while len(parts) < 3:
            parts.append(0.0)
        return round(parts[0] + parts[1] / 60 + parts[2] / 3600, 4)
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def _date(v: str, order: str = "MDY") -> dt.date | None:
    v = re.split(r"[ T]", (v or "").strip(), maxsplit=1)[0]
    slash = ("%m/%d/%Y", "%d/%m/%Y") if order == "MDY" else ("%d/%m/%Y", "%m/%d/%Y")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y") + slash:
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def date_order(values: list[str], preferred: str | None) -> tuple[str, bool]:
    """Day/month order for a file's slash dates: decided from the data when any day is > 12, else `preferred`.
    Returns (order, ambiguous)."""
    first, second = set(), set()
    for v in values:
        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/\d{2,4}", v or "")
        if m:
            first.add(int(m.group(1)))
            second.add(int(m.group(2)))
    if any(x > 12 for x in first):
        return "DMY", False
    if any(x > 12 for x in second):
        return "MDY", False
    return (preferred or "MDY"), bool(first) and preferred is None


def _pick(row: dict, *names: str) -> str:
    low = {k.strip().lower(): v for k, v in row.items() if k}
    for n in names:
        if low.get(n) not in (None, ""):
            return str(low[n]).strip()
    return ""


def parse_csv(text: str, order: str | None = None) -> tuple[str, list[dict], str, bool]:
    """Recognise the export format. Returns (format, rows, date order used, order was ambiguous).
    rows: {date, person, hours, task, tags, note, project, client, start, phase, refs}."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    heads = {h.strip().lower() for h in reader.fieldnames or []}
    reader = list(reader)
    used_order, ambiguous = date_order([_pick(r, "start date", "date", "spent date", "day") for r in reader], order)
    fmt = ("toggl" if {"start date", "duration", "user"} <= heads else
           "clockify" if {"start date", "duration (decimal)"} <= heads else
           "harvest" if {"date", "hours", "first name"} <= heads else "generic")
    rows = []
    for r in reader:
        if fmt == "toggl":
            hours = _duration(_pick(r, "duration"))
            person = _pick(r, "user", "email")
            date = _date(_pick(r, "start date"), used_order)
        elif fmt == "clockify":
            hours = _duration(_pick(r, "duration (decimal)", "duration (h)"))
            person = _pick(r, "user", "email")
            date = _date(_pick(r, "start date"), used_order)
        elif fmt == "harvest":
            hours = _duration(_pick(r, "hours"))
            person = " ".join(x for x in (_pick(r, "first name"), _pick(r, "last name")) if x)
            date = _date(_pick(r, "date", "spent date"), used_order)
        else:
            hours = _duration(_pick(r, "hours", "duration", "time"))
            person = _pick(r, "person", "user", "who", "name", "consultant")
            date = _date(_pick(r, "date", "day", "start date"), used_order)
        rows.append({"date": date, "person": person, "hours": hours, "task": _pick(r, "task", "activity", "category"),
                     "tags": _pick(r, "tags", "tag"), "note": _pick(r, "description", "notes", "note", "comment"),
                     "project": _pick(r, "project", "project code"), "client": _pick(r, "client"),
                     "start": _pick(r, "start time"), "phase": _pick(r, "phase"), "refs": _pick(r, "refs", "references")})
    return fmt, rows, used_order, ambiguous


REF = re.compile(r"\b(GAP-\d+|NC-\d{3}|OFI-\d{3}|IA-\d{3,}|DOC-[A-Z0-9-]+|MR-\d{4}-\d{2}|AUD-\d{4}-\d{2}|[A-Z]\.\d+(?:\.\d+)*|\d{1,2}\.\d+(?:\.\d+)*)\b")
# In free-text notes only unambiguous ids count ("2.5 hours" is not clause 2.5); bare clause numbers
# like 6.1.2 are taken from the refs/tags columns.
NOTE_REF = re.compile(r"\b(GAP-\d+|NC-\d{3}|OFI-\d{3}|IA-\d{3,}|DOC-[A-Z0-9-]+|MR-\d{4}-\d{2}|AUD-\d{4}-\d{2}|[A-Z]\.\d+(?:\.\d+)+)\b")


def known_refs(model: Engagement) -> set[str]:
    refs = set(model.requirement_index) | {g.get("id") for g in model.gaps} | set(model.impacts) | set(model.documents) \
        | set(model.reviews) | {a.get("id") for a in model.audits if isinstance(a, dict)}
    refs |= {f.get("id") for f in model.findings if isinstance(f, dict)}
    return {str(r) for r in refs if r}


def _write(model: Engagement, items: list[dict]) -> None:
    path = model.engagement_dir / "hours.yaml"
    items = sorted(items, key=lambda e: (str(e.get("date")), str(e.get("person")), str(e.get("id"))))
    data = {k: v for k, v in model.hours_meta.items() if k in ("aliases", "ignored") and v}
    data["entries"] = items
    path.write_text(HEADER + yaml.safe_dump(_plain(data), sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")


def _plain(v):
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v.isoformat() if isinstance(v, dt.date) else v


def clean_match(match: str | None) -> list[str]:
    """The client/project filter, forgiving of how it was typed: quotes, spaces, a 'HOURS_MATCH=' prefix,
    and several alternatives separated by commas or '|'."""
    if not match:
        return []
    m = re.sub(r"^\s*HOURS_MATCH\s*[=:]\s*", "", str(match), flags=re.I)
    parts = [x.strip().strip("'\"“”‘’").strip() for x in re.split(r"[,|\n]", m)]
    return [x.lower() for x in parts if x]


def import_files(model: Engagement, paths: list[Path], match: str | None = None, person: str | None = None,
                 order: str | None = None) -> list[str]:
    existing = [_plain(e) for e in model.hours if isinstance(e, dict)]
    seen = {e.get("id") for e in existing} | ignored(model)
    al = aliases(model)
    known = known_refs(model)
    log, added = [], 0
    for path in paths:
        fmt, rows, used_order, ambiguous = parse_csv(Path(path).read_text(encoding="utf-8-sig", errors="replace"),
                                                     order or method(model).get("date_order"))
        if ambiguous:
            log.append(f"[!] {Path(path).name}: dates like 05/09/2026 could be day/month or month/day; read as "
                       f"{'month/day' if used_order == 'MDY' else 'day/month'}. Set --date-order (or hours.date_order) to be sure.")
        skipped = {"other client/project": 0, "no date or hours": 0, "already imported or ignored": 0}
        occurrence: dict = {}
        wanted = clean_match(match)
        seen_clients = collections.Counter()
        for r in rows:
            seen_clients[" / ".join(x for x in (r["client"], r["project"]) if x) or "(no client or project)"] += 1
            if wanted and not any(w in f"{r['client']} {r['project']}".lower() for w in wanted):
                skipped["other client/project"] += 1
                continue
            if not r["date"] or not r["hours"] or r["hours"] <= 0:
                skipped["no date or hours"] += 1
                continue
            who = person or r["person"] or "unknown"
            who = al.get(who.strip().lower(), who)
            key = (fmt, r["date"], who, r["hours"], r["start"], r["note"], r["task"], r["project"], r["client"])
            occurrence[key] = occurrence.get(key, 0) + 1     # identical rows in one export are separate work
            eid = entry_id(*key, occurrence[key])            # no file name: renamed or cumulative exports are safe
            if eid in seen:
                skipped["already imported or ignored"] += 1
                continue
            refs = sorted(x for x in set(REF.findall(f"{r['refs']} {r['tags']}")) | set(NOTE_REF.findall(r["note"])) if x in known)
            e = {"id": eid, "date": r["date"].isoformat(), "person": who, "hours": round(r["hours"], 2),
                 "activity": classify(model, r["task"], r["tags"], r["note"])}
            if r["phase"]:
                e["phase"] = r["phase"]
            if refs:
                e["refs"] = refs
            if r["note"]:
                e["note"] = r["note"][:300]
            e["source"] = f"{fmt}:{Path(path).name}"
            existing.append(e)
            seen.add(eid)
            added += 1
        log.append(f"{Path(path).name} ({fmt}): {len(rows)} row(s); " + "; ".join(
            [f"{added} added so far"] + [f"{v} skipped ({k})" for k, v in skipped.items() if v]))
        if wanted:
            log.append(f"    client/project filter: {' or '.join(repr(w) for w in wanted)}")
        if rows and skipped["other client/project"] == len(rows):
            log.append("[!] the client/project filter skipped every row. Clients/projects in this file: "
                       + "; ".join(f"{k} ({v})" for k, v in seen_clients.most_common(10))
                       + ". Check the HOURS_MATCH variable (or --match).")
    _write(model, existing)
    log.append(f"timesheet now has {len(existing)} entries, {round(sum(_num(e['hours']) for e in existing), 2):g} hours")
    return log


def log_entry(model: Engagement, hours: float, activity: str, person: str, on: dt.date | None = None,
              note: str = "", refs: list[str] | None = None, phase: str | None = None) -> list[str]:
    if not hours or hours <= 0 or hours > 24:
        raise ValueError("hours must be between 0 and 24")
    ids = {a["id"] for a in method(model)["activities"]}
    if activity not in ids:
        raise ValueError(f"unknown activity '{activity}' (one of: {', '.join(sorted(ids))})")
    on = on or model.today
    if on > model.today:
        raise ValueError("date is in the future")
    items = [_plain(e) for e in model.hours if isinstance(e, dict)]
    n = sum(1 for e in items if e.get("date") == on.isoformat() and e.get("person") == person)
    e = {"id": entry_id("log", on, person, hours, activity, note, n), "date": on.isoformat(), "person": person,
         "hours": round(float(hours), 2), "activity": activity}
    if phase:
        e["phase"] = phase
    if refs:
        e["refs"] = list(refs)
    if note:
        e["note"] = note[:300]
    e["source"] = "log"
    items.append(e)
    _write(model, items)
    return [f"{e['id']}  {on}  {person}  {e['hours']:g} h  {activity}" + (f"  ({note})" if note else "")]
