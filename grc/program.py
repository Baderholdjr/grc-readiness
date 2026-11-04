"""The compliance program: one control catalog across frameworks, a governance calendar and owner certification.

An engagement record (engagement/, engagement-<name>/) holds one framework. The program layer sits above the
records, in program/ at the repository root, and describes how the organization actually runs:

  program/controls.yaml       the common control catalog: each control once, with its owner, its evidence and
                              the requirements it satisfies in every framework (records' frameworks and
                              reference catalogs such as NIST SP 800-53)
  program/calendar.yaml       recurring governance obligations (access reviews, policy reviews, training,
                              vendor reviews, partner assessments), each with an owner, due dates and the
                              evidence that closes each occurrence
  program/certifications/     quarterly owner certifications: one file per owner per quarter, opened as a pull
    <period>/<owner>.yaml     request, completed and signed by the owner
  program/owners.yaml         optional: program owners (same format as a record's owners.yaml). Without it, the
                              owners of every record are used.

    python -m grc program validate             # P-codes, like `grc validate` for a record
    python -m grc program report --out out     # catalog, coverage, scorecard, matrix workbook, calendar (.ics)
    python -m grc program certify              # certification files for the quarter that just ended
    python -m grc program issues [--apply]     # an Issue per obligation that is due soon or overdue

Nothing here marks a requirement verified. The catalog says which control is meant to satisfy which
requirement; each record still tests the requirement against its evidence. Mappings are the program's claim,
reviewed like any other change, in a pull request.
"""
from __future__ import annotations

import copy
import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from .model import Engagement, discover, jsonable, load, load_schema, load_yaml, resource, to_date
from .rules import Finding

PROGRAM = "program"
FREQUENCIES = ("continuous", "daily", "weekly", "monthly", "quarterly", "semiannual", "annual", "event")
EVERY_MONTHS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}
RESPONSES = ("pending", "operating", "exception", "not_operating", "not_applicable")
CERT_DUE_DAYS = 30
LEAD_DAYS = 14
EVIDENCE_REF = re.compile(r"^([a-z0-9]+):([A-Za-z0-9._-]+)$")
PERIOD = re.compile(r"^(\d{4})-Q([1-4])$")


# ------------------------------------------------------------------ loading
def _date(v) -> dt.date | None:
    """A date, or None for anything that isn't one (the schema reports it; reports must not crash)."""
    try:
        return to_date(v)
    except (TypeError, ValueError):
        return None


def _int(v, default: int) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else default


@dataclass
class Program:
    root: Path
    today: dt.date
    controls: list[dict] = field(default_factory=list)
    obligations: list[dict] = field(default_factory=list)
    owners: list[dict] = field(default_factory=list)
    owners_from: str = "records"
    certifications: dict[str, dict[str, dict]] = field(default_factory=dict)   # period -> slug -> data
    cert_files: dict[str, Path] = field(default_factory=dict)                  # "period/slug" -> path
    records: dict[str, Engagement] = field(default_factory=dict)               # framework id -> record
    raw: dict[str, object] = field(default_factory=dict)                       # file name -> parsed YAML (schema)
    _catalogs: dict[str, dict | None] = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return self.root / PROGRAM

    @property
    def control_index(self) -> dict[str, dict]:
        return {str(c.get("id")): c for c in self.controls if isinstance(c, dict)}

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    # catalogs: a framework of the engine (or the client repo), else a reference catalog
    def catalog(self, fw: str) -> dict | None:
        if fw not in self._catalogs:
            path = resource(self.root, "frameworks", fw, "catalog.yaml")
            if not path.exists():
                path = resource(self.root, "reference", f"{fw}.yaml")
            self._catalogs[fw] = load_yaml(path) if path.exists() else None
        return self._catalogs[fw]

    def requirement_index(self, fw: str) -> dict[str, dict]:
        cat = self.catalog(fw) or {}
        return {str(r["id"]): r for r in cat.get("requirements", []) or []}

    def framework_name(self, fw: str) -> str:
        cat = self.catalog(fw) or {}
        f = cat.get("framework", {}) or {}
        return f.get("short_name") or f.get("name") or fw

    # owners
    def role(self, name: str | None) -> dict | None:
        n = (name or "").strip().lower()
        return next((o for o in self.owners if (o.get("role") or "").strip().lower() == n), None) if n else None

    def github_users(self, role: str | None) -> list[str]:
        o = self.role(role)
        users = (o or {}).get("github") if o else None
        return [str(u).lstrip("@") for u in users if "/" not in str(u)] if isinstance(users, list) else []

    def controls_owned_by(self, role: str) -> list[dict]:
        r = role.strip().lower()
        return [c for c in self.controls if isinstance(c, dict) and str(c.get("owner") or "").strip().lower() == r]

    # evidence held in the records, cited as "<framework>:<EV-id>"
    def evidence(self, ref: str) -> tuple[Engagement | None, dict | None]:
        m = EVIDENCE_REF.match(str(ref))
        if not m:
            return None, None
        rec = self.records.get(m.group(1))
        if rec is None:
            return None, None
        return rec, rec.evidence_index.get(m.group(2))


