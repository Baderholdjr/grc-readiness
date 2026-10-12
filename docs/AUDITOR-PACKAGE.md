# Auditor package

A single, checksummed bundle of the record as of one commit, for the certification body (Stage 1, Stage 2, surveillance) or an internal reviewer.

## Producing it

- **For an audit:** publish a release from the GitHub UI (*Releases → Draft a new release*, tag e.g. `v2027.03-stage1`). The release workflow validates the record. Errors block the package; warnings are listed in it. It then attaches the reports, the auditor index PDF and the package zip to the release.
- **Locally or for a dry run:** `python -m grc package --out dist --label stage1`. Use `--force` only for a draft, when the record has validation errors; they are listed in the index.

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
| `manifest.json`, `SHA256SUMS` | Every file with its size and SHA-256 |

Artifacts the client holds elsewhere (contracts, tickets, screenshots) are not copied in. The index says where each one is, so the auditor can ask to see it.

## Verifying it

- `sha256sum -c SHA256SUMS` inside the package checks every file.
- The package is **reproducible**: running `grc package` at the same commit, with the same as-of date and engine version, produces byte-for-byte the same files and zip. Timestamps are fixed, and PDF, Word and zip output are deterministic. An auditor (or the client) can regenerate it and compare checksums.

PDFs use the standard PDF fonts, so a few symbols are written as text (for example `[OK]`, `>=`, `->`).
