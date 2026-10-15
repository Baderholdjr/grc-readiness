"""Load an engagement (framework catalog + playbook + engagement data) into one object."""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Built-in resources shipped with the engine (catalogs, schemas, Word template).
ENGINE = Path(__file__).resolve().parent / "resources"


def resource(repo_root: Path, *parts: str) -> Path:
    """A file from the client repo if it overrides it, else the engine's built-in copy.

    Lets a client repo customise e.g. frameworks/iso42001/playbook.yaml or
    templates/brief-template.docx without forking the engine.
    """
    local = repo_root.joinpath(*parts)
    return local if local.exists() else ENGINE.joinpath(*parts)
LEGS = ("documented", "implemented", "evidenced", "tested")

# Requirement kinds used by the ISO catalogs. Other catalogs declare theirs under `kinds:`.
KIND_DEFAULTS = {
    "clause": {"label": "Clause", "short": "Clause", "mandatory": True},
    "control": {"label": "Annex A control", "short": "Annex A", "mandatory": False},
}

# Wording that differs between frameworks. A playbook overrides any of these under `terms:`.
TERM_DEFAULTS = {
    "goal": "certification",                       # "Path to certification", "would block certification"
    "audit_body": "Certification body",
    "focus": "Certification readiness and gap closure",  # new-engagement subtitle
    "stage1": "Stage 1 audit",                     # what dates.stage1 and dates.stage2 mean
    "stage2": "Stage 2 audit",
    "countdown": "Stage 1 audit is",               # site: "Your ISO 27001 Stage 1 audit is in 12 days."
    "applicability_title": "Statement of Applicability",
    "applicability_short": "SoA",
    "applicability_intro": "Annex A controls with inclusion/exclusion justification and implementation status.",
    "internal_audit_ref": "9.2",                   # requirement the internal audit evidences
    "corrective_ref": "10.2",                      # requirement the corrective action register evidences
    "review_ref": "9.3",                           # requirement the management review evidences
    "record_control_ref": "7.5",
    "review_required": "yes",                      # "no": a missing management review isn't warned about (SOC 2)
    "applicability_id_header": "Control",          # first column of the applicability report
    "scope_ref": "4.3",                            # requirements whose library documents the review pack reports on
    "objectives_ref": "6.2",
    "risk_ref": "6.1.2",                   # requirement the engagement repo's own branch protection evidences
}


class RecordError(SystemExit):
    """A record file can't be read. Raised as SystemExit so the CLI prints one clear line, not a traceback."""


