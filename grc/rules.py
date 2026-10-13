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
    for iid, path in model.impact_files.items():
        run("impact-assessment", model.impacts[iid], path, iid)
    for sid, path in model.submission_files.items():
        s = model.submissions[sid]
        if s.get("_error"):
            out.append(Finding("error", "E001", f"{sid}: {s['_error']}.", _rel(model, path), sid))
        else:
            run("submission", s, path, sid)
    for rid, path in model.review_files.items():
        r = model.reviews[rid]
        if isinstance(r, dict) and r.get("_error"):
            out.append(Finding("error", "E001", f"{rid}: {r['_error']}.", _rel(model, path), rid))
        else:
            run("management-review", r, path, rid)
    for did, path in model.document_files.items():
        d = model.documents[did]
        if d.get("error"):
            out.append(Finding("error", "E001", f"{did}: {d['error']}.", _rel(model, path), did))
        else:
            run("document", d["raw"], path, did)
    if (edir / "hours.yaml").exists():
        run("hours", {**model.hours_meta, "entries": model.hours}, edir / "hours.yaml")
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
    for label, items in (("evidence", model.evidence), ("gap", model.gaps), ("finding", model.findings),
                         ("audit", model.audits)):
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
                    wps = [e["id"] for e in known if e.get("source") == "audit" and model.evidence_is_failing(e)]
                    ias = [e["id"] for e in known if e.get("source") == "impact" and model.evidence_is_failing(e)]
                    dcs = [e["id"] for e in known if e.get("source") == "document" and model.evidence_is_failing(e)]
                    mrs = [e["id"] for e in known if e.get("source") == "review" and model.evidence_is_failing(e)]
                    if mrs and len(mrs) == len(known):
                        out.append(Finding("error", "E015", f"{cid}.{k} is 'verified' on management review(s) {', '.join(mrs)} "
                                           "that are not held with complete, approved minutes.", path, cid))
                    elif dcs and len(dcs) == len(known):
                        out.append(Finding("error", "E015", f"{cid}.{k} is 'verified' on document(s) {', '.join(dcs)} "
                                           "that are not soundly approved (see E041/E042).", path, cid))
                    elif ias and len(ias) == len(known):
                        out.append(Finding("error", "E015", f"{cid}.{k} is 'verified' on impact assessment(s) {', '.join(ias)} "
                                           "that are not approved (independently, with an approve decision).", path, cid))
                    elif wps and len(wps) == len(known):
                        out.append(Finding("error", "E015", f"{cid}.{k} is 'verified' on audit workpaper(s) {', '.join(wps)} "
                                           "that are not concluded effective and independently reviewed.", path, cid))
                    elif failing and not any(e.get("source") in ("audit", "impact", "document", "review") for e in known if e["id"] in failing):
                        out.append(Finding("error", "E015", f"{cid}.{k} is 'verified' but the collector check for "
                                           f"{', '.join(failing)} is failing; no other current evidence supports it.", path, cid))
                    else:
                        out.append(Finding("error", "E007", f"{cid}.{k} is 'verified' but all cited evidence has expired.", path, cid))
                # E012 evidence type fits the leg - judged on CURRENT evidence only, so an expired
                # document or an unreviewed workpaper can't make up the required type.
                cur = [e for e in known if model.evidence_is_current(e)]
                types = {e["type"] for e in cur}
                if cur and k == "documented":
                    if not any(e["type"] == "document" and e.get("approved_by") for e in cur):
                        out.append(Finding("error", "E012", f"{cid}.documented needs a current, approved 'document' (with approved_by).", path, cid))
                elif cur and k in ("implemented", "evidenced") and not types & OPERATING_TYPES:
                    out.append(Finding("error", "E012", f"{cid}.{k} cites only design documents; operating evidence (record/log/config/...) is required.", path, cid))
                elif cur and k == "tested" and not types & TEST_TYPES:
                    out.append(Finding("error", "E012", f"{cid}.tested needs current test, sample or interview evidence.", path, cid))
                # W125: an audit workpaper cited for a different requirement
                for e in known:
                    if e.get("source") == "audit":
                        aid, wid = e["id"].split("/")
                        wreq = model.workpapers.get(aid, {}).get(wid, {}).get("requirement")
                        if wreq and wreq != cid:
                            out.append(Finding("warning", "W125", f"{cid}.{k} cites {e['id']}, which tested {wreq}.", path, cid))
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
                elif model.evidence_index[e].get("source") in ("audit", "impact", "document", "review") and model.evidence_is_failing(model.evidence_index[e]):
                    out.append(Finding("error", "E013", f"{gid} is closed on {e}, which isn't approved/concluded effective "
                                       "and independently reviewed.", path, gid))
    return out


