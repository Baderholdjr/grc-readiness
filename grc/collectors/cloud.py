"""Cloud configuration collectors: logging, storage protection, retention.

Authentication is ambient - the workflow signs in with OIDC (no long-lived keys):
  AWS   aws-actions/configure-aws-credentials  (read-only role)
  Azure azure/login                            (Reader role)
  GCP   google-github-actions/auth             (viewer roles)
If a provider isn't signed in, its checks are skipped, not failed.
"""
from __future__ import annotations

import json
import shutil
import subprocess

from .base import FAIL, PASS, CheckResult, MissingCredentials, collector

# ----------------------------------------------------------------------- AWS
_aws_factory = None  # tests inject a fake: callable(service, region) -> client


def _aws(service: str, region: str | None = None):
    if _aws_factory:
        return _aws_factory(service, region)
    try:
        import boto3
    except ImportError as exc:
        raise MissingCredentials("boto3 is not installed") from exc
    session = boto3.Session(region_name=region)
    if session.get_credentials() is None:
        raise MissingCredentials("no AWS credentials (configure OIDC role)")
    return session.client(service)


@collector("aws.cloudtrail")
def aws_cloudtrail(region: str = "us-east-1", require_multi_region: bool = True) -> CheckResult:
    """An account-wide CloudTrail trail exists and is logging (event logs, A.6.2.8)."""
    ct = _aws("cloudtrail", region)
    trails = ct.describe_trails(includeShadowTrails=False).get("trailList", [])
    rows = []
    for t in trails:
        status = ct.get_trail_status(Name=t["TrailARN"])
        rows.append({"name": t.get("Name"), "multi_region": t.get("IsMultiRegionTrail", False),
                     "logging": status.get("IsLogging", False), "log_validation": t.get("LogFileValidationEnabled", False)})
    good = [r for r in rows if r["logging"] and (r["multi_region"] or not require_multi_region)]
    findings = [] if good else ["no logging" + (" multi-region" if require_multi_region else "") + " CloudTrail trail"]
    return CheckResult(FAIL if findings else PASS, f"{len(good)}/{len(rows)} trails compliant", {"trails": rows}, findings)


