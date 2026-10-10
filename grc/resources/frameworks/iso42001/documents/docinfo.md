# {{title}}

## Purpose

This procedure controls the documented information the AI management system needs: how it is created, approved, made available, protected, changed and retained.

## Creating and updating

AIMS documents and records are kept as version-controlled files in the GRC repository. Each document carries an identifier, title, owner, version and status (draft, in review, approved, retired). Changes are proposed in a pull request that shows exactly what changed.

AIMS documents:

{{document_register}}

## Approval

- A document is approved by a named approver who is not its author. The approval is recorded in the document (approver, date and a fingerprint of the approved text) and through the reviewed pull request.
- Any change to an approved document's text requires a new version and a new approval. Automated checks block an approved document whose text no longer matches its approval fingerprint.
- Records produced by processes (impact assessments, audit workpapers, risk entries, evidence) follow the approval rules of their own procedures.

## Control

- **Availability:** approved documents are published to [[TODO: e.g. the intranet / the reports branch]] for the people who need them.
- **Protection:** the repository is private; changes to `main` require review by the document's owner or approver [[TODO: confirm branch protection / CODEOWNERS]].
- **Distribution and access:** [[TODO]].
- **External documents** (e.g. contracts, standards, supplier documentation) needed for the AIMS are identified in [[TODO]] and controlled by reference.
- **Confidential artifacts** are not committed; the repository holds a pointer to where they live.

## Retention

| Information | Retention | Reason |
|---|---|---|
| Approved documents and superseded versions | [[TODO: e.g. life of the AIMS + 3 years]] | Certification and legal |
| Impact assessments, risk records, audit records | [[TODO]] | [[TODO]] |
| Evidence pointers and collector snapshots | [[TODO]] | [[TODO]] |

Git history is the version history; tagged releases freeze the record for each audit.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