# -------------------------------------------------------------- engagement
def check_engagement(model: Engagement) -> list[Finding]:
    out = []
    path = _rel(model, model.engagement_dir / "engagement.yaml")
    from . import hours as H
    b = model.engagement.get("budget", {})
    total, used = b.get("hours_total", 0), H.hours_used(model)
    if total and used / total >= float(H.method(model).get("warn_at") or 0.8):
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
    out: list[Finding] = []
    prog = _rel(model, model.engagement_dir / "audit" / "program.yaml")
    fpath = _rel(model, model.engagement_dir / "findings.yaml")
    for a in model.audits:
        try:
            _check_one_audit(model, a, prog, out)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            out.append(Finding("error", "E000", f"{a.get('id', '?')}: could not evaluate this audit ({exc!r}); "
                               "fix the schema errors above.", prog, str(a.get("id"))))
    for f in model.findings:
        try:
            _check_one_finding(model, f, fpath, out)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            out.append(Finding("error", "E000", f"{f.get('id', '?')}: could not evaluate this finding ({exc!r}).", fpath, str(f.get("id"))))
    # W121: clause 9.2 can't be operating without a completed audit
    c92 = model.controls.get("9.2", {}).get("test", {})
    if any((c92.get(k) or {}).get("status") == "verified" for k in ("evidenced", "tested")) and \
            not any(a.get("status") in ("reporting", "closed") for a in model.audits):
        out.append(Finding("warning", "W121", "9.2 is marked verified but no internal audit has reached reporting.",
                           _rel(model, model.control_files.get("9.2")), "9.2"))
    return out


def _owner_of(model: Engagement, rid: str | None) -> str:
    return (model.controls.get(rid or "", {}).get("owner") or "").strip()


def _check_one_audit(model: Engagement, a: dict, prog: str, out: list[Finding]) -> None:
    from .audit import in_scope, unmatched_scope
    aid = a["id"]
    scope = in_scope(model, a)
    for sel in unmatched_scope(model, a):
        out.append(Finding("warning", "W124", f"{aid}: scope/exclude entry '{sel}' matches no requirement.", prog, aid))
    auditor_ids = set().union(*[model.identities(x) for x in a.get("auditors", [])]) if a.get("auditors") else set()
    # E020 independence: auditors must not audit their own controls
    conflicts = [f"{rid} ({_owner_of(model, rid)})" for rid in scope
                 if _owner_of(model, rid) and model.identities(_owner_of(model, rid)) & auditor_ids]
    if conflicts:
        out.append(Finding("error", "E020", f"{aid}: auditor(s) would audit controls they own: {', '.join(conflicts[:10])}"
                           + (" …" if len(conflicts) > 10 else "") + ". Exclude them from scope or change auditors.", prog, aid))
    if dt.date.fromisoformat(str(a["planned"]["end"])) < dt.date.fromisoformat(str(a["planned"]["start"])):
        out.append(Finding("error", "E014", f"{aid}: planned end is before start.", prog, aid))
    wps = model.workpapers.get(aid, {})
    status = a.get("status")
    if status in ("fieldwork", "reporting", "closed") and not wps:
        out.append(Finding("error", "E021", f"{aid} is '{status}' but has no workpapers (run `grc audit plan {aid}`).", prog, aid))
    open_wps = [w for w, wp in wps.items() if wp.get("conclusion", "not_started") == "not_started"]
    if status in ("reporting", "closed") and open_wps:
        out.append(Finding("error", "E021", f"{aid} is '{status}' but {len(open_wps)} workpaper(s) are not concluded: "
                           + ", ".join(open_wps[:8]), prog, aid))
    if status == "closed":
        unreviewed = [w for w, wp in wps.items() if wp.get("conclusion") not in (None, "not_started")
                      and not model.independent(wp.get("reviewed_by"), wp.get("performed_by"))]
        if unreviewed:
            out.append(Finding("error", "E021", f"{aid} is closed but workpapers lack independent review: {', '.join(unreviewed[:8])}", prog, aid))
        rep = a.get("report") or {}
        if not (rep.get("issued") and rep.get("approved_by")):
            out.append(Finding("error", "E021", f"{aid} is closed without report.issued and report.approved_by.", prog, aid))
    if status in ("planned", "fieldwork") and dt.date.fromisoformat(str(a["planned"]["end"])) < model.today:
        out.append(Finding("warning", "W122", f"{aid} planned to finish {a['planned']['end']} but is still '{status}'.", prog, aid))
    covered = {wp.get("requirement") for wp in wps.values()}
    if wps:
        for rid in scope:
            if rid not in covered:
                out.append(Finding("warning", "W123", f"{aid}: {rid} is in scope but has no workpaper (re-run `grc audit plan`).", prog, aid))

    fidx = model.finding_index
    for wid, wp in wps.items():
        path = _rel(model, model.workpaper_files[f"{aid}/{wid}"])
        ref = f"{aid}/{wid}"
        if str(wp.get("id")) != wid:
            out.append(Finding("error", "E025", f"{ref}: file is {wid}.yaml but its id is '{wp.get('id')}'.", path, ref))
        if wp.get("audit") != aid:
            out.append(Finding("error", "E025", f"{ref}: audit field is '{wp.get('audit')}'.", path, ref))
        if wp.get("requirement") not in model.requirement_index:
            out.append(Finding("error", "E025", f"{ref}: unknown requirement {wp.get('requirement')}.", path, ref))
        concl = wp.get("conclusion", "not_started")
        sample = [s for s in wp.get("sample") or [] if isinstance(s, dict)]
        pending = [str(s.get("item")) for s in sample if s.get("result", "not_tested") == "not_tested"]
        exceptions = [str(s.get("item")) for s in sample if s.get("result") == "exception"]
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
        if wp.get("reviewed_by") and wp.get("performed_by") and not model.independent(wp["reviewed_by"], wp["performed_by"]):
            out.append(Finding("error", "E022", f"{ref} is reviewed by the person who performed it ({wp['reviewed_by']}).", path, ref))
        if wp.get("reviewed_by") and concl == "not_started":
            out.append(Finding("error", "E022", f"{ref} is marked reviewed but not concluded.", path, ref))
        owner = _owner_of(model, wp.get("requirement"))
        for role in ("performed_by", "reviewed_by"):
            if wp.get(role) and owner and not model.independent(wp[role], owner):
                out.append(Finding("error", "E020", f"{ref}: {role} '{wp[role]}' owns {wp.get('requirement')} - "
                                   "nobody may audit or review their own control.", path, ref))