def _read(path: Path, key: str) -> tuple[object, list]:
    if not path.exists():
        return None, []
    try:
        data = load_yaml(path)
    except ValueError as exc:          # e.g. a date that doesn't exist (2026-02-30) fails while YAML is read
        return {"_error": f"{path.name} can't be read: {exc}. Check the dates in it"}, []
    items = data.get(key) if isinstance(data, dict) else None
    return data, items if isinstance(items, list) else []


def exists(root: str | Path = ".") -> bool:
    d = Path(root) / PROGRAM
    return d.is_dir() and (any((d / f).exists() for f in ("controls.yaml", "calendar.yaml"))
                           or any((d / "itgc").glob("*/workpaper.yaml")))


def load_program(root: str | Path = ".", today: dt.date | None = None) -> Program:
    root = Path(root).resolve()
    prog = Program(root=root, today=today or dt.date.today())
    d = root / PROGRAM
    # The schema checks the files as written (prog.raw); the rules and reports work on a normalized copy that
    # keeps only well-formed entries, so a malformed file is reported (P101) rather than crashing a report.
    for name, key, attr in (("controls.yaml", "controls", "controls"), ("calendar.yaml", "obligations", "obligations")):
        raw, items = _read(d / name, key)
        prog.raw[name] = copy.deepcopy(raw) if raw is not None else None
        setattr(prog, attr, [copy.deepcopy(x) for x in items if isinstance(x, dict) and x.get("id") not in (None, "")])
    for c in prog.controls:
        c["id"] = str(c["id"])
        maps = c.get("maps")
        c["maps"] = ({str(k): [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in maps.items()}
                     if isinstance(maps, dict) else {})
        c["evidence"] = [str(x) for x in c.get("evidence") or []] if isinstance(c.get("evidence"), list) else []
    for o in prog.obligations:
        o["id"] = str(o["id"])
        o["done"] = [e for e in o.get("done") or [] if isinstance(e, dict)] if isinstance(o.get("done"), list) else []
        o["controls"] = [str(x) for x in o.get("controls") or []] if isinstance(o.get("controls"), list) else []
    for rdir in discover(root):
        rec = load(rdir, today=prog.today)
        prog.records.setdefault(str(rec.engagement.get("framework") or "iso42001"), rec)
    if (d / "owners.yaml").exists():
        prog.raw["owners.yaml"], owners = _read(d / "owners.yaml", "owners")
        prog.owners = [o for o in owners if isinstance(o, dict)]
        prog.owners_from = "program/owners.yaml"
    else:  # every record's owners, first record wins on a repeated role
        seen = set()
        for rec in prog.records.values():
            for o in rec.owners:
                k = (o.get("role") or "").strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    prog.owners.append(o)
    cdir = d / "certifications"
    for path in sorted(cdir.glob("*/*.yaml")) if cdir.is_dir() else []:
        try:
            data = load_yaml(path)
        except (SystemExit, ValueError) as exc:
            data = {"_error": str(exc)}
        prog.certifications.setdefault(path.parent.name, {})[path.stem] = data if isinstance(data, dict) else {}
        prog.cert_files[f"{path.parent.name}/{path.stem}"] = path
    return prog


# ------------------------------------------------------------------ calendar arithmetic
def add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


def due_dates(ob: dict, until: dt.date) -> list[dt.date]:
    """Every due date of an obligation from its first_due up to `until` (inclusive)."""
    first = _date(ob.get("first_due"))
    months = EVERY_MONTHS.get(ob.get("every"))
    if not first or not months:
        return []
    out, k = [], 0
    while True:
        d = add_months(first, months * k)
        if d > until:
            return out
        out.append(d)
        k += 1


def _done_index(ob: dict) -> dict[dt.date, dict]:
    out = {}
    for e in ob.get("done") or []:
        if isinstance(e, dict):
            p = _date(e.get("period"))
            if p:
                out[p] = e
    return out


def occurrences(prog: Program, ob: dict, horizon_days: int = 0) -> list[dict]:
    """[{due, status, done}] status: done_on_time | done_late | overdue | due_soon | upcoming."""
    lead = _int(ob.get("lead_days"), LEAD_DAYS)
    done = _done_index(ob)
    out = []
    for d in due_dates(ob, prog.today + dt.timedelta(days=max(lead, horizon_days))):
        e = done.get(d)
        if e:
            on = _date(e.get("completed"))
            status = "done_on_time" if on and on <= d else "done_late"
        elif d < prog.today:
            status = "overdue"
        elif (d - prog.today).days <= lead:
            status = "due_soon"
        else:
            status = "upcoming"
        out.append({"due": d, "status": status, "done": e})
    return out


# ------------------------------------------------------------------ certification periods
def quarter_of(d: dt.date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def previous_quarter(d: dt.date) -> str:
    first = dt.date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    return quarter_of(first - dt.timedelta(days=1))


def quarter_end(period: str) -> dt.date:
    m = PERIOD.match(period)
    if not m:
        raise ValueError(f"period must look like 2026-Q3 (got {period!r})")
    y, q = int(m.group(1)), int(m.group(2))
    return add_months(dt.date(y, 3 * q - 2, 1), 3) - dt.timedelta(days=1)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "owner"


CERT_HEADER = ("# Quarterly control owner certification - opened by `grc program certify`.\n"
               "# For each control: set response to operating, exception, not_operating or not_applicable.\n"
               "# Anything other than operating needs a note; an exception or a control that didn't operate needs a\n"
               "# follow_up (a gap, finding or issue). Then set certified_by to your GitHub user and certified_on to\n"
               "# today, and approve the pull request. CI checks that nothing is left pending.\n")


def certify_open(prog: Program, period: str | None = None, due_days: int = CERT_DUE_DAYS) -> list[Path]:
    """One certification file per control owner for the period; existing files are never overwritten."""
    period = period or previous_quarter(prog.today)
    end = quarter_end(period)
    created = []
    by_owner: dict[str, list[dict]] = {}
    for c in prog.controls:
        if isinstance(c, dict) and str(c.get("owner") or "").strip():
            by_owner.setdefault(str(c["owner"]).strip(), []).append(c)
    for owner, ctls in sorted(by_owner.items()):
        path = prog.dir / "certifications" / period / f"{slug(owner)}.yaml"
        if path.exists():
            continue
        data = {"period": period, "owner": owner, "due": (end + dt.timedelta(days=due_days)).isoformat(),
                "statement": f"I confirm that during {period} each control below operated as described in "
                             "program/controls.yaml, except where I say otherwise.",
                "controls": [{"id": c["id"], "title": c.get("title", ""), "response": "pending", "note": "",
                              "follow_up": ""} for c in ctls],
                "certified_by": "", "certified_on": None}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CERT_HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120),
                        encoding="utf-8")
        created.append(path)
    return created


