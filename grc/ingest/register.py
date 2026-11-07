"""A customer's existing control register: an export from a GRC tool (Vanta, Drata, Secureframe, Hyperproof,
AuditBoard and the like), their own spreadsheet of controls, or a Statement of Applicability.

No AI is involved. The header row is recognized by its column names (a control name, plus a framework-mapping or
requirements column), on any sheet of a workbook; each row's mapping cells are searched for this record's
requirement ids, written the way tools write them ("CC6.1", "ISO 27001: A.5.15", "Annex A 8.8", "Art. 32(1)(b)",
"164.308(a)(1)(ii)(A)", "AC-2 (3)").

Every row is kept in the record's existing-controls.yaml, mapped or not, for the gap assessment. A row's status
turns into a claim (a hypothesis, never evidence) or a gap:
  in place        -> documented and implemented claims on each mapped requirement
  partial         -> a documented claim, and a medium gap            (in progress, draft, exception, deviation)
  planned         -> a medium gap                                    (planned, not started, deferred, backlog)
  not in place    -> a high gap (medium for an accepted risk)        (not implemented, failing, missing)
  not applicable  -> nothing                                         (N/A, out of scope, excluded, retired)
  unknown/blank   -> a documented claim (the control is written down; whether it runs is unknown)
A register gap carries the register and the control (`register: <register>/<control>`), so re-importing the
register finds it again instead of adding another.
"""
from __future__ import annotations

import re
from pathlib import Path

from .draft import empty

# column name synonyms, lower-cased with spaces and punctuation removed; within a role, earlier names win
COLUMNS = {
    "ref": ["controlid", "controlref", "controlnumber", "controlno", "controlidentifier", "controlcode", "id", "ref",
            "reference", "code", "key", "number", "no"],
    "name": ["controlname", "controltitle", "title", "name", "controlstatement", "control"],
    "description": ["description", "controldescription", "details", "controldetails", "activity", "controlactivity",
                    "statement", "implementation", "implementationdetails", "procedure"],
    "owner": ["owner", "controlowner", "assignee", "responsible", "responsibleparty", "accountable", "assignedto"],
    "status": ["status", "implementationstatus", "controlstatus", "state", "health", "teststatus", "testresult",
               "result", "compliancestatus", "effectiveness", "implemented"],
    "applicable": ["applicable", "applicability", "inscope", "included", "applies"],
    "evidence": ["evidence", "evidencelocation", "evidencename", "linkedevidence", "documents", "tests"],
    "tested": ["lasttested", "lasttestdate", "lastreviewed", "lastreview", "testdate", "lastchecked", "updated", "lastupdated"],
}
TEXT_ROLES = ("ref", "name", "description", "owner", "status", "applicable", "evidence", "tested")
MAPPING_WORDS = ["framework", "mapping", "requirement", "criteria", "criterion", "clause", "annex",
                 "article", "citation", "standard", "regulation", "tsc", "ksi"]

# framework hints in a column name or a cell
HINTS = {
    "iso27001": r"27001",
    "iso42001": r"42001",
    "soc2": r"soc\s*2|soc2|trust services|\btsc\b|aicpa",
    "hipaa": r"hipaa|45\s*cfr|164\.\d",
    "gdpr": r"gdpr|2016/679",
    "txramp": r"tx-?ramp|800-53|nist",
    "fedramp20x": r"fedramp|\bksi\b",
    "cbpr": r"cbpr|\bprp\b|cross-border privacy",
}
HINT_RE = {k: re.compile(v, re.I) for k, v in HINTS.items()}
# a comma starts a new piece when a framework name follows it: "ISO 42001 9.2, ISO 27001 A.5.1"
PIECES = re.compile(r"[;\n|]+|,(?=\s*(?:iso|soc|hipaa|gdpr|nist|tx-?ramp|fedramp|cbpr|prp|ksi|45\s*cfr|aicpa)\b)", re.I)

