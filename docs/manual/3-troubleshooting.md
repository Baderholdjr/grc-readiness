# Part 3: Troubleshooting guide

Find your symptom in the index, then follow the entry. Each entry gives:
- **What you see:** the message or behaviour
- **Why:** the cause in plain terms
- **Fix:** the steps

Entries marked **(seen in the pilot)** happened during the Larkspur pilot, so the fix is proven.

## Before anything else

1. **Read the exact message.** Error messages from this tool name the file, the rule code and what to change.
2. **Find the failed step.** In **Actions**, open the failed run, click the job, then expand the step with the red ✗. The last lines usually say what happened.
3. **Check whether it's already fixed.** Re-run the workflow (**Re-run all jobs**). Some failures are transient, such as a network blip or GitHub delay.

## Index

| Symptom | Entry |
|---|---|
| A workflow fails at "Install the GRC engine" | [T-01](#t-01-a-workflow-fails-at-install-the-grc-engine) |
| "workflow was not found" / not accessible | [T-02](#t-02-workflow-not-found-or-not-accessible) |
| Automation can't open pull requests | [T-03](#t-03-automation-cant-open-pull-requests) |
| "engine-vX.Y.Z already exists - bump the version first" | [T-04](#t-04-engine-vxyz-already-exists---bump-the-version-first) |
| Release stopped halfway | [T-05](#t-05-an-engine-release-stopped-halfway) |
| A new workflow didn't arrive with an engine upgrade | [T-06](#t-06-a-new-workflow-didnt-arrive-with-an-engine-upgrade) |
| *validate* fails on my pull request | [T-07](#t-07-validate-fails-on-my-pull-request) |
| "not valid YAML" / E001 | [T-08](#t-08-not-valid-yaml-or-e001) |
| A verified requirement turned red without anyone changing it | [T-09](#t-09-a-verified-requirement-turned-red-on-its-own) |
| Hundreds of warnings | [T-10](#t-10-hundreds-of-warnings) |
| The reports branch isn't updating | [T-11](#t-11-the-reports-branch-isnt-updating) |
| A collector "could not run" (W109) | [T-12](#t-12-a-collector-could-not-run-w109) |
| A collector check is failing (W108) | [T-13](#t-13-a-collector-check-is-failing-w108) |
| "branch protection unavailable on this GitHub plan" | [T-14](#t-14-main-is-not-protected) |
| "0 of N merged PRs independently approved" | [T-15](#t-15-no-merged-prs-were-independently-approved) |
| Ingest added nothing / dropped items | [T-16](#t-16-ingest-added-nothing-or-dropped-items) |
| `docs approve` refuses, or E042 | [T-17](#t-17-a-document-wont-approve-or-e042) |
| Impact assessment won't pass (E031 / E032) | [T-18](#t-18-an-impact-assessment-wont-pass) |
| Hours import skips every row | [T-19](#t-19-hours-import-skips-every-row) |
| Hours on the wrong dates | [T-20](#t-20-hours-land-on-the-wrong-dates) |
| Client site didn't deploy / "No projects found" in Cloudflare | [T-21](#t-21-the-client-site-didnt-deploy) |
| Client site shows a sign-in or setup message | [T-22](#t-22-the-client-site-shows-a-sign-in-or-setup-message) |
| *validate* fails on a client submission after you edit it | [T-23](#t-23-validate-fails-on-a-client-submission-after-you-edit-it) |
| "We couldn't send your answer … (reference X999)" | [T-24](#t-24-we-couldnt-send-your-answer--reference-x999) |
| A client didn't get a sign-in code | [T-25](#t-25-a-client-didnt-get-a-sign-in-code) |
| "You've sent several answers…" / "Many answers are already waiting…" | [T-26](#t-26-answer-limits) |
| Client still sees "Sent, waiting for review" after you merged | [T-27](#t-27-the-client-site-doesnt-show-your-decision-yet) |
| Cloudflare screens don't match the instructions | [T-28](#t-28-cloudflare-screens-dont-match-the-instructions) |
| E080 when citing evidence from the other framework's record | [T-29](#t-29-e080-evidence-from-the-other-frameworks-record) |
| A second framework's workflow changed the wrong record | [T-30](#t-30-a-workflow-acted-on-the-wrong-record) |
| SOC 2: E002 after adding a category, or E016 | [T-31](#t-31-soc-2-e002-after-adding-a-category-or-e016) |
| Actions storage is full | [T-32](#t-32-actions-storage-is-full) |

---

## Setup and engine

### T-01: A workflow fails at "Install the GRC engine"

**What you see:** the step fails with `Repository not found`, `Authentication failed`, or `could not read Username`.

**Why:** the client repository reads the private engine with the `GRC_ENGINE_TOKEN` secret, and it's missing, expired, or can't see the engine repository.

**Fix:**
1. In GitHub, go to **Settings → Developer settings → Fine-grained tokens** and check the token:
   - it hasn't expired
   - it includes the engine repository
   - it has *Contents: Read*
2. In the client repository, go to **Settings → Secrets and variables → Actions** and update `GRC_ENGINE_TOKEN`.
3. Re-run the workflow.

### T-02: Workflow not found or not accessible

**What you see:** `workflow was not found` or `… is not accessible` when a client workflow calls `grc-readiness/.github/workflows/grc-….yml@engine-v0`.

**Why:** either the engine repository doesn't let other repositories use its workflows, or the engine release that added that workflow hasn't happened yet.

**Fix:**
1. In the engine repository, go to **Settings → Actions → General → Access** and choose *Accessible from repositories owned by the user*.
2. Check that the engine version that added the workflow has been released (`engine-v0` moves on each release).

### T-03: Automation can't open pull requests

**What you see:** `GitHub Actions is not permitted to create or approve pull requests`. The *Evidence refresh*, *Timesheet update*, *Upgrade GRC engine* and similar PRs never appear.

**Fix:** in the client repository, go to **Settings → Actions → General → Workflow permissions** and tick **Allow GitHub Actions to create and approve pull requests**.

### T-04: "engine-vX.Y.Z already exists - bump the version first"

**What you see:** *Release GRC engine* stops at its *Version checks* step with that message. **(Seen in the pilot.)**

**Why:** this version has already been released. The release ran before the pull request that bumped the version was merged.

**Fix:**
1. Make sure the pull request that bumps the version in **both** `grc/__init__.py` and `pyproject.toml` is merged.
2. Run *Release GRC engine* again on `main`.

### T-05: An engine release stopped halfway

**What you see:** the release run failed at "Tag and release". The version tag exists, but there's no GitHub release and `engine-v0` didn't move. **(Seen in the pilot, version 0.10.0.)**

**Why:** a failure after the tag was created, for example a GitHub API hiccup. Tags can't be safely moved from automation.

**Fix:** don't try to repair the tag. Bump to the next version (for example 0.10.0 → 0.11.0), merge, and release again. Clients simply skip the broken version.

### T-06: A new workflow didn't arrive with an engine upgrade

**What you see:** after merging *Upgrade GRC engine*, a new feature's workflow, such as *Client site*, isn't in the client's **Actions** list.

**Why:** GitHub's built-in token isn't allowed to add or change workflow files, so the upgrade PR can only change `requirements.txt`.

**Fix:** a person adds the wrapper. Copy it from the engine's `grc/resources/client/dot-github/workflows/<name>.yml` into the client's `.github/workflows/`, replacing `__ENGINE_REPO__` with `Baderholdjr/grc-readiness` and `__ENGINE_MAJOR__` with `0`, in a pull request.

---

## Validation

### T-07: *validate* fails on my pull request

**What you see:** a red ✗ on the pull request. The *validate* summary lists errors such as `E012 …`.

**Fix:** read the error; it names the file and what's wrong. The most common ones are:

| Code | Usually means | Fix |
|---|---|---|
| E009 | You recorded progress on a requirement with no owner | Set `owner:` in the control file |
| E012 | Wrong kind of evidence for the leg (a draft for *Documented*, a policy for *Implemented*) | Cite evidence of the right type (see the table in [Module 6](2-training-guide.md#module-6-make-your-first-evidence-change)) |
| E006 | The evidence id isn't in the index | Add it to `evidence/index.yaml` first, or fix the typo |
| E007 | The evidence has expired | Get current evidence, or lower the leg to `partial` |
| E008 | Legs out of order (Tested verified before Evidenced) | Verify the earlier legs first |
| E013 | Gap closed without valid closure evidence | Add `closure_evidence` that is current and sound |
| E015 | The evidence's automated check is failing, or the document or assessment behind it isn't soundly approved | Fix the underlying problem; don't remove the check |

Full list: [Product guide, Appendix C](1-product-guide.md#appendix-c-validation-codes).

### T-08: "not valid YAML" or E001

**What you see:** one of these:
- `error: engagement/controls/6.1.4.yaml: not valid YAML at line 20 (mapping values are not allowed here)`, and *validate* stops (control files, gaps, evidence and most other files)
- `E001 … not valid YAML at line N …` (client submissions, management reviews, document headers)
- a schema message such as `'verfied' is not one of ['not_started', 'claimed', 'partial', 'verified']`

**Why:** the file's layout or a value is wrong. YAML is sensitive to:
- **Indentation.** Lines that belong together must line up, and top-level lines start at the left edge.
- **Colons in text.** `note: Policy: approved` breaks. Use quotes: `note: "Policy: approved"`.
- **Tabs.** Use spaces only.
- **Spelling of fixed values.** For example `not_started`, `claimed`, `partial`, `verified`.

**Fix:**
1. Go to the line named in the message and check its indentation against the lines around it.
2. Put quotes around any text containing a colon.
3. Commit again.

### T-09: A verified requirement turned red on its own

**What you see:** nobody changed anything, but the daily build shows E007 or E015.

**Why:** time passed. Either the evidence passed its `valid_for_days`, or a document, assessment or review passed its review date, or the automated check behind the evidence started failing.

**Fix:**
1. Get current evidence and update the date, or re-approve the document if nothing changed.
2. If a collector is failing, fix the underlying issue with the client.

To see what will expire before an audit, run `python -m grc --today 2027-03-08 validate`.

### T-10: Hundreds of warnings

**What you see:** the summary lists many W-codes.

**Why:** early in an engagement this is normal. Most requirements aren't started, documents are drafts, and AI systems have no assessments yet.

**Fix:** work them down in this order:
1. W104 (gaps past due)
2. W108 (failing checks)
3. W101 (evidence expiring)
4. W130–W143 (assessments and documents)
5. W171 (client answers waiting for you)

Warnings never block a merge, but each one appears as a known issue in the auditor package.

---

## Reports and collectors

### T-11: The reports branch isn't updating

**What you see:** the `reports` branch shows an old date.

**Fix:**
1. Open **Actions → Publish reports** and look at the latest run. If it failed, see [T-01](#t-01-a-workflow-fails-at-install-the-grc-engine).
2. If it hasn't run at all, check that the merge actually reached `main`.
3. Run it by hand with **Run workflow**.

Reports publish even when the record has validation errors. The errors are shown on the landing page.

### T-12: A collector "could not run" (W109)

**Why:** the check ran but errored: the credentials are wrong or lack a permission, a parameter (repository, bucket, site) doesn't exist, or the service couldn't be reached. A **missing** secret doesn't cause W109: that check is simply marked *skipped* in the refresh PR.

**Fix:**
1. Check the secret and variable values against `docs/AUTOMATION.md`, and that each credential has the read permissions listed there.
2. Check the `params:` in `collectors.yaml`.
3. Run **Actions → Collect evidence** again and read the check's message in the refresh PR.

### T-13: A collector check is failing (W108)

**Why:** the check ran and the client's system doesn't currently meet the condition. For example, `vendor 'Hugging Face' is not in the Drata vendor program`.

**Fix:** this is a finding about the client, not a tool fault. Raise it with the owner. The evidence counts again as soon as the check passes. Don't remove the check to make the warning go away.

### T-14: `main` is not protected

**What you see:** EV-101 fails with `branch protection unavailable on this GitHub plan | branch protection and rulesets are not available for private repositories on this GitHub plan`. **(Seen in the pilot.)**

**Why:** GitHub Free doesn't offer branch protection or rulesets on private repositories. Without them, GitHub doesn't *force* the *validate* check or CODEOWNERS approval before a merge. The tool still runs and reports everything, but the gate depends on people following the process.

**Fix:**
- **For the pilot:** accept it and keep merging only green pull requests.
- **For real client engagements:** use a GitHub plan that supports protected branches on private repositories (Pro for a personal account, or Team for an organization). Then require **`validate / validate`** and a code-owner review on `main`.

### T-15: No merged PRs were independently approved

**What you see:** EV-102 fails with `0/22 merged PRs independently approved`. **(Seen in the pilot.)**

**Why:** one person opened and merged every pull request. In the pilot that's expected; for a client it's a real control weakness (change management without independent review).

**Fix:** have a second person review and approve pull requests before merging. Client control owners approving their own controls through CODEOWNERS also counts.

---

## Ingest, documents, assessments

### T-16: Ingest added nothing or dropped items

**Why:** one of these:
- AI drafting is off (`ingest.ai_drafting`)
- the `ANTHROPIC_API_KEY` secret is missing
- the file was already processed with the same content (see `intake/.processed.yaml`)
- items were dropped because they had no source citation; claims naming a requirement that isn't in the catalog are dropped, and gaps keep only their valid requirement ids

**Fix:** read the ingest report comment on the pull request. It lists everything dropped and why. Upload a changed version of a file to have it read again.

### T-17: A document won't approve, or E042

**What you see:** `docs approve` refuses (TODO markers left, sections missing, or the approver is the author). Or validation reports **E042** (approved text changed).

**Fix:**
- **Refusal:** finish every `[[TODO]]`, keep the required sections, set `owner`, `author` and `version`, and pick an approver who isn't the author.
- **E042:** an approved document was edited after approval. Set `status: draft`, bump `version`, then approve again. If nothing really changed, restore the approved text.

### T-18: An impact assessment won't pass

**What you see:** E031 or E032 on an `IA-…` file.

**Fix:**
- **E031:** every category needs `relevant: true/false` with a rationale; each relevant category needs at least one scored impact; and the approver must differ from the assessor.
- **E032:** each impact needs residual likelihood and severity. A residual of 12 or more needs `accepted_by`, `accepted_on` and `rationale` from someone other than the assessor. A residual of 20 or more can't be approved: reduce it, or set `decision: reject`.

---

## Hours

### T-19: Hours import skips every row

**What you see:** `9 row(s); 0 added so far; 9 skipped (other client/project)`. **(Seen in the pilot.)**

**Why:** the `HOURS_MATCH` variable doesn't match the client or project names in the export. In the pilot, the value was entered as `HOURS_MATCH=Larkspur`. Since engine 0.9.1 that form is cleaned up automatically, so today the usual cause is a name that differs from the tracker's (for example `Larkspur` against a client called `LH Health`).

**Fix:**
1. Read the *Timesheet update* PR: when everything is skipped, it lists the client and project names it found.
2. Go to **Settings → Secrets and variables → Actions → Variables** and set `HOURS_MATCH` to part of one of those names (separate alternatives with commas).
3. Run **Actions → Hours → Run workflow** with action **import** (the default action is *log*).

### T-20: Hours land on the wrong dates

**Why:** a date like `05/09/2026` is ambiguous. The import assumes month/day unless the file shows otherwise, and says so in the pull request.

**Fix:**
- **From a terminal:** `python -m grc hours import FILE --date-order DMY`.
- **From GitHub:** the workflow has no date-order setting. Copy the engine's `frameworks/iso42001/playbook.yaml` into the client repository at the same path, and set `date_order: DMY` under its `hours:` section. A local playbook replaces the engine's whole playbook, so copy it in full and keep it up to date after engine upgrades.

---

## Client site

### T-21: The client site didn't deploy

**What you see:** the *Client site* workflow fails, or Cloudflare **Workers & Pages** says "No projects found". **(Seen in the pilot.)**

**Why and fix:** check these in order.
1. **Account ID.** The `CLOUDFLARE_ACCOUNT_ID` secret must be the 32-character code (letters and digits), **not your email address**. Copy it with Ctrl/Cmd+K → "Copy account ID" on the Cloudflare home page, then update the secret.
2. **workers.dev subdomain.** A new Cloudflare account must claim its free `something.workers.dev` subdomain once. Go to **Workers & Pages** and set the subdomain in the account details.
3. **API token.** `CLOUDFLARE_API_TOKEN` must use the *Edit Cloudflare Workers* template, with **Account Resources → Include → your account**.
4. **Turned on?** `portal.enabled: true` must be in `engagement.yaml`. The run summary says "not deployed" if it isn't.

Then re-run **Actions → Client site**.

### T-22: The client site shows a sign-in or setup message

| Message | Why | Fix |
|---|---|---|
| "This site isn't set up yet: its sign-in settings are missing." | `portal.access_team` or `portal.access_aud` isn't set | Add both to `engagement.yaml` and merge |
| "Sign in through the link your engagement team sent you." | The request reached the site without a Cloudflare Access login | Make sure Access protects the Worker for **All traffic**, not "Previews only" |
| "Your sign-in has expired or isn't valid." | The login is old, or it was issued for a different Access application (wrong AUD tag or team) | Reload the page. If it persists, check that `access_aud` matches the application's AUD tag and `access_team` matches the team name |
| "This email address isn't on the list for this site." | `allowed_email_domains` is set and the email's domain isn't in it | Add the domain, or remove the setting while testing with a personal address |

### T-23: *validate* fails on a client submission after you edit it

**What you see:** you added your review lines to a `SUB-….yaml` file and *validate* fails with E001, "not valid YAML at line 18 … check that every top-level line … starts at the left edge". **(Seen in the pilot.)**

**Why:** the lines were indented, typically by copying them from an indented example.

**Fix:** remove the spaces before `status:`, `reviewed_by:`, `reviewed_on:` and `note:`, then commit again. Keep only one `status:` line, replacing the original `status: received`. The end of the file should look like this:

```yaml
status: needs_more
reviewed_by: Bernard Aderhold
reviewed_on: 2026-10-13
note: Please link the approved policy rather than a test page.
```

### T-24: "We couldn't send your answer … (reference X999)"

**What you see:** the client's answer fails with a reference. **(Seen in the pilot, before references existed: the token's *Contents* permission was missing.)**

**Why:** GitHub refused one of the steps. The letter is the step and the number is GitHub's reply:

| Reference | Meaning | Fix |
|---|---|---|
| `R403`, `B403`, `F403` (or 404) | The token can see pull requests but can't read or write files | GitHub → **Settings → Developer settings → Fine-grained tokens** → the token → set **Contents: Read and write**, and check grc-pilot (or the client repo) is selected. Saving keeps the same token; nothing to redeploy |
| `P403` | The token can't open pull requests | Set **Pull requests: Read and write** on the token |
| `x401` | Token expired or revoked between steps (rare; usually you get the no-reference message below) | Create a new token, update the `PORTAL_GITHUB_TOKEN` secret, and re-run *Client site* |
| `B422` | A branch with that name already exists (very rare) | Send again |

Two messages carry no reference:
- "We couldn't send your answer. Nothing was saved. Try again in a minute." means GitHub refused even to list pull requests. Usually the token expired or was revoked, or lacks *Pull requests* access. Replace the token, or set **Pull requests: Read and write**, then update `PORTAL_GITHUB_TOKEN` and re-run *Client site*.
- "Answers can't be sent yet: the site isn't connected to the engagement record" means the `PORTAL_GITHUB_TOKEN` secret is missing. Add it and re-run *Client site*.

For more detail, open the Worker in Cloudflare and look under **Observability → Logs**. Each failure logs its step and status, never the answer text.

### T-25: A client didn't get a sign-in code

**Why and fix:**
1. **One-time PIN isn't enabled.** New Zero Trust organizations (since June 2026) start with only the *Cloudflare* login, which admits members of your own Cloudflare account. Add **One-time PIN** under **Zero Trust → Integrations → Identity providers**, and allow it on the Access application.
2. **The email isn't in the policy.** The application's **Allow** rule must include that exact address under **Include → Emails**. Cloudflare doesn't send a code to addresses that aren't allowed.
3. **Spam.** Ask the client to check spam or quarantine for a message from Cloudflare Access.

### T-26: Answer limits

| Message | Why | Fix |
|---|---|---|
| "You've sent several answers in the last minute…" | More than five answers a minute from one person, or one still sending | Wait a minute |
| "Many answers are already waiting for review…" | 15 answers from one person, or 40 in total, are waiting for you | Review and merge (or close) the waiting *Client submission* PRs |

### T-27: The client site doesn't show your decision yet

**Why:** the site rebuilds after each merge to `main`, and takes a minute or two. Until the submission PR is merged, the client sees "Sent, waiting for review".

**Fix:**
1. Check that you **merged** the PR, not just approved it.
2. Check that **Actions → Client site** ran after the merge and succeeded.
3. Ask the client to reload the page.

### T-28: Cloudflare screens don't match the instructions

**Why:** Cloudflare renames and moves screens regularly. **(Seen in the pilot.)**

**Fix:** use the dashboard's search box (Ctrl/Cmd+K) with the name of what you need, for example "Copy account ID", "Identity providers" or "Access applications". The Cloudflare developer documentation has the current navigation. Tell the engine maintainer so `docs/CLIENT-SITE.md` and this manual can be updated.

---

## Several frameworks

### T-29: E080, evidence from the other framework's record

**What you see:** `E080 7.5.documented cites iso42001:DOC-DOCINFO from the iso42001 record, but no reviewed 'equivalent' mapping links 7.5 to a iso42001 requirement`.

**Why:** evidence can count for two standards only where a person has confirmed the two requirements are equivalent. The engine's mappings are proposals until reviewed, and *related* mappings never allow it.

**Fix:**
1. Copy the engine's `mappings/iso27001__iso42001.yaml` to `mappings/` at the repository root, if it isn't there yet.
2. On the line for this requirement, check the relationship. If it is `equivalent` and you agree, fill `reviewed_by` and `reviewed_on`, then merge.
3. If the requirements aren't really equivalent, collect evidence in this record instead.

If the message says "this repository has no … record", the prefix is wrong, or the other record (`engagement-*/` with that `framework:`) doesn't exist.

### T-30: A workflow acted on the wrong record

**Why:** workflows you run by hand default to the main record, `engagement`.

**Fix:** run it again with the **engagement** input set to the other record, for example `engagement-27001`, and close the pull request that went to the wrong record. Branches for a second record end in its suffix (`docs/drafts-27001`), so you can tell them apart.

### T-31: SOC 2: E002 after adding a category, or E016

**What you see:** after adding a category (say `privacy`) to `scope.categories` in a SOC 2 record, *validate* fails with many `E002 No assessment file for requirement P1.1 …`; or it fails with `E016 scope.categories: 'privcy' is not a category of SOC 2`.

**Why:** each criterion in a chosen category needs its assessment file, and the files are only created by `grc init`. E016 is a misspelt category; the valid ones are `availability`, `confidentiality`, `processing_integrity` and `privacy` (Security is always included).

**Fix:** correct the spelling, then run `python -m grc --engagement engagement-soc2 init` and commit the new files in the same pull request. Then run *Policies and procedures* to draft the new category's document.

### T-32: Actions storage is full

**What you see:** GitHub emails that you have used most of your Actions storage, or a run fails at *Upload artifact* with a storage quota message.

**Why:** every *validate* and *Client site* run saves a copy of its output as a run artifact. GitHub Free includes 500 MB for all your private repositories. Engines before 0.14.2 kept each copy for 90 days and each copy was about 45 MB, so a busy repository filled the quota in days.

**Fix:** upgrade the client repository to engine 0.14.2 or later (copies are about a quarter of the size and kept 7 days). Then delete the old copies: in the repository, open **Actions**, open a run, and click the bin icon next to each artifact, or delete whole runs from the **⋯** menu. With the GitHub CLI: `gh api repos/<owner>/<repo>/actions/artifacts --paginate -q '.artifacts[].id' | xargs -I{} gh api -X DELETE repos/<owner>/<repo>/actions/artifacts/{}`. Nothing is lost: the `reports` branch keeps the published reports, and any run can be repeated. GitHub updates the usage figure within 6–12 hours.

## When you need help

Send the engine maintainer:
1. the repository and the pull request or Actions run link
2. the exact message, copied
3. what you changed just before it happened

Never paste tokens or secrets into an issue, a pull request or a chat.