def _validly_signed(prog: Program, d: dict) -> bool:
    rows = [x for x in d.get("controls") or [] if isinstance(x, dict)]
    users = {u.lower() for u in prog.github_users(str(d.get("owner") or ""))}
    return (bool(d.get("certified_by")) and _date(d.get("certified_on")) is not None
            and str(d.get("certified_by")).lstrip("@").lower() in users
            and not any(x.get("response") == "pending" for x in rows))


def certification_status(prog: Program, period: str) -> dict:
    files = prog.certifications.get(period, {})
    owners = {str(c.get("owner")).strip() for c in prog.controls if isinstance(c, dict) and c.get("owner")}
    lower = {o.lower() for o in owners}
    signed = {str(d.get("owner")).strip().lower() for d in files.values()
              if isinstance(d, dict) and str(d.get("owner") or "").strip().lower() in lower and _validly_signed(prog, d)}
    responses = [x for d in files.values() for x in (d.get("controls") or []) if isinstance(x, dict)]
    return {"period": period, "owners": len(owners), "opened": len(files), "certified": len(signed),
            "exceptions": sum(1 for x in responses if x.get("response") in ("exception", "not_operating")),
            "responses": len(responses)}


# ------------------------------------------------------------------ validation
def _schema(prog: Program, name: str, data, path: Path, out: list[Finding]) -> bool:
    v = Draft202012Validator(load_schema(name), format_checker=FormatChecker())
    errs = sorted(v.iter_errors(jsonable(data)), key=lambda e: list(e.path))
    for e in errs:
        loc = "/".join(str(p) for p in e.path) or "(root)"
        from .rules import _hint
        out.append(Finding("error", "P101", f"Schema: {loc}: {_hint(e.message)}", prog.rel(path)))
    return not errs


def in_scope(rec: Engagement) -> list[str]:
    return [r["id"] for r in rec.requirements if rec.in_category_scope(r["id"]) and rec.is_applicable(r["id"])]


