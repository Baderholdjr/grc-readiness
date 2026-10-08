"""Collectors with faked APIs: results, snapshots, and their effect on readiness rules."""
import datetime as dt
import json
import shutil
from pathlib import Path

import yaml

from grc import collect
from grc.collectors import cloud, http
from grc.collectors.base import run_check
from grc.model import load
from grc.rules import validate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "engagement"
NOW = dt.datetime(2026, 10, 8, 12, 0, tzinfo=dt.timezone.utc)


class FakeHTTP:
    """Route GET URLs (by substring) to canned JSON."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, params=None, body=None, **kw):
        self.calls.append((url, params))
        for key, val in self.routes.items():
            if key in url:
                return val(url, params) if callable(val) else val
        raise http.HTTPError(404, url)


def patched(fake, env):
    import os
    saved_req, saved_env = http.request, {k: os.environ.get(k) for k in env}
    http.request = fake
    os.environ.update(env)

    def restore():
        http.request = saved_req
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


def test_branch_protection_from_rulesets():
    fake = FakeHTTP({"/rules/branches/main": [
        {"type": "pull_request", "parameters": {"required_approving_review_count": 1, "require_code_owner_review": True}},
        {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "validate"}]}},
        {"type": "non_fast_forward"}]})
    restore = patched(fake, {"GH_COLLECTOR_TOKEN": "x"})
    try:
        r = run_check("github.branch_protection", {"repo": "o/r", "required_checks": ["validate"], "require_code_owner_review": True})
        assert r.result == "pass", r.findings
        r = run_check("github.branch_protection", {"repo": "o/r", "required_checks": ["release-gate"]})
        assert r.result == "fail" and "release-gate" in r.findings[0]
    finally:
        restore()


def test_pr_reviews_flags_self_merged():
    recent = "2026-10-01T00:00:00Z"
    prs = [{"number": 1, "merged_at": recent, "updated_at": recent, "user": {"login": "a"}, "labels": []},
           {"number": 2, "merged_at": recent, "updated_at": recent, "user": {"login": "a"}, "labels": []}]
    fake = FakeHTTP({"/pulls/1/reviews": [{"state": "APPROVED", "user": {"login": "b"}}],
                     "/pulls/2/reviews": [{"state": "APPROVED", "user": {"login": "a"}}],
                     "/pulls": lambda u, p: prs if p.get("page") == 1 else []})
    restore = patched(fake, {"GH_COLLECTOR_TOKEN": "x"})
    try:
        import grc.collectors.github as g
        saved = g.utcnow
        g.utcnow = lambda: NOW
        r = run_check("github.pr_reviews", {"repo": "o/r"})
        g.utcnow = saved
        assert r.result == "fail" and r.details["unapproved_prs"] == [2]
    finally:
        restore()


def test_missing_credentials_skip():
    import os
    os.environ.pop("DRATA_API_KEY", None)
    assert run_check("drata.policies", {"names": ["AI Policy"]}).result == "skipped"


def test_drata_policies_and_pagination():
    pages = {None: {"data": [{"name": "AI Policy", "approvedAt": "2026-09-01", "renewalDate": "2027-09-01", "version": 1}],
                    "pagination": {"cursor": "c2"}},
             "c2": {"data": [{"name": "Vendor Management Policy", "approvedAt": None, "renewalDate": "2026-01-01"}],
                    "pagination": {"cursor": None}}}
    fake = FakeHTTP({"/policies": lambda u, p: pages[p.get("cursor")]})
    restore = patched(fake, {"DRATA_API_KEY": "k"})
    try:
        r = run_check("drata.policies", {"names": ["AI Policy", "Vendor Management", "Incident"]})
        assert r.result == "fail"
        text = " ".join(r.findings)
        assert "no approval date" in text and "Incident" in text and "renewal was due" in text
        assert len(fake.calls) == 2  # followed the cursor
    finally:
        restore()


def test_aws_s3_bucket_with_fake_client():
    class S3:
        def get_bucket_encryption(self, Bucket):
            return {"ServerSideEncryptionConfiguration": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]}}
        def get_bucket_versioning(self, Bucket):
            return {"Status": "Suspended"}
        def get_public_access_block(self, Bucket):
            return {"PublicAccessBlockConfiguration": dict.fromkeys(
                ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"], True)}
    cloud._aws_factory = lambda svc, region: S3()
    try:
        r = run_check("aws.s3_bucket", {"bucket": "b"})
        assert r.result == "fail" and r.findings == ["versioning is Suspended"]
    finally:
        cloud._aws_factory = None


def test_gcp_bucket_with_fake_cli():
    cloud._cli_runner = lambda argv: {"uniform_bucket_level_access": True, "versioning_enabled": True,
                                      "public_access_prevention": "enforced"}
    try:
        assert run_check("gcp.bucket", {"bucket": "b"}).result == "pass"
    finally:
        cloud._cli_runner = None


def _engagement_with_collector(tmp_path, result_bool):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    (edir / "collectors.yaml").write_text(yaml.safe_dump({"enabled": True, "checks": [
        {"evidence": "EV-150", "title": "Gate runs", "collector": "github.workflow_runs",
         "params": {"repo": "o/r", "workflow": "gate.yml"}, "type": "record", "requirements": ["A.6.2.6"]}]}))
    # A.6.2.6 implemented is verified on EV-012 only; make it rely on EV-150 only
    p = edir / "controls" / "A.6.2.6.yaml"
    c = yaml.safe_load(p.read_text())
    c["test"]["implemented"]["evidence"] = ["EV-150"]
    p.write_text(yaml.safe_dump(c, sort_keys=False))
    run = {"conclusion": "success" if result_bool else "failure", "html_url": "u", "head_sha": "s"}
    fake = FakeHTTP({"/actions/workflows/gate.yml/runs": {"workflow_runs": [run]}})
    return edir, fake


def test_collect_writes_snapshot_and_failure_downgrades_verified_leg(tmp_path):
    edir, fake = _engagement_with_collector(tmp_path, result_bool=True)
    restore = patched(fake, {"GH_COLLECTOR_TOKEN": "x"})
    try:
        results, report = collect.run(load(edir, today=NOW.date()), now=NOW)
        assert results[0]["result"] == "pass"
        snap = json.loads((edir / "evidence" / "collected" / "EV-150.json").read_text())
        assert snap["result"] == "pass" and len(snap["sha256"]) == 64
        assert "A.6.2.6·implemented" in report
        assert not [f for f in validate(load(edir, today=NOW.date())) if f.severity == "error"]

        # next run: the gate starts failing
        fake.routes["/actions/workflows/gate.yml/runs"] = {"workflow_runs": [{"conclusion": "failure"}]}
        results, report = collect.run(load(edir, today=NOW.date()), now=NOW)
        assert results[0]["result"] == "fail" and "regressed" in report
        codes = {f.code for f in validate(load(edir, today=NOW.date()))}
        assert "E015" in codes and "W108" in codes
    finally:
        restore()


def test_collect_disabled(tmp_path):
    edir = tmp_path / "engagement"
    shutil.copytree(FIXTURE, edir)
    results, report = collect.run(load(edir))
    assert results == [] and "disabled" in report


def test_env_expansion():
    import os
    os.environ["GITHUB_REPOSITORY"] = "me/repo"
    assert collect.expand({"repo": "${GITHUB_REPOSITORY}", "x": ["${NOPE_NOT_SET}"]}) == \
        {"repo": "me/repo", "x": ["${NOPE_NOT_SET}"]}