def _check_one_finding(model: Engagement, f: dict, fpath: str, out: list[Finding]) -> None:
    fid, st = f["id"], f.get("status")
    if f.get("requirement") not in model.requirement_index:
        out.append(Finding("error", "E025", f"{fid}: unknown requirement {f.get('requirement')}.", fpath, fid))
    if f.get("audit") and f["audit"] not in model.audit_index:
        out.append(Finding("error", "E025", f"{fid}: unknown audit {f['audit']}.", fpath, fid))
    if f.get("workpaper") and f.get("audit") and f["workpaper"] not in model.workpapers.get(f["audit"], {}):
        out.append(Finding("error", "E025", f"{fid}: unknown workpaper {f['audit']}/{f['workpaper']}.", fpath, fid))
    if fid.startswith("OFI") != (f.get("grade") == "ofi"):
        out.append(Finding("error", "E024", f"{fid}: OFI-… ids are for grade 'ofi'; NC-… ids for major/minor.", fpath, fid))
    ev_idx = model.evidence_index
    for e in (f.get("evidence") or []) + ((f.get("effectiveness") or {}).get("evidence") or []):
        if e not in ev_idx:
            out.append(Finding("error", "E006", f"{fid} cites unknown evidence {e}.", fpath, fid))
        elif ev_idx[e].get("source") == "audit" and model.evidence_is_failing(ev_idx[e]):
            out.append(Finding("error", "E024", f"{fid} cites workpaper {e}, which is not concluded effective and "
                               "independently reviewed.", fpath, fid))
        elif ev_idx[e].get("source") == "review" and model.evidence_is_failing(ev_idx[e]):
            out.append(Finding("error", "E024", f"{fid} cites management review {e}, which is not held with complete, "
                               "approved minutes.", fpath, fid))
        elif ev_idx[e].get("source") == "document" and model.evidence_is_failing(ev_idx[e]):
            out.append(Finding("error", "E024", f"{fid} cites document {e}, which is not soundly approved.", fpath, fid))
        elif ev_idx[e].get("source") == "impact" and model.evidence_is_failing(ev_idx[e]):
            out.append(Finding("error", "E024", f"{fid} cites impact assessment {e}, which is not approved "
                               "(independently, with an approve decision).", fpath, fid))
    if f.get("grade") == "ofi":
        return
    if st in ("action_planned", "implemented", "closed"):
        need = [k for k in ("owner", "due", "root_cause", "corrective_action") if not str(f.get(k) or "").strip()]
        if need:
            out.append(Finding("error", "E024", f"{fid} is '{st}' without {', '.join(need)}.", fpath, fid))
    if st in ("implemented", "closed") and not f.get("evidence"):
        out.append(Finding("error", "E024", f"{fid} is '{st}' without implementation evidence.", fpath, fid))
    if st == "closed":
        eff = f.get("effectiveness") or {}
        if not (eff.get("effective") is True and eff.get("reviewed_by") and eff.get("reviewed_on") and eff.get("evidence")):
            out.append(Finding("error", "E024", f"{fid} is closed without an effectiveness review "
                               "(effective: true, reviewed_by, reviewed_on, evidence).", fpath, fid))
        elif not model.independent(eff.get("reviewed_by"), f.get("owner")):
            out.append(Finding("error", "E024", f"{fid}: effectiveness was reviewed by the action owner "
                               f"('{eff.get('reviewed_by')}' is '{f.get('owner')}').", fpath, fid))
    if st == "accepted" and f.get("grade") == "major":
        out.append(Finding("error", "E024", f"{fid}: a major nonconformity cannot be risk-accepted; it must be corrected.", fpath, fid))
    if st not in ("closed", "accepted") and f.get("due") and dt.date.fromisoformat(str(f["due"])) < model.today:
        out.append(Finding("warning", "W120", f"{fid} ({f['grade']}) is past due ({f['due']}).", fpath, fid))
    if st == "open" and not f.get("owner"):
        out.append(Finding("warning", "W103", f"{fid} is open with no owner.", fpath, fid))
    if f.get("grade") == "major" and st != "closed":
        c = model.controls.get(f.get("requirement"), {})
        if (c.get("test", {}).get("tested", {}) or {}).get("status") == "verified":
            out.append(Finding("error", "E026", f"{f['requirement']}.tested is 'verified' but {fid} (major) is still {st}.",
                               _rel(model, model.control_files.get(f["requirement"])), f["requirement"]))