def mapped(prog: Program) -> dict[str, dict[str, list[str]]]:
    """framework -> requirement id -> control ids mapped to it."""
    out: dict[str, dict[str, list[str]]] = {}
    for c in prog.controls:
        if not isinstance(c, dict):
            continue
        for fw, rids in (c.get("maps") or {}).items():
            for rid in rids:
                out.setdefault(fw, {}).setdefault(rid, []).append(c["id"])
    return out


def _check_evidence_ref(prog: Program, ref: str, where: str, file: str, out: list[Finding], code="P105") -> None:
    m = EVIDENCE_REF.match(str(ref))
    if not m:
        out.append(Finding("error", code, f"{where}: evidence '{ref}' must be <framework>:<evidence id>, "
                                          "e.g. iso27001:EV-012", file))
        return
    if m.group(1) not in prog.records:
        out.append(Finding("error", code, f"{where}: evidence '{ref}': no {m.group(1)} record in this repository "
                                          f"(records: {', '.join(sorted(prog.records)) or 'none'})", file))
        return
    rec, ev = prog.evidence(ref)
    if ev is None:
        out.append(Finding("error", code, f"{where}: evidence '{ref}' is not in {rec.record_dir}/evidence", file))


def check_controls(prog: Program) -> list[Finding]:
    out: list[Finding] = []
    path = prog.dir / "controls.yaml"
    if prog.raw.get("controls.yaml") is None:
        return out
    f = prog.rel(path)
    if isinstance(prog.raw["controls.yaml"], dict) and "_error" in prog.raw["controls.yaml"]:
        return [Finding("error", "P101", prog.raw["controls.yaml"]["_error"], f)]
    if not _schema(prog, "program-controls", prog.raw["controls.yaml"], path, out):
        return out
    seen = set()
    for c in prog.controls:
        cid = c["id"]
        if cid in seen:
            out.append(Finding("error", "P102", f"{cid}: control id used more than once", f, cid))
        seen.add(cid)
        if c.get("owner") and prog.role(c["owner"]) is None:
            out.append(Finding("warning", "P106", f"{cid}: owner '{c['owner']}' is not a role in {prog.owners_from}",
                               f, cid))
        for fw, rids in (c.get("maps") or {}).items():
            idx = prog.requirement_index(fw)
            if prog.catalog(fw) is None:
                out.append(Finding("error", "P103", f"{cid}: unknown framework '{fw}' (no catalog in frameworks/ or "
                                                    "reference/)", f, cid))
                continue
            for rid in rids:
                if rid not in idx:
                    out.append(Finding("error", "P104", f"{cid}: '{rid}' is not a requirement of "
                                                        f"{prog.framework_name(fw)}", f, cid))
                elif fw in prog.records:
                    rec = prog.records[fw]
                    if not rec.in_category_scope(rid):
                        out.append(Finding("warning", "P108", f"{cid}: maps to {fw} {rid}, which is outside the "
                                                              f"categories in scope of {rec.record_dir}/", f, cid))
                    elif not rec.is_applicable(rid):
                        out.append(Finding("warning", "P108", f"{cid}: maps to {fw} {rid}, which {rec.record_dir}/ "
                                                              "marks not applicable", f, cid))
        for ref in c.get("evidence") or []:
            _check_evidence_ref(prog, ref, cid, f, out)
            rec, ev = prog.evidence(ref)
            if ev is not None and rec.evidence_is_expired(ev):
                out.append(Finding("warning", "P110", f"{cid}: evidence {ref} expired on {rec.evidence_expiry(ev)}",
                                   f, cid))
        if not c.get("evidence"):
            out.append(Finding("info", "P109", f"{cid}: no evidence cited yet", f, cid))
    m = mapped(prog)
    for fw, rec in prog.records.items():
        todo = [rid for rid in in_scope(rec) if rid not in m.get(fw, {})]
        if todo and prog.controls:
            n = len(in_scope(rec))
            out.append(Finding("warning", "P107", f"{rec.record_dir}/: {len(todo)} of {n} in-scope "
                                                  f"{prog.framework_name(fw)} requirements map to no common control "
                                                  f"(first: {', '.join(todo[:8])}). See program coverage report.", f))
    return out


