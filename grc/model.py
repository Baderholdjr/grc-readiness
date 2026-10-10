"""Load an engagement (framework catalog + playbook + engagement data) into one object."""
from __future__ import annotations

import datetime as dt
import json
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


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def to_date(value: Any) -> dt.date | None:
    if value is None or value == "":
        return None
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
    today: dt.date = field(default_factory=dt.date.today)

    # ------------------------------------------------------------------ lookups
    @property
    def client(self) -> str:
        return self.engagement["client"]["name"]

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
                    "type": "test", "location": f"engagement/audit/{aid}/workpapers/{wid}.yaml",
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

    def is_applicable(self, req_id: str) -> bool:
        req = self.requirement_index.get(req_id, {})
        if req.get("kind") == "clause":
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
    from .documents import parse
    for path in sorted((edir / "documents").glob("*.md")) if (edir / "documents").is_dir() else []:
        if path.name.lower() == "readme.md":
            continue
        meta, body, error = parse(path.read_text(encoding="utf-8"))
        if isinstance(meta, dict) and isinstance(meta.get("satisfies"), list):
            meta["satisfies"] = [str(r) for r in meta["satisfies"]]
        if isinstance(meta, dict) and meta.get("version") is not None:
            meta["version"] = str(meta["version"])
        model.documents[path.stem] = {"meta": meta, "body": body, "error": error}
        model.document_files[path.stem] = path
    fnd = edir / "findings.yaml"
    if fnd.exists():
        model.findings = load_yaml(fnd).get("findings", []) or []
        for f in model.findings:
            if isinstance(f, dict) and f.get("requirement") is not None:
                f["requirement"] = str(f["requirement"])
    return model


def load_schema(name: str) -> dict:
    with open(ENGINE / "schemas" / f"{name}.schema.json", encoding="utf-8") as fh:
        return json.load(fh)
