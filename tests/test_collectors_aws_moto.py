"""The AWS collectors against moto's simulated AWS: the real boto3 calls, request shapes and pagination, with no
AWS account. moto is a dev dependency (grc/resources/locks/dev.txt), so these run in CI; they are skipped where
moto isn't installed."""
import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from grc.collectors import cloud  # noqa: E402  (registers the collectors)
from grc.collectors.base import FAIL, PASS, SKIPPED, run_check  # noqa: E402

REGION = "us-east-1"


@pytest.fixture
def aws(monkeypatch):
    # fictional credentials that only moto sees; nothing here can reach a real account
    for k, v in {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_SESSION_TOKEN": "testing",
                 "AWS_DEFAULT_REGION": REGION, "AWS_EC2_METADATA_DISABLED": "true"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(cloud, "_aws_factory", None)
    with moto.mock_aws():
        yield


def test_cloudtrail_logging_multi_region_trail_passes(aws):
    boto3.client("s3", region_name=REGION).create_bucket(Bucket="larch-trail-logs")
    ct = boto3.client("cloudtrail", region_name=REGION)
    ct.create_trail(Name="org-trail", S3BucketName="larch-trail-logs", IsMultiRegionTrail=True,
                    EnableLogFileValidation=True)
    r = run_check("aws.cloudtrail", {"region": REGION})
    assert r.result == FAIL and "no logging multi-region CloudTrail trail" in r.findings[0]   # created, not started
    ct.start_logging(Name="org-trail")
    r = run_check("aws.cloudtrail", {"region": REGION})
    assert r.result == PASS, r.findings
    assert r.details["trails"] == [{"name": "org-trail", "multi_region": True, "logging": True, "log_validation": True}]


def test_cloudtrail_single_region_trail(aws):
    boto3.client("s3", region_name=REGION).create_bucket(Bucket="larch-trail-logs")
    ct = boto3.client("cloudtrail", region_name=REGION)
    ct.create_trail(Name="one-region", S3BucketName="larch-trail-logs")
    ct.start_logging(Name="one-region")
    assert run_check("aws.cloudtrail", {"region": REGION}).result == FAIL
    assert run_check("aws.cloudtrail", {"region": REGION, "require_multi_region": False}).result == PASS


def test_s3_bucket_hardened_and_not(aws):
    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket="larch-models")
    s3.put_bucket_encryption(Bucket="larch-models", ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]})
    s3.put_bucket_versioning(Bucket="larch-models", VersioningConfiguration={"Status": "Enabled"})
    s3.put_public_access_block(Bucket="larch-models", PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    r = run_check("aws.s3_bucket", {"bucket": "larch-models", "region": REGION})
    assert r.result == PASS, r.findings
    assert r.details["encryption"] == ["aws:kms"] and r.details["versioning"] == "Enabled"

    s3.create_bucket(Bucket="larch-scratch")
    r = run_check("aws.s3_bucket", {"bucket": "larch-scratch", "region": REGION})
    text = " | ".join(r.findings)
    assert r.result == FAIL and "versioning is Disabled" in text and "public access block not fully enabled" in text

    s3.put_public_access_block(Bucket="larch-scratch", PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": False, "RestrictPublicBuckets": True})
    r = run_check("aws.s3_bucket", {"bucket": "larch-scratch", "region": REGION, "require": ["public_access_block"]})
    assert r.findings == ["public access block not fully enabled: BlockPublicPolicy"]


def test_log_retention_follows_every_page(aws):
    logs = boto3.client("logs", region_name=REGION)
    for i in range(60):                      # more than one page of describe_log_groups (50)
        logs.create_log_group(logGroupName=f"/ai/triage/{i:02d}")
        logs.put_retention_policy(logGroupName=f"/ai/triage/{i:02d}", retentionInDays=400)
    logs.put_retention_policy(logGroupName="/ai/triage/59", retentionInDays=30)
    logs.create_log_group(logGroupName="/other/app")
    r = run_check("aws.log_retention", {"prefix": "/ai/", "min_days": 365, "region": REGION})
    assert len(r.details["log_groups"]) == 60
    assert r.result == FAIL and r.findings == ["1 log group(s) retain < 365 days: /ai/triage/59"]
    logs.put_retention_policy(logGroupName="/ai/triage/59", retentionInDays=731)
    assert run_check("aws.log_retention", {"prefix": "/ai/", "region": REGION}).result == PASS
    r = run_check("aws.log_retention", {"prefix": "/missing/", "region": REGION})
    assert r.findings == ["no log groups with prefix '/missing/'"]


def test_sagemaker_registry_latest_version_must_be_approved(aws):
    sm = boto3.client("sagemaker", region_name=REGION)
    sm.create_model_package_group(ModelPackageGroupName="triage")
    sm.create_model_package(ModelPackageGroupName="triage", ModelApprovalStatus="Approved")
    sm.create_model_package(ModelPackageGroupName="triage", ModelApprovalStatus="PendingManualApproval")
    r = run_check("aws.sagemaker_model_registry", {"groups": ["triage"], "region": REGION})
    assert r.result == FAIL
    assert any("'triage' latest version 2 is PendingManualApproval" in f for f in r.findings), r.findings
    assert r.details["items"] == ["triage/v1"]


def test_no_credentials_means_skipped_not_failed(monkeypatch, tmp_path):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE",
              "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_ROLE_ARN", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
              "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(cloud, "_aws_factory", None)
    r = run_check("aws.cloudtrail", {"region": REGION})
    assert r.result == SKIPPED and "no AWS credentials" in r.summary