def check_calendar(prog: Program) -> list[Finding]:
    out: list[Finding] = []
    path = prog.dir / "calendar.yaml"
    if prog.raw.get("calendar.yaml") is None:
        return out
    f = prog.rel(path)
    if isinstance(prog.raw["calendar.yaml"], dict) and "_error" in prog.raw["calendar.yaml"]:
        return [Finding("error", "P101", prog.raw["calendar.yaml"]["_error"], f)]
    if not _schema(prog, "program-calendar", prog.raw["calendar.yaml"], path, out):
        return out
    seen, ctl = set(), prog.control_index
    for ob in prog.obligations:
        oid = ob["id"]
        if oid in seen:
            out.append(Finding("error", "P202", f"{oid}: obligation id used more than once", f, oid))
        seen.add(oid)
        if prog.role(ob.get("owner")) is None:
            out.append(Finding("warning", "P207", f"{oid}: owner '{ob.get('owner')}' is not a role in "
                                                  f"{prog.owners_from}", f, oid))
        for c in ob.get("controls") or []:
            if str(c) not in ctl:
                out.append(Finding("error", "P208", f"{oid}: control '{c}' is not in program/controls.yaml", f, oid))
        dues = set(due_dates(ob, prog.today + dt.timedelta(days=3660)))
        for e in ob.get("done") or []:
            p, on = _date(e.get("period")), _date(e.get("completed"))
            where = f"{oid} {e.get('period')}"
            if p not in dues:
                out.append(Finding("error", "P203", f"{where}: not a due date of this obligation (due dates run "
                                                    f"{ob.get('every')} from {ob.get('first_due')})", f, oid))
            if on and on > prog.today:
                out.append(Finding("error", "P209", f"{where}: completed {on} is in the future", f, oid))
            months = EVERY_MONTHS.get(ob.get("every"))
            if on and p and months and on < add_months(p, -months):
                out.append(Finding("warning", "P210", f"{where}: completed {on}, more than one {ob.get('every')} "
                                                      "interval before it was due: is this the right period?", f, oid))
            if not e.get("evidence"):
                out.append(Finding("error", "P204", f"{where}: marked done with no evidence of completion", f, oid))
            for ref in e.get("evidence") or []:
                _check_evidence_ref(prog, ref, where, f, out, code="P205")
        for occ in occurrences(prog, ob):
            if occ["status"] == "overdue":
                out.append(Finding("warning", "P206", f"{oid}: '{ob.get('title')}' was due {occ['due']} and has no "
                                                      "completion recorded", f, oid))
    return out


def check_certifications(prog: Program) -> list[Finding]:
    out: list[Finding] = []
    ctl = prog.control_index
    for key, path in sorted(prog.cert_files.items()):
        period, s = key.split("/", 1)
        d = prog.certifications[period][s]
        f = prog.rel(path)
        if "_error" in d:
            out.append(Finding("error", "P301", d["_error"], f))
            continue
        if not _schema(prog, "program-certification", d, path, out):
            continue
        if str(d.get("period")) != period:
            out.append(Finding("error", "P301", f"period '{d.get('period')}' doesn't match its folder {period}/", f))
        owner = str(d.get("owner") or "")
        if prog.role(owner) is None:
            out.append(Finding("warning", "P302", f"{key}: owner '{owner}' is not a role in {prog.owners_from}", f))
        rows = [x for x in d.get("controls") or [] if isinstance(x, dict)]
        listed = {str(x.get("id")) for x in rows}
        for x in rows:
            cid = str(x.get("id"))
            if cid not in ctl:
                out.append(Finding("error", "P308", f"{key}: control {cid} is not in program/controls.yaml", f, cid))
            elif str(ctl[cid].get("owner") or "").strip().lower() != owner.strip().lower():
                out.append(Finding("error", "P308", f"{key}: control {cid} is owned by '{ctl[cid].get('owner')}', "
                                                    f"not {owner}: only its owner can certify it", f, cid))
            r = x.get("response")
            if r != "operating" and r != "pending" and not str(x.get("note") or "").strip():
                out.append(Finding("error", "P304", f"{key}: {cid} is '{r}' with no note explaining it", f, cid))
            if r in ("exception", "not_operating") and not str(x.get("follow_up") or "").strip():
                out.append(Finding("warning", "P307", f"{key}: {cid} is '{r}' with no follow_up (a gap, finding or "
                                                      "issue that tracks the fix)", f, cid))
        signed_by = str(d.get("certified_by") or "").strip().lstrip("@")
        on = _date(d.get("certified_on"))
        if signed_by or on:
            if not (signed_by and on):
                out.append(Finding("error", "P303", f"{key}: set both certified_by and certified_on", f))
            pending = [str(x.get("id")) for x in rows if x.get("response") == "pending"]
            if pending:
                out.append(Finding("error", "P303", f"{key}: certified with {len(pending)} control(s) still pending: "
                                                    f"{', '.join(pending)}", f))
            if on and on > prog.today:
                out.append(Finding("error", "P309", f"{key}: certified_on {on} is in the future", f))
            if on and PERIOD.match(period) and on <= quarter_end(period) - dt.timedelta(days=1):
                out.append(Finding("error", "P309", f"{key}: certified on {on}, before {period} ended "
                                                    f"({quarter_end(period)})", f))
            users = prog.github_users(owner)
            if signed_by and users and signed_by.lower() not in {u.lower() for u in users}:
                out.append(Finding("error", "P305", f"{key}: certified_by '{signed_by}' is not a GitHub user of "
                                                    f"{owner} ({', '.join(users)}): owners certify their own "
                                                    "controls", f))
            elif signed_by and not users:
                out.append(Finding("error", "P305", f"{key}: {owner} has no GitHub users in {prog.owners_from}, so "
                                                    f"the signature '{signed_by}' can't be checked. Add the owner's "
                                                    "GitHub user to the role first", f))
        else:
            due = _date(d.get("due"))
            if due and due < prog.today:
                out.append(Finding("warning", "P306", f"{key}: certification was due {due} and isn't signed", f))
        missing = [c["id"] for c in prog.controls_owned_by(owner) if c["id"] not in listed] if owner else []
        if missing:
            signed = bool(signed_by and on)
            out.append(Finding("error" if signed else "warning", "P310",
                               f"{key}: {owner} also owns {', '.join(missing)}, which this certification doesn't list"
                               + (": add them and answer them before signing" if signed else ""), f))
    return out


