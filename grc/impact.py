"""AI system impact assessments (ISO 42001 6.1.4, 8.4, Annex A.5.2-A.5.5).

One file per AI system: engagement/impact/IA-NNN.yaml, generated from the AI
inventory and completed by the assessor. The methodology (categories, scales,
thresholds, review cycle) lives in the playbook under `impact_assessment:` so a
client repo can override it.

    python -m grc impact new INV-001     # or: all
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

from .model import Engagement, to_date

DEFAULT_METHOD = {
    "required_for_kinds": ["ai_system"],
    "review_every_days": {"default": 365},
    "bands": [[1, "Low"], [6, "Medium"], [12, "High"], [20, "Critical"]],
    "acceptance_required_at": 12,
    "unacceptable_at": 20,
    "categories": [],
}


def method(model: Engagement) -> dict:
    return {**DEFAULT_METHOD, **(model.playbook.get("impact_assessment") or {})}


def score(likelihood, severity) -> int | None:
    try:
        return int(likelihood) * int(severity)
    except (TypeError, ValueError):
        return None


def band(model: Engagement, value: int | None) -> str:
    if value is None:
        return "—"
    label = "—"
    for lower, name in method(model)["bands"]:
        if value >= lower:
            label = name
    return label


def safe_date(value) -> dt.date | None:
    """to_date that returns None for malformed values (the schema reports them; nothing else should crash)."""
    try:
        return to_date(value)
    except (TypeError, ValueError):
        return None


def assessments(model: Engagement) -> dict[str, dict]:
    """Well-formed assessment files only (others are reported by the schema check)."""
    return {iid: ia for iid, ia in model.impacts.items() if isinstance(ia, dict)}


def active_by_system(model: Engagement) -> dict[str, dict]:
    """The assessment that counts for each system: an effective one if any, else the lowest-numbered active one."""
    out: dict[str, tuple[str, dict]] = {}
    for iid, ia in sorted(assessments(model).items()):
        if ia.get("status") == "superseded":
            continue
        sid = ia.get("system")
        if sid not in out or (is_effective(model, ia) and not is_effective(model, out[sid][1])):
            out[sid] = (iid, ia)
    return {sid: {"id": iid, **ia} for sid, (iid, ia) in out.items()}


def required_systems(model: Engagement) -> list[dict]:
    kinds = set(method(model)["required_for_kinds"])
    return [i for i in model.inventory if i.get("kind") in kinds and i.get("in_scope", True) is not False]


def review_days(model: Engagement, system: dict | None) -> int:
    days = method(model)["review_every_days"]
    if isinstance(days, int):
        return days
    tier = str((system or {}).get("risk_tier") or "").strip().casefold()
    by_tier = {str(k).casefold(): v for k, v in days.items()}
    return int(by_tier.get(tier, by_tier.get("default", 365)))


def next_review(model: Engagement, ia: dict) -> dt.date | None:
    """approved_on + the review cycle for the system's risk tier; an explicit next_review can only bring it forward."""
    approved = safe_date(ia.get("approved_on"))
    explicit = safe_date(ia.get("next_review"))
    if not approved:
        return explicit
    system = {i.get("id"): i for i in model.inventory if isinstance(i, dict)}.get(ia.get("system"))
    cycle = approved + dt.timedelta(days=review_days(model, system))
    return min(cycle, explicit) if explicit else cycle


def is_effective(model: Engagement, ia: dict) -> bool:
    """Approved (not in the future) by someone independent of the assessor, not rejected, not past review."""
    if not isinstance(ia, dict):
        return False
    nr = next_review(model, ia)
    approved = safe_date(ia.get("approved_on"))
    return (ia.get("status") == "approved" and ia.get("decision") in ("approve", "approve_with_conditions")
            and model.independent(ia.get("approver"), ia.get("assessor"))
            and approved is not None and approved <= model.today
            and nr is not None and nr >= model.today)


