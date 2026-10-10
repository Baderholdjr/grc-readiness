"""Validation rules. Each rule encodes part of the engagement's working rule:

    If a control is described but you cannot trace it to an owner, current
    artifact, and operating evidence, treat it as unresolved.

Severity:
  error   - blocks merge (CI fails)
  warning - shown in PR summary; fails only with --strict
  info    - analyst follow-up list (e.g. unverified client claims)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .model import LEGS, Engagement, jsonable, load_schema

TEST_TYPES = {"test", "sample", "interview"}
OPERATING_TYPES = {"record", "log", "config", "test", "sample", "screenshot", "interview"}


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    file: str | None = None
    ref: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _rel(model: Engagement, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(model.root))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------- schema
def check_schemas(model: Engagement) -> list[Finding]:
    out: list[Finding] = []

    def run(schema_name: str, data, path: Path, ref=None):
        v = Draft202012Validator(load_schema(schema_name), format_checker=FormatChecker())
        for err in sorted(v.iter_errors(jsonable(data)), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            out.append(Finding("error", "E001", f"Schema: {loc}: {err.message}", _rel(model, path), ref))

    edir = model.engagement_dir
    run("engagement", model.engagement, edir / "engagement.yaml")
    run("gaps", {"gaps": model.gaps}, edir / "gaps.yaml")
    n = model.human_evidence_count
    run("evidence", {"evidence": model.evidence[:n]}, edir / "evidence" / "index.yaml")
    if len(model.evidence) > n:
        run("evidence", {"evidence": model.evidence[n:]}, edir / "evidence" / "collected.yaml")
    if (edir / "collectors.yaml").exists():
        from .model import load_yaml
        cfg = load_yaml(edir / "collectors.yaml")
        run("collectors", cfg, edir / "collectors.yaml")
        known_ids = {e.get("id") for e in model.evidence[:n]}
        for chk in cfg.get("checks", []) or []:
            if chk.get("evidence") in known_ids:
                out.append(Finding("error", "E011", f"collectors.yaml check uses {chk['evidence']}, which is a human-owned "
                                   "evidence id in evidence/index.yaml. Use a separate id range (e.g. EV-1xx).",
                                   _rel(model, edir / "collectors.yaml"), chk["evidence"]))
    if (edir / "owners.yaml").exists():
        run("owners", {"owners": model.owners}, edir / "owners.yaml")
    if (edir / "audit" / "program.yaml").exists():
        run("audit-program", {"audits": model.audits}, edir / "audit" / "program.yaml")
    for key, path in model.workpaper_files.items():
        aid, wid = key.split("/")
        run("workpaper", model.workpapers[aid][wid], path, key)
    if (edir / "findings.yaml").exists():
        run("findings", {"findings": model.findings}, edir / "findings.yaml")
    if (edir / "inventory.yaml").exists():
        run("inventory", {"items": model.inventory}, edir / "inventory.yaml")
    for cid, data in model.controls.items():
        run("control", data, model.control_files[cid], cid)
    return out


# ------------------------------------------------------------------ structure
def check_structure(model: Engagement) -> list[Finding]:
    out: list[Finding] = []
    req_ids = model.requirement_index
    # E002 every requirement has an assessment file
    for rid in req_ids:
        if rid not in model.controls:
            out.append(Finding("error", "E002", f"No assessment file for requirement {rid}. Run `python -m grc init`.",
                               _rel(model, model.engagement_dir / "controls"), rid))
    # E003 unknown control ids / filename mismatch
    for cid, path in model.control_files.items():
        if cid not in req_ids:
            out.append(Finding("error", "E003", f"'{cid}' is not a requirement in the {model.catalog['framework']['short_name']} catalog.",
                               _rel(model, path), cid))
        elif path.stem != cid:
            out.append(Finding("error", "E003", f"File name should be {cid}.yaml.", _rel(model, path), cid))
    # E011 duplicate ids
    for label, items in (("evidence", model.evidence), ("gap", model.gaps)):
        seen = set()
        for it in items:
            if it.get("id") in seen:
                out.append(Finding("error", "E011", f"Duplicate {label} id {it['id']}.", None, it["id"]))
            seen.add(it.get("id"))
    return out


# ----------------------------------------------------------- applicability/SoA
def check_applicability(model: Engagement) -> list[Finding]:
    out = []
    for cid, c in model.controls.items():
        req = model.requirement_index.get(cid)
        if not req:
            continue
        path = _rel(model, model.control_files[cid])
        if req["kind"] == "clause" and c.get("applicable") is False:
            out.append(Finding("error", "E004", f"Clause {cid} is mandatory and cannot be excluded.", path, cid))
        if req["kind"] == "control" and c.get("applicable") is False and not (c.get("justification") or "").strip():
            out.append(Finding("error", "E004", f"Annex A control {cid} is excluded without a justification (needed for the SoA).", path, cid))
    return out


# --------------------------------------------------------- four-part evidence
def leg_effective(model: Engagement, leg: dict) -> str:
    """A 'verified' leg whose evidence has all expired is effectively 'partial'."""
    status = leg.get("status", "not_started")
    if status != "verified":
        return status
    evs = [model.evidence_index.get(e) for e in leg.get("evidence", [])]
    evs = [e for e in evs if e]
    if evs and not any(model.evidence_is_current(e) for e in evs):
        return "partial"
    return status


def check_evidence_test(model: Engagement) -> list[Finding]:
    out: list[Finding] = []
    ev_idx = model.evidence_index
    warn_days = int(model.engagement.get("evidence_expiry_warning_days", 30))
    for cid, c in model.controls.items():
        if cid not in model.requirement_index or not model.is_applicable(cid):
            continue
        path = _rel(model, model.control_files[cid])
        test = c.get("test", {})
        statuses = {k: test.get(k, {}).get("status", "not_started") for k in LEGS}

        # E009 owner required once there is real progress; claims alone only warn
        if not (c.get("owner") or "").strip():
            if any(s in ("partial", "verified") for s in statuses.values()):
                out.append(Finding("error", "E009", f"{cid} has progress recorded but no accountable owner.", path, cid))
            elif any(s == "claimed" for s in statuses.values()):
                out.append(Finding("warning", "W110", f"{cid} has client claims but no accountable owner yet.", path, cid))

        for k in LEGS:
            leg = test.get(k, {})
            st = statuses[k]
            refs = leg.get("evidence", [])
            # E006 unknown refs
            for r in refs:
                if r not in ev_idx:
                    out.append(Finding("error", "E006", f"{cid}.{k} cites {r}, which is not in evidence/index.yaml.", path, cid))
            known = [ev_idx[r] for r in refs if r in ev_idx]
            if st == "verified":
                # E005 verified needs evidence
                if not refs:
                    out.append(Finding("error", "E005", f"{cid}.{k} is 'verified' but cites no evidence.", path, cid))
                    continue
                # E007 expired / E015 collector failing
                if known and not any(model.evidence_is_current(e) for e in known):
                    failing = [e["id"] for e in known if model.evidence_is_failing(e)]
                    wps = [e["id"] for e in known if e.get("source") == "audit"]
                    if wps and len(wps) == len(known):
                        out.append(Finding("error", "E015", f"{cid}.{k} is 'verified' on audit workpaper(s) {', '.join(wps)} "
                                           "that are not concluded effective and independently reviewed.", path, cid))
                    elif failing:
                        out.append(Finding("error", "E015", f"{cid}.{k} is 'verified' but the collector check for "
                                           f"{', '.join(failing)} is failing; no other current evidence supports it.", path, cid))
                    else:
                        out.append(Finding("error", "E007", f"{cid}.{k} is 'verified' but all cited evidence has expired.", path, cid))
                # E012 evidence type fits the leg
                types = {e["type"] for e in known}
                if k == "documented":
                    if not any(e["type"] == "document" and e.get("approved_by") for e in known):
                        out.append(Finding("error", "E012", f"{cid}.documented needs an approved 'document' (with approved_by).", path, cid))
                elif k in ("implemented", "evidenced") and known and not types & OPERATING_TYPES:
                    out.append(Finding("error", "E012", f"{cid}.{k} cites only design documents; operating evidence (record/log/config/...) is required.", path, cid))
                elif k == "tested" and known and not types & TEST_TYPES:
                    out.append(Finding("error", "E012", f"{cid}.tested needs test, sample or interview evidence.", path, cid))
            # expiring soon
            for e in known:
                exp = model.evidence_expiry(e)
                if st == "verified" and exp and model.today <= exp <= model.today + dt.timedelta(days=warn_days):
                    out.append(Finding("warning", "W101", f"{cid}.{k}: {e['id']} expires {exp.isoformat()}.", path, cid))
            if st == "claimed":
                out.append(Finding("info", "I201", f"{cid}.{k} is a client claim not yet backed by evidence.", path, cid))

        # E008 leg ordering
        eff = {k: leg_effective(model, test.get(k, {})) for k in LEGS}
        if eff["tested"] == "verified" and eff["evidenced"] != "verified":
            out.append(Finding("error", "E008", f"{cid}: 'tested' cannot be verified before 'evidenced'.", path, cid))
        if eff["evidenced"] == "verified" and eff["implemented"] in ("not_started", "claimed"):
            out.append(Finding("error", "E008", f"{cid}: 'evidenced' cannot be verified while 'implemented' is {eff['implemented']}.", path, cid))
        # W102 implemented but not documented: the 'control codification' gap
        if eff["implemented"] == "verified" and eff["documented"] in ("not_started", "claimed"):
            out.append(Finding("warning", "W102", f"{cid} operates in practice but is not codified in an approved document.", path, cid))
        # E010 gap refs
        for g in c.get("gaps", []) or []:
            if g not in model.gap_index:
                out.append(Finding("error", "E010", f"{cid} links {g}, which is not in gaps.yaml.", path, cid))
    return out


# ---------------------------------------------------------------------- gaps
def check_gaps(model: Engagement) -> list[Finding]:
    out = []
    path = _rel(model, model.engagement_dir / "gaps.yaml")
    phases = model.phase_index
    for g in model.gaps:
        gid = g.get("id")
        for r in g.get("requirements", []):
            if r not in model.requirement_index:
                out.append(Finding("error", "E010", f"{gid} references unknown requirement {r}.", path, gid))
        ph = g.get("phase")
        if ph and ph not in phases:
            out.append(Finding("error", "E010", f"{gid} references unknown phase '{ph}'.", path, gid))
        open_ = g.get("status") in ("open", "in_progress")
        if open_ and not g.get("owner"):
            out.append(Finding("warning", "W103", f"{gid} is open with no owner.", path, gid))
        due = g.get("due")
        if open_ and due and dt.date.fromisoformat(str(due)) < model.today:
            out.append(Finding("warning", "W104", f"{gid} is past due ({due}).", path, gid))
        if due and ph in phases and dt.date.fromisoformat(str(due)) > dt.date.fromisoformat(str(phases[ph]["end"])):
            out.append(Finding("warning", "W105", f"{gid} is due {due}, after its phase '{ph}' ends {phases[ph]['end']}.", path, gid))
        if g.get("status") == "closed":
            if not g.get("closure_evidence"):
                out.append(Finding("error", "E013", f"{gid} is closed without closure_evidence.", path, gid))
            for e in g.get("closure_evidence", []):
                if e not in model.evidence_index:
                    out.append(Finding("error", "E006", f"{gid} cites unknown closure evidence {e}.", path, gid))
    return out


# -------------------------------------------------------------- engagement
def check_engagement(model: Engagement) -> list[Finding]:
    out = []
    path = _rel(model, model.engagement_dir / "engagement.yaml")
    b = model.engagement.get("budget", {})
    total, used = b.get("hours_total", 0), b.get("hours_used", 0) or 0
    if total and used / total >= 0.8:
        out.append(Finding("warning", "W106", f"Budget: {used:g} of {total:g} hours used ({used/total:.0%}).", path))
    d = model.engagement.get("dates", {})
    try:
        if d and dt.date.fromisoformat(str(d["stage1"])) >= dt.date.fromisoformat(str(d["stage2"])):
            out.append(Finding("error", "E014", "Stage 1 must be before Stage 2.", path))
    except (KeyError, ValueError):
        pass
    prev_end = None
    for p in model.engagement.get("phases", []):
        try:
            s, e = dt.date.fromisoformat(str(p["start"])), dt.date.fromisoformat(str(p["end"]))
        except (KeyError, ValueError):
            continue
        if e < s:
            out.append(Finding("error", "E014", f"Phase '{p['id']}' ends before it starts.", path))
        if prev_end and s < prev_end:
            out.append(Finding("warning", "W107", f"Phase '{p['id']}' overlaps the previous phase.", path))
        prev_end = e
    return out


def check_owners(model: Engagement) -> list[Finding]:
    """When owners.yaml exists, every owner named on controls and gaps should be in it."""
    if not model.owners:
        return []
    known = {o.get("role", "").strip().lower() for o in model.owners}
    seen: dict[str, str] = {}
    for cid, c in model.controls.items():
        if c.get("owner"):
            seen.setdefault(c["owner"], _rel(model, model.control_files[cid]))
    for g in model.gaps:
        if g.get("owner"):
            seen.setdefault(g["owner"], _rel(model, model.engagement_dir / "gaps.yaml"))
    out = []
    for name, where in sorted(seen.items()):
        if name.strip().lower() not in known:
            out.append(Finding("warning", "W111", f"Owner '{name}' is not in owners.yaml, so nobody is assigned or notified.",
                               where, name))
    return out


def check_audit(model: Engagement) -> list[Finding]:
    """Internal audit (9.2) and corrective action (10.2) integrity."""
    from .audit import in_scope
    out: list[Finding] = []
    edir = model.engagement_dir
    prog = _rel(model, edir / "audit" / "program.yaml")
    fpath = _rel(model, edir / "findings.yaml")
    users = lambda role: {u.lower() for u in model.github_users(role)}
    fidx = model.finding_index

    for a in model.audits:
        aid = a["id"]
        scope = in_scope(model, a)
        auditors = {x.strip().lower() for x in a.get("auditors", [])}
        # E020 independence: auditors must not audit their own controls
        conflicts = []
        for rid in scope:
            owner = (model.controls.get(rid, {}).get("owner") or "").strip()
            if owner and (owner.lower() in auditors or users(owner) & auditors):
                conflicts.append(f"{rid} ({owner})")
        if conflicts:
            out.append(Finding("error", "E020", f"{aid}: auditor(s) would audit controls they own: {', '.join(conflicts[:10])}"
                               + (" …" if len(conflicts) > 10 else "") + ". Exclude them from scope or change auditors.", prog, aid))
        try:
            if dt.date.fromisoformat(str(a["planned"]["end"])) < dt.date.fromisoformat(str(a["planned"]["start"])):
                out.append(Finding("error", "E014", f"{aid}: planned end is before start.", prog, aid))
        except (KeyError, ValueError):
            pass
        wps = model.workpapers.get(aid, {})
        if a.get("status") in ("fieldwork", "reporting", "closed") and not wps:
            out.append(Finding("error", "E021", f"{aid} is '{a['status']}' but has no workpapers (run `grc audit plan {aid}`).", prog, aid))
        open_wps = [w for w, wp in wps.items() if wp.get("conclusion", "not_started") == "not_started"]
        if a.get("status") in ("reporting", "closed") and open_wps:
            out.append(Finding("error", "E021", f"{aid} is '{a['status']}' but {len(open_wps)} workpaper(s) are not concluded: "
                               + ", ".join(open_wps[:8]), prog, aid))
        unreviewed = [w for w, wp in wps.items() if wp.get("conclusion") not in (None, "not_started") and not wp.get("reviewed_by")]
        if a.get("status") == "closed":
            if unreviewed:
                out.append(Finding("error", "E021", f"{aid} is closed but workpapers lack review: {', '.join(unreviewed[:8])}", prog, aid))
            rep = a.get("report") or {}
            if not (rep.get("issued") and rep.get("approved_by")):
                out.append(Finding("error", "E021", f"{aid} is closed without report.issued and report.approved_by.", prog, aid))
        if a.get("status") in ("planned", "fieldwork"):
            try:
                if dt.date.fromisoformat(str(a["planned"]["end"])) < model.today:
                    out.append(Finding("warning", "W122", f"{aid} planned to finish {a['planned']['end']} but is still '{a['status']}'.", prog, aid))
            except (KeyError, ValueError):
                pass
        for rid in scope:
            if not any(wp.get("requirement") == rid for wp in wps.values()) and wps:
                out.append(Finding("warning", "W123", f"{aid}: {rid} is in scope but has no workpaper (re-run `grc audit plan`).", prog, aid))

        # workpapers
        for wid, wp in wps.items():
            path = _rel(model, model.workpaper_files[f"{aid}/{wid}"])
            ref = f"{aid}/{wid}"
            if wp.get("audit") != aid:
                out.append(Finding("error", "E025", f"{ref}: audit field is '{wp.get('audit')}'.", path, ref))
            if wp.get("requirement") not in model.requirement_index:
                out.append(Finding("error", "E025", f"{ref}: unknown requirement {wp.get('requirement')}.", path, ref))
            concl = wp.get("conclusion", "not_started")
            sample = wp.get("sample") or []
            pending = [str(s["item"]) for s in sample if s.get("result", "not_tested") == "not_tested"]
            exceptions = [str(s["item"]) for s in sample if s.get("result") == "exception"]
            if concl in ("effective", "not_effective"):
                if not (wp.get("performed_by") and wp.get("performed_on")):
                    out.append(Finding("error", "E022", f"{ref} is concluded without performed_by/performed_on.", path, ref))
                if pending:
                    out.append(Finding("error", "E022", f"{ref} is concluded with {len(pending)} untested sample item(s): {', '.join(pending[:6])}.", path, ref))
                if not (wp.get("summary") or "").strip():
                    out.append(Finding("error", "E022", f"{ref} is concluded without a summary of what was tested.", path, ref))
            if concl == "effective" and exceptions and not (wp.get("exception_rationale") or "").strip():
                out.append(Finding("error", "E022", f"{ref} is 'effective' despite exceptions ({', '.join(exceptions[:6])}) "
                                   "with no exception_rationale.", path, ref))
            if concl == "not_effective" and not wp.get("findings"):
                out.append(Finding("error", "E022", f"{ref} is 'not_effective' but raises no finding.", path, ref))
            for fid in wp.get("findings") or []:
                if fid not in fidx:
                    out.append(Finding("error", "E025", f"{ref} cites {fid}, which is not in findings.yaml.", path, ref))
            if wp.get("reviewed_by") and wp.get("reviewed_by") == wp.get("performed_by"):
                out.append(Finding("error", "E022", f"{ref} is reviewed by the person who performed it.", path, ref))
            if wp.get("reviewed_by") and concl == "not_started":
                out.append(Finding("error", "E022", f"{ref} is marked reviewed but not concluded.", path, ref))

    # findings register (10.2)
    ev_idx = model.evidence_index
    for f in model.findings:
        fid, st = f["id"], f.get("status")
        if f.get("requirement") not in model.requirement_index:
            out.append(Finding("error", "E025", f"{fid}: unknown requirement {f.get('requirement')}.", fpath, fid))
        if f.get("audit") and f["audit"] not in model.audit_index:
            out.append(Finding("error", "E025", f"{fid}: unknown audit {f['audit']}.", fpath, fid))
        if f.get("workpaper") and f.get("audit") and f["workpaper"] not in model.workpapers.get(f["audit"], {}):
            out.append(Finding("error", "E025", f"{fid}: unknown workpaper {f['audit']}/{f['workpaper']}.", fpath, fid))
        if f["id"].startswith("OFI") != (f.get("grade") == "ofi"):
            out.append(Finding("error", "E024", f"{fid}: OFI-… ids are for grade 'ofi'; NC-… ids for major/minor.", fpath, fid))
        if f.get("grade") == "ofi":
            continue
        need = []
        if st in ("action_planned", "implemented", "closed"):
            need = [k for k in ("owner", "due", "root_cause", "corrective_action") if not (str(f.get(k) or "")).strip()]
            if need:
                out.append(Finding("error", "E024", f"{fid} is '{st}' without {', '.join(need)}.", fpath, fid))
        if st in ("implemented", "closed") and not f.get("evidence"):
            out.append(Finding("error", "E024", f"{fid} is '{st}' without implementation evidence.", fpath, fid))
        if st == "closed":
            eff = f.get("effectiveness") or {}
            if not (eff.get("effective") is True and eff.get("reviewed_by") and eff.get("reviewed_on") and eff.get("evidence")):
                out.append(Finding("error", "E024", f"{fid} is closed without an effectiveness review "
                                   "(effective: true, reviewed_by, reviewed_on, evidence).", fpath, fid))
            elif (eff.get("reviewed_by") or "").strip().lower() == (f.get("owner") or "").strip().lower():
                out.append(Finding("error", "E024", f"{fid}: effectiveness was reviewed by the action owner.", fpath, fid))
        if st == "accepted" and f.get("grade") == "major":
            out.append(Finding("error", "E024", f"{fid}: a major nonconformity cannot be risk-accepted; it must be corrected.", fpath, fid))
        for e in (f.get("evidence") or []) + ((f.get("effectiveness") or {}).get("evidence") or []):
            if e not in ev_idx:
                out.append(Finding("error", "E006", f"{fid} cites unknown evidence {e}.", fpath, fid))
        if st not in ("closed", "accepted") and f.get("due"):
            try:
                if dt.date.fromisoformat(str(f["due"])) < model.today:
                    out.append(Finding("warning", "W120", f"{fid} ({f['grade']}) is past due ({f['due']}).", fpath, fid))
            except ValueError:
                pass
        if st == "open" and not f.get("owner"):
            out.append(Finding("warning", "W103", f"{fid} is open with no owner.", fpath, fid))
        # E026: an open major NC contradicts a 'verified' tested leg
        if f.get("grade") == "major" and st not in ("closed",):
            c = model.controls.get(f.get("requirement"), {})
            if (c.get("test", {}).get("tested", {}) or {}).get("status") == "verified":
                out.append(Finding("error", "E026", f"{f['requirement']}.tested is 'verified' but {fid} (major) is still {st}.",
                                   _rel(model, model.control_files.get(f["requirement"])), f["requirement"]))

    # W121: clause 9.2 can't be operating without a completed audit
    c92 = model.controls.get("9.2", {}).get("test", {})
    if any((c92.get(k) or {}).get("status") == "verified" for k in ("evidenced", "tested")) and \
            not any(a.get("status") in ("reporting", "closed") for a in model.audits):
        out.append(Finding("warning", "W121", "9.2 is marked verified but no internal audit has reached reporting.",
                           _rel(model, model.control_files.get("9.2")), "9.2"))
    return out


def check_collected(model: Engagement) -> list[Finding]:
    out = []
    path = _rel(model, model.engagement_dir / "evidence" / "collected.yaml")
    for e in model.evidence:
        if e.get("result") == "fail":
            out.append(Finding("warning", "W108", f"{e['id']} ({e['title']}) collector check is failing: {e.get('notes', '')}"[:300], path, e["id"]))
        elif e.get("result") == "error":
            out.append(Finding("warning", "W109", f"{e['id']} ({e['title']}) could not be collected: {e.get('notes', '')}"[:300], path, e["id"]))
    return out


ALL_RULES = (check_schemas, check_structure, check_applicability, check_evidence_test, check_gaps, check_engagement, check_collected, check_owners, check_audit)


def validate(model: Engagement) -> list[Finding]:
    findings: list[Finding] = []
    schema_findings = check_schemas(model)
    findings.extend(schema_findings)
    for rule in ALL_RULES[1:]:
        try:
            findings.extend(rule(model))
        except (KeyError, TypeError, ValueError) as exc:  # malformed data already reported by schema check
            if not schema_findings:
                findings.append(Finding("error", "E000", f"{rule.__name__} could not run: {exc!r}"))
    return findings


# ----------------------------------------------------------- readiness metrics
def requirement_state(model: Engagement, cid: str) -> str:
    if not model.is_applicable(cid):
        return "Excluded"
    c = model.controls.get(cid)
    if not c:
        return "Missing"
    eff = {k: leg_effective(model, c.get("test", {}).get(k, {})) for k in LEGS}
    if all(v == "verified" for v in eff.values()):
        return "Ready"
    if all(v == "not_started" for v in eff.values()):
        return "Not started"
    if all(v in ("not_started", "claimed") for v in eff.values()):
        return "Unverified claim"
    return "In progress"


def metrics(model: Engagement) -> dict:
    applicable = [r["id"] for r in model.requirements if model.is_applicable(r["id"])]
    legs = {k: {"verified": 0, "partial": 0, "claimed": 0, "not_started": 0} for k in LEGS}
    for cid in applicable:
        c = model.controls.get(cid, {})
        for k in LEGS:
            legs[k][leg_effective(model, c.get("test", {}).get(k, {}))] += 1
    states: dict[str, int] = {}
    for r in model.requirements:
        s = requirement_state(model, r["id"])
        states[s] = states.get(s, 0) + 1
    ready = states.get("Ready", 0)
    total_legs = len(applicable) * 4
    verified_legs = sum(v["verified"] for v in legs.values())
    gaps_open = sum(1 for g in model.gaps if g.get("status") in ("open", "in_progress"))
    stale = [e["id"] for e in model.evidence if model.evidence_is_expired(e)]
    failing = [e["id"] for e in model.evidence if model.evidence_is_failing(e)]
    b = model.engagement.get("budget", {})
    return {
        "as_of": model.today.isoformat(),
        "framework": model.catalog["framework"]["short_name"],
        "requirements_total": len(model.requirements),
        "requirements_applicable": len(applicable),
        "requirements_ready": ready,
        "states": states,
        "legs": legs,
        "legs_verified_pct": round(100 * verified_legs / total_legs, 1) if total_legs else 0.0,
        "gaps_open": gaps_open,
        "gaps_total": len(model.gaps),
        "evidence_total": len(model.evidence),
        "evidence_stale": stale,
        "evidence_failing": failing,
        "findings_total": len(model.findings),
        "nc_open_major": sum(1 for f in model.findings if f.get("grade") == "major" and f.get("status") not in ("closed", "accepted")),
        "nc_open_minor": sum(1 for f in model.findings if f.get("grade") == "minor" and f.get("status") not in ("closed", "accepted")),
        "audits": {a["id"]: a.get("status") for a in model.audits},
        "hours_total": b.get("hours_total"),
        "hours_used": b.get("hours_used", 0),
    }
