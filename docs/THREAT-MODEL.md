# Threat model: the GRC engine and client repositories

Scope: the engine (this repository, public under the PolyForm Noncommercial license), the client repositories
(private) built from it, their GitHub Actions workflows, the
client site on Cloudflare, and the services they call (the Anthropic API for AI drafting; AWS, Azure, GCP and
identity providers for evidence collectors). Reviewed when the architecture changes, and at least yearly. The
friendlier UI (workspace, auditor room, executive dashboard) has its own section below, written before it is built.

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
- An OSCAL catalog or profile given to `grc oscal import`, or a file given to `grc oscal validate`, is JSON only
  (no XML parser is involved), size-limited (80 MB), refused if nested too deeply, and must pass NIST's OSCAL 1.2.3
  schema before anything is read from it; its text becomes requirement wording, which every report already
  treats as data. The framework id is checked (letters, digits, `-`, `_`), so it can't write outside
  `frameworks/`, and a built-in framework can't be replaced.

**3. Text inside documents is untrusted** (prompt injection). Claude is told the documents are data and to ignore
instructions in them; its output is a draft in a PR, schema-checked; claims only move a leg from `not_started` to
`claimed`. A document that says "mark everything verified" can at worst add a wrong claim, which a reviewer sees.
Everything drafted or taken from a file name is made inert before it goes into the ingest PR comment: no links
or images (so nothing can leak through an image URL), no @mentions, no HTML (no hidden comments).

**4. Outputs people open, and outputs machines read.** Text from records that would start a spreadsheet formula (`=`, `+`, `-`, `@`) stays
text in every workbook and CSV the engine writes. The client site builds its page with DOM text nodes (no
`innerHTML`), serves a strict Content-Security-Policy (no inline or third-party script), and sends no-sniff,
no-frame and HSTS headers. The OSCAL export (`grc oscal export`, and `09-oscal/` in the auditor package) is
checked against NIST's schema before any file is written, refuses a record that fails validation (a forced draft
is marked DRAFT and shows no requirement with an error as met), and claims no more than the record: a requirement
is `satisfied` only when the record shows it Ready, and the results say they are the client's readiness record,
not an independent assessment.

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
  ties it to the release workflow run and commit. The tests run in a separate job with a read-only token; the
  signing job installs only hash-locked build tools and builds without fetching anything else.
- Clients pin the engine to a release tag and call its reusable workflows at a major-version tag
  (`engine-v0`). That tag is a deliberate trust in the engine's maintainer; protect it (below).

## The friendlier UI (design; not built yet)

Status: proposed, for review before any code is written. Three surfaces sit in front of each client repository.
**GitHub stays the system of record**: the UI keeps no data of its own beyond a login session; every change is a
pull request reviewed and merged as today, and every page is built from the merged record.