def validate(prog: Program) -> list[Finding]:
    out: list[Finding] = []
    if prog.raw.get("owners.yaml") is not None:
        _schema(prog, "owners", prog.raw["owners.yaml"], prog.dir / "owners.yaml", out)
    from .itgc import check as check_itgc
    def ids(x: str) -> set[str]:
        x = x.strip().lstrip("@")
        out = {x.lower(), *(u.lower() for u in prog.github_users(x))}
        out |= {(o.get("role") or "").strip().lower() for o in prog.owners
                if x.lower() in {str(u).lstrip("@").lower() for u in o.get("github") or [] if isinstance(o.get("github"), list)}}
        return out - {""}
    same = lambda a, b: bool(ids(a) & ids(b))
    return (out + check_controls(prog) + check_calendar(prog) + check_certifications(prog)
            + check_itgc(prog.root, prog.today, independent=same))


# ------------------------------------------------------------------ crosswalk suggestions
def _mapping_files(prog: Program) -> list[dict]:
    seen, out = set(), []
    for base in (prog.root / "mappings", Path(__file__).resolve().parent / "resources" / "mappings"):
        for p in sorted(base.glob("*__*.yaml")) if base.is_dir() else []:
            if p.name in seen:
                continue                 # the client repo's copy wins over the engine's
            seen.add(p.name)
            data = load_yaml(p)
            if isinstance(data, dict):
                out.append(data)
    return out


def suggestions(prog: Program) -> list[dict]:
    """Mappings a crosswalk proposes that a control doesn't have yet: {control, from, to, relationship, reviewed}."""
    out = []
    files = _mapping_files(prog)
    for c in prog.controls:
        if not isinstance(c, dict):
            continue
        maps = c.get("maps") or {}
        have = {(fw, rid) for fw, rids in maps.items() for rid in rids}
        for data in files:
            fws = [str(x) for x in data.get("frameworks") or []]
            if len(fws) != 2:
                continue
            for m in data.get("mappings") or []:
                if not isinstance(m, dict) or m.get("relationship") not in ("equivalent", "subset", "superset"):
                    continue
                a, b = fws
                for src, dst in ((a, b), (b, a)):
                    if (src, str(m.get(src))) in have and (dst, str(m.get(dst))) not in have:
                        out.append({"control": c["id"], "from": f"{src} {m.get(src)}", "to_fw": dst,
                                    "to": str(m.get(dst)), "relationship": m["relationship"],
                                    "reviewed": bool(str(m.get("reviewed_by") or "").strip())})
    uniq = {(s["control"], s["to_fw"], s["to"]): s for s in out}
    return sorted(uniq.values(), key=lambda s: (s["control"], s["to_fw"], s["to"]))


# ------------------------------------------------------------------ metrics
def coverage(prog: Program) -> list[dict]:
    m = mapped(prog)
    out = []
    for fw, rec in prog.records.items():
        scope = in_scope(rec)
        covered = [r for r in scope if r in m.get(fw, {})]
        out.append({"framework": fw, "name": prog.framework_name(fw), "record": rec.record_dir,
                    "in_scope": len(scope), "covered": len(covered),
                    "pct": round(100 * len(covered) / len(scope)) if scope else 0,
                    "unmapped": [r for r in scope if r not in m.get(fw, {})]})
    for fw in sorted(set(m) - set(prog.records)):
        out.append({"framework": fw, "name": prog.framework_name(fw), "record": None,
                    "in_scope": None, "covered": len(m[fw]), "pct": None, "unmapped": []})
    return out


