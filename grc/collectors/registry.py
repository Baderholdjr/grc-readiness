"""Model registries: models released to production were validated and approved by someone else.

SageMaker Model Registry: uses the AWS sign-in (OIDC read-only role, needs sagemaker:List*/Describe*).
MLflow (open source or Databricks): MLFLOW_TRACKING_URI (repository variable) and either
MLFLOW_TRACKING_TOKEN (secret, bearer) or MLFLOW_TRACKING_USERNAME / MLFLOW_TRACKING_PASSWORD.
"""
from __future__ import annotations

import base64
import os

from . import http
from .base import FAIL, PASS, CheckResult, MissingCredentials, collector, env, parse_time, setting, utcnow
from .cloud import _aws


# ------------------------------------------------------------------ SageMaker
def _who(meta) -> str | None:
    if not isinstance(meta, dict):
        return None
    return meta.get("UserProfileName") or (meta.get("IamIdentity") or {}).get("Arn") or meta.get("DomainId")


@collector("aws.sagemaker_model_registry")
def sagemaker_model_registry(groups: list[str], region: str | None = None, recent_versions: int = 10,
                             max_pending_days: int | None = 30, require_independent_approval: bool = False,
                             require_model_card: bool = False) -> CheckResult:
    """Each model package group has an Approved latest version, nothing waits too long for approval,
    and (optionally) the approver differs from the creator and a model card is attached.

    Independence uses CreatedBy vs LastModifiedBy (the approval is the usual last modification), so treat
    it as an indicator and sample the approval records in the internal audit.
    """
    sm = _aws("sagemaker", region)
    now = utcnow()
    findings, rows, approvals = [], [], []
    for g in groups:
        try:
            pkgs = sm.list_model_packages(ModelPackageGroupName=g, SortBy="CreationTime", SortOrder="Descending",
                                          MaxResults=max(1, min(recent_versions, 100))).get("ModelPackageSummaryList", [])
        except Exception as exc:  # ResourceNotFound etc. - keep going with the other groups
            findings.append(f"model package group '{g}' could not be read ({type(exc).__name__})")
            continue
        if not pkgs:
            findings.append(f"model package group '{g}' has no versions")
            continue
        latest = pkgs[0]
        if latest.get("ModelApprovalStatus") != "Approved":
            findings.append(f"'{g}' latest version {latest.get('ModelPackageVersion')} is "
                            f"{latest.get('ModelApprovalStatus')}, not Approved")
        for p in pkgs:
            created = parse_time(p.get("CreationTime"))
            status = p.get("ModelApprovalStatus")
            row = {"group": g, "version": p.get("ModelPackageVersion"), "status": status,
                   "created": created.date().isoformat() if created else None}
            if status == "PendingManualApproval" and max_pending_days is not None and created \
                    and (now - created).days > max_pending_days:
                findings.append(f"'{g}' v{p.get('ModelPackageVersion')} pending approval for more than {max_pending_days} days")
            if status == "Approved" and (require_independent_approval or require_model_card):
                d = sm.describe_model_package(ModelPackageName=p.get("ModelPackageArn"))
                creator, approver = _who(d.get("CreatedBy")), _who(d.get("LastModifiedBy"))
                row.update(created_by=creator, approved_by=approver, model_card=bool(d.get("ModelCard")))
                if require_independent_approval and (not approver or not creator or approver == creator):
                    findings.append(f"'{g}' v{p.get('ModelPackageVersion')} approval not shown to be by someone other "
                                    f"than its creator (created by {creator or '?'}, approved by {approver or '?'})")
                if require_model_card and not d.get("ModelCard"):
                    findings.append(f"'{g}' v{p.get('ModelPackageVersion')} is approved without a model card")
            if status == "Approved":
                approvals.append(f"{g}/v{p.get('ModelPackageVersion')}")
            rows.append(row)
    return CheckResult(FAIL if findings else PASS,
                       f"{len(groups)} model group(s), {len(approvals)} approved version(s) in the last {recent_versions}",
                       {"groups": groups, "items": approvals, "versions": rows}, findings)


