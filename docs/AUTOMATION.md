# Automation setup

Two automations keep the engagement record current without hand-editing:

| | What it does | Trigger | Output |
|---|---|---|---|
| **Ingest** (`ingest.yml`) | Drafts engagement data from client documents uploaded to `intake/` | A PR that adds or changes files in `intake/` | A commit on that PR, plus a report comment |
| **Collect** (`collect.yml`) | Pulls fresh evidence from GitHub, Drata and the cloud | Daily, or **Actions → Collect evidence → Run workflow** | A rolling **Evidence refresh** PR |

Both only *propose* changes. A person merges every PR, and nothing automated can mark a control `verified`.

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

## How collected evidence affects readiness

- Each check writes a snapshot to `engagement/evidence/collected/<ID>.json`. The snapshot holds metadata only (settings, counts, IDs) plus a SHA-256 hash. It also writes an index entry to `engagement/evidence/collected.yaml`, which is machine-owned. Humans keep editing `evidence/index.yaml`.
- Evidence from collectors expires after `valid_for_days` (default 30), so a control kept `verified` on collected evidence needs the daily refresh to keep passing.
- If a check **fails**, its evidence stops counting. Any leg marked `verified` only on that evidence fails CI (E015) until the problem is fixed. Failing checks also show as warnings (W108).
- The refresh PR lists **regressions** (passed before, fails now) and **passing evidence not yet cited**, with the requirements it could support. An analyst then cites it in the control files through a normal PR.

## Required check on automated PRs

GitHub doesn't start workflows for PRs or pushes made with the built-in token. So both automations start the `validate` check explicitly on their branch, which keeps your branch protection's required check satisfied. If you'd rather have it trigger natively, use a GitHub App token for the automation's pushes.
