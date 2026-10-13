# Client site

The client site is a small website for the client's people. It shows:

- where they stand
- what's coming up
- what's needed from them

They can answer each request there.

It is the interactive version of the [client view](CLIENT-VIEW.md), built from the same plain-language content:

| Page | What it shows |
|---|---|
| **Overview** | Days to the Stage 1 audit, how many requests are open, the path to certification (phases, today, Stage 1 and Stage 2), the next four requests, key figures and other dated events. |
| **Requests** | Every request, grouped by when it's due, filterable by person. "Needs action" hides what's already been sent or needs nothing right now. |
| **One request** | What we need, why it matters, and what good evidence looks like. A short form takes an answer, up to five links and a "no patient or personal data" confirmation. |
| **Progress** | Each area of the standard with a done / under way / not started bar. Areas open to show each requirement in plain words, with an optional technical layer: requirement numbers and the four evidence checks. |
| **Help** | Each term in plain language, with the technical term underneath. |

When an engagement covers more than one framework, each framework appears as a tab: run `grc portal --also <other engagement dir>`.

## How answers are handled

```
client fills the form ──► Worker checks the login ──► pull request with
                                                     engagement/submissions/SUB-YYYYMMDD-xxxxxx.yaml
                                                              │
               analyst reviews it like any other change ◄─────┘
               (sets status, files evidence, merges)
                                                              │
               site rebuilds on merge: the client sees ◄──────┘
               "Accepted" or "We need a bit more: <your note>"
```

- **The client can't choose the record's details.** The Worker writes the file. The client can't set the status, the submitter (taken from the verified login) or the request details (taken from the site's own data).
- **A submission changes no status.** It never changes a control, gap or evidence status. You file evidence in `evidence/index.yaml` as usual and list the ids under the submission's `evidence:`.
- **Validation applies.** `grc validate` checks every submission against `submission.schema.json`:
  - **E070:** the id and the file name differ.
  - **W171:** a submission has waited for review longer than `portal.triage_days` (default 5).
  - **W172:** a listed evidence id doesn't exist.
  - **W170** (info): it answers a request that is no longer open.
- **The analyst's queue** is `submissions.md` in the reports, with waiting ones on top. It is not part of the auditor package.

To review a submission, open the pull request ("Client submission: …", label `client-submission`), read the file, and open the links. Edit the file in the PR:

```yaml
status: accepted          # or needs_more (note required, the client sees it), or withdrawn
reviewed_by: Bernard Aderhold
reviewed_on: 2026-10-14
note: Thanks. We've filed this as EV-031.
evidence: [EV-031]
```

Then merge.

## Security model

- **Every request needs a Cloudflare Access login.** That includes the pages themselves (`run_worker_first`). Access sends a one-time code to an allowed email address.
- **The Worker checks the login itself as well.** It verifies:
  - the RS256 signature against your team's keys
  - the audience tag, issuer and expiry
  - optionally, the email domain

  If the Access settings are missing, the site refuses everyone (fails closed). It never opens up.
- **The GitHub token is limited.** It is fine-grained and covers this one repository, with Contents and Pull requests permissions only. It lives as a Worker secret, never in the repository.
- **Answers are only accepted from the site itself**, as same-origin JSON. They are limited to 4,000 characters and five https links, and are cleaned of control and bidirectional characters.
- **Limits:**
  - one answer at a time per person, and five per minute
  - at most 15 answers per person waiting for review, and 40 for the whole site
  - the list of waiting answers is reused for 20 seconds between page loads

  The per-minute limit is kept by each Worker instance, so it is a speed bump rather than a guarantee. For production, add a Cloudflare rate-limiting rule (see the table below).
- **No file uploads.** Clients share links to documents in their own systems. Patient or other personal data must never be included; the form requires the client to confirm this, and the Help page says why.
- **The site loads nothing from third parties.** A strict content-security policy blocks it, and the site has no cookies of its own.

## Setting it up (proof of concept, free plans)

**What you need:**
- a free Cloudflare account
- about 30 minutes
- the client's email addresses