NOT_APPLICABLE = re.compile(r"^(n/?a|not applicable|not relevant|out of scope|excluded|exclude|retired|deprecated|"
                            r"disabled|inactive|no longer used|not in scope)$", re.I)
IN_PLACE = re.compile(r"^(implemented|fully implemented|in place|operating|operating effectively|effective|compliant|"
                      r"passing|passed|pass|ok|okay|healthy|complete|completed|done|yes|y|active|met|fully met|green|"
                      r"monitored|ready|configured|enabled|in use|true|1|x)$", re.I)
ACCEPTED = re.compile(r"\b(accepted risk|risk accepted|risk acceptance)\b", re.I)
NOT_IN_PLACE = re.compile(r"\b(not implemented|not in place|missing|gaps?|fail|failing|failed|non-?compliant|no|n|false|"
                          r"0|not met|ineffective|overdue|needs attention|needs remediation|at risk|red|not operating|"
                          r"deficien\w*|not configured|not enabled)\b", re.I)
PLANNED = re.compile(r"\b(planned|scheduled|not started|to ?do|backlog|deferred|future|roadmap|proposed)\b", re.I)
PARTIAL = re.compile(r"\b(partial\w*|in progress|in-progress|draft|started|amber|yellow|needs review|pending|due soon|"
                     r"exception|deviation|some|limited)\b", re.I)

STATES = ("in_place", "partial", "planned", "not_in_place", "not_applicable", "unknown")


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def _roles(header: list[str]) -> dict[str, int]:
    """Column index per role; within a role, the column whose name comes earliest in its synonym list wins
    ("Control Name" over a bare "Control"). A header with '#' ("Control #") is an id."""
    best: dict[str, tuple[int, int]] = {}
    for i, col in enumerate(header):
        n = _norm(col)
        if "#" in str(col) and n in ("control", "", "controls"):
            cand = [("ref", 0)]
        else:
            cand = [(r, names.index(n)) for r, names in COLUMNS.items() if n in names]
        for role, rank in cand:
            if role not in best or rank < best[role][1]:
                best[role] = (i, rank)
    return {r: v[0] for r, v in best.items()}


def _mapping_cols(header: list[str], roles: dict[str, int]) -> list[int]:
    taken = set(roles.values())
    out = []
    for i, col in enumerate(header):
        h = str(col or "").lower()
        if i in taken:
            continue
        if any(w in h for w in MAPPING_WORDS) or any(r.search(h) for r in HINT_RE.values()):
            out.append(i)
    return out


def find_header(table: list[list[str]]) -> int | None:
    """Index of the header row (an export may start with a title or blank lines): within the first 15 rows,
    one with a control-name column and a mapping column."""
    for i, row in enumerate(table[:15]):
        if not row or not any(str(c).strip() for c in row):
            continue
        roles = _roles(row)
        if "name" in roles and _mapping_cols(row, roles):
            return i
    return None


def detect(table: list[list[str]]) -> bool:
    return bool(table) and find_header(table) is not None


def state_of(status: str, applicable: str = "") -> str:
    a = str(applicable or "").strip()
    if a and (NOT_APPLICABLE.match(a) or re.fullmatch(r"(?i)no|n|false|0|excluded", a)):
        return "not_applicable"
    s = str(status or "").strip()
    if not s:
        return "unknown"
    if NOT_APPLICABLE.match(s):
        return "not_applicable"
    if IN_PLACE.match(s):
        return "in_place"
    if ACCEPTED.search(s):
        return "not_in_place"
    if PLANNED.search(s):
        return "planned"
    if PARTIAL.search(s):
        return "partial"
    if NOT_IN_PLACE.search(s):
        return "not_in_place"
    return "unknown"


# ------------------------------------------------------------------ requirement ids as tools write them
def _trim(i: str) -> list[str]:
    """164.308(a)(1)(ii)(A) -> itself, then 164.308(a)(1)(ii), 164.308(a)(1), ...: the deepest id the catalog has."""
    out = [i]
    while "(" in i:
        i = i[:i.rindex("(")]
        out.append(i)
    return out


