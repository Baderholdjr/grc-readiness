"""A customer's existing control register: an export from a GRC tool (Vanta, Drata, Secureframe, Hyperproof,
AuditBoard and the like) or their own spreadsheet of controls.

No AI is involved. The header row is recognized by its column names (a control name, plus a framework-mapping or
requirements column); each row's mapping cells are searched for this record's requirement ids, written the way
tools write them ("CC6.1", "ISO 27001: A.5.15", "Art. 32(1)(b)", "164.308(a)(1)(ii)(A)", "AC-2 (3)").

Every row is kept in the record's existing-controls.yaml, mapped or not, for the gap assessment. A row's status
turns into a claim (a hypothesis, never evidence) or a gap:
  in place      -> documented and implemented claims on each mapped requirement
  partial       -> a documented claim, and a medium gap
  not in place  -> a high gap
  unknown/blank -> a documented claim (the control is written down; whether it runs is unknown)
"""
from __future__ import annotations

import re

from .draft import empty

# column name synonyms, lower-cased with spaces and punctuation removed
COLUMNS = {
    "ref": ["controlid", "id", "ref", "controlref", "reference", "controlnumber", "controlcode", "code", "key", "number", "no"],
    "name": ["control", "controlname", "name", "title", "controltitle", "controlstatement"],
    "description": ["description", "controldescription", "details", "controldetails", "activity", "controlactivity",
                    "statement", "implementation", "procedure"],
    "owner": ["owner", "controlowner", "assignee", "responsible", "responsibleparty", "accountable", "assignedto"],
    "status": ["status", "implementationstatus", "controlstatus", "state", "health", "teststatus", "testresult",
               "result", "compliancestatus", "effectiveness"],
    "evidence": ["evidence", "evidencelocation", "evidencename", "linkedevidence", "documents", "tests"],
    "tested": ["lasttested", "lasttestdate", "lastreviewed", "lastreview", "testdate", "lastchecked", "updated", "lastupdated"],
}
MAPPING_WORDS = ["framework", "mapping", "requirement", "criteria", "criterion", "reference", "clause", "annex",
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

IN_PLACE = re.compile(r"^(implemented|fully implemented|in place|operating|operating effectively|effective|compliant|"
                      r"passing|passed|pass|ok|okay|healthy|complete|completed|done|yes|y|active|met|fully met|green|"
                      r"monitored|ready)$", re.I)
PARTIAL = re.compile(r"partial|in progress|in-progress|draft|planned|started|some|amber|yellow|needs review|"
                     r"pending|due soon|partially", re.I)
NOT_IN_PLACE = re.compile(r"not implemented|not in place|not started|missing|gap|fail|non-?compliant|^no$|^n$|not met|"
                          r"ineffective|overdue|needs attention|needs remediation|at risk|red|not operating|deficien",
                          re.I)


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def _role(header: str) -> str | None:
    n = _norm(header)
    for role, names in COLUMNS.items():
        if n in names:
            return role
    return None


def _is_mapping(header: str) -> bool:
    h = str(header or "").lower()
    return any(w in h for w in MAPPING_WORDS) or any(r.search(h) for r in HINT_RE.values())


def find_header(table: list[list[str]]) -> int | None:
    """Index of the header row (an export may start with a title or a blank line): within the first 10 rows,
    one with a control-name column and a mapping column."""
    for i, row in enumerate(table[:10]):
        roles = {_role(h) for h in row}
        if "name" in roles and any(_is_mapping(h) and _role(h) not in ("name", "description") for h in row):
            return i
    return None


def detect(table: list[list[str]]) -> bool:
    return bool(table) and find_header(table) is not None


def state_of(status: str) -> str:
    s = str(status or "").strip()
    if not s:
        return "unknown"
    if NOT_IN_PLACE.search(s):
        return "not_in_place"
    if IN_PLACE.match(s):
        return "in_place"
    if PARTIAL.search(s):
        return "partial"
    return "unknown"


# ------------------------------------------------------------------ requirement ids as tools write them
def _first_known(cands: list[str], known: set[str]) -> str | None:
    for c in cands:
        if c in known:
            return c
    return None


def _trim(i: str) -> list[str]:
    """164.308(a)(1)(ii)(A) -> itself, then 164.308(a)(1)(ii), 164.308(a)(1), ...: the deepest id the catalog has."""
    out = [i]
    while "(" in i:
        i = i[:i.rindex("(")]
        out.append(i)
    return out


def ids_in(text: str, fw: str, known: set[str]) -> tuple[list[str], list[str]]:
    """(ids of framework fw found in text that the catalog knows, references that look like ids but aren't known)."""
    found, unknown = [], []

    def add(cands: list[str], raw: str):
        hit = _first_known(cands, known)
        if hit:
            if hit not in found:
                found.append(hit)
        elif raw.strip() and raw.strip() not in unknown:
            unknown.append(raw.strip())
    t = str(text or "")
    if fw in ("iso27001", "iso42001"):
        for m in re.finditer(r"(?:annex\s*)?\bA\s*\.?\s*(\d{1,2}(?:\.\d{1,2}){1,2})\b", t, re.I):
            add([f"A.{m.group(1)}"], m.group(0))
        rest = re.sub(r"(?:annex\s*)?\bA\s*\.?\s*\d{1,2}(?:\.\d{1,2}){1,2}\b", " ", t, flags=re.I)
        rest = re.sub(r"\b(?:iso|iec)\s*/?\s*(?:iec\s*)?\d{4,5}(?::\d{4})?", " ", rest, flags=re.I)
        for m in re.finditer(r"(?:clause\s*)?\b(\d{1,2}(?:\.\d{1,2}){0,2})\b", rest, re.I):
            if 4 <= int(m.group(1).split(".")[0]) <= 10 and "." in m.group(1):
                add([m.group(1)], m.group(0))
    elif fw == "soc2":
        for m in re.finditer(r"\b(CC|PI|[ACP])\s?(\d{1,2})\s?\.\s?(\d{1,2})\b", t):
            add([f"{m.group(1)}{m.group(2)}.{m.group(3)}"], m.group(0))
    elif fw == "hipaa":
        for m in re.finditer(r"164\s*\.\s*(\d{3})((?:\s*\(\s*[A-Za-z0-9]+\s*\))*)", t):
            i = "164." + m.group(1) + re.sub(r"\s+", "", m.group(2))
            add(_trim(i), m.group(0))
    elif fw == "gdpr":
        for m in re.finditer(r"\bArt(?:icle)?s?\s*\.?\s*(\d{1,2})((?:\s*\(\s*\w{1,4}\s*\))*)", t, re.I):
            i = "Art" + m.group(1) + re.sub(r"\s+", "", m.group(2))
            add(_trim(i), m.group(0))
    elif fw == "txramp":
        for m in re.finditer(r"\b([A-Z]{2})\s?-\s?(\d{1,2})(?:\s?\(\s?(\d{1,2})\s?\))?", t):
            i = f"{m.group(1)}-{int(m.group(2))}" + (f"({int(m.group(3))})" if m.group(3) else "")
            add(_trim(i), m.group(0))
    elif fw == "fedramp20x":
        for m in re.finditer(r"\b[A-Z]{3}-[A-Z]{3}-[A-Z]{3}\b", t):
            add([m.group(0)], m.group(0))
    elif fw == "cbpr":
        for m in re.finditer(r"\b(PRP|PR)\s?(\d{1,2})\b", t):
            add([f"{m.group(1)}{int(m.group(2))}"], m.group(0))
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
    for header, value in cells:
        head_hint = _hint(header)
        if head_hint and fw not in head_hint and not (fw == "txramp" and "txramp" in head_hint):
            named = named or bool(str(value).strip())
            continue
        for piece in re.split(r"[;\n|]+", str(value or "")):
            if not piece.strip():
                continue
            hint = _hint(piece) or head_hint
            named = named or bool(hint)
            if hint and fw not in hint:
                continue
            got, unknown = ids_in(piece, fw, known)
            ids += [i for i in got if i not in ids]
            if hint and fw in hint:
                other += [u for u in unknown if u not in other]
    return ids, other, named


# ------------------------------------------------------------------ the register as a draft
def to_draft(table: list[list[str]], source: str, fw: str, known: set[str], label: str = "") -> tuple[dict, list[dict], list[str]]:
    """(draft for apply, rows for existing-controls.yaml, notes)."""
    d, rows, notes = empty(), [], []
    label = label or fw
    h = find_header(table)
    if h is None:
        return d, rows, ["not recognized as a control register"]
    header = table[h]
    roles: dict[str, int] = {}
    for i, col in enumerate(header):
        r = _role(col)
        if r and r not in roles:
            roles[r] = i
    mapping_cols = [i for i, col in enumerate(header) if _is_mapping(col) and _role(col) not in ("name", "description", "ref")]
    unmapped = 0
    for n, raw in enumerate(table[h + 1:], start=h + 2):
        cell = lambda role: (raw[roles[role]] if role in roles and roles[role] < len(raw) else "").strip()
        name = cell("name")
        if not name or name.startswith("#"):
            continue
        src = f"{source} row {n}"
        ids, other, named = mapped_ids([(header[i], raw[i] if i < len(raw) else "") for i in mapping_cols], fw, known)
        status = cell("status")
        state = state_of(status)
        row = {"ref": cell("ref"), "name": name, "description": cell("description")[:600], "owner": cell("owner"),
               "status": status, "state": state, "maps": ids, "source": src}
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
        if state in ("partial", "not_in_place"):
            d["gaps"].append({"area": name[:80], "finding": f"The client's control register shows {ctl} as '{status}'.",
                              "requirements": ids, "owner": row["owner"],
                              "severity": "high" if state == "not_in_place" else "medium", "source": src})
    if unmapped:
        notes.append(f"{unmapped} of {len(rows)} control(s) map to no {label} requirement; they are listed in the gap "
                     "assessment so an analyst can map them or confirm they are out of scope")
    unknown = sorted({u for r in rows for u in r.get("unrecognized", [])})
    if unknown:
        notes.append(f"references to {label} requirements that aren't in this record's catalog or scope: {', '.join(unknown[:12])}{' …' if len(unknown) > 12 else ''}")
    return d, rows, notes


FILE = "existing-controls.yaml"
HEAD = """# The client's existing controls, imported from their control register by `grc ingest`. Each row keeps what the
# register said (status as written) and the requirement ids found in its mapping columns (`maps`). These are the
# client's statements, not evidence: the gap assessment reports on them, and an analyst may correct `maps`.
# Re-ingesting a changed register replaces the rows that came from it.
"""


def save(engagement_dir, by_file: dict[str, list[dict]]) -> None:
    import yaml
    from pathlib import Path
    path = Path(engagement_dir) / FILE
    data = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None) or {}
    keep = [r for r in data.get("controls") or [] if isinstance(r, dict)
            and not any(str(r.get("source", "")).startswith(f"{f} row ") for f in by_file)]
    rows = keep + [r for f in sorted(by_file) for r in by_file[f]]
    path.write_text(HEAD + yaml.safe_dump({"controls": rows}, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
