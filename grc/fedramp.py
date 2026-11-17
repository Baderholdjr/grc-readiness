"""FedRAMP 20x outputs, in FedRAMP's own JSON formats (the FedRAMP Consolidated Rules 2026 schemas).

From a FedRAMP 20x engagement record and the files in `engagement/fedramp/`, `grc fedramp export` writes:

    certification-package-overview.json        FRC-CSO-PKG / CDS-CSO-PUB: the offering, its contacts and repositories
    security-decision-record.json              SDR-CSO-FRR: each Key Security Indicator and rule in scope, with its
                                               implementation, validation and evidence, from the record
    ongoing-certification-report-<period>.json CCM-OCR-AVL: the 3-month report
    vulnerability-detail-report-<period>.json  VER-RPT-VDT: vulnerabilities (not accepted) with activity in the period
    accepted-vulnerability-info-<period>.json  VER-RPT-AVI: accepted vulnerabilities with activity in the period
    historical-vulnerability-activity.json     VER-TFR-MRH: every vulnerability, as of today
    incidents/<id>.json                        IEC-CSO-IIR/OIR/FIR: one report per incident, at its current stage
    significant-changes/<id>.json              SCN-CSO-INF: one notification per significant change

Each JSON file is validated against FedRAMP's schema before it is written, and comes with a Markdown copy for
people (FedRAMP asks for human-readable and JSON formats). Statuses come only from what reviewers verified in the
record: nothing here marks anything implemented on its own. The record is a readiness assessment by the engagement
team, not an independent assessment, and the documents say so.
"""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path

from .model import ENGINE, LEGS, Engagement, jsonable, load_schema, read_yaml

SCHEMA_DIR = ENGINE / "fedramp20x" / "schemas"
SCHEMA_DATE = "2026-06-24"
FILES = ("package", "vulnerabilities", "incidents", "changes", "reports")
LIST_KEY = {"vulnerabilities": "vulnerabilities", "incidents": "incidents", "changes": "changes", "reports": "reports"}
DOCS = {  # output kind -> FedRAMP schema name
    "overview": "certification-package-overview",
    "sdr": "security-decision-record",
    "ocr": "ongoing-certification-report",
    "vdr": "vulnerability-detail-report",
    "avi": "accepted-vulnerability-info",
    "history": "historical-ver-activity",
    "incident": "incident-report",
    "scn": "significant-change-notifications",
}
LEG_LABEL = {"documented": "Documented", "implemented": "Implemented", "evidenced": "Evidence exists", "tested": "Tested"}
STATUS_WORD = {"verified": "verified by a reviewer", "partial": "partly in place", "claimed": "claimed by the provider, not yet verified"}
EVIDENCE_TYPE = {"document": "Policy", "record": "Audit Record", "config": "Configuration", "log": "Log", "test": "Report",
                 "sample": "Report", "interview": "Report", "screenshot": "Screenshot"}
FINISHED = ("Fully Mitigated", "Remediated", "False Positive")   # "Partially Mitigated" is still open
MAV_DAYS = 192   # VER-TFR-MAV: not fully mitigated or remediated within 192 days of evaluation -> accepted vulnerability
READINESS = "Readiness review by the engagement team (not an independent assessment)"


class FedrampError(ValueError):
    pass


# ------------------------------------------------------------------ the record's 20x files
def folder(model: Engagement) -> Path:
    return model.engagement_dir / "fedramp"


def applies(model: Engagement) -> bool:
    return model.catalog["framework"]["id"] == "fedramp20x" or folder(model).is_dir()


def load(model: Engagement) -> dict:
    """{name: data or None} for the files in engagement/fedramp/; a file that can't be read is {"_error": ...}."""
    out = {}
    for name in FILES:
        p = folder(model) / f"{name}.yaml"
        if not p.exists():
            out[name] = None
            continue
        try:
            data = read_yaml(p)
        except Exception as exc:   # reported by check(), never a crash
            out[name] = {"_error": f"not valid YAML ({str(exc).splitlines()[0][:160]})"}
            continue
        out[name] = data if isinstance(data, dict) else {"_error": "not a YAML mapping"}
    return out


def _items(data: dict | None, name: str) -> list[dict]:
    if not isinstance(data, dict) or data.get("_error"):
        return []
    rows = data.get(LIST_KEY[name]) or []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