def reuse(c: dict) -> int:
    return sum(len(v) for v in (c.get("maps") or {}).values())


def scorecard(prog: Program) -> dict:
    """The program's KPIs, for the quarterly report to security leadership."""
    t = prog.today
    ctls = [c for c in prog.controls if isinstance(c, dict)]
    # frameworks the organization reports against (one record each); reference catalogs don't count here
    multi = [c for c in ctls if len([fw for fw, v in (c.get("maps") or {}).items() if v and fw in prog.records]) >= 2]
    automated = [c for c in ctls if c.get("type") == "automated"]
    ev_refs = [(c["id"], r) for c in ctls for r in c.get("evidence") or []]
    current = 0
    for _, r in ev_refs:
        rec, ev = prog.evidence(r)
        current += bool(ev is not None and rec.evidence_is_current(ev))
    # calendar: occurrences due in the last 90 days
    window = [(ob, o) for ob in prog.obligations for o in occurrences(prog, ob)
              if t - dt.timedelta(days=90) <= o["due"] <= t and (o["due"] < t or o["done"])]
    on_time = sum(1 for _, o in window if o["status"] == "done_on_time")
    overdue_now = [(ob, o) for ob in prog.obligations for o in occurrences(prog, ob) if o["status"] == "overdue"]
    # certification: the latest period with files, else the quarter that just ended
    periods = sorted(p for p in prog.certifications if PERIOD.match(p))
    period = periods[-1] if periods else previous_quarter(t)
    cert = certification_status(prog, period)
    # findings and gaps across records
    open_findings, ages, closed_days = 0, [], []
    for rec in prog.records.values():
        for fnd in rec.findings:
            if not isinstance(fnd, dict):
                continue
            raised = _date(fnd.get("raised_on"))
            closed = _date((fnd.get("effectiveness") or {}).get("reviewed_on")) \
                if isinstance(fnd.get("effectiveness"), dict) else None
            if fnd.get("status") not in ("closed", "accepted"):
                open_findings += 1
                if raised:
                    ages.append((t - raised).days)
            elif raised and closed:
                closed_days.append((closed - raised).days)
    open_gaps = sum(1 for rec in prog.records.values() for g in rec.gaps
                    if isinstance(g, dict) and g.get("status") not in ("closed", "risk_accepted")
                    and rec.gap_in_scope(g))
    return {
        "as_of": t.isoformat(),
        "controls": len(ctls),
        "requirements_mapped": sum(reuse(c) for c in ctls),
        "avg_requirements_per_control": round(sum(reuse(c) for c in ctls) / len(ctls), 1) if ctls else 0,
        "multi_framework_controls": len(multi),
        "automated_controls_pct": round(100 * len(automated) / len(ctls)) if ctls else 0,
        "evidence_current_pct": round(100 * current / len(ev_refs)) if ev_refs else 0,
        "controls_without_evidence": sum(1 for c in ctls if not c.get("evidence")),
        "coverage": [{k: v for k, v in x.items() if k != "unmapped"} for x in coverage(prog)],
        "obligations": len(prog.obligations),
        "obligations_due_90d": len(window),
        "obligations_on_time_pct": round(100 * on_time / len(window)) if window else None,
        "obligations_overdue": len(overdue_now),
        "certification": cert,
        "certification_pct": round(100 * cert["certified"] / cert["owners"]) if cert["owners"] else None,
        "open_findings": open_findings,
        "findings_over_90d": sum(1 for a in ages if a > 90),
        "avg_days_to_close_finding": round(sum(closed_days) / len(closed_days)) if closed_days else None,
        "open_gaps": open_gaps,
    }


# ------------------------------------------------------------------ issues for due obligations
OBL_MARKER = re.compile(r"<!-- grc:obligation:([A-Za-z0-9._-]+)@(\d{4}-\d{2}-\d{2}) -->")