def _resolve(cands: list[str], known: set[str]) -> list[str]:
    """The first candidate the catalog has; failing that, the catalog's parts of the first candidate (a register
    that cites "Article 32" or "164.308(a)(1)" means all of it)."""
    for c in cands:
        if c in known:
            return [c]
    parts = sorted(k for k in known if k.startswith(cands[0] + "(") or k.startswith(cands[0] + "."))
    return parts if cands[0] and parts and ("(" in parts[0] or cands[0].startswith("A.")) else []


ISO_CLAUSE = re.compile(r"^(?:4\.[1-4]|5\.[1-3]|6\.[1-3](?:\.\d)?|7\.[1-5](?:\.\d)?|8\.[1-4](?:\.\d)?|9\.[1-3](?:\.\d)?|10\.[12])$")


def ids_in(text: str, fw: str, known: set[str], hinted: bool = False, annex: bool = False) -> tuple[list[str], list[str]]:
    """(ids of framework fw found in text that the catalog knows, references that look like ids but aren't known).
    hinted: the piece or its column names this framework, so bare numbers ("5.2", "PR 12") may be read as ids.
    annex: the column or piece says Annex A, so a bare "5.15" is A.5.15."""
    found, unknown = [], []

    def add(cands: list[str], raw: str):
        hit = _resolve(cands, known)
        for h in hit:
            if h not in found:
                found.append(h)
        if not hit and raw.strip() and raw.strip() not in unknown:
            unknown.append(raw.strip())
    t = str(text or "")
    if fw in ("iso27001", "iso42001"):
        annex = annex or bool(re.search(r"annex", t, re.I))
        for m in re.finditer(r"(?:annex\s*)?\bA\s*\.?\s*(\d{1,2}(?:\.\d{1,2}){1,2})\b", t, re.I):
            add([f"A.{m.group(1)}"], m.group(0))
        rest = re.sub(r"(?:annex\s*)?\bA\s*\.?\s*\d{1,2}(?:\.\d{1,2}){1,2}\b", " ", t, flags=re.I)
        rest = re.sub(r"\b(?:iso|iec)\s*/?\s*(?:iec\s*)?\d{4,5}(?::\d{4})?|\b(?:27001|42001)(?::\d{4})?", " ", rest, flags=re.I)
        if hinted or annex or re.search(r"clause", t, re.I):
            for m in re.finditer(r"(?:clause\s*)?\b(\d{1,2}(?:\.\d{1,2}){1,2})\b(?!\s*(?:hours?|hrs|days?|%|mb|gb))", rest, re.I):
                n = m.group(1)
                if annex or not ISO_CLAUSE.match(n):
                    add([f"A.{n}"], m.group(0))
                else:
                    add([n], m.group(0))
    elif fw == "soc2":
        for m in re.finditer(r"\b(CC|PI|[ACP])\s?(\d{1,2})\s?\.\s?(\d{1,2})\b", t, re.I):
            add([f"{m.group(1).upper()}{m.group(2)}.{m.group(3)}"], m.group(0))
    elif fw == "hipaa":
        for m in re.finditer(r"164\s*\.\s*(\d{3})((?:\s*\(\s*[A-Za-z0-9]+\s*\))*)", t):
            add(_trim("164." + m.group(1) + re.sub(r"\s+", "", m.group(2))), m.group(0))
    elif fw == "gdpr":
        for m in re.finditer(r"\bArt(?:icle)?s?\s*\.?\s*(\d{1,2})((?:\s*\(\s*\w{1,4}\s*\))*)", t, re.I):
            add(_trim("Art" + m.group(1) + re.sub(r"\s+", "", m.group(2))), m.group(0))
    elif fw == "txramp":
        for m in re.finditer(r"\b([A-Z]{2})\s?-\s?(\d{1,2})(?:\s?\(\s?(\d{1,2})\s?\))?", t):
            add(_trim(f"{m.group(1)}-{int(m.group(2))}" + (f"({int(m.group(3))})" if m.group(3) else "")), m.group(0))
    elif fw == "fedramp20x":
        for m in re.finditer(r"\b[A-Z]{3}-[A-Z]{3}-[A-Z]{3}\b", t):
            add([m.group(0)], m.group(0))
    elif fw == "cbpr":
        for m in re.finditer(r"\b(PRP|PR)(\s?)(\d{1,2})\b", t):
            if m.group(2) and not hinted:      # "PR 12" in prose is a pull request unless the column says CBPR
                continue
            add([f"{m.group(1)}{int(m.group(3))}"], m.group(0))
    else:   # a framework the engine doesn't know how tools write: exact ids only
        for tok in re.split(r"[\s;,|]+", t):
            if tok in known:
                add([tok], tok)
    return found, unknown


