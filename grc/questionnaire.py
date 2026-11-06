"""Security questionnaires answered from the compliance program (docs/QUESTIONNAIRES.md).

A questionnaire arrives as a workbook (HECVAT 4 today). The engine:
  import  - copies the workbook into questionnaires/<name>/ and lists its questions, where each answer goes and
            which answers its dropdowns allow (questions.yaml);
  draft   - proposes an answer for every question it can: from approved answers in the answer library, from the
            company profile, and from the controls and records that back each question (answers.yaml);
  fill    - writes the approved answers back into a copy of the workbook, editing the sheet XML directly so the
            workbook keeps its dropdowns, formulas, formatting and scoring;
  learn   - copies approved answers into the library, so the next questionnaire starts from them;
  report  - what is approved, proposed and still open, and who should answer each open question.

Nothing automated approves an answer. `draft` only proposes; a person approves in a reviewed pull request
(approved_by, approved_on), and `fill` writes approved answers only unless asked for a marked draft.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from .model import ENGINE, load_schema, load_yaml
from .rules import Finding, requirement_state

QDIR = Path("questionnaires")
LIBRARY = QDIR / "library.yaml"
PROFILE = QDIR / "profile.yaml"
STATUSES = ("needs_answer", "proposed", "approved", "not_applicable")
CLOSED_GAP = ("closed", "risk_accepted")
FREE_TEXT = None          # allowed values for a cell with no dropdown


# ------------------------------------------------------------------ definitions
def definition_path(qid: str, root: Path | None = None) -> Path:
    local = (root or Path(".")) / QDIR / "definitions" / f"{qid}.yaml"
    return local if local.exists() else ENGINE / "questionnaires" / f"{qid}.yaml"


def definitions() -> list[str]:
    return sorted(p.stem for p in (ENGINE / "questionnaires").glob("*.yaml"))


def load_definition(qid: str, root: Path | None = None) -> dict:
    path = definition_path(qid, root)
    if not path.exists():
        raise SystemExit(f"questionnaire: no definition '{qid}' (built in: {', '.join(definitions())})")
    return load_yaml(path)


# ------------------------------------------------------------------ reading a workbook (read-only)
def _col_row(ref: str) -> tuple[str, int]:
    m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", ref)
    if not m:
        raise ValueError(f"not a cell reference: {ref}")
    return m.group(1), int(m.group(2))


def _expand(sqref: str) -> list[str]:
    """'C23 C25:C26' -> ['C23', 'C25', 'C26'] (single-column ranges, as questionnaires use)."""
    from openpyxl.utils import column_index_from_string, get_column_letter
    out = []
    for part in sqref.split():
        if ":" in part:
            a, b = part.split(":")
            (ca, ra), (cb, rb) = _col_row(a), _col_row(b)
            for ci in range(column_index_from_string(ca), column_index_from_string(cb) + 1):
                out += [f"{get_column_letter(ci)}{r}" for r in range(ra, rb + 1)]
        else:
            out.append(part)
    return out


class Workbook:
    """The parts of an .xlsx a questionnaire needs, read straight from the package."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.names = set(self.zip.namelist())
        wb = self.zip.read("xl/workbook.xml").decode("utf-8")
        rels = self.zip.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        targets = {m.group(1): m.group(2) for m in re.finditer(r'<Relationship [^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels)}
        targets.update({m.group(2): m.group(1) for m in re.finditer(r'<Relationship [^>]*?Target="([^"]+)"[^>]*?Id="([^"]+)"', rels)})
        self.sheets: dict[str, str] = {}
        for m in re.finditer(r"<sheet ([^>]*)/>", wb):
            attrs = dict(re.findall(r'([\w:]+)="([^"]*)"', m.group(1)))
            target = targets.get(attrs.get("r:id", ""), "")
            target = target.lstrip("/")
            self.sheets[_unescape(attrs["name"])] = target if target.startswith("xl/") else f"xl/{target}"
        self._values = None

    def xml(self, sheet: str) -> str:
        return self.zip.read(self.sheets[sheet]).decode("utf-8")

    def values(self):
        if self._values is None:
            import warnings

            import openpyxl
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._values = openpyxl.load_workbook(self.path, data_only=False, read_only=False)
        return self._values

    def cell(self, sheet: str, ref: str):
        return self.values()[sheet][ref].value

    def validations(self, sheet: str) -> dict[str, list[str]]:
        """cell -> allowed values, from the sheet's list validations (classic and x14)."""
        text = self.xml(sheet)
        out: dict[str, list[str]] = {}
        blocks = re.findall(r"<x14:dataValidation\b(.*?)</x14:dataValidation>", text, re.S)
        blocks += re.findall(r"<dataValidation\b(.*?)</dataValidation>", text, re.S)
        for b in blocks:
            if 'type="list"' not in b:
                continue
            f = re.search(r"<(?:xm:f|formula1)>(.*?)</(?:xm:f|formula1)>", b, re.S)
            sq = re.search(r'<xm:sqref>(.*?)</xm:sqref>', b) or re.search(r'sqref="([^"]+)"', b)
            if not (f and sq):
                continue
            allowed = self._list_values(_unescape(f.group(1)), sheet)
            for ref in _expand(sq.group(1)):
                out[ref] = allowed
        return out

    def _list_values(self, formula: str, sheet: str) -> list[str]:
        formula = formula.strip().lstrip("=")
        if formula.startswith('"'):
            return [v.strip() for v in formula.strip('"').split(",")]
        m = re.fullmatch(r"(?:'([^']+)'|([^!]+))!(\$?[A-Z]+\$?\d+)(?::(\$?[A-Z]+\$?\d+))?", formula)
        if not m:
            return []
        ws = self.values()[m.group(1) or m.group(2)]
        a, b = m.group(3).replace("$", ""), (m.group(4) or m.group(3)).replace("$", "")
        return [str(c.value) for row in ws[a:b] for c in row if c.value not in (None, "")]


def _unescape(s: str) -> str:
    return s.replace("&quot;", '"').replace("&apos;", "'").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def read_questions(wbk: Workbook, d: dict) -> list[dict]:
    """Every question that takes an answer: id, sheet, answer cell, detail cell, allowed values and text."""
    lay = d["layout"]
    pat = re.compile(lay["id_pattern"])
    qcols = lay["question_columns"]
    text = {}
    qs = wbk.values()[lay["question_sheet"]]
    for row in qs.iter_rows():
        by = {c.column_letter: c.value for c in row if c.value is not None}
        qid = by.get(qcols["id"])
        if isinstance(qid, str) and pat.fullmatch(qid.strip()):
            text[qid.strip()] = {k: str(by.get(col) or "").strip() for k, col in qcols.items() if k != "id"}
    out = []
    for sheet in lay["answer_sheets"]:
        ws = wbk.values()[sheet]
        dv = wbk.validations(sheet)
        for row in ws.iter_rows(min_col=1, max_col=1):
            c = row[0]
            if not (isinstance(c.value, str) and pat.fullmatch(c.value.strip())):
                continue
            ans_ref = f"{lay['answer_column']}{c.row}"
            current = ws[ans_ref].value
            if isinstance(current, str) and current.startswith("="):
                continue                       # filled from another sheet (the general questions repeat on each tab)
            qid = c.value.strip()
            allowed = dv.get(ans_ref, FREE_TEXT)
            t = text.get(qid, {})
            out.append({"id": qid, "sheet": sheet, "answer_cell": ans_ref,
                        "detail_cell": f"{lay['detail_column']}{c.row}" if lay.get("detail_column") else None,
                        "allowed": allowed, "question": t.get("text", ""), "compliant": t.get("compliant", ""),
                        "guidance": t.get("guidance", "")})
    return out


# ------------------------------------------------------------------ a questionnaire in the repository
@dataclass
class Questionnaire:
    root: Path
    name: str
    meta: dict
    definition: dict
    questions: list[dict]
    answers: list[dict]
    raw_answers: object = None

    @property
    def dir(self) -> Path:
        return self.root / QDIR / self.name

    @property
    def qindex(self) -> dict[str, dict]:
        return {q["id"]: q for q in self.questions}

    @property
    def aindex(self) -> dict[str, dict]:
        return {str(a.get("id")): a for a in self.answers if isinstance(a, dict)}

    def ref(self, qid: str) -> str:
        return f"{self.definition['id']}:{qid}"


def _yes_no(entries) -> None:
    """YAML reads an unquoted Yes/No as true/false; the workbook wants the words."""
    for e in entries or []:
        if isinstance(e, dict) and isinstance(e.get("answer"), bool):
            e["answer"] = "Yes" if e["answer"] else "No"


def names(root: Path) -> list[str]:
    d = Path(root) / QDIR
    return sorted(p.parent.name for p in d.glob("*/questionnaire.yaml")) if d.is_dir() else []


def load_questionnaire(root: Path, name: str) -> Questionnaire:
    root = Path(root)
    qdir = root / QDIR / name
    meta = load_yaml(qdir / "questionnaire.yaml")
    d = load_definition(str(meta.get("definition")), root)
    questions = (load_yaml(qdir / "questions.yaml") or {}).get("questions") or []
    raw = load_yaml(qdir / "answers.yaml") if (qdir / "answers.yaml").exists() else {"answers": []}
    if isinstance(raw, dict):
        _yes_no(raw.get("answers"))
    answers = [a for a in (raw or {}).get("answers") or [] if isinstance(a, dict)]
    return Questionnaire(root, name, meta or {}, d, questions, answers, raw)


def load_library(root: Path) -> dict:
    p = Path(root) / LIBRARY
    data = load_yaml(p) if p.exists() else {}
    if isinstance(data, dict):
        _yes_no(data.get("answers"))
    return data if isinstance(data, dict) else {}


def load_profile(root: Path) -> dict:
    p = Path(root) / PROFILE
    data = load_yaml(p) if p.exists() else {}
    return data if isinstance(data, dict) else {}


QUESTIONS_HEADER = """# Questions read from the workbook by `grc questionnaire import`. Don't edit: re-import instead.
# The question text is the publisher's and stays in this (private) repository.
"""

ANSWERS_HEADER = """# Answers for this questionnaire. `grc questionnaire draft` proposes; a person approves.
# To approve: check answer and detail, set status: approved, approved_by and approved_on, in a pull request.
# To answer yourself: write answer/detail and set source: person (draft never overwrites those), then approve.
# status: needs_answer | proposed | approved | not_applicable (a Start Here answer switched the section off)
"""


def import_workbook(root: Path, workbook: Path, name: str, definition: str = "hecvat-4", requester: str = "",
                    due: str | None = None, today: dt.date | None = None, force: bool = False) -> Path:
    root = Path(root)
    qdir = root / QDIR / name
    if (qdir / "questionnaire.yaml").exists() and not force:
        raise SystemExit(f"questionnaire: {qdir.relative_to(root)}/ already exists (use --force to re-import "
                         "the workbook; answers.yaml is kept)")
    d = load_definition(definition, root)
    wbk = Workbook(workbook)
    missing = [s for s in d["layout"]["answer_sheets"] + [d["layout"]["question_sheet"]] if s not in wbk.sheets]
    if missing:
        raise SystemExit(f"questionnaire: {workbook} doesn't look like {d['title']}: no sheet {', '.join(missing)}")
    vc = d.get("version_cell") or {}
    version = str(wbk.cell(vc["sheet"], vc["cell"]) or "").replace("Version", "").strip() if vc else ""
    questions = read_questions(wbk, d)
    qdir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(workbook, qdir / "received.xlsx")
    meta = {"definition": d["id"], "title": f"{d['title']} for {requester}".strip() if requester else d["title"],
            "version": version, "requester": requester, "received_on": (today or dt.date.today()).isoformat(),
            "due": due, "status": "open", "sent_on": None}
    if (qdir / "questionnaire.yaml").exists():
        old = load_yaml(qdir / "questionnaire.yaml") or {}
        meta.update({k: old[k] for k in ("requester", "due", "status", "sent_on", "title") if old.get(k)})
    (qdir / "questionnaire.yaml").write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (qdir / "questions.yaml").write_text(QUESTIONS_HEADER + yaml.safe_dump({"questions": questions}, sort_keys=False,
                                         allow_unicode=True, width=120), encoding="utf-8")
    if not (qdir / "answers.yaml").exists():
        (qdir / "answers.yaml").write_text(ANSWERS_HEADER + "answers: []\n", encoding="utf-8")
    return qdir


# ------------------------------------------------------------------ what backs an answer
@dataclass
class Support:
    level: str = "unmapped"                       # supported | partial | gap | unmapped
    basis: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)


def support(prog, maps: dict) -> Support:
    """How well the program and records back a question mapped to these requirements."""
    s = Support()
    wanted = {fw: {str(x) for x in ids or []} for fw, ids in (maps or {}).items()}
    levels = []
    for c in prog.controls:
        if not any(set(c.get("maps", {}).get(fw, [])) & ids for fw, ids in wanted.items()):
            continue
        current = False
        for r in c.get("evidence") or []:
            rec, ev = prog.evidence(r)
            current |= bool(ev is not None and rec.evidence_is_current(ev))
        levels.append("supported" if current else "partial")
        s.basis.append(f"program:{c['id']} {c.get('title', '')}" + ("" if current else " (no current evidence)"))
        if c.get("owner"):
            s.owners.append(str(c["owner"]))
        if str(c.get("description") or "").strip():
            s.statements.append(str(c["description"]).strip())
    for fw, ids in wanted.items():
        rec = prog.records.get(fw)
        if rec is None:
            continue
        for rid in sorted(ids):
            if rid not in rec.requirement_index or not rec.is_applicable(rid):
                continue
            st = requirement_state(rec, rid)
            levels.append({"Ready": "supported", "In progress": "partial", "Unverified claim": "partial"}.get(st, "gap"))
            s.basis.append(f"{fw}:{rid} {st}")
            ctl = rec.controls.get(rid, {})
            if ctl.get("owner"):
                s.owners.append(str(ctl["owner"]))
            if str(ctl.get("implementation") or "").strip():
                s.statements.append(str(ctl["implementation"]).strip())
            for g in rec.gaps:
                if (isinstance(g, dict) and rid in [str(x) for x in g.get("requirements") or []]
                        and g.get("status") not in CLOSED_GAP and rec.gap_in_scope(g)):
                    s.gaps.append(f"{fw}:{g.get('id')}")
    s.owners = list(dict.fromkeys(s.owners))
    s.statements = list(dict.fromkeys(s.statements))
    s.gaps = sorted(set(s.gaps))
    if not levels:
        s.level = "unmapped"
    elif "supported" in levels and not s.gaps:
        s.level = "supported"
    elif all(x == "gap" for x in levels):
        s.level = "gap"
    else:
        s.level = "partial"
    return s


def _library_index(lib: dict, qid_prefix: str) -> dict[str, dict]:
    out = {}
    for e in lib.get("answers") or []:
        if not isinstance(e, dict):
            continue
        for ref in e.get("questions") or []:
            ref = str(ref)
            if ref.startswith(qid_prefix + ":"):
                out.setdefault(ref.split(":", 1)[1], e)
    return out


def _library_current(e: dict, today: dt.date) -> bool:
    on = e.get("approved_on")
    on = on if isinstance(on, dt.date) else (dt.date.fromisoformat(on) if isinstance(on, str) and on else None)
    if not (e.get("approved_by") and on):
        return False
    return on + dt.timedelta(days=int(e.get("review_every_days") or 365)) >= today


def _gated_off(q: dict, d: dict, answers: dict[str, dict]) -> dict | None:
    """The gate that switches this question's section off, if its answer is No."""
    for g in d.get("gates") or []:
        hit = q["sheet"] in (g.get("sheets") or []) or q["id"][:4] in (g.get("prefixes") or [])
        if hit and str((answers.get(g["question"]) or {}).get("answer") or "").strip().lower() == "no":
            return g
    return None


def draft(qn: Questionnaire, prog, today: dt.date | None = None) -> dict:
    """Propose answers. Keeps everything a person wrote or approved; refreshes the rest."""
    today = today or prog.today
    d = qn.definition
    defq = d.get("questions") or {}
    lib = _library_index(load_library(qn.root), d["id"])
    profile = load_profile(qn.root)
    prof_map = d.get("profile") or {}
    old = qn.aindex
    new: dict[str, dict] = {}
    counts = {k: 0 for k in STATUSES}
    # gates first: their answers decide which sections are in scope
    order = [g["question"] for g in d.get("gates") or []] + [q["id"] for q in qn.questions]
    seen = set()
    for qid in order:
        if qid in seen or qid not in qn.qindex:
            continue
        seen.add(qid)
        q = qn.qindex[qid]
        prev = old.get(qid)
        if prev and (prev.get("status") == "approved" or prev.get("source") == "person"):
            new[qid] = prev
            counts[prev.get("status") if prev.get("status") in STATUSES else "needs_answer"] += 1
            continue
        info = defq.get(qid) or {}
        entry = {"id": qid, "topic": info.get("topic") or "", "status": "needs_answer", "answer": None,
                 "detail": None, "source": None, "support": None, "basis": [], "owner": None,
                 "approved_by": None, "approved_on": None}
        gate = _gated_off(q, d, new)
        if gate:
            entry.update(status="not_applicable", source=f"gate:{gate['question']}",
                         detail=None, support="n/a")
            entry["basis"] = [f"{gate['question']} is No ({gate.get('label', '')}): leave this section blank"]
        elif qid in lib and _library_current(lib[qid], today):
            e = lib[qid]
            entry.update(status="proposed", answer=e.get("answer"), detail=e.get("detail"),
                         source=f"library:{e.get('id')}", owner=e.get("owner"))
            s = support(prog, info.get("maps") or {})
            entry.update(support=s.level, basis=s.basis)
        elif qid in prof_map and str(profile.get(prof_map[qid]) or "").strip():
            entry.update(status="proposed", answer=str(profile[prof_map[qid]]).strip(),
                         source=f"profile:{prof_map[qid]}", support="n/a")
        elif qid in (d.get("gate_hints") or {}):
            hint = d["gate_hints"][qid]
            if hint.get("record") in prog.records:
                entry.update(status="proposed", answer="Yes", source="program", support="n/a",
                             basis=[hint.get("reason", "")])
        else:
            s = support(prog, info.get("maps") or {})
            entry.update(support=s.level, basis=s.basis, owner=s.owners[0] if s.owners else None)
            if s.gaps:
                entry["basis"] = entry["basis"] + [f"open gap {g}" for g in s.gaps]
            want = (q.get("compliant") or "").strip()
            if s.level == "supported" and q.get("allowed") and want in q["allowed"]:
                entry.update(status="proposed", answer=want, source="program",
                             detail=" ".join(s.statements[:2]) or None)
        new[qid] = entry
        counts[entry["status"]] += 1
    # keep answers for ids no longer in the workbook out (validation reports stray ones in the old file)
    qn.answers = [new[q["id"]] for q in qn.questions if q["id"] in new]
    return counts


def write_answers(qn: Questionnaire) -> Path:
    path = qn.dir / "answers.yaml"
    path.write_text(ANSWERS_HEADER + yaml.safe_dump({"answers": qn.answers}, sort_keys=False, allow_unicode=True,
                                                    width=120), encoding="utf-8")
    return path


# ------------------------------------------------------------------ writing the workbook
def _set_cell(xml: str, ref: str, text: str) -> str:
    col, row = _col_row(ref)
    cell = (f'<c r="{ref}"{{style}} t="inlineStr"><is><t xml:space="preserve">'
            f'{escape(text)}</t></is></c>')
    m = re.search(rf'<c r="{ref}"(?P<attrs>[^>]*?)(?:/>|>.*?</c>)', xml, re.S)
    if m:
        style = re.search(r'\ss="(\d+)"', m.group("attrs"))
        return xml[:m.start()] + cell.format(style=f' s="{style.group(1)}"' if style else "") + xml[m.end():]
    rm = re.search(rf'<row r="{row}"(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</row>)', xml, re.S)
    from openpyxl.utils import column_index_from_string
    new_cell = cell.format(style="")
    if not rm:                            # an empty row isn't stored: add it before the first later row
        if "<sheetData" not in xml:
            raise ValueError(f"no sheet data to put {ref} in")
        new_row = f'<row r="{row}">{new_cell}</row>'
        for m2 in re.finditer(r'<row r="(\d+)"', xml):
            if int(m2.group(1)) > row:
                return xml[:m2.start()] + new_row + xml[m2.start():]
        if "<sheetData/>" in xml:
            return xml.replace("<sheetData/>", f"<sheetData>{new_row}</sheetData>", 1)
        return xml.replace("</sheetData>", new_row + "</sheetData>", 1)
    if rm.group("body") is None:          # <row .../> with no cells
        return xml[:rm.start()] + f'<row r="{row}"{rm.group("attrs")}>{new_cell}</row>' + xml[rm.end():]
    body = rm.group("body")
    want = column_index_from_string(col)
    for cm in re.finditer(r'<c r="([A-Z]+)\d+"', body):
        if column_index_from_string(cm.group(1)) > want:
            body = body[:cm.start()] + new_cell + body[cm.start():]
            break
    else:
        body += new_cell
    start = rm.start("body")
    return xml[:start] + body + xml[rm.end("body"):]


def fill(qn: Questionnaire, out: Path, include_proposed: bool = False, today: dt.date | None = None) -> dict:
    """Write answers into a copy of the received workbook. Only the answer and detail cells change."""
    src = qn.dir / "received.xlsx"
    wbk = Workbook(src)
    edits: dict[str, dict[str, str]] = {}
    written = skipped = 0
    for a in qn.answers:
        q = qn.qindex.get(str(a.get("id")))
        if not q or a.get("status") == "not_applicable":
            continue
        ok = a.get("status") == "approved" or (include_proposed and a.get("status") == "proposed")
        if not ok or a.get("answer") in (None, ""):
            skipped += 1
            continue
        part = wbk.sheets[q["sheet"]]
        edits.setdefault(part, {})[q["answer_cell"]] = str(a["answer"])
        detail = str(a.get("detail") or "").strip()
        if include_proposed and a.get("status") == "proposed":
            detail = ("[DRAFT - not approved] " + detail).strip()
        if detail and q.get("detail_cell"):
            edits[part][q["detail_cell"]] = detail
        written += 1
    dc = qn.definition["layout"].get("date_cell")
    if dc and written:
        edits.setdefault(wbk.sheets[dc["sheet"]], {})[dc["cell"]] = (today or dt.date.today()).isoformat()
    buf = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in edits:
                xml = data.decode("utf-8")
                for ref, text in edits[item.filename].items():
                    xml = _set_cell(xml, ref, text)
                data = xml.encode("utf-8")
            elif item.filename == "xl/workbook.xml":
                xml = data.decode("utf-8")
                if "<calcPr" in xml:
                    xml = re.sub(r"<calcPr\b([^>]*?)/>", lambda m: "<calcPr" + re.sub(r'\sfullCalcOnLoad="[^"]*"', "", m.group(1))
                                 + ' fullCalcOnLoad="1"/>', xml, count=1)
                else:
                    xml = xml.replace("</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>')
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())
    return {"written": written, "left_blank": skipped}


# ------------------------------------------------------------------ the library
LIBRARY_HEADER = """# Approved answers, reused across questionnaires. `grc questionnaire learn <name>` adds the approved answers
# of a questionnaire; edit an entry here and every later draft uses it. Each entry is reviewed again after
# review_every_days (default 365): until then drafts propose it; after that it needs a fresh approval.
"""


def learn(qn: Questionnaire) -> int:
    path = qn.root / LIBRARY
    lib = load_library(qn.root)
    entries = [e for e in lib.get("answers") or [] if isinstance(e, dict)]
    by_ref = {str(r): e for e in entries for r in e.get("questions") or []}
    added = 0
    for a in qn.answers:
        if a.get("status") != "approved" or a.get("answer") in (None, "") or str(a.get("source") or "").startswith("profile:"):
            continue
        ref = qn.ref(str(a["id"]))
        e = by_ref.get(ref)
        if e is None:
            e = {"id": f"ANS-{a['id']}", "questions": [ref]}
            entries.append(e)
            by_ref[ref] = e
        changed = (e.get("answer"), e.get("detail")) != (a.get("answer"), a.get("detail"))
        e.update({"topic": a.get("topic") or e.get("topic"), "answer": a.get("answer"), "detail": a.get("detail"),
                  "owner": a.get("owner") or e.get("owner"), "approved_by": a.get("approved_by"),
                  "approved_on": a.get("approved_on"), "review_every_days": e.get("review_every_days") or 365})
        added += changed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LIBRARY_HEADER + yaml.safe_dump({"answers": entries}, sort_keys=False, allow_unicode=True, width=120),
                    encoding="utf-8")
    return added


