"""Internal audit (ISO 42001 clause 9.2) and the corrective action register (10.2).

Files (all under engagement/):
  audit/program.yaml                      the audit programme (human-owned)
  audit/<AUD-ID>/workpapers/WP-NN.yaml    one per requirement in scope (generated, then filled in)
  audit/populations/*.csv                 optional hand-supplied sample populations
  findings.yaml                           nonconformities, OFIs and corrective actions

    python -m grc audit plan   AUD-2027-01   # workpaper per in-scope requirement, with test steps
    python -m grc audit sample AUD-2027-01   # draw reproducible samples from the populations

Sampling is deterministic: the same population and audit/workpaper ids always
select the same items, and the population size and hash are recorded, so an
auditor can re-perform the selection.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import random
import re
from pathlib import Path

import yaml

from .model import LEGS, Engagement, load_yaml

# Default sample sizes by population size (a common internal-audit convention;
# override per workpaper with `sample_size`).
SAMPLE_TABLE = [(1, 1), (4, 2), (12, 3), (52, 5), (250, 15)]
SAMPLE_MAX = 25


def default_sample_size(population: int) -> int:
    if population <= 0:
        return 0
    for upper, n in SAMPLE_TABLE:
        if population <= upper:
            return min(n, population)
    return SAMPLE_MAX


# ------------------------------------------------------------------- scope
def _selectors(value) -> list[str]:
    if value is None or value == "all":
        return []
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return [str(value)]  # a single string/number, not its characters


def _match(rid: str, req: dict, sel: str) -> bool:
    return rid == sel or req.get("group") == sel or rid.startswith(sel + ".")


def in_scope(model: Engagement, audit: dict) -> list[str]:
    scope = audit.get("scope", "all")
    reqs = [r for r in model.requirements if model.is_applicable(r["id"])]
    if scope != "all":
        sels = _selectors(scope)
        reqs = [r for r in reqs if any(_match(r["id"], r, s) for s in sels)]
    excl = _selectors(audit.get("exclude"))
    return [r["id"] for r in reqs if not any(_match(r["id"], r, s) for s in excl)]


def unmatched_scope(model: Engagement, audit: dict) -> list[str]:
    """Scope/exclude entries that match no requirement - usually a typo."""
    sels = _selectors(audit.get("scope")) + _selectors(audit.get("exclude"))
    return [s for s in sels if not any(_match(r["id"], r, s) for r in model.requirements)]


def _check_program(model: Engagement) -> None:
    """Refuse to plan/sample from a programme that fails its schema."""
    from jsonschema import Draft202012Validator
    from .model import jsonable, load_schema
    errs = list(Draft202012Validator(load_schema("audit-program")).iter_errors(jsonable({"audits": model.audits})))
    if errs:
        e = errs[0]
        raise ValueError(f"program.yaml is invalid at {'/'.join(map(str, e.path)) or '(root)'}: {e.message}")


def audit_dir(model: Engagement, audit_id: str) -> Path:
    return model.engagement_dir / "audit" / audit_id


# -------------------------------------------------------------- populations
def _collector_populations(model: Engagement) -> dict[str, list[str]]:
    """requirement id -> collector evidence ids whose snapshots list items."""
    cfg_path = model.engagement_dir / "collectors.yaml"
    cfg = load_yaml(cfg_path) if cfg_path.exists() else {}
    out: dict[str, list[str]] = {}
    for chk in cfg.get("checks", []) or []:
        snap = model.engagement_dir / "evidence" / "collected" / f"{chk['evidence']}.json"
        if not snap.exists() or not json.loads(snap.read_text()).get("details", {}).get("items"):
            continue
        for ref in chk.get("supports", []) or []:
            out.setdefault(ref.rsplit(":", 1)[0], []).append(chk["evidence"])
    return out


def load_population(model: Engagement, audit: dict, name: str) -> tuple[list[str], str]:
    """Items (as strings) and a description of where they came from."""
    spec = (audit.get("populations") or {}).get(name)
    if spec is None and name.startswith("EV-"):
        spec = {"from_evidence": name}
    if spec is None:
        raise ValueError(f"unknown population '{name}' (define it under populations: in program.yaml)")
    if "items" in spec:
        return [str(x) for x in spec["items"]], f"listed in program.yaml ({name})"
    if "from_evidence" in spec:
        ev = spec["from_evidence"]
        snap = model.engagement_dir / "evidence" / "collected" / f"{ev}.json"
        if not snap.exists():
            raise ValueError(f"population '{name}': no snapshot for {ev} (run the collector first)")
        data = json.loads(snap.read_text())
        items = data.get("details", {}).get("items") or []
        key = spec.get("key", "id")
        missing = sum(1 for i in items if isinstance(i, dict) and i.get(key) in (None, ""))
        if missing:
            raise ValueError(f"population '{name}': {missing} item(s) in {ev} have no '{key}'")
        note = " (TRUNCATED by the collector - population may be incomplete)" if data.get("details", {}).get("truncated") else ""
        return ([str(i.get(key)) if isinstance(i, dict) else str(i) for i in items],
                f"{ev} snapshot collected {data.get('collected_at', '?')}{note}")
    if "file" in spec:
        path = model.engagement_dir / "audit" / spec["file"]
        if not path.is_file():
            raise ValueError(f"population '{name}': file engagement/audit/{spec['file']} not found")
        if path.suffix.lower() in (".yaml", ".yml"):
            rows = load_yaml(path)
            rows = rows.get("items", rows) if isinstance(rows, dict) else rows
        else:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        key = spec.get("key", "id")
        rows = rows or []
        missing = sum(1 for r in rows if isinstance(r, dict) and r.get(key) in (None, ""))
        if missing:
            raise ValueError(f"population '{name}': {missing} row(s) in {spec['file']} have no '{key}' column value")
        return [str(r.get(key)) if isinstance(r, dict) else str(r) for r in rows], f"file {spec['file']}"
    raise ValueError(f"population '{name}' needs one of: items, from_evidence, file")


def draw(items: list[str], n: int, seed: str) -> list[str]:
    """Deterministic selection: same items + seed -> same sample, in population order."""
    pop = sorted(set(items), key=lambda x: (len(x), x))
    if n >= len(pop):
        return pop
    chosen = set(random.Random(seed).sample(pop, n))
    return [x for x in pop if x in chosen]


def population_hash(items: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(set(items))).encode()).hexdigest()


# --------------------------------------------------------------- procedures
def procedures(model: Engagement, rid: str, population: str | None) -> list[str]:
    custom = {str(k): v for k, v in (model.playbook.get("audit_procedures") or {}).items()}.get(rid)
    if custom:
        return list(custom)
    req = model.requirement_index[rid]
    ctl = model.controls.get(rid, {})
    examples = ", ".join(req.get("evidence_examples", [])) or "records of operation"
    steps = [
        f"Inspect the documented requirement ({examples.split(',')[0].strip()}): confirm it is approved, current, "
        f"and addresses: {req['intent']}",
        f"Interview the owner ({ctl.get('owner') or 'owner not yet assigned'}) about how the process operates in practice.",
    ]
    if population:
        steps.append(f"For each sampled item from population '{population}', confirm it demonstrates the requirement "
                     "operating as designed; record pass or exception with a note.")
    else:
        steps.append(f"Obtain records of operation for the audit period ({examples}) and confirm they demonstrate "
                     "the requirement operating as designed.")
    claimed = [k for k in LEGS if (ctl.get("test", {}).get(k, {}) or {}).get("status") == "claimed"]
    if claimed:
        steps.append(f"Client claims on this control ({', '.join(claimed)}) are not evidence: obtain support or raise a finding.")
    gaps = ctl.get("gaps") or []
    if gaps:
        steps.append(f"Check the status of linked gaps ({', '.join(gaps)}); open gaps usually mean a nonconformity.")
    steps.append("Conclude: effective / not effective. Raise a finding in findings.yaml for every exception "
                 "that is not explained in exception_rationale.")
    return steps


# --------------------------------------------------------------------- plan
HEADER = ("# Internal audit workpaper - generated by `grc audit plan`, completed by the auditor.\n"
          "# Fill in: sample results (pass/exception), conclusion, summary, performed_by/on.\n"
          "# A different person sets reviewed_by/on. Raise findings in engagement/findings.yaml.\n")


def _write_wp(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")


def plan(model: Engagement, audit_id: str) -> list[str]:
    audit = model.audit_index.get(audit_id)
    if not audit:
        raise ValueError(f"{audit_id} is not in engagement/audit/program.yaml")
    _check_program(model)
    existing = model.workpapers.get(audit_id, {})
    covered = {wp.get("requirement") for wp in existing.values()}
    wdir = audit_dir(model, audit_id) / "workpapers"
    files = [p.stem for p in wdir.glob("WP-*.yaml")] if wdir.is_dir() else []
    n = max([int(m.group(1)) for f in files if (m := re.fullmatch(r"WP-(\d+)", f))] or [0])
    pops = _collector_populations(model)
    log = [f"warning: scope/exclude entry '{s}' matches no requirement" for s in unmatched_scope(model, audit)]
    for rid in in_scope(model, audit):
        if rid in covered:
            continue
        n += 1
        wid = f"WP-{n:02d}"
        while (wdir / f"{wid}.yaml").exists():  # never overwrite an existing workpaper
            n += 1
            wid = f"WP-{n:02d}"
        population = (pops.get(rid) or [None])[0]
        data = {"id": wid, "audit": audit_id, "requirement": rid, "title": model.requirement_index[rid]["title"],
                "procedure": procedures(model, rid, population)}
        if population:
            data["population"] = population
        data.update({"sample": [], "conclusion": "not_started", "summary": "", "findings": [],
                     "performed_by": "", "reviewed_by": ""})
        _write_wp(audit_dir(model, audit_id) / "workpapers" / f"{wid}.yaml", data)
        log.append(f"{wid}  {rid:8} {data['title'][:60]}" + (f"  [population {population}]" if population else ""))
    if not [x for x in log if not x.startswith("warning:")]:
        log.append("All in-scope requirements already have workpapers.")
    return log


# ------------------------------------------------------------------- sample
def sample(model: Engagement, audit_id: str, force: bool = False) -> list[str]:
    audit = model.audit_index.get(audit_id)
    if not audit:
        raise ValueError(f"{audit_id} is not in engagement/audit/program.yaml")
    _check_program(model)
    log = []
    for wid, wp in sorted(model.workpapers.get(audit_id, {}).items()):
        pop_name = wp.get("population")
        if not pop_name:
            continue
        entries = wp.get("sample", []) or []
        tested = [s for s in entries if not isinstance(s, dict) or s.get("result", "not_tested") != "not_tested"]
        if wp.get("sample") and not force:
            log.append(f"{wid}: already sampled ({len(wp['sample'])} items) - use --force to redraw")
            continue
        if tested and force:
            log.append(f"{wid}: NOT redrawn - {len(tested)} item(s) already have results")
            continue
        try:
            items, source = load_population(model, audit, pop_name)
            size = wp.get("sample_size")
            if size is None:
                size = default_sample_size(len(set(items)))
            elif not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ValueError(f"sample_size must be a whole number >= 0 (got {size!r})")
        except ValueError as exc:
            log.append(f"{wid}: {exc}")
            continue
        seed = f"{audit_id}/{wid}"
        chosen = draw(items, size, seed)
        dupes = len(items) - len(set(items))
        wp["sampling"] = {"population_size": len(set(items)), "population_sha256": population_hash(items),
                          "seed": seed, "drawn_on": model.today.isoformat(),
                          "method": f"deterministic random (Python random.Random(seed)); source: {source}"
                                    + (f"; {dupes} duplicate item(s) counted once" if dupes else "")}
        wp["sample"] = [{"item": x, "result": "not_tested", "note": ""} for x in chosen]
        _write_wp(model.workpaper_files[f"{audit_id}/{wid}"], {k: wp[k] for k in _ordered(wp)})
        log.append(f"{wid}: sampled {len(chosen)} of {len(set(items))} from {pop_name}")
    if not log:
        log.append("No workpapers with a population to sample.")
    return log


ORDER = ["id", "audit", "requirement", "title", "procedure", "evidence_reviewed", "population", "sample_size",
         "sampling", "sample", "conclusion", "summary", "exception_rationale", "findings",
         "performed_by", "performed_on", "reviewed_by", "reviewed_on"]


def _ordered(wp: dict) -> list[str]:
    return [k for k in ORDER if k in wp] + [k for k in wp if k not in ORDER]


# ------------------------------------------------------------------ metrics
def audit_status(model: Engagement, audit_id: str) -> dict:
    wps = model.workpapers.get(audit_id, {})
    concl = {}
    for wp in wps.values():
        concl[wp.get("conclusion", "not_started")] = concl.get(wp.get("conclusion", "not_started"), 0) + 1
    fs = [f for f in model.findings if f.get("audit") == audit_id]
    return {"workpapers": len(wps), "conclusions": concl,
            "reviewed": sum(1 for wp in wps.values() if wp.get("reviewed_by")),
            "findings": {g: sum(1 for f in fs if f["grade"] == g) for g in ("major", "minor", "ofi")},
            "open_findings": sum(1 for f in fs if f["status"] not in ("closed", "accepted"))}
