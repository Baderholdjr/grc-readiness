# Auditor package

A single, checksummed bundle of the record as of one commit, for the certification body (Stage 1, Stage 2, surveillance) or an internal reviewer.

## Producing it

- **For an audit:** publish a release from the GitHub UI (*Releases → Draft a new release*, tag e.g. `v2027.03-stage1`). The release workflow validates the record. Errors block the package; warnings are listed in it. It then attaches the auditor index PDF and the package zip to the release. The full internal reports (hours, client view, client submissions) stay on the `reports` branch. Share the zip with the auditor rather than access to the Release page: the release notes carry the full validation summary, including budget warnings.
- **Locally or for a dry run:** `python -m grc package --out dist --label stage1` writes the package folder, its zip and a copy of the index PDF to `dist/`. Use `--force` only for a draft, when the record has validation errors; they are listed in the index.

## What's inside

| Path | Contents |
|---|---|
| `00-auditor-index.pdf` / `.md` | Engagement facts (scope, dates, source commit, engine version); how to read the evidence test; readiness at a glance; **requirement → evidence traceability** for every requirement and leg; where each cited item is (in the package, or where the client holds it); known issues at packaging; every file with its SHA-256 |
| `01-overview/` | Analyst brief (PDF and Word), readiness status, gap register |
| `02-applicability/` | Statement of Applicability, control matrix (PDF and CSV) |
| `03-documented-information/` | Policy and procedure register; each document (PDF and Word) with its document-control block |
| `04-risk-and-impact/` | AI impact assessment register and each assessment |
| `05-evidence/` | Evidence index (PDF and CSV) and every collector snapshot (JSON, metadata only) |
| `06-internal-audit/` | Audit programme, audit reports with workpapers, corrective actions |
| `07-management-review/` | Review records and their frozen input packs |
| `08-source-record/` | The engagement YAML and Markdown the reports were generated from |
| `manifest.json`, `SHA256SUMS` | `manifest.json`: every file except itself and `SHA256SUMS`, with size and SHA-256, plus the engine and ReportLab versions. `SHA256SUMS`: every file, including the index and the manifest |

Artifacts the client holds elsewhere (contracts, tickets, screenshots) are not copied in. The index says where each one is, so the auditor can ask to see it.

## Verifying it

- `sha256sum -c SHA256SUMS` inside the package checks every file.
- The package is **reproducible**: running `grc --today <as-of> package --label <label>` at the same commit, with the same engine and ReportLab versions (both recorded in the manifest), produces byte-for-byte the same files and zip. Timestamps are fixed, and PDF, Word and zip output are deterministic. An auditor (or the client) can regenerate it and compare checksums.
- The source commit is marked `-dirty` if the engagement folder had uncommitted changes. Such a package can't be rebuilt from the commit alone, so release packages are always built from a clean checkout.
- `08-source-record/` contains only files tracked in git (when built in a repository), never symlinks or hidden files.
- The release also attaches `<name>-auditor-index.pdf` on its own, for quick reading.

PDFs use the standard PDF fonts, so a few symbols are written as text (for example `[OK]`, `>=`, `->`).