# ------------------------------------------------------------------ validation
def _date(v):
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def _schema(name: str, data, file: str, out: list[Finding]) -> bool:
    from jsonschema import Draft202012Validator, FormatChecker

    from .model import jsonable
    errs = sorted(Draft202012Validator(load_schema(name), format_checker=FormatChecker()).iter_errors(jsonable(data)),
                  key=lambda e: list(e.path))
    for e in errs:
        loc = "/".join(str(p) for p in e.path) or "(root)"
        out.append(Finding("error", "Q101", f"Schema: {loc}: {e.message}", file))
    return not errs


def validate(root: Path, prog, today: dt.date | None = None) -> list[Finding]:
    root = Path(root)
    today = today or prog.today
    out: list[Finding] = []
    lib = load_library(root)
    lib_file = str(LIBRARY)
    if (root / LIBRARY).exists() and _schema("questionnaire-library", lib, lib_file, out):
        seen = set()
        for e in lib.get("answers") or []:
            eid = str(e.get("id"))
            if eid in seen:
                out.append(Finding("error", "Q105", f"{eid}: duplicate library id.", lib_file, eid))
            seen.add(eid)
            for ref in e.get("questions") or []:
                qdef, _, qid = str(ref).partition(":")
                if not definition_path(qdef, root).exists():
                    out.append(Finding("error", "Q105", f"{eid}: '{ref}' names no questionnaire ({', '.join(definitions())}).",
                                       lib_file, eid))
                elif qid not in (load_definition(qdef, root).get("questions") or {}):
                    out.append(Finding("error", "Q105", f"{eid}: '{ref}' is not a question of {qdef}.", lib_file, eid))
            if not (e.get("approved_by") and _date(e.get("approved_on"))):
                out.append(Finding("error", "Q103", f"{eid}: a library answer needs approved_by and approved_on.", lib_file, eid))
            elif not _library_current(e, today):
                out.append(Finding("warning", "Q106", f"{eid}: approved on {e.get('approved_on')}, due for review "
                                   f"(every {e.get('review_every_days') or 365} days); drafts won't use it until it is re-approved.",
                                   lib_file, eid))
    for name in names(root):
        try:
            qn = load_questionnaire(root, name)
        except (SystemExit, ValueError) as exc:
            out.append(Finding("error", "Q101", f"{name}: {exc}", str(QDIR / name)))
            continue
        afile = str(QDIR / name / "answers.yaml")
        _schema("questionnaire", qn.meta, str(QDIR / name / "questionnaire.yaml"), out)
        if not _schema("questionnaire-answers", qn.raw_answers or {"answers": []}, afile, out):
            continue
        out += check_answers(qn, today)
    return out