| Surface | Who | Sign-in | Can do |
|---|---|---|---|
| **Workspace** | Our consultants | GitHub (OAuth through our GitHub App), MFA enforced by GitHub | Read the record; propose edits as pull requests under their own GitHub name |
| **Workspace** | Client staff (no GitHub account) | Cloudflare Access, email code (SSO with MFA in production) | Read their record; answer requests and propose edits to fields their role allows; the App opens the pull request and names them in it |
| **Auditor room** | Named auditors | Cloudflare Access, email code, only between the dates the engagement sets | Read only: the reports, the OSCAL export, the evidence index (evidence stays in the client's systems), and the auditor package |
| **Executive dashboard** | Client executives | Cloudflare Access, email code (SSO in production) | Read only: readiness %, days to the audit, top risks and gaps, trend. No evidence, no document text, no requirement detail |

Each client gets its own Worker and its own Cloudflare Access application for each surface, so one client's
people can never be let into another client's pages by a policy mistake on a shared app.

### New assets

| Asset | Why it matters |
|---|---|
| The GitHub App's private key | It mints tokens for every client repository the App is installed on |
| Consultants' GitHub user tokens | They act as that consultant on GitHub |
| Login sessions (Access tokens, the workspace session cookie) | Whoever holds one is that person to the UI |
| The auditor-room access list and window | It decides who outside the client sees the record, and until when |
| The pages' content | The record's text, read by people with different rights |

### Threats and controls

**Spoofing (someone acting as someone else).**
- Every request needs a Cloudflare Access login, and the Worker verifies the Access token itself: signature,
  audience, issuer and expiry, failing closed if Access isn't configured (as the client site does today).
- Consultants sign in with GitHub through the App's OAuth flow (state and PKCE checked); their user token expires
  after 8 hours and lives only in an encrypted, `HttpOnly`, `Secure`, `SameSite=Strict` session cookie, never in
  storage the page's script can read. A consultant must also be on the engagement's list of consultants.
- Email codes can be phished or a mailbox taken over. Proof of concept only; production uses the client's SSO with
  MFA through Access, and our own SSO for consultants who use email.

**Tampering (changing the record wrongly).**
- The UI can only open pull requests. The App is not on any ruleset's bypass list, so its pull requests need the
  same review and checks as anyone's, and nothing merges without a person.
- What each role may change is decided in the Worker, field by field, from an allow-list in the engine (for
  example: client staff may answer requests, update an owner's contact or an implementation statement, add an
  evidence link; they may not touch status, legs, gaps' severity, approvals or anything another client owns).
  The Worker writes the file itself from validated fields; the browser never sends a file or a path.
- Nothing in the UI can set a leg to `verified` or an answer to `approved`; that stays a reviewer's edit in the
  pull request, and `grc validate` runs on every pull request as today.
- Every write is schema-checked in the Worker, and again by `validate` in CI.
- Cross-site request forgery: writes are same-origin JSON only, the Worker checks `Origin`, and cookies are
  `SameSite=Strict`.

**Repudiation (denying a change).** Each pull request from a client person names the verified email from the
Access token in its body and in a commit trailer (`Submitted-by:`); consultants' pull requests carry their own
GitHub identity. Access and Worker logs are exported and kept with the engagement record for its retention period.

**Information disclosure (the wrong person reading something).**
- Installation tokens are minted per request for the one repository that client's Worker serves (the
  `repositories` parameter), with the least permissions that request needs, and expire within an hour.
- The auditor room opens and closes on the dates in `engagement.yaml` (checked in the Worker as well as in the
  Access policy), lists auditors by name, and stamps each page with the viewer's email and the date. It shows the
  evidence index (where evidence lives), not the evidence.
- The executive dashboard is built at publish time as summary numbers only; the record's text never reaches the
  executive's browser, so it can't be read from the page source.
- Pages are built with DOM text nodes (no `innerHTML`), under a strict Content-Security-Policy with no
  third-party script, as today. Responses that depend on the person are `Cache-Control: private, no-store`.
- No uploads in the first version: links to documents in the client's systems, with the "no patient or personal
  data" confirmation kept. Uploads (to a private, per-client store with scanning) are a later, separate design.

**Denial of service and cost.** Cloudflare rate-limiting rules keyed on the signed-in identity, limits on open
pull requests per person and per client (as the client site has), and request size limits.

**Elevation of privilege.**
- The App asks for: Contents (write), Pull requests (write), Metadata (read). No administration, workflows,
  secrets or members permissions. It can't change rulesets or workflows, so it can't weaken the review it relies
  on. Edits to `.github/` are refused in the Worker as well.
- The private key lives only as a Worker secret (per client Worker, or in one signing Worker that client Workers
  call over a service binding, so a client Worker never holds the key). Rotated on a schedule and on any doubt.
- The engine's allow-list of fields per role is code reviewed like the rest of the engine; a client repository
  can narrow it, not widen it.

### Accepted risks and open questions

| Item | Position |
|---|---|
| Email codes in the proof of concept | Accepted for fictional test data only; SSO with MFA before real client data |
| The App's key can open pull requests on every installed client repository | Mitigated by per-repository tokens and a signing Worker; a separate App per client is the stronger option if a client requires it |
| Cloudflare sees the pages and the Access identities | A data-processing agreement with Cloudflare before real data; no protected health information, ever |
| A reviewer could merge a bad pull request opened through the UI | Same as today: the review is the control; the UI shows the reviewer which fields changed |
| Does the auditor room need downloads of the package? | Proposed yes, the signed package zip, with its manifest checksums |

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
