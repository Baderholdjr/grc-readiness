# Policies and procedures (5.2, 7.5, and the *Documented* leg)

Every requirement's *Documented* leg needs a current, approved document. The engine keeps those documents as Markdown in the repository, drafts them from a library, and makes sure an "approved" document really is the text that was approved.

## Files

| File | Holds | Who edits |
|---|---|---|
| `engagement/documents/DOC-*.md` | One policy or procedure: YAML front matter (owner, author, version, status, approval) followed by the text | Drafted by the engine, completed by the analyst and client |
| Playbook `documents:` | The library: 17 documents, their templates, the requirements each one supports, and the sections each must keep | Engine default; a client repo can override the playbook or any template |
| `frameworks/iso42001/documents/*.md` | The templates | Engine default; overridable per client |

The 17 library documents cover all 65 ISO 42001 requirements exactly once: scope and context, AI policy, roles and reporting concerns, risk, impact assessment, objectives and changes, people, documented information, AI resources, lifecycle, data, information for users, responsible use, third parties, monitoring and internal audit, management review, and improvement. Template wording is our own; it paraphrases the standard rather than reproducing it.

## Workflow

1. **Draft.** Run **Actions → Policies and procedures** with `new` and `all` (or one `DOC-…` id). Locally: `python -m grc docs new all`.
   Templates are filled from the engagement record: client, scope, owners, AI inventory, suppliers, and the engine's own methods (impact assessment scales and thresholds, audit sample sizes, the evidence test), so each procedure describes what the engine actually enforces. Each document's owner is suggested from the owners of the controls it supports. Whatever the record can't supply is left as a `[[TODO: …]]` marker.
2. **AI fill (optional).** If AI drafting is on (`ingest: {ai_drafting: true}` and `ANTHROPIC_API_KEY`, or sandbox mode), `new` also asks Claude to fill the markers, and `fill` does it for drafts later. Safeguards, enforced in code:
   - only `[[TODO]]` markers are replaced; every other character of the document, including the front matter, stays as it was. A marker can't span lines, so an unclosed `[[TODO` can't swallow text
   - each fill must cite its source (the engagement record or a named client document in `intake/`); unsourced fills are dropped
   - fills are flattened to one line of plain text: brackets, braces, `<`, `>` and backticks are removed (so no markers, placeholders, links, HTML or code), a fill that starts a line can't start a heading, list, quote or table, pipes are neutralised inside tables, and length is capped
   - only drafts are filled; approved documents are never touched
   - the PR lists every fill with its source and the model's open questions
3. **Complete.** In PRs, the analyst and client resolve every remaining `[[TODO]]`, and set `owner` and `author`. CI shows each draft as **W141**.
4. **Approve.** Run the workflow with `approve`, the document id and the approver (or `python -m grc docs approve DOC-AI-POLICY --approver "Chief Executive Officer"`). The command refuses unless:
   - there are no `[[TODO]]` markers or unfilled placeholders
   - the library's required sections are all present
   - owner, author and version are set, and the approver isn't the author (same identity rules as audits and impact assessments)
   - the date isn't in the future

   It then records the approver, date and a SHA-256 **fingerprint** covering the text *and* the approval details (id, title, version, approver, date, requirements), clears any `next_review` left from an earlier approval, and appends to `history`. The front matter is rewritten on approval (YAML comments in it are not kept). **Merging that PR is the approval**, so the approver (or someone on their documented instruction) should review and merge it.
5. **Cite it.** On each requirement the document supports, cite it on the *Documented* leg (e.g. `evidence: [DOC-AI-POLICY]`). An approved document counts as `document` evidence with `approved_by`, which is what E012 requires. **W143** lists the requirements where it isn't cited yet.
6. **Change it.** Edit the text, set status back to `draft`, bump `version`, and approve again. Re-approving the same version with different text is refused.
7. **Review it.** When a document is due (W142) and nothing needs to change, approve it again: same version, same text, new date.

## Rules

| Code | Severity | Rule |
|---|---|---|
| E001 | error | Front matter missing, invalid YAML, or doesn't match the schema |
| E040 | error | File name and `id` differ, or the document claims an unknown requirement |
| E041 | error | Marked approved but incomplete: TODOs or any leftover `[[…]]`, missing sections, no owner/author/approver/date/version, approver is the author, future date |
| E042 | error | Marked approved without a fingerprint (not approved through `grc docs approve`), or the text or approval details (title, version, approver, date, requirements) changed after approval |
| E015 / E007 | error | A *Documented* leg is verified on a document that isn't soundly approved / is past its review |
| E013 / E024 | error | A gap is closed, or a finding cites, a document that isn't soundly approved |
| W140 | warning | Library documents not started yet |
| W141 | warning | Document is a draft or in review |
| W142 | warning | Past its review date (every 365 days from approval, set in the library; a document's `next_review` can only bring it forward) |
| W143 | warning | Approved document not yet cited on the requirements it supports |

## Reports

`documents.md` lists every library document with status, version, owner, approval, next review and the number of items left to complete. Each document has its own page (`doc-DOC-….md`) and a Word file (`doc-DOC-….docx`) in the house style, with a document-control block; drafts are marked **DRAFT**. Word files are reproducible: the same text produces the same file (stamped with the approval date, or the date drafted).

The engine checks that a document is complete, approved by someone other than its author, and unchanged since approval. Whether its content is right for the client is for the author, the approver and, later, the auditor.