# ------------------------------------------------------------------ dates and times
def _dt(v) -> dt.datetime | None:
    """An aware datetime (UTC when no zone is given; a date is its midnight UTC)."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day, tzinfo=dt.timezone.utc)
    s = str(v).strip().replace(" ", "T", 1)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _iso(v) -> str | None:
    d = _dt(v)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def _date(v) -> dt.date | None:
    """The UTC date (report periods are stated in UTC)."""
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        return v
    d = _dt(v)
    return d.astimezone(dt.timezone.utc).date() if d else None


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    import calendar
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _in(v, start: dt.date, end: dt.date) -> bool:
    d = _date(v)
    return bool(d and start <= d <= end)


def _clean(obj):
    """Drop keys whose value is None, recursively (FedRAMP's schemas have no nulls)."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _text(s) -> str:
    return " ".join(str(s or "").split())


# ------------------------------------------------------------------ FedRAMP's schemas
@lru_cache(maxsize=1)
def _registry():
    from referencing import Registry, Resource
    resources = []
    for p in sorted(SCHEMA_DIR.glob("fedramp-*-schema-*.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        resources.append((s["$id"], Resource.from_contents(s)))
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def schema(kind: str) -> dict:
    return json.loads((SCHEMA_DIR / f"fedramp-{DOCS[kind]}-schema-{SCHEMA_DATE}.json").read_text(encoding="utf-8"))


def validate(doc: dict, kind: str | None = None) -> list[str]:
    """Schema problems in a FedRAMP 20x document, as 'path: message' lines (empty when valid). Without `kind`, the
    schema is found from the document's own fields."""
    from jsonschema import Draft202012Validator, FormatChecker
    kind = kind or guess_kind(doc)
    if not kind:
        return ["(root): not a FedRAMP 20x document this engine knows (no matching schema)"]
    v = Draft202012Validator(schema(kind), registry=_registry(), format_checker=FormatChecker())
    out = []
    for e in sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{where}: {e.message[:300]}")
    return out


def guess_kind(doc) -> str | None:
    if not isinstance(doc, dict):
        return None
    keys = set(doc)
    for kind, marker in (("overview", "serviceIdentification"), ("sdr", "fedRampRequirements"),
                         ("ocr", "activeAgencies"), ("history", "generatedAt"), ("avi", "acceptedVulnerabilities"),
                         ("vdr", "vulnerabilities"), ("incident", "providerTrackingId"), ("scn", "changeType")):
        if marker in keys:
            return kind
    return None


# ------------------------------------------------------------------ the requirements (SDR)
def _flagged(model: Engagement) -> set[str]:
    """Requirements whose record has a validation error: never shown as implemented."""
    from .rules import validate as run_rules
    return {str(f.ref) for f in run_rules(model) if f.severity == "error" and f.ref}


def _status(model: Engagement, rid: str, flagged: set[str]) -> str | None:
    from .rules import requirement_state
    state = requirement_state(model, rid)
    if state == "Excluded":
        return None
    if state == "Ready" and rid not in flagged:
        return "Implemented"
    if state == "In progress" or state == "Ready":
        return "Partially Implemented"
    return "Not Implemented"


def _cited(model: Engagement, c: dict, states=("verified", "partial")) -> list[tuple[str, dict]]:
    """Evidence cited by the checks a reviewer has verified (or found partly in place): never by a bare claim."""
    from .rules import leg_effective
    seen, out = set(), []
    tests = c.get("test") if isinstance(c.get("test"), dict) else {}
    for leg in LEGS:
        data = tests.get(leg) if isinstance(tests.get(leg), dict) else {}
        if leg_effective(model, data) not in states:
            continue
        for eid in data.get("evidence") or []:
            eid = str(eid).split(":")[-1]
            ev = model.evidence_index.get(eid)
            if ev and eid not in seen:
                seen.add(eid)
                out.append((eid, ev))
    return out


def _evidence_entry(ev: dict) -> dict:
    loc = str(ev.get("location") or "")
    shareable = loc.startswith(("https://", "http://")) and ev.get("sensitivity") not in ("confidential", "restricted")
    return _clean({"evidenceType": EVIDENCE_TYPE.get(ev.get("type"), "Report"),
                   "evidenceDescription": _text(ev.get("title")) or str(ev.get("id")),
                   "evidenceLocation": loc if shareable else None,
                   "lastUpdated": str(ev.get("collected")) if ev.get("collected") else None})


def _leg_line(model: Engagement, c: dict, leg: str) -> str | None:
    from .rules import leg_effective
    tests = c.get("test") if isinstance(c.get("test"), dict) else {}
    data = tests.get(leg) if isinstance(tests.get(leg), dict) else {}
    state = leg_effective(model, data)
    if state == "not_started":
        return None
    ids = [str(e).split(":")[-1] for e in data.get("evidence") or []]
    titles = [f"{i} {_text(model.evidence_index[i].get('title'))}" for i in ids if i in model.evidence_index]
    return f"{LEG_LABEL[leg]}: {STATUS_WORD.get(state, state)}." + (f" Evidence: {'; '.join(titles)}." if titles else "")


def _accepted_risk(model: Engagement, rid: str) -> list[str]:
    out = []
    for g in model.gaps:
        if isinstance(g, dict) and g.get("status") == "risk_accepted" and rid in [str(x) for x in g.get("requirements") or []]:
            out.append(f"Not fully met; the risk is accepted (gap {g.get('id')}): {_text(g.get('finding'))}")
    return out


def requirement_entry(model: Engagement, rid: str, flagged: set[str]) -> dict:
    req = model.requirement_index[rid]
    c = model.controls.get(rid) or {}
    status = _status(model, rid, flagged)
    if status is None:
        why = _text(c.get("justification")) or "No justification recorded."
        impl = [f"Not applicable to this offering. Reason and resulting risk to customers: {why}"]
    else:
        impl = [_text(c.get("implementation")) or "Not yet described."] + _accepted_risk(model, rid)
    # validation: what the readiness review found for each check that has started. Assessment (verification by an
    # independent assessor) is left empty: the engine never fills it.
    validation = [f"{READINESS}: {x}" for x in (_leg_line(model, c, leg) for leg in ("implemented", "evidenced", "tested")) if x]
    cited = _cited(model, c)
    tests = [f"{_text(ev.get('title'))} ({ev.get('collector') or ev.get('type')}"
             + (f", latest result {ev['result']}" if ev.get("result") else "") + ")"
             for _, ev in _cited(model, c, ("verified",)) if ev.get("type") in ("test", "sample") or ev.get("collector")]
    if req.get("kind") == "indicator":
        return _clean({"ksiId": rid, "ksiImplementationStatus": status, "ksiImplementation": impl,
                       "ksiValidation": validation, "ksiAssessment": [], "ksiTests": tests,
                       "ksiEvidence": [_evidence_entry(ev) for _, ev in cited]})
    return _clean({"frrID": rid, "frrImplementationStatus": status, "frrImplementation": impl,
                   "frrValidation": validation or None})


# ------------------------------------------------------------------ the documents
def overview_url(pkg: dict) -> str | None:
    return (pkg or {}).get("overview_url")


def build_overview(model: Engagement, pkg: dict, reports: list[dict]) -> dict:
    svc = pkg.get("service") or {}

    def repo(r: dict, default_type: str) -> dict:
        return _clean({"repositoryType": list(r.get("types") or [default_type]), "url": r.get("url"),
                       "repositoryDescription": r.get("description"),
                       "authenticationRequired": bool(r.get("authentication_required")),
                       "accessRequestInstructions": r.get("access_instructions")})

    nxt = None
    ends = [_date(r.get("to")) for r in reports if _date(r.get("to"))]
    if ends and add_months(max(ends), 3) >= model.today:
        nxt = add_months(max(ends), 3).isoformat()
    tp = pkg.get("third_party") or {}
    doc = {
        "serviceIdentification": {
            "fedRampPackageId": str(pkg.get("fedramp_id") or f"{pkg.get('provider')} {svc.get('acronym')}".strip()),
            "ueiNumber": pkg.get("uei"),
            "providerName": pkg.get("provider"), "serviceName": svc.get("name"), "serviceAcronym": svc.get("acronym"),
            "serviceDescription": svc.get("description"), "certificationType": "20x",
            "website": svc.get("website"), "logo": svc.get("logo")},
        "serviceProperties": {
            "serviceType": list(svc.get("types") or []), "deploymentModel": svc.get("deployment_model"),
            "businessCategory": list(svc.get("business_categories") or []) or None,
            "trustCenter": repo(pkg["trust_center"], "Trust Center") if pkg.get("trust_center") else None,
            "secureConfigurationGuidance": (repo(pkg["secure_configuration_guide"], "Secure Configuration Guidance")
                                            if pkg.get("secure_configuration_guide") else None),
            "additionalRepositories": [repo(r, "Documentation") for r in pkg.get("repositories") or []] or None,
            "nextOngoingCertificationReportDate": nxt},
        "contactInformation": [_clean({"contactType": c.get("type"), "contactName": c.get("name"),
                                       "contactEmail": c.get("email"), "contactPhone": c.get("phone")})
                               for c in pkg.get("contacts") or []],
        "assessor": ({"name": pkg["assessor"]["name"], "assessorID": str(pkg["assessor"]["id"])}
                     if isinstance(pkg.get("assessor"), dict) and pkg["assessor"].get("name") else None),
        "advisors": [{"name": a} for a in pkg.get("advisors") or []] or None,
        "certifiedServices": [_clean({"serviceName": s.get("name"), "serviceDescription": s.get("description"),
                                      "dateAvailable": str(s["available"]) if s.get("available") else None})
                              for s in pkg.get("certified_services") or []] or None,
        "thirdPartyInformationResources": ({
            "certified": [{"fedRampCertifiedThirdPartyInformationResource": t.get("fedramp_id"), "useCase": t.get("use_case")}
                          for t in tp.get("certified") or []] or None,
            "nonCertified": [_clean({"name": t.get("name"), "provider": t.get("provider"), "website": t.get("website"),
                                     "useCase": t.get("use_case")}) for t in tp.get("non_certified") or []] or None}
            if tp else None),
    }
    return _clean(doc)


def build_sdr(model: Engagement, pkg: dict) -> dict:
    from . import __version__
    flagged = _flagged(model)
    ksis, rules = [], []
    for r in model.requirements:
        rid = str(r["id"])
        if not model.in_category_scope(rid):
            continue
        (ksis if r.get("kind") == "indicator" else rules).append(requirement_entry(model, rid, flagged))
    sdr = pkg.get("sdr") or {}
    ports = [_clean({"serviceName": p.get("service"), "portNumber": str(p.get("port")),
                     "transportProtocol": p.get("protocol"), "encryption": p.get("encryption"),
                     "purpose": p.get("purpose")}) for p in pkg.get("ports_and_protocols") or []]
    return _clean({
        "certificationPackageOverviewUri": overview_url(pkg),
        "metadata": {"version": str(sdr.get("version") or model.today.isoformat()),
                     "lastUpdated": _iso(model.today),
                     "updateSource": sdr.get("update_source") or f"GRC readiness engine {__version__}, from the engagement record"},
        "portsAndProtocols": ports or None,
        "fedRampRequirements": rules,
        "keySecurityIndicators": ksis,
    })


def _vuln(v: dict, today: dt.date) -> dict:
    explanation = (v.get("overdue") or {}).get("explanation")
    ev = _date(v.get("evaluated"))
    breach = bool(ev and v.get("disposition") not in FINISHED and not v.get("accepted") and (today - ev).days > MAV_DAYS)
    overdue = {"isOverdue": True, "explanation": explanation} if explanation else (
        {"isOverdue": True, "explanation": f"Not fully mitigated or remediated within {MAV_DAYS} days of evaluation "
                                           "(VER-TFR-MAV): it should be an accepted vulnerability."}
        if breach else {"isOverdue": False})
    nxt = v.get("next_reduction") or {}
    return _clean({
        "providerTrackingId": str(v.get("id")),
        "detection": {"detectedAt": _iso(v.get("detected")), "detectionSource": v.get("source")},
        "vulnerabilityDescription": v.get("description"),
        "potentialAgencyImpact": v.get("impact"),
        "evaluationCompletedAt": _iso(v.get("evaluated")),
        "isInternetReachable": v.get("internet_reachable"),
        "isLikelyExploitable": v.get("likely_exploitable"),
        "currentRating": v.get("rating"),
        "projectedNextReduction": ({"estimatedAt": _iso(nxt.get("by")), "targetRating": nxt.get("rating")}
                                   if nxt and v.get("disposition") not in FINISHED else None),
        "overdueStatus": overdue,
        "supplementaryRiskInformation": v.get("supplementary"),
        "painReductionEvents": [{"reducedAt": _iso(r.get("on")), "rating": r.get("rating")}
                                for r in v.get("reductions") or []] or None,
        "finalDisposition": v.get("disposition"),
    })


def _active(v: dict, start: dt.date, end: dt.date) -> bool:
    """Any detection, evaluation, reduction, closure or acceptance in the period, or still open during it."""
    dates = [v.get("detected"), v.get("evaluated"), v.get("closed"), (v.get("accepted") or {}).get("on")]
    dates += [r.get("on") for r in v.get("reductions") or [] if isinstance(r, dict)]
    if any(_in(d, start, end) for d in dates):
        return True
    det, closed = _date(v.get("detected")), _date(v.get("closed"))
    return bool(det and det <= end and (closed is None or closed >= start) and v.get("disposition") not in FINISHED)


def _period(start: dt.date, end: dt.date) -> dict:
    return {"from": _iso(start), "to": _iso(dt.datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=dt.timezone.utc))}


def build_vdr(model: Engagement, pkg: dict, vulns: list[dict], start: dt.date, end: dt.date) -> dict:
    return {"certificationPackageOverviewUri": overview_url(pkg), "reportPeriod": _period(start, end),
            "vulnerabilities": [_vuln(v, model.today) for v in vulns if not v.get("accepted") and _active(v, start, end)]}


def build_avi(model: Engagement, pkg: dict, vulns: list[dict], start: dt.date, end: dt.date) -> dict:
    return {"certificationPackageOverviewUri": overview_url(pkg), "reportPeriod": _period(start, end),
            "acceptedVulnerabilities": [{"vulnerabilityDetail": _vuln(v, model.today), "acceptanceRationale": v["accepted"]["rationale"]}
                                        for v in vulns if v.get("accepted") and _active(v, start, end)]}


def build_history(model: Engagement, pkg: dict, vulns: list[dict]) -> dict:
    return {"certificationPackageOverviewUri": overview_url(pkg), "generatedAt": _iso(model.today),
            "activeVulnerabilities": [_vuln(v, model.today) for v in vulns if not v.get("accepted")],
            "acceptedVulnerabilities": [{"vulnerabilityDetail": _vuln(v, model.today), "acceptanceRationale": v["accepted"]["rationale"]}
                                        for v in vulns if v.get("accepted")]}


def incident_stage(i: dict) -> str:
    if i.get("resolved"):
        return "Final"
    if any(i.get(k) for k in ("activity", "indicators", "cves", "root_cause", "response")):
        return "Ongoing"
    return "Initial"


def build_incident(pkg: dict, i: dict) -> dict:
    timeline = _clean({"startedAt": _iso(i.get("started")), "detectedAt": _iso(i.get("detected")),
                       "detectionSource": i.get("source"), "evaluationCompletedAt": _iso(i.get("evaluated")),
                       "milestones": [{"occurredAt": _iso(m.get("at")), "milestoneDescription": m.get("description")}
                                      for m in i.get("milestones") or []] or None})
    impact = _clean({"historicalRating": list(i.get("history") or []) or None, "currentRating": i.get("rating"),
                     "evaluationNotes": i.get("rating_notes")})
    return _clean({
        "certificationPackageOverviewUri": overview_url(pkg), "reportType": incident_stage(i),
        "providerTrackingId": str(i.get("id")), "federalIncidentCoordinator": i.get("coordinator"),
        "incidentDescription": i.get("description"), "timeline": timeline or None, "potentialImpact": impact or None,
        "functionalImpact": i.get("functional_impact"), "recoveryPlan": i.get("recovery_plan"),
        "affectedAgencies": list(i.get("agencies") or []) or None, "observedActivity": i.get("activity"),
        "indicatorsOfCompromise": list(i.get("indicators") or []) or None, "relatedCveIds": list(i.get("cves") or []) or None,
        "rootCause": i.get("root_cause"), "responseAndRecoveryActivities": i.get("response"),
        "resolvedAt": _iso(i.get("resolved"))})


def build_scn(pkg: dict, c: dict) -> dict:
    plan = c.get("plan") or {}
    return _clean({
        "certificationPackageOverviewUri": overview_url(pkg), "assessorName": c.get("assessor"),
        "relatedVulnerability": c.get("related_vulnerability"), "changeType": c.get("type"),
        "changeTypeExplanation": c.get("type_explanation"), "changeDescription": c.get("description"),
        "reason": c.get("reason"), "customerImpact": c.get("customer_impact"),
        "planAndTimeline": _clean({"summary": plan.get("summary"),
                                   "plannedStart": str(plan["start"]) if plan.get("start") else None,
                                   "plannedCompletion": str(plan["completion"]) if plan.get("completion") else None,
                                   "milestones": [_clean({"milestoneDescription": m.get("description"),
                                                          "targetDate": str(m["date"]) if m.get("date") else None})
                                                  for m in plan.get("milestones") or []] or None}) if plan else None,
        "impactedControls": [str(x) for x in c.get("requirements") or []] or None,
        "impactAnalysis": c.get("impact_analysis")})


def build_ocr(model: Engagement, pkg: dict, report: dict, vulns: list[dict], incidents: list[dict], changes: list[dict],
              start: dt.date, end: dt.date) -> dict:
    accepted = [v for v in vulns if v.get("accepted") and _active(v, start, end)]
    if accepted:
        top = max((v.get("rating") or 0) for v in accepted)
        summary = (f"{len(accepted)} accepted vulnerabilit{'y' if len(accepted) == 1 else 'ies'} with activity in this period "
                   f"({', '.join(str(v['id']) for v in accepted)}); highest current Potential Agency Impact rating N{top}. "
                   "Full records are in the Accepted Vulnerability Info report for the same period.")
    else:
        summary = "No accepted vulnerabilities had activity in this period."
    horizon = _date(report.get("planned_through")) or add_months(end, 3)
    inc = []
    for i in incidents:
        when = i.get("started") or i.get("detected")
        d0, d1 = _date(when), _date(i.get("resolved"))
        if d0 and d0 <= end and (d1 is None or d1 >= start):
            inc.append(_clean({"summary": _text(i.get("description")), "occurredAt": _iso(when),
                               "resolvedAt": _iso(i.get("resolved")) if d1 and d1 <= end else None,
                               "incidentLessonsLearned": list(i.get("lessons") or []) or None}))
    return {
        "certificationPackageOverviewUri": overview_url(pkg),
        "reportPeriod": {"from": start.isoformat(), "to": end.isoformat()},
        "certificationDataChanges": [str(x) for x in report.get("data_changes") or []],
        "plannedCertificationDataChanges": {"planningHorizonThrough": horizon.isoformat(),
                                            "changes": [str(x) for x in report.get("planned_changes") or []]},
        "acceptedVulnerabilities": summary,
        "transformativeChanges": [f"{c.get('id')} ({c.get('date')}): {_text(c.get('description'))}" for c in changes
                                  if c.get("type") == "Transformative" and _in(c.get("date"), start, end)],
        "updatedRecommendations": [str(x) for x in report.get("recommendations") or []],
        "activeAgencies": [str(a) for a in pkg.get("agencies") or []],
        "reportableIncidents": {"incidents": inc},
    }


# ------------------------------------------------------------------ Markdown copies
def to_markdown(doc: dict, kind: str, title: str) -> str:
    """A readable copy, using the field titles from FedRAMP's schema."""
    s = schema(kind)
    reg = _registry()

    def resolve(node: dict, base: dict) -> tuple[dict, dict]:
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if ref.startswith("#"):
                target, root = base, base
            else:
                url, _, frag = ref.partition("#")
                root = reg.contents(url)
                target, ref = root, "#" + frag
            for part in [p for p in ref[2:].split("/") if p]:
                target = target[part]
            node, base = target, root
        return node or {}, base

    def label(node: dict, key: str) -> str:
        return node.get("title") or key

    lines = [f"# {title}", ""]

    def emit(value, node: dict, base: dict, depth: int):
        node, base = resolve(node, base)
        pad = "  " * max(depth - 1, 0) if isinstance(value, dict) else "  " * depth
        if isinstance(value, dict):
            props = node.get("properties") or {}
            for k, v in value.items():
                sub, sbase = resolve(props.get(k, {}), base)
                name = label(sub, k)
                if isinstance(v, (dict, list)):
                    if depth == 0:
                        lines.extend([f"## {name}", ""])
                        emit(v, sub, sbase, 0 if isinstance(v, list) else 1)
                        lines.append("")
                    else:
                        lines.append(f"{pad}- **{name}:**")
                        emit(v, sub, sbase, depth + 1)
                else:
                    if depth == 0:
                        lines.extend([f"**{name}:** {_scalar(v)}", ""])
                    else:
                        lines.append(f"{pad}- **{name}:** {_scalar(v)}")
        elif isinstance(value, list):
            item = node.get("items") or {}
            if not value:
                lines.append(f"{pad}- None")
            for v in value:
                if isinstance(v, dict):
                    isub, ibase = resolve(item, base)
                    first = True
                    for k, x in v.items():
                        p = (isub.get("properties") or {}).get(k, {})
                        psub, pbase = resolve(p, ibase)
                        mark = "- " if first else "  "
                        first = False
                        if isinstance(x, (dict, list)):
                            lines.append(f"{pad}{mark}**{label(psub, k)}:**")
                            emit(x, psub, pbase, depth + 2)
                        else:
                            lines.append(f"{pad}{mark}**{label(psub, k)}:** {_scalar(x)}")
                else:
                    lines.append(f"{pad}- {_scalar(v)}")
        else:
            lines.append(f"{pad}{_scalar(value)}")

    emit(doc, s, s, 0)
    return "\n".join(lines).rstrip() + "\n"


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return " ".join(str(v).split()) if isinstance(v, str) and "\n" not in v else str(v)


# ------------------------------------------------------------------ export
def default_period(model: Engagement, reports: list[dict]) -> tuple[dt.date, dt.date, dict]:
    """The latest report entry that has ended by today, else the 3 months ending today."""
    done = [r for r in reports if _date(r.get("to")) and _date(r.get("from")) and _date(r.get("to")) <= model.today]
    if done:
        r = max(done, key=lambda r: _date(r.get("to")))
        return _date(r["from"]), _date(r["to"]), r
    end = model.today
    return add_months(end, -3) + dt.timedelta(days=1), end, {}


def problems(model: Engagement, files: dict) -> list[str]:
    """What stops a complete export (before FedRAMP's schemas are even checked)."""
    out = []
    if model.catalog["framework"]["id"] != "fedramp20x":
        out.append(f"this record's framework is {model.catalog['framework']['id']}, not fedramp20x")
    for name, data in files.items():
        if isinstance(data, dict) and data.get("_error"):
            out.append(f"engagement/fedramp/{name}.yaml: {data['_error']}")
    from .rules import validate as run_rules
    errors = [f for f in run_rules(model) if f.severity == "error"]
    if errors:
        out.append(f"the record has {len(errors)} validation error(s) (first: {errors[0].code} {errors[0].message[:160]}); "
                   "fix them (`grc validate`) or use --force for a draft")
    for name in ("vulnerabilities", "incidents"):
        if files.get(name) is None:
            out.append(f"engagement/fedramp/{name}.yaml is missing: the reports would say there are none. Create it "
                       f"(`grc fedramp init`); `{name}: []` states that there are none")
    pkg = files.get("package")
    if not pkg:
        out.append("engagement/fedramp/package.yaml is missing: run `grc fedramp init` and fill it in")
    elif not pkg.get("_error") and not pkg.get("overview_url"):
        out.append("engagement/fedramp/package.yaml: set overview_url, the https address where the Certification "
                   "Package Overview will be published (every other report points to it)")
    return out


def export(model: Engagement, out: Path, start: dt.date | None = None, end: dt.date | None = None,
           force: bool = False) -> list[tuple[str, int, list[str]]]:
    """Write every document; returns (relative path, bytes, schema errors). Without `force`, nothing is written
    when the package is incomplete or any document fails FedRAMP's schema."""
    files = load(model)
    stop = problems(model, files)
    if stop and not force:
        raise FedrampError("; ".join(stop))
    try:
        return _export(model, files, Path(out), start, end, force, bool(stop))
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        if isinstance(exc, FedrampError):
            raise
        raise FedrampError("the files in engagement/fedramp/ aren't laid out as expected "
                           f"({exc.__class__.__name__}: {str(exc)[:120]}); run `grc validate` and fix what it reports") from exc


def _safe_ids(rows: list[dict], name: str) -> None:
    """Ids become file names: each must be a plain token and unique (ignoring case), even for a draft."""
    import re
    seen = set()
    for r in rows:
        rid = str(r.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", rid) or ".." in rid:
            raise FedrampError(f"engagement/fedramp/{name}.yaml: '{rid[:40]}' can't be used as an id (letters, digits, "
                               "'.', '_' and '-' only)")
        if rid.lower() in seen:
            raise FedrampError(f"engagement/fedramp/{name}.yaml: {rid} appears twice")
        seen.add(rid.lower())


def _export(model: Engagement, files: dict, out: Path, start, end, force: bool, draft: bool) -> list:
    pkg = files.get("package") if isinstance(files.get("package"), dict) and not files["package"].get("_error") else {}
    pkg = jsonable(pkg)
    vulns = jsonable(_items(files.get("vulnerabilities"), "vulnerabilities"))
    incidents = jsonable(_items(files.get("incidents"), "incidents"))
    changes = jsonable(_items(files.get("changes"), "changes"))
    reports = jsonable(_items(files.get("reports"), "reports"))
    _safe_ids(incidents, "incidents")
    _safe_ids(changes, "changes")
    usable = {n: isinstance(files.get(n), dict) and not files[n].get("_error") for n in ("vulnerabilities", "incidents")}
    p_start, p_end, report = default_period(model, reports)
    if start or end:
        p_start, p_end = start or p_start, end or p_end
        report = next((r for r in reports if _date(r.get("from")) == p_start and _date(r.get("to")) == p_end), {})
    if p_start > p_end:
        raise FedrampError(f"the period starts ({p_start}) after it ends ({p_end})")
    tag = f"{p_start.isoformat()}_{p_end.isoformat()}"
    docs: list[tuple[str, str, dict, str]] = [
        ("certification-package-overview.json", "overview", build_overview(model, pkg, reports), "Certification Package Overview"),
        ("security-decision-record.json", "sdr", build_sdr(model, pkg), "Security Decision Record"),
    ]
    # a report whose source file is missing or unreadable would state "none": it isn't written, even as a draft
    if usable["vulnerabilities"] and usable["incidents"]:
        docs.append((f"ongoing-certification-report-{tag}.json", "ocr",
                     build_ocr(model, pkg, report, vulns, incidents, changes, p_start, p_end),
                     f"Ongoing Certification Report, {p_start} to {p_end}"))
    if usable["vulnerabilities"]:
        docs += [(f"vulnerability-detail-report-{tag}.json", "vdr", build_vdr(model, pkg, vulns, p_start, p_end),
                  f"Vulnerability Detail Report, {p_start} to {p_end}"),
                 (f"accepted-vulnerability-info-{tag}.json", "avi", build_avi(model, pkg, vulns, p_start, p_end),
                  f"Accepted Vulnerability Info, {p_start} to {p_end}"),
                 ("historical-vulnerability-activity.json", "history", build_history(model, pkg, vulns),
                  f"Vulnerability detection and response activity as of {model.today}")]
    for i in incidents:
        docs.append((f"incidents/{i.get('id')}.json", "incident", build_incident(pkg, i),
                     f"Incident report {i.get('id')} ({incident_stage(i)})"))
    for c in changes:
        docs.append((f"significant-changes/{c.get('id')}.json", "scn", build_scn(pkg, c),
                     f"Significant Change Notification {c.get('id')}"))
    checked = [(name, kind, doc, title, validate(doc, kind)) for name, kind, doc, title in docs]
    bad = [(n, e) for n, _, _, _, e in checked if e]
    if bad and not force:
        detail = "; ".join(f"{n}: {e[0]}" + (f" (and {len(e) - 1} more)" if len(e) > 1 else "") for n, e in bad[:6])
        raise FedrampError(f"{len(bad)} document(s) don't match FedRAMP's schema, so nothing was written: {detail}")
    if draft:   # forced past a refusal: say so in the JSON where FedRAMP's format has a place for it
        sdr = next(d for _, k, d, _ in docs if k == "sdr")
        sdr["metadata"]["version"] = "DRAFT " + sdr["metadata"]["version"]
    root = out.resolve()
    written = []
    note = "Generated from the engagement record by the GRC readiness engine."
    sdr_note = (" Statuses reflect what reviewers verified in a readiness review by the engagement team, not an "
                "independent assessment.")
    who = pkg.get("provider") or model.client
    for name, kind, doc, title, errs in checked:
        path = out / name
        if not path.resolve().is_relative_to(root):
            raise FedrampError(f"{name}: would be written outside {out}")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        md = to_markdown(doc, kind, f"{who}: {title}")
        if kind == "sdr":
            md = md.replace("\n", "\n\n" + sdr_summary(doc) + "\n", 1)
        md = md.replace("\n", f"\n\n_{note}{sdr_note if kind == 'sdr' else ''}_" + (" **Draft: this document does not yet match FedRAMP's schema.**" if errs else
                         " **Draft: written with --force despite problems in the record; not for submission.**" if draft else "")
                        + "\n", 1)
        path.with_suffix(".md").write_text(md, encoding="utf-8")
        written.append((name, len(text.encode("utf-8")), errs))
    return written


def sdr_summary(doc: dict) -> str:
    def count(rows, key):
        c = {}
        for r in rows:
            c[r.get(key) or "Not applicable"] = c.get(r.get(key) or "Not applicable", 0) + 1
        order = ["Implemented", "Partially Implemented", "Not Implemented", "Not applicable"]
        return ", ".join(f"{c[k]} {k.lower()}" for k in order if k in c) or "none"
    ksi = doc.get("keySecurityIndicators") or []
    frr = doc.get("fedRampRequirements") or []
    return (f"**Key Security Indicators ({len(ksi)}):** {count(ksi, 'ksiImplementationStatus')}.  \n"
            f"**FedRAMP rules ({len(frr)}):** {count(frr, 'frrImplementationStatus')}.")


# ------------------------------------------------------------------ starter files
STARTERS = {
    "package": """\
# FedRAMP 20x: the cloud service offering. Fictional example values: replace every one.
# Feeds the Certification Package Overview and the Security Decision Record. See docs/FEDRAMP20X.md.
overview_url: https://trust.example.com/fedramp/certification-package-overview.json
fedramp_id: Example Provider EXS        # FedRAMP ID once assigned; until then the provider's name and acronym
# uei: ABCDEFGHJK12                     # SAM.gov Unique Entity Identifier, if you have one
provider: Example Provider (fictional)
service:
  name: Example Service
  acronym: EXS
  description: One paragraph on what the service does for agencies.
  website: https://www.example.com/service
  logo: https://www.example.com/logo.png
  types: [SaaS]                         # SaaS, PaaS, IaaS
  deployment_model: Public Cloud        # Public Cloud, Government-Only Cloud, Hybrid Cloud, Community Cloud, Government Community Cloud
  business_categories: [Collaboration]
trust_center:
  url: https://trust.example.com
  description: FedRAMP Trust Center with the certification package and reports
  authentication_required: true
  access_instructions: Agencies request access at trust.example.com/request.
secure_configuration_guide:
  url: https://docs.example.com/secure-configuration
  description: Secure configuration guide for agency administrators
  authentication_required: false
contacts:                               # at least one Security and one Sales contact
  - {type: Security, name: Security team, email: security@example.com, phone: 202-555-0100}
  - {type: Sales, name: Public sector sales, email: gov-sales@example.com, phone: 202-555-0101}
# assessor: {name: Example Assessor, id: FRA-0000}
ports_and_protocols:
  - {service: Web application and API, port: 443, protocol: TCP, encryption: TLS 1.2+, purpose: Agency users and API clients}
agencies: []                            # agencies directly using the offering
""",
    "vulnerabilities": """\
# FedRAMP 20x: vulnerability detection and response (VER). One entry per vulnerability, by your own tracking id.
# Feeds the Vulnerability Detail Report, Accepted Vulnerability Info and the historical activity file.
vulnerabilities: []
# - id: VULN-2026-0001
#   detected: 2026-11-03T14:20:00Z
#   source: Weekly container image scan
#   description: Outdated OpenSSL in the API image
#   impact: Could expose API traffic to downgrade attacks
#   evaluated: 2026-11-04T09:00:00Z
#   internet_reachable: true
#   likely_exploitable: false
#   rating: 2                            # Potential Agency Impact N-rating, 0 to 5
#   next_reduction: {by: 2026-11-20, rating: 1}
#   reductions: [{on: 2026-11-10, rating: 2}]
#   # disposition: Remediated            # Fully Mitigated, Partially Mitigated, Remediated, False Positive
#   # closed: 2026-11-21
#   # accepted: {rationale: Why it won't be fully fixed within 192 days, on: 2026-11-30}
""",
    "incidents": """\
# FedRAMP 20x: FedRAMP Reportable Incidents (IEC). Each gets a report at its current stage:
# Initial, Ongoing (once there is activity, root cause or response), Final (once resolved).
incidents: []
# - id: INC-2026-001
#   coordinator: Security team, security@example.com, 202-555-0100
#   description: Unauthorized access attempt against the admin console
#   started: 2026-11-02T03:10:00Z
#   detected: 2026-11-02T03:25:00Z
#   source: SIEM alert
#   rating: 2
#   agencies: []
""",
    "changes": """\
# FedRAMP 20x: Significant Change Notifications (SCN). Routine recurring changes don't need one.
changes: []
# - id: SCN-2026-001
#   date: 2026-11-15
#   type: Adaptive                       # Adaptive or Transformative
#   type_explanation: Swaps a managed database version without changing the architecture
#   description: Upgrade the managed PostgreSQL cluster from 15 to 16
#   reason: End of vendor support for version 15
#   customer_impact: None expected; no change to customer configuration responsibilities
#   plan: {summary: Blue-green upgrade with rollback, start: 2026-12-01, completion: 2026-12-05}
#   requirements: [KSI-CMT-VTD]
""",
    "reports": """\
# FedRAMP 20x: notes for each Ongoing Certification Report (every 3 months, CCM-OCR-AVL).
# Accepted vulnerabilities, transformative changes, incidents and agencies are filled in from the other files.
reports: []
# - from: 2026-09-01
#   to: 2026-11-30
#   data_changes: [Updated the secure configuration guide for the new admin console]
#   planned_changes: [Move logging to the new SIEM in January]
#   recommendations: [Enable phishing-resistant MFA for all agency administrators]
""",
}


def init(model: Engagement) -> list[Path]:
    """Write starter files for those not already present."""
    folder(model).mkdir(parents=True, exist_ok=True)
    made = []
    for name, text in STARTERS.items():
        p = folder(model) / f"{name}.yaml"
        if not p.exists():
            p.write_text(text, encoding="utf-8")
            made.append(p)
    return made


# ------------------------------------------------------------------ validation rules
def check(model: Engagement) -> list:
    """E001 (schema), E092 (duplicate ids, unknown requirement ids), W182 (package incomplete), W183 (VER-TFR-MAV)."""
    from jsonschema import Draft202012Validator, FormatChecker
    from .rules import Finding, _rel
    if not applies(model):
        return []
    out = []
    files = load(model)
    for name, data in files.items():
        path = folder(model) / f"{name}.yaml"
        if data is None:
            continue
        if data.get("_error"):
            out.append(Finding("error", "E001", f"fedramp/{name}.yaml: {data['_error']}.", _rel(model, path)))
            continue
        v = Draft202012Validator(load_schema(f"fedramp-{name}"), format_checker=FormatChecker())
        for err in sorted(v.iter_errors(jsonable(data)), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            out.append(Finding("error", "E001", f"Schema: {loc}: {err.message[:300]}", _rel(model, path)))
        if name in LIST_KEY:
            seen = set()
            for item in _items(data, name):
                key = str(item.get("id") or item.get("from"))
                if key.lower() in seen and item.get("id"):
                    out.append(Finding("error", "E092", f"fedramp/{name}.yaml: {key} appears twice; each needs its own id.",
                                       _rel(model, path), key))
                seen.add(key.lower())
    for c in _items(files.get("changes"), "changes"):
        reqs = c.get("requirements") if isinstance(c.get("requirements"), list) else []
        unknown = [str(x) for x in reqs if str(x) not in model.requirement_index]
        if unknown:
            out.append(Finding("error", "E092", f"fedramp/changes.yaml: {c.get('id')} names {', '.join(unknown)}, not in "
                               "the FedRAMP 20x catalog.", _rel(model, folder(model) / "changes.yaml"), str(c.get("id"))))
    if model.catalog["framework"]["id"] == "fedramp20x":
        pkg = files.get("package")
        ppath = _rel(model, folder(model) / "package.yaml")
        if pkg is None:
            out.append(Finding("warning", "W182", "No engagement/fedramp/package.yaml yet: the Certification Package Overview "
                               "and the Security Decision Record need it (run `grc fedramp init`).", ppath))
        elif not pkg.get("_error"):
            missing = []
            if not pkg.get("overview_url"):
                missing.append("overview_url")
            contacts = pkg.get("contacts") if isinstance(pkg.get("contacts"), list) else []
            types = {str(c.get("type")) for c in contacts if isinstance(c, dict)}
            missing += [f"a {t} contact" for t in ("Security", "Sales") if t not in types]
            if not pkg.get("trust_center"):
                missing.append("trust_center (CDS-CSO-UTC)")
            ends = [_date(r.get("to")) for r in _items(files.get("reports"), "reports") if _date(r.get("to"))]
            if ends and add_months(max(ends), 3) < model.today:
                missing.append(f"an Ongoing Certification Report: the last one in reports.yaml ended {max(ends)}, and the "
                               f"next was due by {add_months(max(ends), 3)} (CCM-OCR-AVL)")
            if missing:
                out.append(Finding("warning", "W182", f"fedramp/package.yaml: the Certification Package Overview still needs "
                                   f"{', '.join(missing)}.", ppath))
        for name in ("vulnerabilities", "incidents"):
            if files.get(name) is None:
                out.append(Finding("warning", "W182", f"No engagement/fedramp/{name}.yaml yet: the reports can't say whether "
                                   f"there are any. Create it; `{name}: []` states that there are none.",
                                   _rel(model, folder(model) / f"{name}.yaml")))
        for v in _items(files.get("vulnerabilities"), "vulnerabilities"):
            ev = _date(v.get("evaluated"))
            if ev and v.get("disposition") not in FINISHED and not v.get("accepted") and (model.today - ev).days > MAV_DAYS:
                out.append(Finding("warning", "W183", f"fedramp/vulnerabilities.yaml: {v.get('id')} was evaluated on {ev} and "
                                   f"isn't fully mitigated or remediated after {MAV_DAYS} days: record it as an accepted "
                                   "vulnerability (VER-TFR-MAV), with the reason.",
                                   _rel(model, folder(model) / "vulnerabilities.yaml"), str(v.get("id"))))
    return out