def check_impact(model: Engagement) -> list[Finding]:
    """AI system impact assessments (6.1.4, 8.4, A.5.2-A.5.5)."""
    from .impact import band, method, next_review, required_systems, safe_date, score
    out: list[Finding] = []
    m = method(model)
    cats = {c["id"]: c for c in m["categories"]}
    inv = {i["id"]: i for i in model.inventory}
    kinds = set(m["required_for_kinds"])
    active: dict[str, list[str]] = {}
    for iid, ia in model.impacts.items():
        path = _rel(model, model.impact_files[iid])
        try:
            if not isinstance(ia, dict):
                continue
            if str(ia.get("id")) != iid:
                out.append(Finding("error", "E030", f"{iid}: file is {iid}.yaml but its id is '{ia.get('id')}'.", path, iid))
            sys_id = ia.get("system")
            if sys_id not in inv:
                out.append(Finding("error", "E030", f"{iid}: system {sys_id} is not in inventory.yaml.", path, iid))
            elif inv[sys_id].get("kind") not in kinds:
                out.append(Finding("error", "E030", f"{iid}: {sys_id} is a '{inv[sys_id].get('kind')}', not an AI system.", path, iid))
            if ia.get("status") != "superseded":
                active.setdefault(sys_id, []).append(iid)
            impacts = [x for x in ia.get("impacts") or [] if isinstance(x, dict)]
            ids = [x.get("id") for x in impacts]
            for dup in sorted({i for i in ids if ids.count(i) > 1}):
                out.append(Finding("error", "E030", f"{iid}: impact id {dup} is used more than once.", path, iid))
            screening = [x for x in ia.get("screening") or [] if isinstance(x, dict)]
            scats = [x.get("category") for x in screening]
            for dup in sorted({str(c) for c in scats if scats.count(c) > 1}):
                out.append(Finding("error", "E030", f"{iid}: category '{dup}' is screened more than once.", path, iid))
            for c in sorted({str(c) for c in scats if c not in cats}):
                out.append(Finding("error", "E030", f"{iid}: screening lists unknown category '{c}'.", path, iid))
            screened: dict = {}
            for x in screening:  # a category is relevant if any entry says so
                if x.get("category") not in screened or x.get("relevant") is True:
                    screened[x.get("category")] = x
            for x in impacts:
                ref = f"{iid}/{x.get('id')}"
                if x.get("category") not in cats:
                    out.append(Finding("error", "E030", f"{ref}: unknown category '{x.get('category')}'.", path, iid))
                for r in x.get("controls") or []:
                    if r not in model.requirement_index:
                        out.append(Finding("error", "E030", f"{ref}: unknown requirement {r}.", path, iid))
                for g in x.get("gaps") or []:
                    if g not in model.gap_index:
                        out.append(Finding("error", "E030", f"{ref}: unknown gap {g}.", path, iid))
                inh = score(x.get("likelihood"), x.get("severity"))
                res = score(x.get("residual_likelihood"), x.get("residual_severity"))
                if res is not None and inh is not None and res > inh:
                    out.append(Finding("warning", "W133", f"{ref}: residual ({res}) is higher than inherent ({inh}).", path, iid))
            st = ia.get("status")
            if st in ("draft", "in_review"):
                out.append(Finding("warning", "W131", f"{iid} ({ia.get('title', sys_id)}) is {st}, not yet approved.", path, iid))
            if st != "approved":
                continue
            # ---- approval completeness (E031) and scoring (E032)
            ctx = ia.get("context") or {}
            missing = [k for k in ("intended_use",) if not (ctx.get(k) or "").strip()] + \
                      (["affected_parties"] if not ctx.get("affected_parties") else [])
            missing += [k for k in ("assessor", "assessed_on", "approver", "approved_on", "decision", "conclusion")
                        if not str(ia.get(k) or "").strip()]
            if missing:
                out.append(Finding("error", "E031", f"{iid} is approved without {', '.join(missing)}.", path, iid))
            if ia.get("approver") and ia.get("assessor") and not model.independent(ia["approver"], ia["assessor"]):
                out.append(Finding("error", "E031", f"{iid} is approved by its own assessor ({ia['approver']}).", path, iid))
            unscreened = [c for c in cats if screened.get(c, {}).get("relevant") is None]
            if unscreened:
                out.append(Finding("error", "E031", f"{iid} is approved with unscreened categories: {', '.join(unscreened)}.", path, iid))
            no_reason = [c for c, s in screened.items() if c in cats and s.get("relevant") is not None and not (s.get("rationale") or "").strip()]
            if no_reason:
                out.append(Finding("error", "E031", f"{iid}: screening without a rationale: {', '.join(no_reason)}.", path, iid))
            covered = {x.get("category") for x in impacts}
            uncovered = [c for c, s in screened.items() if s.get("relevant") is True and c not in covered]
            if uncovered:
                out.append(Finding("error", "E031", f"{iid}: relevant categories with no assessed impact: {', '.join(uncovered)}.", path, iid))
            dates = {k: safe_date(ia.get(k)) for k in ("assessed_on", "approved_on")}
            future = [k for k, d in dates.items() if d and d > model.today]
            if future:
                out.append(Finding("error", "E031", f"{iid}: {', '.join(future)} is in the future.", path, iid))
            if dates["assessed_on"] and dates["approved_on"] and dates["approved_on"] < dates["assessed_on"]:
                out.append(Finding("error", "E031", f"{iid} is approved ({dates['approved_on']}) before it was assessed "
                                   f"({dates['assessed_on']}).", path, iid))
            if ia.get("decision") == "approve_with_conditions" and not [c for c in ia.get("conditions") or [] if str(c or "").strip()]:
                out.append(Finding("error", "E031", f"{iid}: 'approve_with_conditions' lists no conditions.", path, iid))
            for x in impacts:
                ref = f"{iid}/{x.get('id')}"
                res = score(x.get("residual_likelihood"), x.get("residual_severity"))
                if res is None:
                    out.append(Finding("error", "E032", f"{ref}: approved without a residual rating (residual_likelihood/severity).", path, iid))
                    continue
                if res >= m["unacceptable_at"] and ia.get("decision") != "reject":
                    out.append(Finding("error", "E032", f"{ref}: residual {res} ({band(model, res)}) is unacceptable "
                                       f"(>= {m['unacceptable_at']}); reduce it or decide 'reject'.", path, iid))
                elif res >= m["acceptance_required_at"]:
                    acc = x.get("acceptance") or {}
                    if not (acc.get("accepted_by") and acc.get("accepted_on") and (acc.get("rationale") or "").strip()):
                        out.append(Finding("error", "E032", f"{ref}: residual {res} ({band(model, res)}) needs acceptance "
                                           "(accepted_by, accepted_on, rationale).", path, iid))
                    elif not model.independent(acc.get("accepted_by"), ia.get("assessor")):
                        out.append(Finding("error", "E032", f"{ref}: residual risk accepted by the assessor.", path, iid))
                    elif (safe_date(acc.get("accepted_on")) or dt.date.min) > model.today:
                        out.append(Finding("error", "E032", f"{ref}: acceptance is dated in the future.", path, iid))
            nr = next_review(model, ia)
            if nr and nr < model.today:
                out.append(Finding("warning", "W132", f"{iid} was due for review on {nr}; reassess it (changes to the "
                                   "system, its data or its use also trigger a reassessment).", path, iid))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            out.append(Finding("error", "E000", f"{iid}: could not evaluate ({exc!r}).", path, iid))
    for sys_id, iids in active.items():
        if sys_id and len(iids) > 1:
            out.append(Finding("error", "E030", f"{sys_id} has more than one active assessment ({', '.join(iids)}); "
                               "mark older ones 'superseded'.", _rel(model, model.impact_files[iids[0]]), sys_id))
    inv_path = _rel(model, model.engagement_dir / "inventory.yaml")
    for s in required_systems(model):
        if s["id"] not in active:
            out.append(Finding("warning", "W130", f"{s['id']} ({s.get('name')}) has no impact assessment "
                               f"(`grc impact new {s['id']}`).", inv_path, s["id"]))
    return out


