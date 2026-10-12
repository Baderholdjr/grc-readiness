# Automation setup

Two automations keep the engagement record current without hand-editing:

| | What it does | Trigger | Output |
|---|---|---|---|
| **Ingest** (`ingest.yml`) | Drafts engagement data from client documents uploaded to `intake/` | A PR that adds or changes files in `intake/` | A commit on that PR, plus a report comment |
| **Collect** (`collect.yml`) | Pulls fresh evidence from GitHub, Drata and the cloud | Daily, or **Actions → Collect evidence → Run workflow** | A rolling **Evidence refresh** PR |

Both only *propose* changes. A person merges every PR, and nothing automated can mark a control `verified`.

**One-time repository setting:** go to **Settings → Actions → General → Workflow permissions** and tick **Allow GitHub Actions to create and approve pull requests**. Without it, the collector can't open its refresh PR.

All credentials go in the repo under **Settings → Secrets and variables → Actions**. Anything that isn't configured is skipped, never failed. You can turn things on one at a time.

---

## 1. Document ingestion

1. **Spreadsheet templates (no AI).** These work with no setup. Send the client the files in `templates/intake/`. Uploaded CSV or XLSX files with those headers are imported exactly as written.
2. **AI drafting.** This is for any Word, PDF, Excel, Markdown or text document.
   - Get the client's agreement first. Document text is sent to the Anthropic API.
   - Add a **secret** named `ANTHROPIC_API_KEY` (from console.anthropic.com).
   - In `engagement/engagement.yaml`, set:
     ```yaml
     ingest:
       ai_drafting: true
       model: claude-sonnet-5-5   # or claude-opus-5-5 for harder documents
     ```
3. **Use it.** Go to **Add file → Upload files** and upload into `intake/`. Choose **Create a new branch** and start a pull request. Within a couple of minutes, the PR gets a drafted commit and a report comment with:
   - new gaps, evidence pointers, inventory items and claims
   - **open questions** for the analyst
   - anything that was dropped or left unchanged

**What ingestion will and won't do:**
- Fills `client.overview`, `ai_usage`, `scope.statement` and `in_place` only if they're empty. Otherwise it lists them as suggestions in the report.
- Adds gaps, evidence pointers and inventory items with new IDs. It skips near-duplicates of existing items.
- Moves a control leg from `not_started` to `claimed` when a document says the control exists. It never touches a leg that's already `partial` or `verified`, and it never sets `verified`.
- Drops anything without a source citation, or that uses a requirement ID not in the catalog.
- Records each processed file and its hash in `intake/.processed.yaml`. Uploading a changed version re-reads it.

---

## 2. Evidence collection

Edit `engagement/collectors.yaml` to point the checks at the client's real repos, buckets, Drata policies and so on. Then add the credentials below. Use **read-only** access everywhere.

### GitHub (client repos)

Create a **secret** `GH_COLLECTOR_TOKEN`: a fine-grained personal access token, or better, a GitHub App token, that can read only the client's repositories. Repository permissions, all **Read-only**:

- Metadata
- Contents
- Pull requests
- Actions
- Administration (needed only to read classic branch protection; rulesets are readable without it)

The three self-checks (EV-101 to EV-103) use the workflow's own token and need nothing.

| Collector | Proves | Typical requirement |
|---|---|---|
| `github.branch_protection` | Required reviews, required checks, and blocked force pushes on a branch | A.6.2.5 |
| `github.pr_reviews` | Share of merged PRs independently approved, optionally filtered by label | A.6.2.5, A.6.2.4 |
| `github.workflow_runs` | A gate workflow runs regularly and passes | A.6.2.4, A.6.2.6 |
| `github.file_present` | A policy or config file exists; records its hash and last change | A.6.1.3 |

### Drata

Create a **secret** `DRATA_API_KEY` (a read-only API key from Drata). For a non-US region, add a **variable** `DRATA_API_BASE`. The default is `https://public-api.drata.com/public/v2`.

| Collector | Proves |
|---|---|
| `drata.policies` | Named policies exist, are approved, and are within renewal |
| `drata.risks` | The AI risk register is populated; every risk has an owner and a treatment |
| `drata.vendors` | AI suppliers are in the vendor program; reviews aren't overdue |
| `drata.training` | AI-awareness training completion rate (counts only, no names) |
| `drata.monitoring_tests` | Selected Drata monitoring tests are passing (needs `workspace_id`) |

