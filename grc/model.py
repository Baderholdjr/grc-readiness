"""Load an engagement (framework catalog + playbook + engagement data) into one object."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
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
        return {e["id"]: e for e in self.evidence}

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
    eng = load_yaml(edir / "engagement.yaml")
    fw = eng.get("framework", "iso42001")
    fw_dir = ROOT / "frameworks" / fw
    if not fw_dir.is_dir():
        raise SystemExit(f"Unknown framework '{fw}': no directory {fw_dir}")
    model = Engagement(
        root=ROOT,
        engagement_dir=edir,
        engagement=eng,
        catalog=load_yaml(fw_dir / "catalog.yaml"),
        playbook=load_yaml(fw_dir / "playbook.yaml"),
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
    return model


def load_schema(name: str) -> dict:
    with open(ROOT / "schemas" / f"{name}.schema.json", encoding="utf-8") as fh:
        return json.load(fh)