def check_documents(model: Engagement) -> list[Finding]:
    """Policies and procedures (5.2, 7.5; the Documented leg)."""
    from .documents import DOC_ID, approval_problems, docs, fingerprint, library, next_review, is_effective
    out: list[Finding] = []
    lib = library(model)
    for did, d in docs(model).items():
        meta, body = d["meta"], d["body"]
        path = _rel(model, model.document_files[did])
        try:
            if str(meta.get("id")) != did:
                out.append(Finding("error", "E040", f"{did}: file is {did}.md but its id is '{meta.get('id')}'.", path, did))
            if not DOC_ID.match(did):
                out.append(Finding("error", "E040", f"{did}: document file names must look like DOC-NAME.md.", path, did))
            for r in meta.get("satisfies") or []:
                if r not in model.requirement_index:
                    out.append(Finding("error", "E040", f"{did}: satisfies unknown requirement {r}.", path, did))
            st = meta.get("status")
            if st in ("draft", "in_review"):
                out.append(Finding("warning", "W141", f"{did} ({meta.get('title')}) is {st}, not yet approved.", path, did))
                continue
            if st != "approved":
                continue
            problems = approval_problems(model, did, meta, body, check_hash=False)
            if problems:
                out.append(Finding("error", "E041", f"{did} is approved but: {'; '.join(problems)}.", path, did))
            h = meta.get("approved_hash")
            if not h:
                out.append(Finding("error", "E042", f"{did} is marked approved without an approval fingerprint; "
                                   f"record approval with `grc docs approve {did} --approver ...`.", path, did))
            elif h != fingerprint(meta, body):
                out.append(Finding("error", "E042", f"{did} v{meta.get('version')}: the text or approval details (title, version, "
                                   "approver, date, requirements) changed after approval; bump `version`, set status back to "
                                   "draft, and re-approve.", path, did))
            nr = next_review(model, meta)
            if nr and nr < model.today:
                out.append(Finding("warning", "W142", f"{did} was due for review on {nr}.", path, did))
            if is_effective(model, did):
                uncited = [r for r in meta.get("satisfies") or [] if r in model.requirement_index and model.is_applicable(r)
                           and did not in ((model.controls.get(r, {}).get("test") or {}).get("documented") or {}).get("evidence", [])]
                if uncited:
                    out.append(Finding("warning", "W143", f"{did} is approved; cite it on the Documented leg of: "
                                       f"{', '.join(uncited)}.", path, did))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            out.append(Finding("error", "E000", f"{did}: could not evaluate ({exc!r}).", path, did))
    missing = [i for i in lib if i not in model.documents]
    if missing and lib:
        out.append(Finding("warning", "W140", f"{len(missing)} of {len(lib)} library documents not started: "
                           f"{', '.join(missing)} (`grc docs new all`).", _rel(model, model.engagement_dir / "documents"), None))
    return out


