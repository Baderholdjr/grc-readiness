# Read-only rooms: the executive dashboard and the auditor room

Two small websites built from the merged record, each a Cloudflare Worker behind its own Cloudflare Access
application. Neither can change anything: they hold no GitHub token, accept only `GET`, and are rebuilt from the
record after every merge and daily. GitHub stays the system of record. The design and its controls are in the
[threat model](THREAT-MODEL.md#the-friendlier-ui).

| Room | Who | Shows |
|---|---|---|
| **Executive dashboard** | The client's executives (whoever the Access policy lets in) | Requirements ready (%), evidence checks complete (%), days to Stage 1 and Stage 2, open and overdue gaps, gaps by severity, the five most urgent gaps (area, severity, due date), and a 12-week trend |
| **Auditor room** | Named auditors, only between two dates | The auditor package: the whole archive and each file, with sizes and SHA-256 checksums from the manifest. That is everything the package holds: the reports, the policies and procedures, impact assessments, collector snapshots, the OSCAL export and the source record |

## What each room leaves out, and why

- **Executive dashboard:** no requirement text, no gap findings or owners, no evidence, no document text. The page
  is built from `data.json`, which holds only the numbers above and each top gap's area label, so what isn't
  shown can't be read from the page source either.
- **Auditor room:** evidence held in the client's own systems (screenshots, tickets, exports). The package's
  evidence index says where each item is held; the auditor asks the client for access as usual. What the package
  itself holds (above) is in the room. Files are always downloaded, never opened inside the room.

## How the auditor room is locked

Two independent checks of who you are, then a date check:

1. **Cloudflare Access**, at Cloudflare's edge, in front of the room: an email code (single sign-on in
   production) for the addresses in the room's own Access policy.
2. **The Worker**, on every request, verifies the Access login itself and then lets in only the emails in
   `rooms.auditor.auditors`, whatever the Access policy allows; so a policy left too wide still admits no one
   else.
3. **The window**, also in the Worker: only from `opens` to `closes` (whole days, UTC). The room shuts on its own;
   nobody has to remember. (Access policies can't hold dates, so this check is the Worker's alone.)

The deploy runs only from `main`: a run started by hand on another branch can't publish an unreviewed list of
auditors or a wider window.

Every page shows "Viewed by <email> on <date>", and every request the Worker lets through is written to its log
with the email and the path. Cloudflare keeps Worker logs for a few days only: to keep them with the engagement
record, export them (Workers Logpush on a paid plan) before they expire. Access keeps its own sign-in log.

## Settings (`engagement.yaml`)

```yaml
rooms:
  executive:
    enabled: true
    access_aud: <64 hex characters: the AUD tag of the dashboard's Access application>
    allowed_email_domains: [larch-finch.example]     # optional second check
  auditor:
    enabled: true
    access_aud: <the AUD tag of the auditor room's own Access application>
    opens: 2027-01-25
    closes: 2027-02-12
    auditors: [ann@audit-firm.example, bo@audit-firm.example]
```

`access_team` defaults to `portal.access_team`. Each room needs **its own** Access application (and AUD tag), so
a policy for one can never let people into another.

`grc validate` fails (E091) when two sites share one AUD tag, and warns when the auditor room is enabled without dates or auditors (W180: it refuses everyone), when
it closes before it opens (W180), or when the window is over 120 days (W181: keep it to the audit).

## Build and deploy

```
python -m grc rooms --out _rooms                  # the enabled rooms (the dashboard alone if none, to preview)
python -m grc rooms --room auditor --out _rooms    # one; or --room all
```

The **Read-only rooms** workflow (`.github/workflows/rooms.yml` in the client repository) builds both after every
merge and daily, and deploys each enabled room (from `main` only) when the `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` secrets are set. Each room is built on its own: an auditor package that can't be built
(a record with validation errors) doesn't stop the dashboard. Only the dashboard is uploaded as a workflow
artifact to preview; the auditor package never is, because anyone with read access could download it. Until a room's `access_aud` is set, the
deployed room refuses everyone.

Setting up Access for a room is the same as for the client site ([CLIENT-SITE.md](CLIENT-SITE.md), step 4), with
one application per room:

1. **Zero Trust → Access → Applications → Add an application → Self-hosted.**
2. Name it, for example *Larch & Finch: auditor room*, and set its domain to the room's `workers.dev` address
   (from the workflow summary).
3. Add a policy: *Allow*, *Emails*: the auditors' addresses (for the dashboard: the executives' addresses or
   the client's email domain).
4. Copy the application's **Audience (AUD) tag** into `rooms.<room>.access_aud` and merge.

## Limits

- Cloudflare serves files up to 25 MiB from a Worker; the auditor room isn't built if a package file is larger.
- The trend reads the record as it was committed at the end of each week, with today's engine. Weeks before the
  record existed, or whose record can't be read, are left out.
- The executive dashboard has no date window: remove people from its Access policy when they no longer need it.

## Files

| File | What it is |
|---|---|
| `grc/rooms.py` | Builds both bundles; the summary, the trend, the window checks (W180, W181) |
| `grc/resources/rooms/worker.js` | The Worker for both rooms |
| `grc/resources/portal/access.js` | The Access login check and security headers, shared with the client site |
| `grc/resources/rooms/site/` | The pages: `executive.*`, `auditor.*`, `rooms.css` |
| `.github/workflows/grc-rooms.yml` | Build, upload, and deploy when enabled |
| `tests/test_rooms.py`, `tests/portal/rooms.test.mjs` | Engine, Worker and browser tests |