def read_yaml(path: Path) -> Any:
    """Like load_yaml, but lets yaml.YAMLError through (for files whose errors are reported as findings)."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        try:
            return yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}" if mark else ""
            problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
            raise RecordError(f"error: {path}: not valid YAML{where} ({problem}). Check the indentation of that line "
                              "against the lines around it, and put quotes around text that contains a colon.") from None


def to_date(value: Any) -> dt.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def jsonable(obj: Any) -> Any:
    """YAML parses ISO dates into date objects; JSON Schema wants strings."""
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    return obj


@dataclass
class Engagement:
    root: Path
    engagement_dir: Path
    engagement: dict
    catalog: dict
    playbook: dict
    controls: dict[str, dict] = field(default_factory=dict)
    control_files: dict[str, Path] = field(default_factory=dict)
    gaps: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    inventory: list[dict] = field(default_factory=list)
    owners: list[dict] = field(default_factory=list)
    human_evidence_count: int = 0
    audits: list[dict] = field(default_factory=list)          # engagement/audit/program.yaml
    workpapers: dict[str, dict[str, dict]] = field(default_factory=dict)   # audit id -> wp id -> data
    workpaper_files: dict[str, Path] = field(default_factory=dict)         # "AUD/WP" -> path
    findings: list[dict] = field(default_factory=list)        # engagement/findings.yaml (10.2 register)
    impacts: dict[str, dict] = field(default_factory=dict)    # engagement/impact/IA-NNN.yaml
    impact_files: dict[str, Path] = field(default_factory=dict)
    documents: dict[str, dict] = field(default_factory=dict)  # engagement/documents/DOC-*.md -> {meta, body, error}
    document_files: dict[str, Path] = field(default_factory=dict)
    hours: list[dict] = field(default_factory=list)           # engagement/hours.yaml (timesheet)
    hours_meta: dict = field(default_factory=dict)            # its aliases / ignored lists
    reviews: dict[str, dict] = field(default_factory=dict)    # engagement/reviews/MR-YYYY-NN.yaml (9.3)
    review_files: dict[str, Path] = field(default_factory=dict)
    submissions: dict[str, dict] = field(default_factory=dict)  # engagement/submissions/SUB-*.yaml (from the client site)
    submission_files: dict[str, Path] = field(default_factory=dict)
    today: dt.date = field(default_factory=dt.date.today)
    internal: bool = True     # False while building what auditors receive: no hours or budget

    # ------------------------------------------------------------------ lookups
    @property
    def client(self) -> str:
        return self.engagement["client"]["name"]

    @property
    def namespace(self) -> str:
        """'' for the repository's primary record (engagement/); the framework id (e.g. iso27001) for any other
        record in the same repository, used to keep issue markers and milestones apart."""
        return "" if self.engagement_dir.name == "engagement" else str(self.engagement.get("framework") or self.engagement_dir.name)

    @property
    def record_dir(self) -> str:
        """The record folder's name in the repository, e.g. engagement or engagement-27001."""
        return self.engagement_dir.name

    @property
    def framework_name(self) -> str:
        """e.g. ISO/IEC 27001:2022"""
        fw = self.catalog.get("framework") or {}
        return str(fw.get("name") or fw.get("short_name") or "the standard")

    @property
    def system_abbrev(self) -> str:
        """The management system's short name, e.g. AIMS or ISMS (from the catalog); SOC 2 says 'system'."""
        if (self.playbook.get("terms") or {}).get("system"):
            return str(self.playbook["terms"]["system"])
        m = re.search(r"\(([A-Z]{2,6})\)", str((self.catalog.get("framework") or {}).get("management_system") or ""))
        return m.group(1) if m else "management system"

    @property
    def uses_impact_assessments(self) -> bool:
        """ISO 42001 assesses AI systems' impacts; frameworks whose playbook requires none (ISO 27001) don't."""
        from .impact import method
        return bool(method(self)["required_for_kinds"])

    @property
    def requirements(self) -> list[dict]:
        return self.catalog["requirements"]

    @property
    def requirement_index(self) -> dict[str, dict]:
        return {r["id"]: r for r in self.requirements}

    @property
    def evidence_index(self) -> dict[str, dict]:
        """Human + collected evidence, plus concluded audit workpapers (citable as 'AUD-…/WP-…')."""
        from . import documents, impact
        idx = {e["id"]: e for e in self.evidence}
        idx.update(self.workpaper_evidence)
        idx.update(impact.evidence_entries(self))
        idx.update(documents.evidence_entries(self))
        from . import review
        idx.update(review.evidence_entries(self))
        from .mappings import cross_evidence
        idx.update(cross_evidence(self))     # '<framework>:<id>' from other records in the repo (rules decide if allowed)
        return idx

    @property
    def audit_index(self) -> dict[str, dict]:
        return {a["id"]: a for a in self.audits}

    @property
    def finding_index(self) -> dict[str, dict]:
        return {f["id"]: f for f in self.findings}

    @property
    def workpaper_evidence(self) -> dict[str, dict]:
        """A workpaper is test evidence once it's concluded effective and independently reviewed."""
        out = {}
        for aid, wps in self.workpapers.items():
            for wid, wp in wps.items():
                reviewed = self.independent(wp.get("reviewed_by"), wp.get("performed_by"))
                ok = wp.get("conclusion") == "effective" and reviewed
                out[f"{aid}/{wid}"] = {
                    "id": f"{aid}/{wid}", "title": f"Internal audit {aid} {wid}: {wp.get('requirement')} {wp.get('title', '')}".strip(),
                    "type": "test", "location": f"{self.record_dir}/audit/{aid}/workpapers/{wid}.yaml",
                    "owner": wp.get("performed_by", ""), "collected": wp.get("performed_on"),
                    "approved_by": wp.get("reviewed_by", ""), "valid_for_days": 365,
                    # not concluded/reviewed -> behaves like failing evidence (not current)
                    "result": None if ok else "fail", "source": "audit",
                    "notes": f"conclusion: {wp.get('conclusion', 'not_started')}"
                             + ("" if reviewed else "; not independently reviewed"),
                }
        return out

    @property
    def gap_index(self) -> dict[str, dict]:
        return {g["id"]: g for g in self.gaps}

    @property
    def phase_index(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.phases}

    @property
    def phases(self) -> list[dict]:
        """Engagement phases merged with playbook defaults (objective/deliverables)."""
        defaults = {p["id"]: p for p in self.playbook.get("phases", [])}
        merged = []
        for p in self.engagement["phases"]:
            base = defaults.get(p["id"], {})
            merged.append({
                **p,
                "objective": p.get("objective") or base.get("objective", p["id"]),
                "deliverables": p.get("deliverables") or base.get("deliverables", []),
            })
        return merged

    def github_users(self, role: str | None) -> list[str]:
        """GitHub handles for an owner role (case-insensitive). Teams are returned as org/team."""
        if not role:
            return []
        for o in self.owners:
            if o.get("role", "").strip().lower() == role.strip().lower():
                return [u.lstrip("@") for u in o.get("github", []) or []]
        return []

    def identities(self, name: str | None) -> set[str]:
        """Everything a person/role name can stand for: itself, a role's GitHub users, a user's roles.

        Used for independence checks, so 'alice', '@Alice' and the role alice belongs to all collide.
        """
        n = (name or "").strip().lstrip("@").lower()
        if not n:
            return set()
        ids = {n}
        for o in self.owners:
            role = (o.get("role") or "").strip().lower()
            users = {u.strip().lstrip("@").lower() for u in o.get("github", []) or []}
            if n == role:
                ids |= users
            if n in users:
                ids.add(role)
        return ids

    def independent(self, a: str | None, b: str | None) -> bool:
        """True when a and b are both set and can't be the same person or role."""
        return bool(a and b) and not (self.identities(a) & self.identities(b))

    def fmt(self, text: str) -> str:
        return text.replace("{client}", self.client)

    def setting(self, key: str, default: Any = None) -> Any:
        """Engagement value if set, else playbook value."""
        if key in self.engagement and self.engagement[key] not in (None, [], ""):
            return self.engagement[key]
        return self.playbook.get(key, default)

    # ------------------------------------------------- framework vocabulary
    def kind(self, kind: str | None) -> dict:
        """How a catalog defines a kind of requirement: its label and whether it can be excluded.
        ISO catalogs use clause (mandatory) and control (Annex A, excludable with a justification);
        other catalogs declare their own under `kinds:`."""
        k = str(kind or "")
        base = KIND_DEFAULTS.get(k, {"label": k.title() or "Requirement", "mandatory": False})
        return {**base, **((self.catalog.get("kinds") or {}).get(k) or {})}

    def kind_label(self, req: dict) -> str:
        """Short label for a requirement's kind in tables: 'Clause', 'Annex A', or a SOC 2 category."""
        cat = self.category_index.get(str(req.get("category") or ""))
        if cat:
            return str(cat.get("short") or cat.get("title"))
        info = self.kind(req.get("kind"))
        return str(info.get("short") or info.get("label"))

    def is_mandatory(self, req_id: str) -> bool:
        return bool(self.kind(self.requirement_index.get(req_id, {}).get("kind")).get("mandatory"))

    @property
    def category_index(self) -> dict[str, dict]:
        """Optional parts of a framework the client chooses (SOC 2: Availability, Confidentiality, ...)."""
        return {str(c["id"]): c for c in self.catalog.get("categories") or [] if isinstance(c, dict) and c.get("id")}

    @property
    def categories_in_scope(self) -> set[str]:
        chosen = (self.engagement.get("scope") or {}).get("categories") or []
        return {k for k, c in self.category_index.items() if c.get("required")} | \
               {str(c) for c in chosen if str(c) in self.category_index}

    def in_category_scope(self, req_id: str) -> bool:
        """False only for a requirement in an optional category the client hasn't chosen."""
        cat = str(self.requirement_index.get(req_id, {}).get("category") or "")
        return not cat or cat not in self.category_index or cat in self.categories_in_scope

    def gap_in_scope(self, gap: dict) -> bool:
        """False for a gap whose requirements all sit in SOC 2 categories the client didn't choose."""
        reqs = [str(r) for r in gap.get("requirements") or [] if str(r) in self.requirement_index]
        return not reqs or any(self.in_category_scope(r) for r in reqs)

    def term(self, key: str) -> str:
        """Framework wording (playbook `terms:`), e.g. what the two audit milestones are called."""
        return str((self.playbook.get("terms") or {}).get(key) or TERM_DEFAULTS[key])

    def is_applicable(self, req_id: str) -> bool:
        if not self.in_category_scope(req_id):
            return False
        if self.is_mandatory(req_id):
            return True
        return self.controls.get(req_id, {}).get("applicable", True)

    def evidence_expiry(self, ev: dict) -> dt.date | None:
        collected = to_date(ev.get("collected"))
        if not collected:
            return None
        return collected + dt.timedelta(days=int(ev.get("valid_for_days", 365)))

    def evidence_is_expired(self, ev: dict) -> bool:
        exp = self.evidence_expiry(ev)
        return exp is not None and exp < self.today

    def evidence_is_failing(self, ev: dict) -> bool:
        """Collector-produced evidence whose latest check failed or errored."""
        return ev.get("result") in ("fail", "error")

    def evidence_is_current(self, ev: dict) -> bool:
        return not self.evidence_is_expired(ev) and not self.evidence_is_failing(ev)


