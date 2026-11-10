# Threat model: the GRC engine and client repositories

Scope: the engine (this repository, public under the PolyForm Noncommercial license), the client repositories
(private) built from it, their GitHub Actions workflows, the
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
- Symlinks are never followed, and a file must resolve inside the folder (or repository) it was uploaded to: a
  symlink can't make ingest, the questionnaire import or the timesheet import read a runner file and send it to
  Claude or into a report.
- Size limits per file; Office files are checked for unpacked size, compression ratio, member count and paths
  outside the package before parsing (zip bombs fail fast).
- The questionnaire reader parses workbook XML itself and refuses any DTD or entity declaration, in any encoding
  (an expat pass before parsing). Ingest reads Office files through openpyxl and python-docx, whose parsers don't
  resolve entities or fetch external ones. PDFs are read to a page limit.
- A damaged or hostile file is reported in the ingest PR comment, never a crash.
- An OSCAL catalog or profile given to `grc oscal import` is JSON only (no XML parser is involved), size-limited,
  and must pass NIST's OSCAL 1.2.3 schema before anything is read from it; its text becomes requirement wording,
  which every report already treats as data.

**3. Text inside documents is untrusted** (prompt injection). Claude is told the documents are data and to ignore
instructions in them; its output is a draft in a PR, schema-checked; claims only move a leg from `not_started` to
`claimed`. A document that says "mark everything verified" can at worst add a wrong claim, which a reviewer sees.
Everything drafted or taken from a file name is made inert before it goes into the ingest PR comment: no links
or images (so nothing can leak through an image URL), no @mentions, no HTML (no hidden comments).

**4. Outputs people open, and outputs machines read.** Text from records that would start a spreadsheet formula (`=`, `+`, `-`, `@`) stays
text in every workbook and CSV the engine writes. The client site builds its page with DOM text nodes (no
`innerHTML`), serves a strict Content-Security-Policy (no inline or third-party script), and sends no-sniff,
no-frame and HSTS headers. The OSCAL export (`grc oscal export`, and `09-oscal/` in the auditor package) is
checked against NIST's schema before any file is written, and claims no more than the record: a requirement is
`satisfied` in the assessment results only when the record shows it Ready, and the results say they are the
client's readiness record, not an independent assessment.

**5. Credentials.**
- Cloud collectors sign in with OIDC federation to read-only roles: no long-lived cloud keys exist.
- Secrets live only in GitHub secrets. Secret scanning and push protection are on in the engine repository.
- Local tool settings and secret files are never committed: `.gitignore` in the engine and in every new client
  repository lists `.claude/settings.local.json` (Claude Code's local permission rules, which can hold a pasted
  token), `CLAUDE.local.md`, `.env*` and key files, and `grc validate` fails (E090) when one is tracked anyway.
  The engine's tests check its own repository the same way.
- The GitHub token is sent only to the GitHub API, whatever a pagination link says; collectors call `https://`
  endpoints only.
- `GRC_ENGINE_TOKEN` lives only in the install step's environment while the engine is fetched (never in git's
  config on disk), and is unset before anything else the client's `requirements.txt` lists is installed.
- The ingest and questionnaire jobs parse files from outside with the write token kept off disk
  (`persist-credentials: false`); the token is used for the one `git push` that commits the draft.
- No workflow uses `pull_request_target`, so a pull request from a fork never runs with the repository's secrets.
  **Anyone with write access to a client repository can reach that repository's secrets** through a pull request
  of their own (as on any GitHub repository). So keep write access to people who need it, make
  `GRC_ENGINE_TOKEN` a fine-grained, read-only token for the engine repository alone, and give each client its own
  Anthropic key with a spend limit. While the engine is public, client installs don't need `GRC_ENGINE_TOKEN`
  at all; it stays supported for a private engine.
- Client repositories protect `main` with a ruleset (`client-protect-main-ruleset.json`): pull requests with one
  approving review from a code owner, stale approvals dismissed, the *Validate* check required, no force pushes
  or deletion.
- Each reusable workflow declares the secrets it uses, and callers pass exactly those by name (never
  `secrets: inherit`): the ingest workflow can't see the Cloudflare token, the site workflow can't see the Anthropic key.

**6. Workflows run with the least privilege.** Every caller (the thin wrapper in each repository) declares the
permissions it grants, and the reusable workflow it calls can use no more. Reusable workflows don't declare their
own: one that asked for more than an older wrapper grants would fail to start. Workflow inputs and event data reach shell scripts through environment variables, never by
`${{ }}` expansion inside a script. Each reusable workflow declares the secrets it uses and callers pass exactly
those. The engine runs as `python -I`, so a `grc/` folder in a client repository can't stand in for it. No job
shares a pip cache. These rules are tested and scanned (zizmor).

**7. Supply chain.**
- Every third-party action is pinned to a commit SHA (Dependabot proposes updates, with the version in a comment).
- The engine's Python dependencies are installed from hash-locked files (`grc/resources/locks/`); a changed or
  substituted package fails the install. The Security workflow fails when a lock no longer matches
  `pyproject.toml`. Not hash-checked: the engine itself (fetched at its release tag), `setuptools` fetched by pip
  to build it, anything else a client adds to `requirements.txt`, and every dependency of an engine older than
  0.25.0 (its workflows warn).
- pip-audit checks every locked dependency for known vulnerabilities on every PR and weekly; bandit and CodeQL
  (Python and the workflows, security-extended queries) scan the code.
- Each release carries the engine as a wheel and a source archive with `SHA256SUMS`, and each file has a signed
  build-provenance attestation (Sigstore, keyless; `gh attestation verify <file> --repo <engine repo>`), which
  ties it to the release workflow run and commit.
- Clients pin the engine to a release tag and call its reusable workflows at a major-version tag
  (`engine-v0`). That tag is a deliberate trust in the engine's maintainer; protect it (below).

## Accepted risks and gaps

| Risk | Why it stands | What would close it |
|---|---|---|
| One maintainer approves their own engine changes | One-person practice during the proof of concept | A second reviewer, then required reviews with "dismiss stale approvals" |
| Clients install the engine from its git tag, not the attested wheel | The tag install is how clients already pin; the wheel and its attestation are new in 0.26 | Pin the attested wheel by URL and hash in `requirements.txt`, then verify the attestation in the install step |
| The engine's source is public | Chosen while the practice is small; it holds no client data or secrets, and its license forbids commercial use | Make it private (clients then need `GRC_ENGINE_TOKEN` again, already supported) |
| `engine-v0` is a moving tag that clients trust | Lets clients receive fixes without a PR per release | Tag protection rules on `engine-v*`; clients that want more pin a SHA |
| The Anthropic API receives client document text | Needed for AI drafting; off by default (`ingest.ai_drafting`) | Keep it opt-in per engagement; record it in the client's data-processing terms |
| Scanner tools change between runs | They are hash-locked like everything else, but new rules can fail a PR | Expected: fix or justify the finding |
| Build tooling and the engine itself aren't hash-checked at install | pip fetches `setuptools` to build the engine; the engine comes from a git tag | Install the attested wheel by hash (above), or pin the engine to a commit |
| Locks age | They move only on an upgrade run of the Security workflow; pip-audit flags known vulnerabilities weekly | Run the upgrade monthly, or when pip-audit fails |
| Prompt injection can still produce a misleading draft | Drafts are reviewed by a person; nothing is verified automatically | Reviewer training; the source on every drafted item |

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