@collector("aws.s3_bucket")
def aws_s3_bucket(bucket: str, require: list[str] | None = None, region: str | None = None) -> CheckResult:
    """A model/data artifact bucket is encrypted, versioned and not public (A.7.5, A.4.3)."""
    require = require or ["encryption", "versioning", "public_access_block"]
    s3 = _aws("s3", region)
    d, findings = {"bucket": bucket}, []
    if "encryption" in require:
        try:
            rules = s3.get_bucket_encryption(Bucket=bucket)["ServerSideEncryptionConfiguration"]["Rules"]
            d["encryption"] = [r["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] for r in rules]
        except Exception as exc:  # ServerSideEncryptionConfigurationNotFoundError
            d["encryption"] = None
            findings.append(f"default encryption not configured ({type(exc).__name__})")
    if "versioning" in require:
        d["versioning"] = s3.get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")
        if d["versioning"] != "Enabled":
            findings.append(f"versioning is {d['versioning']}")
    if "public_access_block" in require:
        try:
            cfg = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
        except Exception:
            cfg = {}
        d["public_access_block"] = cfg
        off = [k for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets") if not cfg.get(k)]
        if off:
            findings.append(f"public access block not fully enabled: {', '.join(off)}")
    return CheckResult(FAIL if findings else PASS, f"s3://{bucket}: {len(findings)} issue(s)", d, findings)


@collector("aws.log_retention")
def aws_log_retention(prefix: str, min_days: int = 365, region: str = "us-east-1") -> CheckResult:
    """CloudWatch log groups for AI services keep logs long enough (A.6.2.8)."""
    logs = _aws("logs", region)
    groups, token = [], None
    while True:
        kw = {"logGroupNamePrefix": prefix}
        if token:
            kw["nextToken"] = token
        page = logs.describe_log_groups(**kw)
        groups += page.get("logGroups", [])
        token = page.get("nextToken")
        if not token:
            break
    rows = [{"name": g["logGroupName"], "retention_days": g.get("retentionInDays")} for g in groups]
    short = [r["name"] for r in rows if r["retention_days"] is not None and r["retention_days"] < min_days]
    findings = []
    if not rows:
        findings.append(f"no log groups with prefix '{prefix}'")
    if short:
        findings.append(f"{len(short)} log group(s) retain < {min_days} days: {', '.join(short[:10])}")
    return CheckResult(FAIL if findings else PASS, f"{len(rows)} log groups, {len(short)} below {min_days}d",
                       {"prefix": prefix, "min_days": min_days, "log_groups": rows}, findings)


# ------------------------------------------------------------- CLI providers
_cli_runner = None  # tests inject: callable(argv) -> parsed JSON


def _cli(argv: list[str]):
    if _cli_runner:
        return _cli_runner(argv)
    if not shutil.which(argv[0]):
        raise MissingCredentials(f"{argv[0]} CLI not installed")
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        if any(s in err.lower() for s in ("az login", "not logged in", "gcloud auth login", "no credentialed accounts")):
            raise MissingCredentials(f"{argv[0]} is not signed in")
        raise RuntimeError(err[:300])
    return json.loads(proc.stdout or "null")


@collector("azure.storage_account")
def azure_storage_account(name: str, resource_group: str) -> CheckResult:
    """An Azure storage account holding AI artifacts enforces HTTPS/TLS1.2 and blocks public blob access."""
    acct = _cli(["az", "storage", "account", "show", "-n", name, "-g", resource_group, "-o", "json"]) or {}
    d = {"name": name, "https_only": acct.get("enableHttpsTrafficOnly"), "min_tls": acct.get("minimumTlsVersion"),
         "allow_blob_public_access": acct.get("allowBlobPublicAccess")}
    findings = []
    if not d["https_only"]:
        findings.append("HTTPS-only traffic is not enforced")
    if d["min_tls"] not in ("TLS1_2", "TLS1_3"):
        findings.append(f"minimum TLS is {d['min_tls']}")
    if d["allow_blob_public_access"]:
        findings.append("public blob access is allowed")
    return CheckResult(FAIL if findings else PASS, f"azure storage {name}: {len(findings)} issue(s)", d, findings)


@collector("azure.activity_log_export")
def azure_activity_log_export() -> CheckResult:
    """The subscription's activity log is exported (diagnostic setting exists)."""
    data = _cli(["az", "monitor", "diagnostic-settings", "subscription", "list", "-o", "json"]) or {}
    items = data.get("value", data) if isinstance(data, dict) else data
    rows = [{"name": s.get("name"), "workspace": bool(s.get("workspaceId")), "storage": bool(s.get("storageAccountId"))}
            for s in items or []]
    findings = [] if rows else ["no subscription diagnostic setting exports the activity log"]
    return CheckResult(FAIL if findings else PASS, f"{len(rows)} activity-log export(s)", {"settings": rows}, findings)


@collector("gcp.bucket")
def gcp_bucket(bucket: str) -> CheckResult:
    """A GCS bucket holding AI artifacts has uniform access, versioning and public access prevention."""
    b = _cli(["gcloud", "storage", "buckets", "describe", f"gs://{bucket}", "--format=json"]) or {}
    d = {"bucket": bucket, "uniform_bucket_level_access": b.get("uniform_bucket_level_access"),
         "versioning_enabled": b.get("versioning_enabled"), "public_access_prevention": b.get("public_access_prevention")}
    findings = []
    if not d["uniform_bucket_level_access"]:
        findings.append("uniform bucket-level access is off")
    if not d["versioning_enabled"]:
        findings.append("object versioning is off")
    if d["public_access_prevention"] != "enforced":
        findings.append(f"public access prevention is {d['public_access_prevention']}")
    return CheckResult(FAIL if findings else PASS, f"gs://{bucket}: {len(findings)} issue(s)", d, findings)


@collector("gcp.log_sinks")
def gcp_log_sinks(project: str, min_sinks: int = 1) -> CheckResult:
    """Cloud Logging exports to a sink (long-term retention of audit/event logs)."""
    sinks = _cli(["gcloud", "logging", "sinks", "list", f"--project={project}", "--format=json"]) or []
    rows = [{"name": s.get("name"), "destination": s.get("destination"), "disabled": s.get("disabled", False)} for s in sinks]
    active = [r for r in rows if not r["disabled"]]
    findings = [] if len(active) >= min_sinks else [f"{len(active)} active log sink(s); expected >= {min_sinks}"]
    return CheckResult(FAIL if findings else PASS, f"{len(active)} active log sink(s) in {project}",
                       {"project": project, "sinks": rows}, findings)