Cloudflare renames screens from time to time. If a label below doesn't match, look for the nearest equivalent.

### 1. Cloudflare account and IDs

1. Sign up at dash.cloudflare.com (Free plan).
2. Copy your **Account ID**. It is a 32-character code of letters and digits, such as `0f1e2d3c4b5a69788796a5b4c3d2e1f0`. It is **not** your email address. To copy it:
   - **Quickest:** on the account home page, press **Ctrl+K** (Windows) or **Cmd+K** (Mac), type **Copy account ID**, and press Enter.
   - **Or:** open **Workers & Pages** and find **Account details** on the right. Select the copy button next to **Account ID**.
3. Open **Zero Trust** in the sidebar and choose a **team name**, for example `aderhold-grc`. This becomes `aderhold-grc.cloudflareaccess.com`.
4. Pick the **Free** plan. Cloudflare may ask for a payment card even on the free plan; it isn't charged.
5. Turn on email codes. In **Zero Trust → Integrations → Identity providers**, select **Add new identity provider** and choose **One-time PIN**.

   New Zero Trust organizations (since June 2026) start with only the **Cloudflare** identity provider, which lets in people who are members of your Cloudflare account. Clients aren't members, so they need One-time PIN to receive a sign-in code by email.

### 2. Tokens, as GitHub secrets

In the client repository, open **Settings → Secrets and variables → Actions → New repository secret** and add these three secrets:

| Secret | How to get it |
|---|---|
| `CLOUDFLARE_API_TOKEN` | In Cloudflare, go to **My Profile → API Tokens → Create Token**. Use the **Edit Cloudflare Workers** template, limit it to your account, then create and copy the token. |
| `CLOUDFLARE_ACCOUNT_ID` | The Account ID from step 1. |
| `PORTAL_GITHUB_TOKEN` | In GitHub, go to **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**. Set **Repository access** to *Only select repositories*, choosing this client repository. Set **Permissions** to **Contents: Read and write** and **Pull requests: Read and write**. Choose an expiry of 90 days or less, and put a reminder in your calendar to replace it. |

Without `PORTAL_GITHUB_TOKEN` the site still works, but read-only.

To **turn answering off** later, revoke the GitHub token (GitHub → Settings → Developer settings → Fine-grained tokens), or remove the Worker's secret in Cloudflare (Worker → **Settings → Variables and Secrets** → delete `GITHUB_TOKEN`). Deleting the repository secret alone isn't enough: the Worker keeps the last token it was given.

### 3. First deploy

In `engagement/engagement.yaml`, add the following through a pull request:

```yaml
portal:
  enabled: true
```

Merge it. **Actions → Client site** builds and deploys the Worker, and the run summary shows the address, for example `https://grc-portal-larkspur-health.<your-subdomain>.workers.dev`.

Opening that address now says **"This site isn't set up yet"**. That's expected: the site stays locked until the login is configured.

### 4. Put the login in front

1. Go to **Workers & Pages** and open the Worker (`grc-portal-…`).
2. Select the **Access** tab, then **Protect this Worker behind Access**.
3. Choose **All traffic**, not "Previews only".
4. Under **Authentication policy**, pick whichever option is quickest. You'll replace the rule in step 5.
5. Select **Apply Access**.

   If your dashboard has no Access tab on the Worker, do it from the Zero Trust side instead. Go to **Zero Trust → Access → Applications → Add an application → Self-hosted**, and use the workers.dev address as the domain.
6. Go to **Zero Trust → Access → Applications** and open the application that was just created.
   - **Policies:** keep a single **Allow** rule with **Include → Emails**, listing exactly the people who should see the site: the client's people and you.
     - Don't use "Everyone", a whole email provider such as gmail.com, or "Cloudflare account" (that one only lets your own account's members in).
     - Under **Login methods** (or **Authentication**), make sure **One-time PIN** is allowed.
   - **AUD tag:** copy the **Application Audience (AUD) Tag**, a 64-character code. It's on the application's overview, or under **Additional settings** / **Basic information**.