### AWS (OIDC; no stored keys)

1. In the client's AWS account, create an IAM OIDC identity provider for `token.actions.githubusercontent.com`.
2. Create a role that this repo can assume. Restrict the trust policy's `sub` to `repo:<owner>/<repo>:ref:refs/heads/main`.
3. Attach this read-only policy:
   ```json
   {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Resource": "*", "Action": [
     "cloudtrail:DescribeTrails", "cloudtrail:GetTrailStatus",
     "s3:GetEncryptionConfiguration", "s3:GetBucketVersioning", "s3:GetBucketPublicAccessBlock",
     "logs:DescribeLogGroups"]}]}
   ```
4. Add **variables** `AWS_ROLE_ARN` and optionally `AWS_REGION`.

### Azure (OIDC)

Create an app registration with a federated credential for this repo's `main` branch, and grant it **Reader** on the subscription. Add **variables** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`. In `collectors.yaml`, set `enabled: true` on the Azure checks.

### Google Cloud (workload identity federation)

Create a workload identity pool and provider for GitHub, and a service account with `logging.sinks.list` and `storage.buckets.get` (a custom role, or Logging Viewer plus Storage Legacy Bucket Reader). Add **variables** `GCP_WORKLOAD_IDENTITY_PROVIDER` and `GCP_SERVICE_ACCOUNT`, then enable the GCP checks.

---

### Jira (incidents, changes, approvals, concerns)