def obligation_items(prog: Program) -> list[dict]:
    """One item per occurrence that is due soon, overdue, or done (to close its issue)."""
    items = []
    for ob in prog.obligations:
        for o in occurrences(prog, ob):
            if o["status"] == "upcoming":
                continue
            key = f"{ob['id']}@{o['due'].isoformat()}"
            is_open = o["status"] in ("due_soon", "overdue")
            lines = [f"<!-- grc:obligation:{key} -->",
                     f"**{ob.get('title')}** is due **{o['due']}** ({ob.get('every')}). Owner: **{ob.get('owner')}**.", ""]
            if ob.get("evidence_expected"):
                lines += [f"Evidence of completion: {ob['evidence_expected']}", ""]
            if ob.get("source"):
                lines += [f"Why: {ob['source']}", ""]
            if ob.get("controls"):
                lines += [f"Controls: {', '.join(map(str, ob['controls']))}", ""]
            lines += ["To close this issue, add the completion to `program/calendar.yaml` in a pull request:", "",
                      "```yaml", "    done:", f"      - {{period: {o['due']}, completed: YYYY-MM-DD, by: <name>, "
                      "evidence: [<framework>:<EV-id>]}", "```"]
            items.append({"key": key, "open": is_open, "owner": ob.get("owner"),
                          "title": f"[{'Overdue' if o['status'] == 'overdue' else 'Due'} {o['due']}] {ob.get('title')}",
                          "body": "\n".join(lines)})
    return items


def sync_obligation_issues(prog: Program, repo: str | None, token: str | None, apply: bool = False) -> list[str]:
    items = obligation_items(prog)
    if not apply or not (repo and token):
        return [f"[dry-run] {'open' if i['open'] else 'closed':6} {i['title']}" for i in items] or ["Nothing due."]
    from .issues import GitHub, _assignable, _with_assignees
    gh, log = GitHub(repo, token), []
    labels = {lab["name"] for lab in gh.paged("/labels")}
    if "grc-obligation" not in labels:
        gh.call("POST", "/labels", {"name": "grc-obligation", "color": "1D76DB"})
    found = {}
    for iss in gh.paged("/issues?state=all&labels=grc-obligation"):
        m = OBL_MARKER.search(iss.get("body") or "")
        if m:
            found[f"{m.group(1)}@{m.group(2)}"] = iss
    for it in items:
        cur = found.get(it["key"])
        if not it["open"] and (cur is None or cur.get("state") == "closed"):
            continue                                       # done, and nothing open to close
        payload = {"title": it["title"], "body": it["body"], "labels": ["grc-obligation"],
                   "state": "open" if it["open"] else "closed"}
        users = _assignable(prog.github_users(it["owner"]))
        if users:
            payload["assignees"] = users
        if cur:
            _with_assignees(gh, "PATCH", f"/issues/{cur['number']}", payload, log, it["key"])
            log.append(f"updated #{cur['number']} {it['key']} ({payload['state']})")
        else:
            payload.pop("state")
            iss = _with_assignees(gh, "POST", "/issues", payload, log, it["key"])
            log.append(f"created #{iss['number']} {it['key']}")
    return log or ["Nothing due."]


# ------------------------------------------------------------------ who actually signed (CI, on a pull request)
def check_signers(prog: Program, repo: str, token: str | None, pr: int, transport=None) -> list[Finding]:
    """P311/P312: a signed certification changed in pull request `pr` must have been committed by its signer.

    certified_by is text anyone with write access could type; the commit that last changed the file, as GitHub
    attributes it, is not. Web edits are signed by GitHub (verified); a local commit's author can be set to any
    email, so an unverified one is reported too.
    """
    from .issues import GitHub
    gh = GitHub(repo, token or "")
    get = transport or (lambda path: gh.call("GET", path))
    out: list[Finding] = []
    info = get(f"/pulls/{pr}") or {}
    head = (info.get("head") or {}).get("sha")
    files, page = [], 1
    while True:
        batch = get(f"/pulls/{pr}/files?per_page=100&page={page}") or []
        files += [x.get("filename") for x in batch if x.get("status") != "removed"]
        if len(batch) < 100:
            break
        page += 1
    for path in files:
        m = re.fullmatch(r"program/certifications/([^/]+)/([^/]+)\.yaml", path or "")
        if not m:
            continue
        d = prog.certifications.get(m.group(1), {}).get(m.group(2)) or {}
        signer = str(d.get("certified_by") or "").strip().lstrip("@")
        if not signer:
            continue
        commits = get(f"/commits?sha={head}&path={path}&per_page=1") or []
        if not commits:
            continue
        c = commits[0]
        who = ((c.get("author") or {}).get("login") or "").strip()
        verified = bool(((c.get("commit") or {}).get("verification") or {}).get("verified"))
        if who.lower() != signer.lower():
            out.append(Finding("error", "P311", f"{path}: signed as '{signer}', but the change was committed by "
                                                f"'{who or 'an unknown GitHub user'}'. The owner must make the signing "
                                                "commit themselves (for example by editing the file on GitHub)", path))
        elif not verified:
            out.append(Finding("warning", "P312", f"{path}: the signing commit by '{who}' isn't verified by GitHub, so "
                                                  "its author could have been set by someone else. Sign on GitHub, or "
                                                  "use a signed commit", path))
    return out