def check_reviews(model: Engagement) -> list[Finding]:
    """Management review (9.3)."""
    from .review import _dicts, last_held, method, problems, reviews, safe_date
    out: list[Finding] = []
    cfg = method(model)
    ev_idx = model.evidence_index
    for rid, r in reviews(model).items():
        if r.get("_error"):
            continue
        path = _rel(model, model.review_files[rid])
        try:
            if str(r.get("id")) != rid:
                out.append(Finding("error", "E050", f"{rid}: file is {rid}.yaml but its id is '{r.get('id')}'.", path, rid))
            for kind in ("decisions", "actions"):
                ids = [str(x.get("id")) for x in _dicts(r.get(kind))]
                for dup in sorted({i for i in ids if ids.count(i) > 1}):
                    out.append(Finding("error", "E050", f"{rid}: {kind[:-1]} id {dup} is used more than once.", path, rid))
            known_inputs = {i["id"] for i in cfg["inputs"]}
            for i in _dicts(r.get("inputs")):
                if str(i.get("id")) not in known_inputs:
                    out.append(Finding("error", "E050", f"{rid}: unknown input '{i.get('id')}'.", path, rid))
            st = r.get("status")
            if st in ("held", "closed"):
                p = problems(model, rid, r)
                if p:
                    out.append(Finding("error", "E051", f"{rid} is '{st}' but: {'; '.join(p)}.", path, rid))
            elif st == "planned":
                planned = safe_date(r.get("planned_on"))
                if planned and planned < model.today:
                    out.append(Finding("warning", "W150", f"{rid} was planned for {planned} but is not recorded as held.", path, rid))
            for a in _dicts(r.get("actions")):
                ref = f"{rid}/{a.get('id')}"
                need = [k for k in ("action", "owner", "due") if not str(a.get(k) or "").strip()]
                if need and a.get("status") != "cancelled":
                    out.append(Finding("error", "E052", f"{ref}: action without {', '.join(need)}.", path, rid))
                for e in a.get("evidence") or []:
                    if e not in ev_idx:
                        out.append(Finding("error", "E006", f"{ref} cites unknown evidence {e}.", path, rid))
                if a.get("status") == "done":
                    if not safe_date(a.get("closed_on")) or not a.get("evidence"):
                        out.append(Finding("error", "E052", f"{ref} is done without closed_on and evidence.", path, rid))
                    elif safe_date(a.get("closed_on")) > model.today:
                        out.append(Finding("error", "E052", f"{ref}: closed_on is in the future.", path, rid))
                due = safe_date(a.get("due"))
                if a.get("status") == "open" and due and due < model.today:
                    out.append(Finding("warning", "W152", f"{ref} is overdue (due {due}): {str(a.get('action'))[:80]}", path, rid))
            if st == "closed" and any(a.get("status") == "open" for a in _dicts(r.get("actions"))):
                out.append(Finding("error", "E052", f"{rid} is closed with open actions; finish or cancel them first.", path, rid))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            out.append(Finding("error", "E000", f"{rid}: could not evaluate ({exc!r}).", path, rid))
    # cadence: a review held within the cycle, and one before the Stage 1 audit
    try:
        last = last_held(model)
    except Exception:
        last = None
    rpath = _rel(model, model.engagement_dir / "reviews")
    if last and (model.today - last[1]).days > int(cfg["review_every_days"]):
        out.append(Finding("warning", "W151", f"The last management review ({last[0]}) was held on {last[1]}, more than "
                           f"{cfg['review_every_days']} days ago.", rpath, last[0]))
    stage1 = safe_date((model.engagement.get("dates") or {}).get("stage1"))
    if not last and stage1 and 0 <= (stage1 - model.today).days <= int(cfg["warn_before_stage1_days"]):
        out.append(Finding("warning", "W151", f"No management review has been held and the Stage 1 audit is on {stage1}.", rpath, None))
    c93 = model.controls.get("9.3", {}).get("test", {})
    if any((c93.get(k) or {}).get("status") == "verified" for k in ("evidenced", "tested")) and not last:
        out.append(Finding("warning", "W153", "9.3 is marked verified but no management review is recorded as held.",
                           _rel(model, model.control_files.get("9.3")), "9.3"))
    return out