def _hint(text: str) -> set[str]:
    return {k for k, r in HINT_RE.items() if r.search(str(text or ""))}


def mapped_ids(cells: list[tuple[str, str]], fw: str, known: set[str]) -> tuple[list[str], list[str], bool]:
    """cells: (column header, value) of a row's mapping columns. Returns (ids, unrecognised references, whether
    the row names any framework at all). A piece of a cell that names another framework is skipped."""
    ids, other, named = [], [], False
    same = lambda hint: fw in hint
    for header, value in cells:
        head_hint = _hint(header)
        head_annex = bool(re.search(r"annex", str(header), re.I))
        if head_hint and not same(head_hint):
            named = named or bool(str(value).strip())
            continue
        for piece in PIECES.split(str(value or "")):
            if not piece or not piece.strip():
                continue
            piece_hint = _hint(piece)
            hint = piece_hint or head_hint
            named = named or bool(hint)
            if hint and not same(hint):
                continue
            got, unknown = ids_in(piece, fw, known, hinted=bool(hint), annex=head_annex)
            ids += [i for i in got if i not in ids]
            if hint:
                other += [u for u in unknown if u not in other]
    return ids, other, named


# ------------------------------------------------------------------ the register as a draft
def register_name(file_name: str) -> str:
    """A register's identity across exports: the file name without folders, extension, dates, versions or
    copy markers ("exports/Vanta Controls 2026-11-06 (1).csv" -> "vanta-controls")."""
    s = Path(str(file_name)).stem.lower()
    s = re.sub(r"\(\d+\)|\bcopy\b|\bfinal\b|\bv\d+(\.\d+)*\b|\d{4}[-_.]?\d{2}[-_.]?\d{2}|\d{8}|\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4}",
               " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "register"


def to_draft(table: list[list[str]], source: str, fw: str, known: set[str], label: str = "",
             register: str | None = None) -> tuple[dict, list[dict], list[str]]:
    """(draft for apply, rows for existing-controls.yaml, notes). `source` names the file (and sheet); row numbers
    are counted from the table as given, so blank rows must be kept in it."""
    d, rows, notes = empty(), [], []
    label = label or fw
    reg = register or register_name(source.split(" sheet ")[0])
    h = find_header(table)
    if h is None:
        return d, rows, ["not recognized as a control register"]
    header = table[h]
    roles = _roles(header)
    mapping_cols = _mapping_cols(header, roles)
    unmapped = nameless = 0
    for n, raw in enumerate(table[h + 1:], start=h + 2):
        cell = lambda role: str(raw[roles[role]] if role in roles and roles[role] < len(raw) else "").strip()
        if not any(str(c).strip() for c in raw):
            continue
        name = cell("name") or cell("ref") or cell("description")[:80]
        if not name or name.startswith("#"):
            nameless += 1
            continue
        src = f"{source} row {n}"
        ids, other, _ = mapped_ids([(header[i], raw[i] if i < len(raw) else "") for i in mapping_cols], fw, known)
        status = cell("status")
        state = state_of(status, cell("applicable"))
        row = {"register": reg, "ref": cell("ref"), "name": name, "description": cell("description")[:600],
               "owner": cell("owner"), "status": status, "state": state, "maps": ids, "source": src}
        if cell("applicable"):
            row["applicable"] = cell("applicable")
        if other:
            row["unrecognized"] = other
        if cell("tested"):
            row["last_tested"] = cell("tested")
        if cell("evidence"):
            row["evidence"] = cell("evidence")[:300]
        rows.append(row)
        if not ids:
            unmapped += 1
            continue
        ctl = f"{row['ref'] + ' ' if row['ref'] else ''}{name}"
        said = f"listed in the client's control register as '{status}'" if status else "listed in the client's control register"
        what = f"{ctl}: {said}" + (f". {row['description'][:200]}" if row["description"] else "")
        if state in ("in_place", "unknown", "partial"):
            legs = ["documented", "implemented"] if state == "in_place" else ["documented"]
            for rid in ids:
                for leg in legs:
                    d["claims"].append({"requirement": rid, "leg": leg, "statement": what, "owner": row["owner"], "source": src})
        if state in ("partial", "planned", "not_in_place"):
            sev = "high" if state == "not_in_place" and not ACCEPTED.search(status) else "medium"
            d["gaps"].append({"area": name[:80], "finding": f"The client's control register shows {ctl} as '{status}'.",
                              "requirements": ids, "owner": row["owner"], "severity": sev, "source": src,
                              "register": f"{reg}/{row['ref'] or name}"[:160]})
    if unmapped:
        notes.append(f"{unmapped} of {len(rows)} control(s) map to no {label} requirement; they are listed in the gap "
                     "assessment so an analyst can map them or confirm they are out of scope")
    if nameless:
        notes.append(f"{nameless} row(s) with no control name, id or description were skipped")
    unknown = sorted({u for r in rows for u in r.get("unrecognized", [])})
    if unknown:
        notes.append(f"references to {label} requirements that aren't in this record's catalog or scope: "
                     f"{', '.join(unknown[:12])}{' …' if len(unknown) > 12 else ''}")
    return d, rows, notes


FILE = "existing-controls.yaml"
HEAD = """# The client's existing controls, imported from their control register by `grc ingest`. Each row keeps what the
# register said (status as written) and the requirement ids found in its mapping columns (`maps`). These are the
# client's statements, not evidence: the gap assessment reports on them, and an analyst may correct `maps`.
# Re-ingesting a register (by its name without dates or versions) replaces the rows that came from it.
"""


def load_rows(engagement_dir) -> list[dict]:
    import yaml
    path = Path(engagement_dir) / FILE
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    rows = data.get("controls") if isinstance(data, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def save(engagement_dir, by_register: dict[str, list[dict]]) -> None:
    import yaml
    path = Path(engagement_dir) / FILE
    keep = [r for r in load_rows(engagement_dir) if str(r.get("register") or "") not in by_register]
    rows = keep + [r for k in sorted(by_register) for r in by_register[k]]
    path.write_text(HEAD + yaml.safe_dump({"controls": rows}, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")


def stale_gaps(gaps: list[dict], by_register: dict[str, list[dict]]) -> list[str]:
    """Open register gaps that the re-imported register no longer supports (the control is now in place, not
    applicable, or gone): listed for an analyst to close with evidence. Nothing is closed automatically."""
    now = {f"{reg}/{r.get('ref') or r.get('name')}"[:160]: r.get("state") for reg, rows in by_register.items() for r in rows}
    out = []
    for g in gaps:
        key = str(g.get("register") or "") if isinstance(g, dict) else ""
        if not key or g.get("status") not in ("open", "in_progress") or key.split("/", 1)[0] not in by_register:
            continue
        st = now.get(key)
        if st not in ("partial", "planned", "not_in_place"):
            out.append(f"{g.get('id')} ({key}): the register now shows it as "
                       + ("not listed" if st is None else st.replace("_", " ")) + "; close it with evidence if it is fixed")
    return out