Add **variables** `JIRA_BASE_URL` (e.g. `https://acme.atlassian.net`) and `JIRA_EMAIL` (a read-only user), and the **secret** `JIRA_API_TOKEN` (that user's API token). One collector, `jira.issues`, runs a JQL query and checks what the process promises:

```yaml
- evidence: EV-140
  title: AI incidents are assigned and resolved within 30 days
  collector: jira.issues
  type: record
  params:
    jql: 'project = AIOPS AND issuetype = "AI Incident" AND created >= -180d'
    min_count: 0
    require_assignee: true
    resolved_within_days: 30        # resolved tickets took longer -> fail
    max_open_age_days: 30           # open tickets older than this -> fail
    require_fields: [customfield_10050]   # e.g. an approval or root-cause field must be filled
  supports: ["A.8.4:evidenced"]
```

Use the same collector for model release approvals, change requests (6.3), reported concerns (A.3.3) or risk treatment tickets. The ticket keys become the population an internal audit samples from.

### SharePoint (Microsoft Graph)

Register an app with the **application** permission `Sites.Read.All` (or `Sites.Selected` scoped to the AIMS site) and admin consent. Add **variables** `MS_TENANT_ID`, `MS_CLIENT_ID` and the **secret** `MS_CLIENT_SECRET`.

```yaml
- evidence: EV-141
  title: Approved AI policies are published and current in SharePoint
  collector: sharepoint.documents
  type: document
  params:
    site: "acme.sharepoint.com:/sites/AIMS"
    library: Documents
    folder: Policies/AI
    names: ["AI Policy", "Impact Assessment Procedure"]
    max_age_days: 400
    require_major_version: true     # latest version must be published (3.0), not a draft (3.1)
```

### Google Drive

Uses the same GCP sign-in as the cloud checks (workload identity). Enable the **Google Drive API** in that project and share the folder (or the shared drive) with the service account as **Viewer**. Then `gdrive.documents` takes `folder_id`, `names` and `max_age_days`, like the SharePoint check; for a folder in a shared drive, add `drive_id`.

### Model registries

- **SageMaker Model Registry** (`aws.sagemaker_model_registry`) uses the AWS sign-in; the role needs `sagemaker:ListModelPackages` and `sagemaker:DescribeModelPackage`. For each model package group it checks the latest version is **Approved**, nothing has waited longer than `max_pending_days` for approval, and optionally that the approver differs from the creator (`require_independent_approval`, based on `CreatedBy` / `LastModifiedBy`, so sample the approvals in the audit as well; identities aren't stored in the snapshot, only whether they differ) and that a model card is attached (`require_model_card`).
- **MLflow** (`mlflow.models`, open source or Databricks): add the **variable** `MLFLOW_TRACKING_URI` (the server URL; for Databricks the workspace URL `https://….cloud.databricks.com`, not `databricks`) and either the **secret** `MLFLOW_TRACKING_TOKEN` or `MLFLOW_TRACKING_USERNAME` (variable) and `MLFLOW_TRACKING_PASSWORD` (secret). For each model it checks there is a description, the required model tags (e.g. `model_card`, `impact_assessment`), a production version (`production_alias`, e.g. `champion`, or a legacy `production_stage` such as `Production`; `champion` if neither is set), the required version tags on it (e.g. `validation_report`), and, with `approver_tag`, that the approver named in that tag isn't the version's creator.

```yaml
- evidence: EV-142
  title: Production models were validated and independently approved
  collector: aws.sagemaker_model_registry
  type: record
  params: {groups: [triage-chatbot, readmission-risk], max_pending_days: 14,
           require_independent_approval: true, require_model_card: true}
  supports: ["A.6.2.5:evidenced"]
```

Approved model versions become the audit population for release-approval testing.

## How collected evidence affects readiness

- Each check writes a snapshot to `engagement/evidence/collected/<ID>.json`. The snapshot holds metadata only (settings, counts, IDs) plus a SHA-256 hash. It also writes an index entry to `engagement/evidence/collected.yaml`, which is machine-owned. Humans keep editing `evidence/index.yaml`.
- Evidence from collectors expires after `valid_for_days` (default 30), so a control kept `verified` on collected evidence needs the daily refresh to keep passing.
- If a check **fails**, its evidence stops counting. Any leg marked `verified` only on that evidence fails CI (E015) until the problem is fixed. Failing checks also show as warnings (W108).
- The refresh PR lists **regressions** (passed before, fails now) and **passing evidence not yet cited**, with the requirements it could support. An analyst then cites it in the control files through a normal PR.

## Required check on automated PRs

GitHub doesn't start workflows for PRs or pushes made with the built-in token. So both automations start the `validate` check explicitly on their branch, which keeps your branch protection's required check satisfied. If you'd rather have it trigger natively, use a GitHub App token for the automation's pushes.

---

## Linking collected evidence to controls

Give each check a `supports` list of the control legs its evidence backs:

```yaml
  - evidence: EV-110
    collector: github.workflow_runs
    params: {repo: client-org/ml-release, workflow: release-gate.yml}
    supports: ["A.6.2.4:implemented", "A.6.2.4:evidenced"]
```

When the check passes, the refresh PR cites the evidence on those legs. It also moves `not_started` or `claimed` legs to `partial`, but only when the control has an owner. It never sets `verified`. Merging the refresh PR is the one click; confirming `verified` is still an analyst decision.

## Owners, assignments and reminders

`engagement/owners.yaml` maps the role names used in `owner:` fields to GitHub users:

```yaml
owners:
  - role: Head of Platform
    github: [alice, client-org/platform-team]
```

- **Issues:** gap Issues are assigned to the owner's users. Teams can't be assignees, and users without repo access are skipped with a note.
- **Reminders:** each day, an overdue gap gets one reminder comment mentioning its owners. There's one reminder per due date; moving the due date re-arms it.
- **Approvals:** `python -m grc codeowners` writes a managed block into `.github/CODEOWNERS`, so changes to a control file need its owner's approval.
- **Missing owners:** an owner name that isn't in `owners.yaml` triggers warning W111.

## Sandbox mode (no credentials)

```yaml
# engagement/engagement.yaml
sandbox:
  enabled: true
  dir: sandbox
```

| Service | Answered from |
|---|---|
| Drata | `sandbox/drata.yaml`: API path → response. Supports `pages:` for pagination and `by_param:` for filtered counts. |
| AWS | `sandbox/aws.yaml`: CloudTrail trails and status, S3 buckets, log groups |
| Azure / GCP | `sandbox/cli.yaml`: CLI command prefix → JSON output |
| AI drafting | `sandbox/ai_draft.json`: returned for any intake document. No document leaves GitHub. |

GitHub checks still run for real. Evidence, snapshots, PRs and reports produced in sandbox mode are all labelled `[SANDBOX]`. Turn the sandbox off once real credentials are in place.