def check_hours(model: Engagement) -> list[Finding]:
    """Timesheet (engagement/hours.yaml): sane entries, phase plans, forecast."""
    from . import hours as H
    out: list[Finding] = []
    if not H.tracked(model):
        return out
    path = _rel(model, model.engagement_dir / "hours.yaml")
    cfg = H.method(model)
    acts = {a["id"] for a in cfg["activities"]}
    phase_ids = {str(p["id"]) for p in H.phases(model)}
    refs_ok = H.known_refs(model)
    ids = [e.get("id") for e in H.entries(model)]
    for dup in sorted({str(i) for i in ids if ids.count(i) > 1}):
        out.append(Finding("error", "E060", f"Timesheet entry id {dup} appears more than once.", path, dup))
    per_day: dict = {}
    for e in H.entries(model):
        eid = str(e.get("id"))
        try:
            float(e.get("hours"))
        except (TypeError, ValueError):
            out.append(Finding("error", "E060", f"{eid}: hours '{e.get('hours')}' is not a number.", path, eid))
        d = H.safe_date(e.get("date"))
        if d and d > model.today:
            out.append(Finding("error", "E060", f"{eid}: dated {d}, in the future.", path, eid))
        if e.get("activity") not in acts:
            out.append(Finding("error", "E060", f"{eid}: unknown activity '{e.get('activity')}'.", path, eid))
        if e.get("phase") and str(e["phase"]) not in phase_ids:
            out.append(Finding("error", "E060", f"{eid}: unknown phase '{e.get('phase')}'.", path, eid))
        bad = [r for r in e.get("refs") or [] if str(r) not in refs_ok]
        if bad:
            out.append(Finding("error", "E060", f"{eid}: unknown reference(s) {', '.join(map(str, bad))}.", path, eid))
        key = (str(e.get("person", "")).strip().lower(), d)
        per_day[key] = per_day.get(key, 0.0) + H._num(e.get("hours"))
    cap = float(cfg.get("max_per_person_day") or 14)
    for (who, d), h in sorted(per_day.items(), key=lambda x: (str(x[0][1]), x[0][0])):
        if h > cap:
            out.append(Finding("error", "E060", f"{who} has {h:g} hours on {d} (more than {cap:g}); is an import duplicated?", path, None))
    plan, used = H.planned(model), H.by(model, lambda e: H.phase_for(model, e))
    for ph, p_hours in plan.items():
        if p_hours and used.get(ph, 0) > p_hours:
            out.append(Finding("warning", "W160", f"Phase '{ph}': {used[ph]:g} hours used of {p_hours:g} planned "
                               f"({used[ph] / p_hours:.0%}).", path, ph))
    f = H.forecast(model)
    if f["budget"] and f["rate_per_week"] and f["projected_total"] > f["budget"]:
        out.append(Finding("warning", "W161", f"At the last {f['weeks']} weeks' rate ({f['rate_per_week']:g} h/week), the "
                           f"engagement will use about {f['projected_total']:g} of {f['budget']:g} hours by {f['end']}.", path, None))
    manual = (model.engagement.get("budget") or {}).get("hours_used")
    if manual not in (None, 0, 0.0) and abs(H._num(manual) - H.total(model)) > 0.01:
        out.append(Finding("warning", "W163", f"budget.hours_used in engagement.yaml ({H._num(manual):g}) differs from the "
                           f"timesheet ({H.total(model):g}); the timesheet is used - remove hours_used.",
                           _rel(model, model.engagement_dir / "engagement.yaml"), None))
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


