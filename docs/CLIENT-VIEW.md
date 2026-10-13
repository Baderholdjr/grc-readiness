# Client view

The reports are written for the engagement team. The **client view** is written for the client's own people: control owners, the AIMS owner and executives. It answers three questions in plain language:

1. **Where do things stand?** Requirements fully ready, evidence checks complete, open gaps, policies approved, impact assessments approved, open nonconformities.
2. **What's coming up?** The next phases, internal audit, management review, and the Stage 1 and Stage 2 dates.
3. **What do you need from me?** Requests grouped by owner, overdue first:
   - for each requirement they own, what's still missing, leg by leg:
     - an approved document (naming the library document and its status)
     - showing where the process runs
     - records, using the requirement's own evidence examples
     - testing, where no action is needed until the internal audit
   - their open gaps, corrective actions, review actions, draft policies to complete or approve, and impact assessments to finish

   Requirements with no owner yet are collapsed into one "needs an owner" item.

**Left out on purpose:** hours and budget, the analyst's working rules and engagement risks, validation codes, and internal notes.

For an interactive version that clients can answer, see [the client site](CLIENT-SITE.md).

## Where to find it

Every build writes `client-view.html` and `client-view.md`, linked from the reports page as **Client view**.
- **`client-view.html`** is one self-contained file with no external resources, so it's safe to email or attach. It has an owner filter and an "overdue only" switch, and it prints cleanly. All record text is escaped, and a content-security policy blocks anything loading from outside.
- **`client-view.md`** reads directly on GitHub, for client staff who have access to the repository.

It is not part of the auditor package.

## Settings (optional, in `engagement.yaml`)

```yaml
client_view:
  intro: Weekly status for the AIMS working group.
  contact: Bernard Aderhold, engagement lead (bernard@example.com)
```