7. Back in `engagement.yaml`, through a pull request:

   ```yaml
   portal:
     enabled: true
     access_team: aderhold-grc            # your team name from step 1
     access_aud: 0123…cdef                # the AUD tag (64 characters)
     allowed_email_domains: [larkspur.example]   # optional second check; leave it out while testing with your own address
   ```

   `allowed_email_domains` is an extra check made by the Worker after Access has let someone in. If you use it, include every domain that needs to sign in, your own too. For a pilot that only you use, with a gmail.com address, leave it out. The email list in the Access policy is what decides who can sign in.
8. Merge. After the redeploy, open the address. Cloudflare asks for an email and sends a code, and then the site appears.

### 5. Try it

1. Answer a request on the site.
2. A pull request "Client submission: …" appears within seconds. Validate runs on it.
3. Set `status: accepted` and `reviewed_by`, then merge.
4. After the rebuild, the request shows **Accepted** on the site.

### If answers fail to send

The site shows "We couldn't send your answer … (reference X999)". The letter is the step that failed, and the number is GitHub's reply:

| Reference | Meaning | Fix |
|---|---|---|
| `R403`, `B403`, `F403` (or 404) | The token can read pull requests but can't read or write files. | In GitHub, go to **Settings → Developer settings → Fine-grained tokens**, open the token, and set **Contents** to **Read and write**. Check that the repository is selected. Saving keeps the same token, so you don't need to redeploy. |
| `P403` | The token can't open pull requests. | Set **Pull requests** to **Read and write** on the token. |
| `x401` | The token expired or was revoked. | Create a new token and update the `PORTAL_GITHUB_TOKEN` secret, then re-run **Actions → Client site**. |
| `B422` | A branch with that name already exists, which is very rare. | Send again. |

For more detail, open the Worker in Cloudflare and go to **Observability → Logs**. Each failure logs its step and status, never the answer itself.

### Previewing without Cloudflare

Every run uploads the built site as an artifact (`client-site-<sha>`). Locally, `grc portal --out _portal` builds the same thing.

The pages need the Worker to load, because it's what lets the browser in. To look at the site without Cloudflare, run the test harness. It plays the part of Access and GitHub:

```
node tests/portal/harness.mjs serve _portal 8787 you@example.com /tmp/gh.json
```

Then open http://localhost:8787.

## Moving to paid, secured services

The free setup above is fine for a proof of concept with test or non-sensitive data. Before real client data goes through it, plan these upgrades:

| Area | Proof of concept | Production |
|---|---|---|
| Sign-in | Email one-time code, email list | Single sign-on with the client's identity provider (Entra ID, Okta, Google Workspace) via Access, with MFA required. A per-client Access application. |
| Address | `*.workers.dev` | Your own domain (for example `clients.yourfirm.com/larkspur`), with Access on the domain. |
| Users | Up to 50 free | Zero Trust paid plan when you pass 50 users, or when you need logs and longer retention. |
| GitHub access | Fine-grained token, rotated by hand | A GitHub App installed on each client repository, with short-lived tokens and no personal account in the loop. |
| Files | Links only | Optional uploads to a private R2 bucket per client, with malware scanning and retention rules, referenced from the evidence index. |
| Rate limits | Per-instance limits in the Worker | A Cloudflare rate-limiting rule or binding on `/api/submit`, keyed on the signed-in email. |
| Records | Workers logs | Access audit logs and Worker logs kept with the engagement record. |
| Agreements | n/a | A data-processing agreement with Cloudflare (and a BAA if any protected health information could ever be involved). Keep the "no patient data" rule either way. |

## Files

| File | What it is |
|---|---|
| `grc/portal.py` | Builds `portal.json`, `wrangler.toml` and the bundle; writes `submissions.md`. |
| `grc/resources/portal/site/` | The site: `index.html`, `app.js`, `app.css`. |
| `grc/resources/portal/worker.js` | The Cloudflare Worker. |
| `grc/resources/schemas/submission.schema.json` | What a submission may contain. |
| `.github/workflows/grc-portal.yml` | Build, upload, and deploy when configured. |
| `tests/portal/` | Worker tests (`node --test`) and the local harness. |