def check_answers(qn: Questionnaire, today: dt.date) -> list[Finding]:
    out = []
    afile = str(QDIR / qn.name / "answers.yaml")
    seen = set()
    answers = qn.aindex
    for a in qn.answers:
        qid = str(a.get("id"))
        if qid in seen:
            out.append(Finding("error", "Q108", f"{qid}: answered twice.", afile, qid))
        seen.add(qid)
        q = qn.qindex.get(qid)
        if q is None:
            out.append(Finding("error", "Q108", f"{qid} is not a question in this workbook.", afile, qid))
            continue
        ans = a.get("answer")
        if ans not in (None, "") and q.get("allowed") and str(ans) not in q["allowed"]:
            out.append(Finding("error", "Q102", f"{qid}: '{ans}' isn't one of the workbook's choices "
                               f"({', '.join(q['allowed'])}).", afile, qid))
        if a.get("status") == "approved":
            if ans in (None, ""):
                out.append(Finding("error", "Q103", f"{qid} is approved but has no answer.", afile, qid))
            if not (a.get("approved_by") and _date(a.get("approved_on"))):
                out.append(Finding("error", "Q103", f"{qid} is approved without approved_by and approved_on.", afile, qid))
            claims = str(ans or "").strip()
            if claims and claims == (q.get("compliant") or "").strip() and a.get("support") == "gap":
                out.append(Finding("warning", "Q104", f"{qid}: answered '{claims}', but the controls behind it aren't in place "
                                   f"yet ({'; '.join(x for x in a.get('basis') or [] if 'gap' in x.lower()) or 'not started'}).",
                                   afile, qid))
        gate = _gated_off(q, qn.definition, answers)
        if gate and a.get("status") == "approved":
            out.append(Finding("warning", "Q109", f"{qid}: {gate['question']} is No, so this section should be left blank.",
                               afile, qid))
    due = _date(qn.meta.get("due"))
    open_items = [a for a in qn.answers if a.get("status") in ("needs_answer", "proposed")]
    missing = [q["id"] for q in qn.questions if q["id"] not in answers]
    if qn.meta.get("status") != "sent" and due and open_items:
        days = (due - today).days
        if days < 0:
            out.append(Finding("warning", "Q107", f"{qn.name}: due {due}, {-days} day(s) ago, with {len(open_items)} "
                               "answer(s) not approved.", str(QDIR / qn.name / "questionnaire.yaml")))
        elif days <= 7:
            out.append(Finding("warning", "Q107", f"{qn.name}: due {due} (in {days} day(s)) with {len(open_items)} "
                               "answer(s) not approved.", str(QDIR / qn.name / "questionnaire.yaml")))
    if missing and qn.answers:
        out.append(Finding("info", "Q110", f"{qn.name}: {len(missing)} question(s) have no entry yet; run "
                           "`grc questionnaire draft`.", afile))
    return out


