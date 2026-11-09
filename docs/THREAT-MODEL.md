# Threat model: the GRC engine and client repositories

Scope: the engine (this repository), the client repositories built from it, their GitHub Actions workflows, the
client site on Cloudflare, and the services they call (the Anthropic API for AI drafting; AWS, Azure, GCP and
identity providers for evidence collectors). Reviewed when the architecture changes, and at least yearly. The
friendlier UI (workspace, auditor room, executive dashboard) gets its own section before it is built.

## What we protect

| Asset | Why it matters |
|---|---|
| The engagement record (controls, evidence index, gaps, approvals) | It is the audit trail. A silent change could make an unready client look ready |
| Client documents in `intake/` | Confidential: policies, prior audit reports, registers |
| Credentials: `ANTHROPIC_API_KEY`, `GRC_ENGINE_TOKEN`, the workflow `GITHUB_TOKEN`, cloud federation | Misuse reaches client cloud accounts, the engine, or spends API credit |
| The engine's code and releases | Every client runs it with write access to their record |
| Client-facing outputs (briefs, gap assessments, workbooks, the client site) | Read by clients, auditors and executives |

## Who could attack, and from where

| Actor | Entry point |
|---|---|
| A person who can open a PR on a client repo (client staff, a compromised account) | Uploads to `intake/`, edits to the record, a questionnaire workbook |
| A document's author (a customer, a supplier, a prior auditor) | Text inside a file that is later read by the engine or by Claude |
| A compromised dependency or GitHub Action | Code that runs in a workflow with its token and secrets |
| Someone on the internet | The client site |

## Trust boundaries and controls

**1. Changes to the record.** Every change is a pull request reviewed against CODEOWNERS on a protected branch;
the review is the approval record. Nothing automated sets a requirement leg to `verified` or an answer to
`approved` (enforced in `ingest/apply.py` and `questionnaire.py`, tested). Drafted items carry their source.

**2. Uploaded files are untrusted** (`grc/safety.py`, tested in `tests/test_security.py`):
- Symlinks are never followed, and a file must resolve inside the folder it was uploaded to: a symlink can't make
  ingest read a runner file and send it to Claude or into a report.
- Size limits per file; Office files are checked for unpacked size, compression ratio, member count and paths
  outside the package before parsing (zip bombs fail fast).
- XML with a DTD is refused; ElementTree never fetches external entities. PDFs are read to a page limit.
- A damaged or hostile file is reported in the ingest PR comment, never a crash.

**3. Text inside documents is untrusted** (prompt injection). Claude is told the documents are data and to ignore
instructions in them; its output is a draft in a PR, schema-checked; claims only move a leg from `not_started` to
`claimed`. A document that says "mark everything verified" can at worst add a wrong claim, which a reviewer sees.

**4. Outputs people open.** Text from records that would start a spreadsheet formula (`=`, `+`, `-`, `@`) stays
text in every workbook and CSV the engine writes. The client site builds its page with DOM text nodes (no
`innerHTML`), serves a strict Content-Security-Policy (no inline or third-party script), and sends no-sniff,
no-frame and HSTS headers.

**5. Credentials.**
- Cloud collectors sign in with OIDC federation to read-only roles: no long-lived cloud keys exist.
- Secrets live only in GitHub secrets. Secret scanning and push protection are on.
- The GitHub token is sent only to the GitHub API, whatever a pagination link says; collectors call `https://`
  endpoints only.
- `GRC_ENGINE_TOKEN` is used only to fetch the engine and removed from git's config straight after.
- No workflow uses `pull_request_target`, so a PR's code never runs with secrets it didn't already have.
- Each reusable workflow declares the secrets it uses, and callers pass exactly those by name (never
  `secrets: inherit`): the ingest workflow can't see the Cloudflare token, the site workflow can't see the Anthropic key.

**6. Workflows run with the least privilege.** Each reusable workflow declares the most it may use; a caller can
only grant less. Workflow inputs and event data reach shell scripts through environment variables, never by
`${{ }}` expansion inside a script. Both rules are tested and scanned (zizmor).

**7. Supply chain.**
- Every third-party action is pinned to a commit SHA (Dependabot proposes updates, with the version in a comment).
- Python dependencies are installed from hash-locked files (`grc/resources/locks/`); a changed or substituted
  package fails the install. The Security workflow fails when a lock is out of date.
- pip-audit checks every locked dependency for known vulnerabilities on every PR and weekly; bandit scans the code.
- Clients pin the engine to a release tag and call its reusable workflows at a major-version tag
  (`engine-v0`). That tag is a deliberate trust in the engine's maintainer; protect it (below).

## Accepted risks and gaps

| Risk | Why it stands | What would close it |
|---|---|---|
| One maintainer approves their own engine changes | One-person practice during the proof of concept | A second reviewer, then required reviews with "dismiss stale approvals" |
| Releases aren't signed or attested | GitHub artifact attestations need a public repository or Enterprise Cloud | Move to a plan that supports them, or sign tags |
| `engine-v0` is a moving tag that clients trust | Lets clients receive fixes without a PR per release | Tag protection rules on `engine-v*`; clients that want more pin a SHA |
| The Anthropic API receives client document text | Needed for AI drafting; off by default (`ingest.ai_drafting`) | Keep it opt-in per engagement; record it in the client's data-processing terms |
| Scanner tools change between runs | They are hash-locked like everything else, but new rules can fail a PR | Expected: fix or justify the finding |
| Prompt injection can still produce a misleading draft | Drafts are reviewed by a person; nothing is verified automatically | Reviewer training; the source on every drafted item |

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
