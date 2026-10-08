# Intake

Drop client documents here, in a pull request, to draft the engagement record automatically.

**How:** On GitHub choose **Add file → Upload files**, select the documents, and choose
*Create a new branch … and start a pull request*. The **Ingest** workflow:

1. Imports any file that matches an intake template (see `templates/intake/`) exactly as written.
2. Sends every other document (Word, PDF, Excel, Markdown, text) to Claude to draft:
   client profile, AI usage, what's in place, AI inventory, gaps, evidence pointers, and
   client *claims* against the four-part evidence test. Every item cites its source.
   This only happens if `ingest: {ai_drafting: true}` is set in `engagement/engagement.yaml`
   and the `ANTHROPIC_API_KEY` secret exists.
3. Commits the drafted YAML to your PR and comments a report: what was added, open questions,
   anything dropped.

Nothing is ever marked `verified` by ingestion. Client statements become `claimed` legs; an
analyst confirms them with evidence in later PRs.

Files already ingested are listed with their hash in `.processed.yaml`; changed files are re-read.

**Confidentiality:** documents committed here live in this (private) repo's history, and with AI
drafting enabled their text is sent to the Anthropic API. Don't upload anything the client hasn't
agreed to share that way.
