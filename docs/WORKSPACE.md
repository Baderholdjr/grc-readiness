# Consultant workspace

A website for the practice's consultants. They sign in with GitHub, pick a client engagement, and change a
requirement without editing YAML. Every save becomes a pull request in the consultant's own name, reviewed and
merged in GitHub like any other change. GitHub stays the system of record: the workspace keeps nothing of its
own except a sign-in session.

| What a consultant can change | Limits |
|---|---|
| A requirement's implementation statement | Up to 4,000 characters |
| A requirement's owner | One of the roles in `owners.yaml` |
| An evidence check's status (Documented, Implemented, Evidence exists, Tested) | Not started, claimed or partial. **Verified is never set here**: the reviewer marks it in the pull request |
| The evidence a check cites | Ids from the evidence index |
| A check's note | Up to 1,000 characters |

A check that is already verified can't be changed from the workspace at all (status, evidence or note): changing
what it rests on is the reviewer's edit in GitHub.

Open gaps are shown read-only. Client staff use the [client site](CLIENT-SITE.md); executives and auditors use
the [rooms](ROOMS.md).

## How sign-in works, and why it's safe

- **The Seshat Workspace GitHub App** signs consultants in (OAuth, with a random `state` and PKCE). It has no
  private key: the workspace never acts as the App, only as the signed-in consultant.
- **The consultant's token** is a GitHub user token that expires within 8 hours: a sign-in whose token doesn't
  expire (the App's *Expire user authorization tokens* setting off) is refused and the token revoked. GitHub limits it to the
  repositories that both the consultant can reach and the App is installed on (Contents and Pull requests,
  read and write; nothing else). It lives only in an encrypted (AES-GCM), `HttpOnly`, `Secure`,
  `SameSite=Strict` cookie; the page's script can't read it, and the workspace stores it nowhere else.
- **Only listed consultants** get in: `consultants` in `workspace.yaml`, checked at sign-in and on every request.
  Taking someone off the list ends their session as soon as the change is deployed. **Sign out** revokes the token
  at GitHub as well as clearing the cookie. A copied session cookie would otherwise work until it expires (at
  most 8 hours); it is `HttpOnly` and `SameSite=Strict`, so page script and other sites can't read or send it.
- **Pull requests are authored by the consultant**, so the review, `CODEOWNERS`, the rulesets and the Validate
  check apply exactly as for an edit made in GitHub. The App is on no ruleset's bypass list.
- **The browser never names a file.** It sends a requirement id and a value; the Worker finds the file in the
  record it read from `main` and changes that one value at that same commit (everything else in the file stays as
  it was).
- **A second check on every change**: the Worker parses the file before and after the edit and refuses unless the
  only difference is the value asked for and no check became verified. A file laid out unusually (a value
  carried over several lines, a key written twice) is refused, with a pointer to edit it in GitHub. The client
  site's changes go through the same check.
- Writes are same-origin JSON only. The workspace's pages are built with DOM text nodes (the two short sign-in
  pages the Worker writes itself contain only fixed text and the GitHub login), under the same strict
  Content-Security-Policy as the client site.

## Setting it up

1. **Create the GitHub App** (once): github.com → Settings → Developer settings → GitHub Apps → New GitHub App.
   - Name: *Seshat Workspace*. Homepage: the engine repository.
   - Callback URL: the workspace's address plus `/auth/callback` (use a placeholder until the first deploy,
     then change it).
   - *Expire user authorization tokens*: on. *Request user authorization during installation*: off.
     *Device flow*: off. *Webhook*: off.
   - Repository permissions: Contents **read and write**, Pull requests **read and write**, Metadata read. No
     others, no account permissions. *Only on this account*.
   - Don't generate a private key: the workspace doesn't use one.
   - Install it on the client repositories only (*Only select repositories*), not on the engine.
2. **Create the workspace repository** (private), for example `seshat-workspace`, with:
   - `workspace.yaml` (from `grc/resources/workspace/repo/workspace.yaml`): the App's **Client ID** and the
     consultants' GitHub logins.
   - `.github/workflows/workspace.yml` (from `grc/resources/workspace/repo/dot-github/workflows/`, with the engine
     repository and `engine-v0` filled in), and `requirements.txt` pinning the engine, as in a client repository.
   - An **environment** named `cloudflare` (Settings → Environments → New environment) with *Deployment branches*
     limited to `main`, holding the secrets `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. Keeping them in the
     environment rather than as repository secrets means a workflow edited on another branch can't reach them.
3. **First deploy**: run the *Consultant workspace* workflow. Its summary shows the address.
4. **Set the Worker's two secrets on Cloudflare** (Workers & Pages → the workspace → Settings → Variables and
   Secrets → Add, type *Secret*). Never put them in GitHub or in chat.
   - `GITHUB_CLIENT_SECRET`: on the App's page, *Generate a new client secret*, and paste it straight into
     Cloudflare.
   - `SESSION_KEY`: 32 or more random characters (a password manager's generator works).
   Until both are set, the workspace answers "isn't set up yet".
5. **Point the App at it**: set the App's callback URL to `https://<the workspace's address>/auth/callback`.
6. Optionally put Cloudflare Access in front as a second lock (the consultants' emails).

## Files

| File | What it is |
|---|---|
| `grc/workspace.py` | Reads `workspace.yaml`, builds the bundle (`grc workspace`) |
| `grc/resources/workspace/worker.js` | The Worker: sign-in, session, the record, changes |
| `grc/resources/portal/yamledit.js` | The one-value file edits, shared with the client site |
| `grc/resources/workspace/vendor/js-yaml.mjs` | YAML parser (js-yaml 4.1.1, MIT; hash checked by the tests) |
| `grc/resources/workspace/site/` | The pages |
| `.github/workflows/grc-workspace.yml` | Build and deploy (from `main` only) |
| `tests/test_workspace.py`, `tests/portal/workspace.test.mjs` | Settings, Worker and browser tests |
