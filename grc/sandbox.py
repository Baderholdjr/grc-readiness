"""Sandbox mode: run the full pipeline without real client credentials.

Enable in engagement/engagement.yaml:

    sandbox:
      enabled: true
      dir: sandbox          # relative to the repo root

Then, instead of calling the real services:
  Drata      -> sandbox/drata.yaml      (route -> canned API response)
  AWS        -> sandbox/aws.yaml        (fake boto3 clients)
  Azure/GCP  -> sandbox/cli.yaml        (argv prefix -> canned CLI JSON)
  Jira, Microsoft Graph (SharePoint), Google Drive, MLflow -> sandbox/http.yaml (URL path -> response)
  SageMaker  -> sandbox/aws.yaml (sagemaker.groups)
  Anthropic  -> sandbox/ai_draft.json   (canned structured draft)
               sandbox/ai_docs.json    (canned document fills, keyed by document id)
GitHub calls are NOT sandboxed: they run for real against the configured repos.

Everything produced in sandbox mode is labelled [SANDBOX] in evidence, snapshots
and reports so it can never be mistaken for real client evidence.
"""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import yaml

_DIR: Path | None = None
NOT_HANDLED = object()


def configure(model) -> None:
    """Activate (or deactivate) the sandbox from the engagement settings."""
    global _DIR
    cfg = (model.engagement.get("sandbox") or {})
    if cfg.get("enabled"):
        _DIR = (model.root / cfg.get("dir", "sandbox")).resolve()
        if not _DIR.is_dir():
            raise SystemExit(f"sandbox enabled but {_DIR} does not exist")
        _install_cloud_fakes()
    else:
        _DIR = None
        _uninstall_cloud_fakes()


def active() -> bool:
    return _DIR is not None


def _load(name: str):
    path = _DIR / name
    if not path.exists():
        return None
    return json.loads(path.read_text()) if path.suffix == ".json" else yaml.safe_load(path.read_text())


# ------------------------------------------------------------------- HTTP
def handle(method: str, url: str, params: dict | None, body: dict | None):
    if not active():
        return NOT_HANDLED
    parsed = urllib.parse.urlparse(url)
    if "drata.com" in parsed.netloc:
        return _drata(parsed.path, params or {})
    if "anthropic.com" in parsed.netloc and "grc-docs" in str((body or {}).get("system", ""))[:40]:
        import re
        prompt = str(((body or {}).get("messages") or [{}])[0].get("content", ""))
        m = re.search(r'<document id="([A-Z0-9-]+)">', prompt)
        canned = (_load("ai_docs.json") or {}).get(m.group(1) if m else "", {"fills": [], "open_questions": [
            "sandbox: no canned fills for this document in sandbox/ai_docs.json"]})
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(canned)}]}
    if "github" in parsed.netloc:
        return NOT_HANDLED  # GitHub is never simulated
    if parsed.netloc == "login.microsoftonline.com":
        return {"access_token": "sandbox", "token_type": "Bearer", "expires_in": 3600}
    if "anthropic.com" not in parsed.netloc:
        return _http(method, parsed.path, params or {}, body or {})
    if "anthropic.com" in parsed.netloc:
        draft = _load("ai_draft.json")
        if draft is None:
            from .collectors.http import HTTPError
            raise HTTPError(404, "sandbox: no ai_draft.json")
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(draft)}]}
    return NOT_HANDLED


def _http(method: str, path: str, params: dict, body: dict):
    """Jira, Microsoft Graph, Google Drive, MLflow ... -> sandbox/http.yaml, keyed by URL path.

    A route is a canned response, or {by_param: name, responses: {value: response}, default: ...}
    (also by_body for POST bodies). Unknown routes are a 404: the sandbox never calls a real service.
    """
    from .collectors.http import HTTPError
    routes = _load("http.yaml") or {}
    route = routes.get(f"{method} {path}", routes.get(path))
    if route is None:
        raise HTTPError(404, f"sandbox: no route for {method} {path} in sandbox/http.yaml")
    if isinstance(route, dict) and ("by_param" in route or "by_body" in route):
        src = params if "by_param" in route else body
        value = src.get(route.get("by_param") or route.get("by_body"))
        value = value[0] if isinstance(value, (list, tuple)) else value
        return route.get("responses", {}).get(str(value), route.get("default", {}))
    return route


