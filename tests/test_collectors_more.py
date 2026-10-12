"""Jira, SharePoint, Google Drive, SageMaker and MLflow collectors with faked APIs."""
import datetime as dt
import json
import shutil
from pathlib import Path

import yaml

from grc import collect, sandbox
from grc.collectors import cloud, http
from grc.collectors.base import parse_time, run_check
from grc.model import load
from tests.test_collectors import FakeHTTP, patched

NOW = dt.datetime.now(dt.timezone.utc)


def ago(days):
    return (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def iso(days):
    return (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- Jira
def _issue(key, created, resolved=None, done=False, assignee=True, approval="yes"):
    return {"key": key, "fields": {"summary": key, "created": ago(created), "resolutiondate": ago(resolved) if resolved is not None else None,
                                   "status": {"name": "Done" if done else "Open", "statusCategory": {"key": "done" if done else "new"}},
                                   "assignee": {"displayName": "A"} if assignee else None, "customfield_10050": approval}}


def test_jira_issues_rules_and_pagination():
    pages = [{"issues": [_issue("AI-1", 40, 30, done=True), _issue("AI-2", 50)], "nextPageToken": "p2"},
             {"issues": [_issue("AI-3", 5, assignee=False, approval=None), _issue("AI-4", 30, 1, done=True)], "isLast": True}]
    bodies = []

    def search(url, params):
        return pages[1] if bodies and bodies[-1].get("nextPageToken") else pages[0]

    fake = FakeHTTP({"/rest/api/3/search/jql": search})
    orig = fake.__call__

    class Capture(FakeHTTP):
        def __call__(self, method, url, headers=None, params=None, body=None, **kw):
            bodies.append(body or {})
            assert method == "POST" and headers["Authorization"].startswith("Basic ")
            return super().__call__(method, url, headers, params, body)
    cap = Capture(fake.routes)
    restore = patched(cap, {"JIRA_BASE_URL": "https://acme.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"})
    try:
        r = run_check("jira.issues", {"jql": "project = AI AND type = Incident", "min_count": 1, "max_open_age_days": 14,
                                      "require_assignee": True, "require_fields": ["customfield_10050"],
                                      "resolved_within_days": 20})
        assert r.details["items"] == ["AI-1", "AI-2", "AI-3", "AI-4"] and r.details["open"] == 2
        text = " | ".join(r.findings)
        assert "older than 14 days: AI-2" in text and "without an assignee: AI-3" in text
        assert "empty 'customfield_10050': AI-3" in text and "more than 20 days: AI-4" in text
        assert r.result == "fail" and bodies[1]["nextPageToken"] == "p2"
        ok = run_check("jira.issues", {"jql": "x"})
        assert ok.result == "pass"
    finally:
        restore()


def test_jira_missing_credentials_skip():
    import os
    saved = {k: os.environ.pop(k, None) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")}
    try:
        assert run_check("jira.issues", {"jql": "x"}).result == "skipped"
    finally:
        os.environ.update({k: v for k, v in saved.items() if v})


# ---------------------------------------------------------------- SharePoint
def test_sharepoint_documents():
    fake = FakeHTTP({
        "login.microsoftonline.com": {"access_token": "tok"},
        "/sites/acme.sharepoint.com:/sites/AIMS": {"id": "site1"},
        "/sites/site1/drives": {"value": [{"id": "d1", "name": "Documents"}]},
        "/drives/d1/root:/Policies:/children": {"value": [
            {"id": "f1", "name": "AI Policy v3.docx", "file": {}, "lastModifiedDateTime": iso(10), "webUrl": "https://x/1"},
            {"id": "f2", "name": "Data Procedure.docx", "file": {}, "lastModifiedDateTime": iso(500), "webUrl": "https://x/2"},
            {"id": "fo", "name": "Archive", "folder": {}}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/page2"},
        "/page2": {"value": [{"id": "f3", "name": "Impact Procedure.docx", "file": {}, "lastModifiedDateTime": iso(3)}]},
        "/items/f1/versions": {"value": [{"id": "3.0"}]},
        "/items/f2/versions": {"value": [{"id": "1.2"}]},
        "/items/f3/versions": {"value": [{"id": "2.0"}]},
    })
    restore = patched(fake, {"MS_TENANT_ID": "t", "MS_CLIENT_ID": "c", "MS_CLIENT_SECRET": "s"})
    try:
        r = run_check("sharepoint.documents", {"site": "acme.sharepoint.com:/sites/AIMS", "folder": "Policies",
                                               "names": ["AI Policy", "Data Procedure", "Impact", "Retention"],
                                               "max_age_days": 365, "require_major_version": True})
        text = " | ".join(r.findings)
        assert r.result == "fail" and "'Retention'" in text and "Data Procedure.docx' last changed" in text
        assert "1.2 is a draft" in text and "AI Policy" not in text
        assert sorted(r.details["items"]) == ["AI Policy v3.docx", "Data Procedure.docx", "Impact Procedure.docx"]
        r = run_check("sharepoint.documents", {"site": "acme.sharepoint.com:/sites/AIMS", "library": "Nope"})
        assert r.result == "fail" and "not found" in r.findings[0]
    finally:
        restore()


# ---------------------------------------------------------------- Google Drive
def test_gdrive_documents_in_sandbox(tmp_path):
    (tmp_path / "sandbox").mkdir()
    (tmp_path / "sandbox" / "http.yaml").write_text(yaml.safe_dump({"/drive/v3/files": {"files": [
        {"name": "AI Policy", "mimeType": "application/vnd.google-apps.document", "modifiedTime": iso(20)},
        {"name": "Sub", "mimeType": "application/vnd.google-apps.folder", "modifiedTime": iso(1)}]}}))
    sandbox._DIR = tmp_path / "sandbox"
    try:
        r = run_check("gdrive.documents", {"folder_id": "abc123", "names": ["AI Policy"], "max_age_days": 30})
        assert r.result == "pass" and r.details["items"] == ["AI Policy"]
        assert run_check("gdrive.documents", {"folder_id": "x' or 1=1", "names": []}).result == "fail"
        # unknown routes never reach a real service in sandbox mode
        assert run_check("jira.issues", {"jql": "x"}).result == "error"
    finally:
        sandbox._DIR = None


# ---------------------------------------------------------------- SageMaker
class FakeSM:
    def __init__(self, groups):
        self.groups = groups

    def list_model_packages(self, ModelPackageGroupName, **kw):
        if ModelPackageGroupName not in self.groups:
            raise RuntimeError("ResourceNotFound")
        return {"ModelPackageSummaryList": self.groups[ModelPackageGroupName]}

    def describe_model_package(self, ModelPackageName):
        for ps in self.groups.values():
            for p in ps:
                if p["ModelPackageArn"] == ModelPackageName:
                    return p


def test_sagemaker_model_registry():
    pkg = lambda g, v, st, days, cb="alice", ab="bob", card=True: {
        "ModelPackageArn": f"arn:{g}/{v}", "ModelPackageVersion": v, "ModelApprovalStatus": st,
        "CreationTime": NOW - dt.timedelta(days=days), "CreatedBy": {"UserProfileName": cb},
        "LastModifiedBy": {"UserProfileName": ab}, **({"ModelCard": {"ModelCardStatus": "Approved"}} if card else {})}
    sm = FakeSM({"triage": [pkg("triage", 3, "PendingManualApproval", 45), pkg("triage", 2, "Approved", 60, ab="alice")],
                 "readmit": [pkg("readmit", 5, "Approved", 10, card=False)]})
    cloud._aws_factory = lambda service, region: sm
    try:
        r = run_check("aws.sagemaker_model_registry", {"groups": ["triage", "readmit", "missing"], "max_pending_days": 30,
                                                        "require_independent_approval": True, "require_model_card": True})
        text = " | ".join(r.findings)
        assert "'triage' latest version 3 is PendingManualApproval" in text and "pending approval for more than 30" in text
        assert "created by alice, approved by alice" in text and "'readmit' v5 is approved without a model card" in text
        assert "'missing' could not be read" in text
        assert r.details["items"] == ["triage/v2", "readmit/v5"]
    finally:
        cloud._aws_factory = None


# ---------------------------------------------------------------- MLflow
def test_mlflow_models():
    fake = FakeHTTP({
        "/registered-models/get": lambda url, params: {"registered_model": {
            "triage": {"name": "triage", "description": "Triage", "tags": [{"key": "model_card", "value": "s3://x"}],
                       "aliases": [{"alias": "champion", "version": "4"}]},
            "readmit": {"name": "readmit", "description": "", "tags": [], "aliases": []}}[params["name"]]},
        "/model-versions/search": lambda url, params: {"model_versions": [
            {"version": "4", "user_id": "alice", "creation_timestamp": 1760000000000,
             "tags": [{"key": "validation_report", "value": "r"}, {"key": "approved_by", "value": "Alice"}]},
            {"version": "3", "user_id": "bob", "creation_timestamp": 1750000000000, "tags": []}]
            if "triage" in params["filter"] else []},
    })
    restore = patched(fake, {"MLFLOW_TRACKING_URI": "https://mlflow.acme", "MLFLOW_TRACKING_TOKEN": "t"})
    try:
        r = run_check("mlflow.models", {"models": ["triage", "readmit"], "require_model_tags": ["model_card"],
                                        "require_version_tags": ["validation_report"], "approver_tag": "approved_by"})
        text = " | ".join(r.findings)
        assert "'triage' v4 (production) is not shown to be approved by someone other than its creator" in text
        assert "'readmit' has no description" in text and "'readmit' lacks tag 'model_card'" in text
        assert "'readmit' has no production version" in text and r.details["items"] == ["triage/v4"]
        assert "filter" in fake.calls[1][1] and fake.calls[1][1]["filter"] == "name='triage'"
    finally:
        restore()


# ---------------------------------------------------------------- end to end through collect
def test_new_collectors_feed_audit_populations(tmp_path):
    """Snapshot `items` become the population an internal audit samples from."""
    edir = tmp_path / "engagement"
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "engagement", edir)
    (edir / "collectors.yaml").write_text(yaml.safe_dump({"enabled": True, "checks": [
        {"evidence": "EV-150", "title": "AI incidents", "collector": "jira.issues", "type": "record",
         "params": {"jql": "project = AI"}, "supports": ["A.8.4:evidenced"]}]}))
    fake = FakeHTTP({"/rest/api/3/search/jql": {"issues": [_issue("AI-1", 3, 1, done=True), _issue("AI-2", 2)], "isLast": True}})
    restore = patched(fake, {"JIRA_BASE_URL": "https://acme.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"})
    try:
        results, _ = collect.run(load(edir), write=True)
    finally:
        restore()
    assert results[0]["result"] == "pass"
    snap = json.loads((edir / "evidence" / "collected" / "EV-150.json").read_text())
    assert snap["details"]["items"] == ["AI-1", "AI-2"]
    from grc import audit
    pops = audit._collector_populations(load(edir))
    assert pops.get("A.8.4") == ["EV-150"]


def test_parse_time_formats():
    assert parse_time("2026-10-01T10:00:00.000+0000").tzinfo is not None
    assert parse_time("2026-10-01T10:00:00.1234567Z").microsecond == 123456
    assert parse_time(1760000000000).year == 2025


# ---------------------------------------------------------------- review regressions
def test_sandbox_passes_github_enterprise_through(tmp_path):
    (tmp_path / "sb").mkdir()
    sandbox._DIR = tmp_path / "sb"
    try:
        assert sandbox.handle("GET", "https://ghe.acme.corp/api/v3/repos/o/r", None, None) is sandbox.NOT_HANDLED
        assert sandbox.handle("GET", "https://api.github.com/repos/o/r", None, None) is sandbox.NOT_HANDLED
        try:
            sandbox.handle("GET", "https://graph.microsoft.com/v1.0/sites/x", None, None)
            raise AssertionError
        except http.HTTPError as exc:
            assert exc.status == 404
    finally:
        sandbox._DIR = None


def test_jira_paging_terminates():
    fake = FakeHTTP({"/search/jql": {"issues": [], "nextPageToken": "same"}})
    restore = patched(fake, {"JIRA_BASE_URL": "https://acme.atlassian.net", "JIRA_EMAIL": "a", "JIRA_API_TOKEN": "t"})
    try:
        r = run_check("jira.issues", {"jql": "x"})
        assert r.result == "pass" and len(fake.calls) == 1 and not r.details["truncated"]
        fake.routes["/search/jql"] = {"issues": [_issue("AI-1", 1)], "nextPageToken": "same"}
        fake.calls.clear()
        r = run_check("jira.issues", {"jql": "x"})
        assert len(fake.calls) == 2
    finally:
        restore()


def test_mlflow_stage_only_and_paging():
    pages = {None: {"model_versions": [{"version": str(i), "current_stage": "None", "user_id": "a", "tags": []} for i in range(200)],
                    "next_page_token": "p2"},
             "p2": {"model_versions": [{"version": "201", "current_stage": "Production", "user_id": "a",
                                        "creation_timestamp": "1760000000000", "tags": []}]}}
    fake = FakeHTTP({"/registered-models/get": {"registered_model": {"name": "m", "description": "d", "aliases": []}},
                     "/model-versions/search": lambda url, params: pages[params.get("page_token")]})
    restore = patched(fake, {"MLFLOW_TRACKING_URI": "https://mlflow.acme", "MLFLOW_TRACKING_TOKEN": "t"})
    try:
        r = run_check("mlflow.models", {"models": ["m"], "production_stage": "Production"})
        assert r.result == "pass", r.findings
        assert r.details["items"] == ["m/v201"]
    finally:
        restore()


def test_sharepoint_missing_site_is_a_finding_and_epoch_strings_parse():
    fake = FakeHTTP({"login.microsoftonline.com": {"access_token": "tok"}})
    restore = patched(fake, {"MS_TENANT_ID": "t", "MS_CLIENT_ID": "c", "MS_CLIENT_SECRET": "s"})
    try:
        r = run_check("sharepoint.documents", {"site": "acme.sharepoint.com:/sites/AI Governance", "names": ["x"]})
        assert r.result == "fail" and "not found" in r.findings[0]
    finally:
        restore()
    assert parse_time("1760000000000").year == 2025