def check_submissions(model: Engagement) -> list[Finding]:
    """Answers from the client site: identity, triage and what was filed from them."""
    out: list[Finding] = []
    if not model.submissions:
        return out
    from .portal import item_key
    from . import client_view
    fw = model.engagement.get("framework", "")
    open_keys = {item_key(fw, i) for i in client_view.items(model)}
    ev_ids = set(model.evidence_index)
    days = int((model.engagement.get("portal") or {}).get("triage_days") or 5)
    for sid, s in model.submissions.items():
        if not isinstance(s, dict) or s.get("_error"):
            continue
        f = _rel(model, model.submission_files[sid])
        if s.get("id") != sid:
            out.append(Finding("error", "E070", f"{sid}: id is {s.get('id')!r} but the file is {sid}.yaml - they must match.", f, sid))
        req = s.get("request") if isinstance(s.get("request"), dict) else {}
        at = str(s.get("submitted_at") or "")[:10]
        when = _safe_date(at)
        if s.get("status") == "received" and when and (model.today - when).days > days:
            out.append(Finding("warning", "W171", f"{sid}: a client answer to {req.get('kind')} {req.get('ref')} has waited "
                               f"{(model.today - when).days} days for review - set status to accepted, needs_more (with a note "
                               "the client will see) or withdrawn.", f, sid))
        # answers to another framework's tab are stored here too; only check this framework's
        same_fw = str(req.get("framework") or fw) == fw
        if same_fw and s.get("status") in ("received", "needs_more") and req.get("key") and req.get("key") not in open_keys:
            out.append(Finding("info", "W170", f"{sid}: answers {req.get('kind')} {req.get('ref')}, which is no longer an open "
                               "request (closed, or its wording changed).", f, sid))
        for ev in s.get("evidence") or []:
            if ev not in ev_ids:
                out.append(Finding("warning", "W172", f"{sid}: lists evidence {ev}, which is not in the evidence index.", f, sid))
    return out


def _safe_date(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


ALL_RULES = (check_schemas, check_structure, check_applicability, check_evidence_test, check_gaps, check_engagement, check_collected, check_owners, check_audit, check_impact, check_documents, check_reviews, check_hours, check_submissions)


def validate(model: Engagement) -> list[Finding]:
    findings: list[Finding] = []
    schema_findings = check_schemas(model)
    findings.extend(schema_findings)
    for rule in ALL_RULES[1:]:
        try:
            findings.extend(rule(model))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:  # malformed data already reported by schema check
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


def _review_metrics(model: Engagement) -> dict:
    from .review import actions, last_held, safe_date
    last = last_held(model)
    acts = actions(model)
    return {"mr_last_held": str(last[1]) if last else None, "mr_actions_open": sum(1 for a in acts if a.get("status") == "open"),
            "mr_actions_overdue": sum(1 for a in acts if a.get("status") == "open" and safe_date(a.get("due"))
                                      and safe_date(a.get("due")) < model.today)}


def _doc_metrics(model: Engagement) -> dict:
    from .documents import is_effective, library
    lib = library(model)
    return {"docs_required": len(lib), "docs_approved": sum(1 for d in lib if is_effective(model, d))}


def _ia_metrics(model: Engagement) -> dict:
    from .impact import active_by_system, is_effective, required_systems
    req = required_systems(model)
    active = active_by_system(model)
    return {"ia_required": len(req), "ia_current": sum(1 for s in req if s["id"] in active and is_effective(model, active[s["id"]]))}


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
    cited = {r for c in model.controls.values() for leg in (c.get("test") or {}).values()
             for r in (leg or {}).get("evidence", []) or []}
    from . import documents, impact, review
    counted = list(model.evidence) + [e for e in list(model.workpaper_evidence.values()) + list(impact.evidence_entries(model).values())
                                      + list(documents.evidence_entries(model).values())
                                      + list(review.evidence_entries(model).values()) if e["id"] in cited]
    stale = [e["id"] for e in counted if model.evidence_is_expired(e)]
    failing = [e["id"] for e in counted if model.evidence_is_failing(e)]
    from . import hours as H
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
        **_ia_metrics(model),
        **_doc_metrics(model),
        **_review_metrics(model),
        "nc_open_major": sum(1 for f in model.findings if f.get("grade") == "major" and f.get("status") not in ("closed", "accepted")),
        "nc_open_minor": sum(1 for f in model.findings if f.get("grade") == "minor" and f.get("status") not in ("closed", "accepted")),
        "audits": {a["id"]: a.get("status") for a in model.audits},
        "hours_total": b.get("hours_total"),
        "hours_used": H.hours_used(model),
        "hours_forecast": H.forecast(model)["projected_total"] if H.tracked(model) else None,
    }