# ------------------------------------------------------------------ report
def summary(qn: Questionnaire) -> dict:
    by = {k: 0 for k in STATUSES}
    for a in qn.answers:
        by[a.get("status") if a.get("status") in STATUSES else "needs_answer"] += 1
    in_scope = len(qn.questions) - by["not_applicable"]
    sup = {}
    for a in qn.answers:
        if a.get("status") != "not_applicable" and a.get("support"):
            sup[a["support"]] = sup.get(a["support"], 0) + 1
    return {"questions": len(qn.questions), "in_scope": in_scope, **by,
            "pct_approved": round(100 * by["approved"] / in_scope) if in_scope else 0, "support": sup}


def report_md(qn: Questionnaire) -> str:
    s = summary(qn)
    m = qn.meta
    lines = [f"# {m.get('title') or qn.definition['title']}", "",
             f"Requested by **{m.get('requester') or 'not recorded'}** · received {m.get('received_on')} · "
             f"due **{m.get('due') or 'not set'}** · workbook version {m.get('version') or 'unknown'} · status {m.get('status')}", "",
             "| | Questions |", "|---|---|",
             f"| In scope | {s['in_scope']} of {s['questions']} |",
             f"| Approved | {s['approved']} ({s['pct_approved']}%) |",
             f"| Proposed, waiting for approval | {s['proposed']} |",
             f"| Needs an answer | {s['needs_answer']} |",
             f"| Not applicable (section switched off) | {s['not_applicable']} |", ""]
    if s["support"]:
        lines += ["How well the control program backs the answers in scope:", "",
                  "| Backing | Questions | Meaning |", "|---|---|---|"]
        meaning = {"supported": "a mapped control is in place with current evidence",
                   "partial": "work under way, or evidence missing or out of date",
                   "gap": "mapped requirements not started or with open gaps",
                   "unmapped": "no mapped control: answered from knowledge, not evidence",
                   "n/a": "company facts and scoping questions"}
        for k in ("supported", "partial", "gap", "unmapped", "n/a"):
            if s["support"].get(k):
                lines.append(f"| {k} | {s['support'][k]} | {meaning[k]} |")
        lines.append("")
    open_ = [a for a in qn.answers if a.get("status") in ("needs_answer", "proposed")]
    if open_:
        lines += ["## Open questions by owner", "",
                  "| Question | Topic | Status | Proposed | Owner | Backing |", "|---|---|---|---|---|---|"]
        for a in sorted(open_, key=lambda x: (str(x.get("owner") or "~"), x["id"])):
            lines.append(f"| {a['id']} | {a.get('topic') or ''} | {a['status']} | {a.get('answer') or ''} | "
                         f"{a.get('owner') or 'unassigned'} | {a.get('support') or ''} |")
        lines.append("")
    warn = [a for a in qn.answers if a.get("support") == "gap" and a.get("status") in ("approved", "proposed")]
    if warn:
        lines += ["## Answers to check against open gaps", ""]
        lines += [f"- **{a['id']}** ({a.get('topic') or ''}): {'; '.join(a.get('basis') or [])}" for a in warn]
        lines.append("")
    return "\n".join(lines)