def evidence_entries(model: Engagement) -> dict[str, dict]:
    """Approved assessments are citable evidence ('IA-001'); others behave like failing evidence."""
    out = {}
    for iid, ia in model.impacts.items():
        if not isinstance(ia, dict):
            out[iid] = {"id": iid, "title": f"AI impact assessment {iid} (malformed)", "type": "record",
                        "location": f"{model.record_dir}/impact/{iid}.yaml", "owner": "", "collected": None,
                        "valid_for_days": 1, "source": "impact", "result": "fail", "notes": "malformed file"}
            continue
        approved = safe_date(ia.get("approved_on"))
        nr = next_review(model, ia)
        days = (nr - approved).days if (approved and nr) else 365
        ok = is_effective(model, ia)
        out[iid] = {
            "id": iid, "title": f"AI impact assessment {iid}: {ia.get('title', ia.get('system', ''))}",
            "type": "record", "location": f"{model.record_dir}/impact/{iid}.yaml", "owner": ia.get("assessor", ""),
            "collected": approved, "approved_by": ia.get("approver", ""), "approved_on": approved,
            "valid_for_days": max(days, 1), "source": "impact",
            # past review -> plain expiry (E007); anything else that isn't effective -> failing (E015)
            "result": None if ok or (ia.get("status") == "approved" and approved and approved <= model.today
                                     and nr and nr < model.today and model.independent(ia.get("approver"), ia.get("assessor"))
                                     and ia.get("decision") in ("approve", "approve_with_conditions")) else "fail",
            "notes": f"status: {ia.get('status')}; decision: {ia.get('decision', '—')}",
        }
    return out


# -------------------------------------------------------------------- new
HEADER = """# AI system impact assessment - generated by `grc impact new`, completed by the assessor.
# 1. Complete `context`. 2. Screen EVERY category (relevant: true/false + rationale).
# 3. For each relevant category add impacts: likelihood/severity 1-5, mitigations, residual 1-5.
#    Residual >= {acc} needs `acceptance`; residual >= {unacc} cannot be approved.
# 4. Set assessor/assessed_on, decision; a different person approves (approver/approved_on, status: approved).
"""


def _next_number(edir: Path) -> int:
    nums = [int(m.group(1)) for p in (edir / "impact").glob("IA-*.yaml") if (m := re.fullmatch(r"IA-(\d+)", p.stem))]
    return max(nums or [0]) + 1


def new(model: Engagement, target: str) -> list[str]:
    systems = {i["id"]: i for i in required_systems(model)}
    if target != "all" and target not in systems:
        known = {i["id"]: i for i in model.inventory}
        if target in known and known[target].get("kind") in method(model)["required_for_kinds"]:
            raise ValueError(f"{target} is marked out of scope (in_scope: false) in inventory.yaml")
        if target in known:
            raise ValueError(f"{target} is a '{known[target].get('kind')}', not a kind that needs an impact assessment")
        raise ValueError(f"{target} is not in engagement/inventory.yaml")
    covered = set(active_by_system(model))
    todo = [s for sid, s in systems.items() if (target in ("all", sid)) and sid not in covered]
    m = method(model)
    log = []
    n = _next_number(model.engagement_dir)
    for s in todo:
        iid = f"IA-{n:03d}"
        n += 1
        path = model.engagement_dir / "impact" / f"{iid}.yaml"
        data = {
            "id": iid, "system": s["id"], "title": s.get("name", s["id"]), "status": "draft", "version": 1,
            "context": {
                "intended_use": s.get("description", ""), "foreseeable_misuse": "",
                "affected_parties": [], "deployment": "", "human_oversight": "", "data": "", "jurisdictions": [],
            },
            "screening": [{"category": c["id"], "relevant": None, "rationale": ""} for c in m["categories"]],
            "impacts": [],
            "conclusion": "", "decision": None, "conditions": [],
            "assessor": "", "assessed_on": None, "approver": "", "approved_on": None,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HEADER.format(acc=m["acceptance_required_at"], unacc=m["unacceptable_at"])
                        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
        log.append(f"{iid}  {s['id']}  {data['title']}  (risk tier: {s.get('risk_tier') or 'unset'})")
    if not log:
        log.append("Every AI system in scope already has an impact assessment.")
    return log
