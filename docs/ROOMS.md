# Read-only rooms: the executive dashboard and the auditor room

Two small websites built from the merged record, each a Cloudflare Worker behind its own Cloudflare Access
application. Neither can change anything: they hold no GitHub token, accept only `GET`, and are rebuilt from the
record after every merge and daily. GitHub stays the system of record. The design and its controls are in the
[threat model](THREAT-MODEL.md#the-friendlier-ui).

| Room | Who | Shows |
|---|---|---|
| **Executive dashboard** | The client's executives (whoever the Access policy lets in) | Requirements ready (%), evidence checks complete (%), days to Stage 1 and Stage 2, open and overdue gaps, gaps by severity, the five most urgent gaps (area, severity, due date), and a 12-week trend |
| **Auditor room** | Named auditors, only between two dates | The auditor package: the whole archive and each file, with sizes and SHA-256 checksums from the manifest |

## What each room leaves out, and why

- **Executive dashboard:** no requirement text, no gap findings or owners, no evidence, no document text. The page
  is built from `data.json`, which holds only the numbers above and each top gap's area label, so what isn't
  shown can't be read from the page source either.
- **Auditor room:** the evidence itself. The package's evidence index says where each item is held; the auditor
  asks the client for access as usual. Files are always downloaded, never opened inside the room.

## How the auditor room is locked

Three locks, each enough on its own:

1. **Cloudflare Access** in front of the room: an email code (single sign-on in production) for the auditors'
   addresses.
2. **The named auditors**: the Worker lets in only the emails in `rooms.auditor.auditors`, whatever the Access
   policy allows.
3. **The window**: the Worker lets them in only from `opens` to `closes` (whole days, UTC). The room shuts on its
   own; nobody has to remember.

Every page shows "Viewed by <email> on <date>", and every view and download is written to the Worker's log with
the email.

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

`grc validate` warns when the auditor room is enabled without dates or auditors (W180: it refuses everyone), when
it closes before it opens (W180), or when the window is over 120 days (W181: keep it to the audit).

## Build and deploy

```
python -m grc rooms --out _rooms                 # both rooms
python -m grc rooms --room auditor --out _rooms   # one
```

The **Read-only rooms** workflow (`.github/workflows/rooms.yml` in the client repository) builds both after every
merge and daily, uploads them as a workflow artifact, and deploys each enabled room when the
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` secrets are set. Until a room's `access_aud` is set, the
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

- Cloudflare serves files up to 25 MiB from a Worker; the build says if a package file is larger.
- The trend reads the record as it was committed at the end of each week, with today's engine. Weeks before the
  record existed are left out.
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