def control_filename(req_id: str) -> str:
    return f"{req_id}.yaml"


def load(engagement_dir: str | Path = "engagement", today: dt.date | None = None) -> Engagement:
    edir = Path(engagement_dir).resolve()
    root = edir.parent  # the repository the engagement lives in
    eng = load_yaml(edir / "engagement.yaml")
    fw = eng.get("framework", "iso42001")
    catalog = resource(root, "frameworks", fw, "catalog.yaml")
    if not catalog.exists():
        raise SystemExit(f"Unknown framework '{fw}': no catalog in {root / 'frameworks'} or the engine")
    model = Engagement(
        root=root,
        engagement_dir=edir,
        engagement=eng,
        catalog=load_yaml(catalog),
        playbook=load_yaml(resource(root, "frameworks", fw, "playbook.yaml")),
        today=today or dt.date.today(),
    )
    for path in sorted((edir / "controls").glob("*.yaml")):
        data = load_yaml(path)
        cid = str(data.get("id", path.stem))
        model.controls[cid] = data
        model.control_files[cid] = path
    gaps_path = edir / "gaps.yaml"
    if gaps_path.exists():
        model.gaps = load_yaml(gaps_path).get("gaps", []) or []
    ev_path = edir / "evidence" / "index.yaml"
    if ev_path.exists():
        model.evidence = load_yaml(ev_path).get("evidence", []) or []
    model.human_evidence_count = len(model.evidence)
    collected = edir / "evidence" / "collected.yaml"  # machine-owned, written by collectors
    if collected.exists():
        model.evidence += load_yaml(collected).get("evidence", []) or []
    own = edir / "owners.yaml"
    if own.exists():
        model.owners = load_yaml(own).get("owners", []) or []
    hrs = edir / "hours.yaml"
    if hrs.exists():
        data = load_yaml(hrs) or {}
        data = data if isinstance(data, dict) else {"entries": []}
        model.hours = data.get("entries") if isinstance(data.get("entries"), list) else []
        model.hours_meta = {k: v for k, v in data.items() if k != "entries"}
    inv = edir / "inventory.yaml"
    if inv.exists():
        model.inventory = load_yaml(inv).get("items", []) or []
    prog = edir / "audit" / "program.yaml"
    if prog.exists():
        model.audits = load_yaml(prog).get("audits", []) or []
        for a in model.audits:
            if isinstance(a, dict):
                a["id"] = str(a.get("id"))
                for k in ("scope", "exclude"):
                    v = a.get(k)
                    if isinstance(v, (list, tuple)):
                        a[k] = [str(x) for x in v]
                    elif v is not None and k == "exclude":
                        a[k] = [str(v)]
                    elif v is not None and v != "all":
                        a[k] = [str(v)]
    for a in model.audits:
        wdir = edir / "audit" / str(a.get("id")) / "workpapers"
        for path in sorted(wdir.glob("WP-*.yaml")) if wdir.is_dir() else []:
            data = load_yaml(path)
            wid = path.stem  # the file name is the identity; a mismatching `id:` is reported (E025)
            if isinstance(data, dict) and data.get("requirement") is not None:
                data["requirement"] = str(data["requirement"])
            model.workpapers.setdefault(a["id"], {})[wid] = data
            model.workpaper_files[f"{a['id']}/{wid}"] = path
    for path in sorted((edir / "impact").glob("IA-*.yaml")) if (edir / "impact").is_dir() else []:
        data = load_yaml(path)
        if isinstance(data, dict):
            for imp in data.get("impacts") or []:
                if isinstance(imp, dict) and isinstance(imp.get("controls"), list):
                    imp["controls"] = [str(c) for c in imp["controls"]]
        model.impacts[path.stem] = data
        model.impact_files[path.stem] = path
    from .documents import coerce, parse
    for path in sorted((edir / "documents").glob("*.md")) if (edir / "documents").is_dir() else []:
        if path.name.lower() == "readme.md":
            continue
        try:
            raw, body, error = parse(path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, OSError) as exc:
            raw, body, error = None, "", f"could not read the file ({exc.__class__.__name__})"
        # `raw` is what the schema checks; `meta` is a type-safe copy the rules and reports use
        model.documents[path.stem] = {"meta": coerce(raw) if isinstance(raw, dict) else None, "raw": raw,
                                      "body": body, "error": error}
        model.document_files[path.stem] = path
    rdir = edir / "reviews"
    for path in sorted(rdir.glob("MR-*.yaml")) if rdir.is_dir() else []:
        try:
            data = read_yaml(path)
        except Exception as exc:  # report, don't crash
            data = {"_error": f"not valid YAML ({str(exc).splitlines()[0][:120]})"}
        model.reviews[path.stem] = data
        model.review_files[path.stem] = path
    sdir = edir / "submissions"
    for path in sorted(sdir.glob("SUB-*.yaml")) if sdir.is_dir() else []:
        try:
            data = read_yaml(path)
        except Exception as exc:  # written by a web form, reviewed by hand: report, never crash
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}" if mark else ""
            data = {"_error": f"not valid YAML{where} ({str(exc).splitlines()[0][:120]}) - check that every "
                              "top-level line (status:, reviewed_by:, note: ...) starts at the left edge, with no spaces before it"}
        model.submissions[path.stem] = data if isinstance(data, dict) else {"_error": "not a YAML mapping"}
        model.submission_files[path.stem] = path
    fnd = edir / "findings.yaml"
    if fnd.exists():
        model.findings = load_yaml(fnd).get("findings", []) or []
        for f in model.findings:
            if isinstance(f, dict) and f.get("requirement") is not None:
                f["requirement"] = str(f["requirement"])
    return model


