# Security questionnaires

Customers send security questionnaires before they buy. Universities send the **HECVAT** (Higher Education Community Vendor Assessment Toolkit, published by EDUCAUSE). The engine answers them from the compliance program, so an answer rests on a control and its evidence, not on memory. Every answer is approved by a person before it leaves.

Built in: **HECVAT 4** (`hecvat-4`, tested with version 4.1.4: 331 questions across the Start Here, Organization, Product, Infrastructure, IT Accessibility, Case-Specific, AI and Privacy tabs).

## How it works

```
questionnaires/
  profile.yaml                  company facts: provider and solution name, contact, headquarters
  library.yaml                  approved answers, reused by every later questionnaire
  hecvat-state-university/
    questionnaire.yaml          who asked, when it's due, status (open, sent, withdrawn)
    received.xlsx               the workbook as received, never changed
    questions.yaml              every question: where its answer goes, which answers its dropdown allows
    answers.yaml                one entry per question: answer, detail, status, what backs it, owner
```

1. **Import.** Upload the workbook you received to `questionnaires/inbox/` (on GitHub: **Add file → Upload files**), then run **Actions → Security questionnaire** with `import`, a name, the requester and the due date. The workflow opens a pull request with the questionnaire and a first draft.
2. **Draft.** For every question, the engine proposes an answer where it can (below) and marks the rest `needs_answer`, with the person who should answer it.
3. **Review and approve** in the pull request. For each answer you accept, set `status: approved`, `approved_by` and `approved_on`. To answer one yourself, write `answer` and `detail`, set `source: person`, then approve it. Re-running `draft` never overwrites an approved answer or one a person wrote.
4. **Fill.** Run the workflow with `fill`. It writes the approved answers into a copy of the workbook and attaches it to the run (**Artifacts**, kept 7 days). Unapproved questions stay blank. With `draft: true` it also writes proposed answers, each detail prefixed `[DRAFT - not approved]` and the date-completed cell reading `DRAFT, not approved`, for internal review only.
5. **Send** the workbook, then set `status: sent` and `sent_on` in `questionnaire.yaml`.
6. **Learn.** Run `learn`. Approved answers go into `library.yaml`, and the next questionnaire starts from them.

From the command line: `python -m grc questionnaire import|draft|fill|learn|report|validate` (`--name`, `--workbook`, `--requester`, `--due`, `--draft`, `--out`).

## Where proposed answers come from

In this order, for each question:

| Source | When | Status |
|---|---|---|
| Start Here gate | A scoping question (REQU-01 to REQU-08) is answered **No**: its section is switched off, as HECVAT instructs ("DO NOT complete…") | `not_applicable` |
| Answer library | An approved library answer for this question, approved within its review period (default 365 days) | `proposed` |
| Company profile | The general questions (GNRL-01 to 09) from `profile.yaml` | `proposed` |
| Program hint | REQU-04 (AI features) when an ISO 42001 record exists; REQU-05 (HIPAA) when a HIPAA record exists | `proposed` |
| Controls | The question is mapped to framework requirements, and **every** mapped program control has current evidence, **every** mapped requirement is Ready, and none has an open gap. Then the workbook's compliant answer is proposed, but only when that answer is Yes: a control shows something is done, it can't prove a negative ("No, staff can't see customer data"). The control's description, or the record's implementation statement, becomes the detail | `proposed` |
| Nothing fits | | `needs_answer` |

Every entry records its **backing**, so a reviewer can see what an answer rests on:

| Backing | Meaning |
|---|---|
| `supported` | Every mapped control has current evidence and every mapped requirement is Ready, with no open gap |
| `partial` | Work under way, or evidence missing or out of date |
| `gap` | Mapped requirements not started, or with open gaps |
| `unmapped` | No mapped control: the answer rests on knowledge, not evidence |
| `n/a` | Company facts and scoping questions |

The `basis` list names the controls and requirements, with their state and any open gaps, and `owner` is the owner of the first mapped control: the person to ask. `draft` refreshes the backing of approved and person-written answers too (never the answer itself), and Q104 works it out afresh, so an approved claim is flagged as soon as a gap opens behind it. A reviewer's `notes:` on an entry are kept.

**The mapping.** `grc/resources/questionnaires/hecvat-4.yaml` maps 218 of the 331 questions to requirements in ISO 27001, SOC 2, HIPAA, ISO 42001 and NIST SP 800-53. It is our judgement: some links are loose, and a reviewer must check each answer against the question as written. A program control counts when its `maps:` shares a requirement with the question; a record counts when it is the framework of a mapped requirement.

## Validation

`questionnaire validate` runs in the *Validate* workflow when `questionnaires/` exists.

| Code | Severity | Meaning |
|---|---|---|
| Q101 | error | A file doesn't match its schema (an unknown status, a malformed date) |
| Q102 | error | An answer isn't one of the workbook's dropdown choices for that question |
| Q103 | error | Approved without an answer, `approved_by` or `approved_on`; a library entry without an approver |
| Q104 | warning | An approved compliant answer whose controls aren't in place (backing `gap`) |
| Q105 | error | A library entry with a duplicate id or naming a question that doesn't exist |
| Q106 | warning | A library answer is past its review date; drafts stop using it until it is approved again |
| Q107 | warning | The questionnaire is due within 7 days, or overdue, with answers not approved |
| Q108 | error | An answer for a question not in the workbook, or a question answered twice |
| Q109 | warning | An approved answer in a section a Start Here answer switched off (fill leaves it blank) |
| Q110 | info | Questions with no entry yet: run `draft` |
| Q111 | error | An answer or detail a workbook can't hold: control characters (often pasted from Word or a PDF), or more than 32,767 characters |

`fill` refuses to write any answer with an error (or Q109), lists them and fails, and the workflow runs `validate` before `fill`, so nothing with an error leaves.

YAML reads an unquoted `Yes` or `No` as true or false; the engine turns them back into the words.

## The workbook

The filled workbook is the received one with only the answer cells, the Additional Information cells and the date-completed cell changed. The engine edits the sheet XML directly, so the dropdowns, formulas, conditional formatting, hidden scoring sheets and the institution's evaluation tabs are all kept. The workbook is set to recalculate when opened, so the guidance and scores update in Excel.

The question text belongs to EDUCAUSE. The engine ships no workbook and no question text: it reads them from the copy you received, which stays in the client's private repository.

## Boundaries

- **Nothing is approved automatically.** `draft` proposes; `fill` writes approved answers only, unless asked for a marked draft.
- **A proposed Yes is a starting point, not a finding.** It means a mapped control is in place with current evidence, not that the control answers the question fully. Read the question.
- **Answers are statements by the client** to its customer. Legal and contractual questions (insurance, breach history, contract terms) go to the people who own them.