def _drata(path: str, params: dict):
    from .collectors.http import HTTPError
    routes = _load("drata.yaml") or {}
    key = path.split("/public/v2", 1)[-1] or "/"
    route = routes.get(key)
    if route is None:
        raise HTTPError(404, f"sandbox: no Drata route for {key}")
    if isinstance(route, dict) and "by_param" in route:
        value = params.get(route["by_param"])
        value = value[0] if isinstance(value, (list, tuple)) else value
        return route["responses"].get(str(value), route.get("default", {"data": [], "pagination": {}}))
    if isinstance(route, dict) and "pages" in route:  # simulate cursor pagination
        pages = route["pages"]
        idx = int(params.get("cursor") or 0)
        nxt = str(idx + 1) if idx + 1 < len(pages) else None
        return {"data": pages[idx], "pagination": {"cursor": nxt, "totalCount": sum(len(p) for p in pages)}}
    return route


# ------------------------------------------------------------------ clouds
class _FakeAWS:
    def __init__(self, service: str, data: dict):
        self.service, self.data = service, data

    # CloudTrail
    def describe_trails(self, includeShadowTrails=False):
        return {"trailList": self.data.get("cloudtrail", {}).get("trails", [])}

    def get_trail_status(self, Name):
        return self.data.get("cloudtrail", {}).get("status", {}).get(Name, {"IsLogging": False})

    # S3
    def _bucket(self, Bucket):
        b = self.data.get("s3", {}).get(Bucket)
        if b is None:
            raise RuntimeError(f"NoSuchBucket: {Bucket}")
        return b

    def get_bucket_encryption(self, Bucket):
        alg = self._bucket(Bucket).get("encryption")
        if not alg:
            raise RuntimeError("ServerSideEncryptionConfigurationNotFoundError")
        return {"ServerSideEncryptionConfiguration": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": alg}}]}}

    def get_bucket_versioning(self, Bucket):
        return {"Status": self._bucket(Bucket).get("versioning", "Disabled")}

    def get_public_access_block(self, Bucket):
        return {"PublicAccessBlockConfiguration": self._bucket(Bucket).get("public_access_block", {})}

    # SageMaker Model Registry
    def list_model_packages(self, ModelPackageGroupName, **kw):
        groups = self.data.get("sagemaker", {}).get("groups", {})
        if ModelPackageGroupName not in groups:
            raise RuntimeError(f"ResourceNotFound: {ModelPackageGroupName}")
        return {"ModelPackageSummaryList": [{k: v for k, v in p.items() if k in (
            "ModelPackageArn", "ModelPackageVersion", "ModelApprovalStatus", "CreationTime")} for p in groups[ModelPackageGroupName]]}

    def describe_model_package(self, ModelPackageName):
        for pkgs in self.data.get("sagemaker", {}).get("groups", {}).values():
            for p in pkgs:
                if p.get("ModelPackageArn") == ModelPackageName:
                    return p
        raise RuntimeError(f"ResourceNotFound: {ModelPackageName}")

    # CloudWatch Logs
    def describe_log_groups(self, logGroupNamePrefix="", nextToken=None):
        groups = [g for g in self.data.get("logs", {}).get("log_groups", []) if g["logGroupName"].startswith(logGroupNamePrefix)]
        return {"logGroups": groups}


def _install_cloud_fakes() -> None:
    from .collectors import cloud
    aws = _load("aws.yaml")
    if aws is not None:
        cloud._aws_factory = lambda service, region: _FakeAWS(service, aws)
    cli = _load("cli.yaml")
    if cli is not None:
        def run(argv):
            joined = " ".join(argv)
            for prefix, response in cli.items():
                if joined.startswith(prefix):
                    return response
            from .collectors.base import MissingCredentials
            raise MissingCredentials(f"sandbox: no CLI fixture for '{joined[:60]}'")
        cloud._cli_runner = run


def _uninstall_cloud_fakes() -> None:
    from .collectors import cloud
    cloud._aws_factory = None
    cloud._cli_runner = None
