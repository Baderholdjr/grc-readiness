"""Deterministic import of the CSV/XLSX intake templates (no AI involved).

A file is recognised by its header row, not its name:
  gaps       area, finding, requirements, [owner, due, severity, phase]
  evidence   title, type, location, [owner, collected, approved_by, approved_on, valid_for_days]
  controls   requirement, leg, status, [owner, note]
  inventory  name, kind, [owner, risk_tier, description]
"""
from __future__ import annotations

import re

from .draft import EVIDENCE_TYPES, INVENTORY_KINDS, LEG_ALIASES, SEVERITIES, empty

KINDS = {
    "gaps": {"area", "finding", "requirements"},
    "evidence": {"title", "type", "location"},
    "controls": {"requirement", "leg", "status"},
    "inventory": {"name", "kind"},
}


def _norm(h: str) -> str:
    return re.sub(r"[^a-z_]", "", h.strip().lower().replace(" ", "_"))


def detect(header: list[str]) -> str | None:
    cols = {_norm(h) for h in header}
    for kind, need in KINDS.items():
        if need <= cols:
            return kind
    return None


def _split(v: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;,\n]", v or "") if x.strip()]


def to_draft(table: list[list[str]], source: str) -> tuple[str | None, dict, list[str]]:
    """Returns (kind, draft, problems)."""
    d, problems = empty(), []
    if not table:
        return None, d, ["empty file"]
    header = [_norm(h) for h in table[0]]
    kind = detect(table[0])
    if not kind:
        return None, d, [f"header not recognised as an intake template: {table[0]}"]
    for n, raw in enumerate(table[1:], start=2):
        row = {header[i]: (raw[i] if i < len(raw) else "").strip() for i in range(len(header))}
        if not any(row.values()) or row.get(header[0], "").startswith("#"):
            continue
        src = f"{source} row {n}"
        if kind == "gaps":
            sev = row.get("severity", "").lower()
            d["gaps"].append({"area": row["area"], "finding": row["finding"], "requirements": _split(row["requirements"]),
                              "owner": row.get("owner", ""), "severity": sev if sev in SEVERITIES else "medium",
                              "due": row.get("due", ""), "phase": row.get("phase", ""), "source": src})
        elif kind == "evidence":
            t = row["type"].lower()
            if t not in EVIDENCE_TYPES:
                problems.append(f"{src}: type '{row['type']}' not one of {EVIDENCE_TYPES}; used 'record'")
                t = "record"
            d["evidence"].append({"title": row["title"], "type": t, "location": row["location"],
                                  "owner": row.get("owner", ""), "date": row.get("collected", ""),
                                  "approved_by": row.get("approved_by", ""), "approved_on": row.get("approved_on", ""),
                                  "valid_for_days": row.get("valid_for_days", ""), "source": src})
        elif kind == "controls":
            leg = LEG_ALIASES.get(row["leg"].strip().lower())
            if not leg:
                problems.append(f"{src}: unknown leg '{row['leg']}'")
                continue
            status = row["status"].strip().lower()
            if status in ("", "not_started", "no", "none"):
                continue
            d["claims"].append({"requirement": row["requirement"], "leg": leg,
                                "statement": row.get("note", "") or f"client reported '{status}'",
                                "owner": row.get("owner", ""), "source": src})
        elif kind == "inventory":
            k = row["kind"].lower().replace(" ", "_")
            if k not in INVENTORY_KINDS:
                problems.append(f"{src}: kind '{row['kind']}' not one of {INVENTORY_KINDS}; used 'ai_system'")
                k = "ai_system"
            d["inventory"].append({"name": row["name"], "kind": k, "owner": row.get("owner", ""),
                                   "risk_tier": row.get("risk_tier", ""), "description": row.get("description", ""),
                                   "source": src})
    return kind, d, problems