RECORD_NAME = re.compile(r"^engagement(-[a-z0-9]+)?$")


def discover(root: str | Path = ".") -> list[Path]:
    """Every engagement record in a repository: engagement/ first, then engagement-<name>/ (one per extra framework).
    Only well-named folders that hold an engagement.yaml count; problems_with_records() reports the rest."""
    root = Path(root)
    return [p for p in [root / "engagement", *sorted(root.glob("engagement-*"))]
            if RECORD_NAME.match(p.name) and p.is_dir() and (p / "engagement.yaml").is_file()]


def problems_with_records(root: str | Path = ".") -> list[str]:
    """Folders that look like records but won't be picked up, and records that clash."""
    root = Path(root)
    out = []
    for p in sorted(root.glob("engagement*")):
        if not p.is_dir():
            continue
        if not RECORD_NAME.match(p.name):
            out.append(f"{p.name}/: record folders must be named engagement or engagement-<lowercase letters/digits>")
        elif not (p / "engagement.yaml").is_file():
            out.append(f"{p.name}/: no engagement.yaml, so this record would be skipped")
    seen: dict[str, str] = {}
    for p in discover(root):
        try:
            fw = str((load_yaml(p / "engagement.yaml") or {}).get("framework") or "iso42001")
        except SystemExit as exc:
            out.append(str(exc))
            continue
        if fw in seen:
            out.append(f"{p.name}/ and {seen[fw]}/ both hold framework {fw}: keep one record per framework")
        seen[fw] = p.name
    return out


def load_schema(name: str) -> dict:
    with open(ENGINE / "schemas" / f"{name}.schema.json", encoding="utf-8") as fh:
        return json.load(fh)
