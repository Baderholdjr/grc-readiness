# Management review (9.3)

Top management must review the AI management system at planned intervals, consider a fixed set of inputs, and record decisions and actions. The engine assembles those inputs from the record, freezes what was presented, checks the minutes are complete, and chases the actions.

## Files

| File | Holds | Who edits |
|---|---|---|
| `engagement/reviews/MR-YYYY-NN.yaml` | One review: planned and held dates, chair, attendees, notes against every input, decisions, actions, minutes approval | Scheduled by the engine; completed by the AIMS owner |
| `engagement/reviews/MR-YYYY-NN-pack.md` | The input pack: what management was shown, generated from the record | Generated only; never edited |
| Playbook `management_review:` | Required inputs, review cycle (365 days), Stage 1 warning window (60 days) | Engine default; overridable |

A new engagement schedules its first review at the end of the Test phase, before Stage 1.

## Running a review

1. **Schedule.** Run **Actions → Management review** with `new` and the planned date (or `python -m grc review new 2027-02-22`). Set the chair and attendees in the PR.
2. **Prepare the pack.** Shortly before the meeting, run the workflow with `pack` and the review id. The pack is generated from the record as of that day, one section per required input:
   1. **Previous actions:** every action from earlier reviews, with overdue ones flagged.
   2. **Context changes:** AI systems in scope, the scope document's status, and documents approved since the last review.
   3. **Interested parties:** findings raised from incidents and monitoring, plus discussion prompts.
   4. **Performance:** readiness and the evidence-test breakdown; nonconformities by grade and status, and overdue ones; expired evidence and failing automated checks; internal audit results; the objectives document.
   5. **Risks and impacts:** each AI system's impact assessment (status, highest residual risk, accepted risks, conditions, next review), and open gaps by severity.
   6. **Improvement:** open OFIs, and policies and procedures not yet approved.
   7. **Resources:** requirements without an accountable owner, plus discussion prompts. Consulting hours are not included; they are the engagement team's economics.

   The record stores the pack's date and SHA-256. Merge the PR and circulate the pack (Markdown, or Word from the reports). You can refresh it until the review is held; after that it is frozen.
3. **Record the meeting.** In a PR, set `status: held`, `held_on`, `chair`, `attendees`; write `notes` for **every** input; record `decisions` (record "no change needed" explicitly if that was the decision) and `actions` with an owner and due date. CI blocks an incomplete record (**E051**).
4. **Track actions.** Actions become GitHub Issues (label `grc-review-action`), assigned to their owners, with overdue reminders. Close an action with `status: done`, `closed_on` and `evidence`.
5. **Approve the minutes.** Set `minutes_approved_by` and `minutes_approved_on`. A held review with approved minutes can be cited as evidence (`MR-2027-01`), for example on 9.3's *Implemented* and *Evidence exists* legs. It stays current for the review cycle.
6. **Close it.** Once every action is done or cancelled, set `status: closed`.

## Rules

| Code | Severity | Rule |
|---|---|---|
| E050 | error | File/id mismatch, duplicate decision or action ids, unknown input |
| E051 | error | Held or closed but incomplete: no date (or a future one), chair, attendees, notes for every input, or decisions; no input pack, a pack changed after it was generated, or a pack dated after the meeting; minutes approval missing (when closed) or dated before the meeting or in the future; closed with open actions |
| E052 | error | Action without owner or due date; done without `closed_on` and evidence; review closed with open actions |
| E015 / E007 | error | A leg is verified on a review that isn't held with approved minutes / is older than the review cycle |
| W150 | warning | Planned date has passed but the review isn't recorded as held |
| W151 | warning | No review held within the cycle, or none held and Stage 1 is within 60 days |
| W152 | warning | Action overdue |
| W153 | warning | 9.3 marked verified but no review recorded as held |

The engine checks that the review happened as recorded, considered every required input, and followed through on its actions. Whether management's decisions are good ones is for management and, later, the auditor.