# ------------------------------------------------------------------ MLflow
def _mlflow_headers() -> dict:
    from .. import sandbox
    token = os.environ.get("MLFLOW_TRACKING_TOKEN", "").strip()
    user, pw = os.environ.get("MLFLOW_TRACKING_USERNAME", "").strip(), os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
    if sandbox.active() or token:
        return {"Authorization": f"Bearer {env('MLFLOW_TRACKING_TOKEN')}"}
    if user:
        return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}
    raise MissingCredentials("MLFLOW_TRACKING_TOKEN (or MLFLOW_TRACKING_USERNAME/PASSWORD) is not set")


def _tags(obj) -> dict:
    t = obj.get("tags") or []
    return {x.get("key"): x.get("value") for x in t if isinstance(x, dict)} if isinstance(t, list) else dict(t)


@collector("mlflow.models")
def mlflow_models(models: list[str], production_alias: str | None = "champion", production_stage: str | None = None,
                  require_model_tags: list[str] | None = None, require_version_tags: list[str] | None = None,
                  approver_tag: str | None = None) -> CheckResult:
    """Registered models are documented and the production version is validated and independently approved.

    production_alias / production_stage: how the production version is identified (MLflow aliases, or
    the legacy stages such as "Production"). require_model_tags: tags every model must carry (e.g.
    "model_card", "impact_assessment"). require_version_tags: tags the production version must carry
    (e.g. "validation_report"). approver_tag: a version tag naming the approver, which must differ
    from the version's creator (user_id).
    """
    base = setting("MLFLOW_TRACKING_URI").rstrip("/") + "/api/2.0/mlflow"
    h = {**_mlflow_headers(), "Accept": "application/json"}
    findings, rows, prod = [], [], []
    for name in models:
        try:
            rm = (http.request("GET", f"{base}/registered-models/get", headers=h, params={"name": name}) or {}).get("registered_model") or {}
        except http.HTTPError as exc:
            findings.append(f"model '{name}' could not be read ({exc.status})")
            continue
        if not str(rm.get("description") or "").strip():
            findings.append(f"model '{name}' has no description")
        mt = _tags(rm)
        for t in require_model_tags or []:
            if not str(mt.get(t) or "").strip():
                findings.append(f"model '{name}' lacks tag '{t}'")
        versions = (http.request("GET", f"{base}/model-versions/search", headers=h,
                                 params={"filter": "name='" + name.replace("'", "\\'") + "'", "max_results": 200}) or {}).get("model_versions") or []
        aliases = {a.get("alias"): str(a.get("version")) for a in rm.get("aliases") or [] if isinstance(a, dict)}
        if production_alias:
            pv = aliases.get(production_alias)
            current = [v for v in versions if str(v.get("version")) == pv]
        else:
            current = [v for v in versions if v.get("current_stage") == production_stage]
        if not current:
            findings.append(f"model '{name}' has no production version "
                            f"({'alias ' + production_alias if production_alias else 'stage ' + str(production_stage)})")
        for v in current:
            vt = _tags(v)
            for t in require_version_tags or []:
                if not str(vt.get(t) or "").strip():
                    findings.append(f"'{name}' v{v.get('version')} (production) lacks tag '{t}'")
            if approver_tag:
                appr, creator = str(vt.get(approver_tag) or "").strip(), str(v.get("user_id") or "").strip()
                if not appr or (creator and appr.lower() == creator.lower()):
                    findings.append(f"'{name}' v{v.get('version')} (production) is not shown to be approved by someone "
                                    f"other than its creator ({approver_tag}: {appr or 'missing'}, created by {creator or '?'})")
            prod.append(f"{name}/v{v.get('version')}")
        for v in versions[:50]:
            created = parse_time(v.get("creation_timestamp")) if v.get("creation_timestamp") is not None else None
            rows.append({"model": name, "version": v.get("version"), "stage": v.get("current_stage"),
                         "created": created.date().isoformat() if created else None,
                         "production": f"{name}/v{v.get('version')}" in prod})
    return CheckResult(FAIL if findings else PASS, f"{len(models)} model(s); {len(prod)} production version(s) checked",
                       {"models": models, "items": prod, "versions": rows}, findings)
