# (Example Client) — ISO 42001 gap assessment

As of 2026-11-14. Prepared from the information (Example Client) provided: its existing controls, policies and earlier assessments. What it reports as in place is its own statement until the engagement team has tested it.

## 1. Summary

**65** requirements of ISO 42001 apply to (Example Client).

| Coverage | Requirements | Share | What it means |
|---|---|---|---|
| Verified | 0 | 0% | Tested by the engagement team: documented, in use, with records, and tested |
| Reported in place | 14 | 22% | An existing control covers it and is reported as working; to be tested |
| Partly in place | 4 | 6% | Something is written down or under way, not yet in use |
| Gap | 34 | 52% | A known gap must be closed (section 3) |
| No existing control | 13 | 20% | Nothing found yet (section 4) |


## 2. Coverage by area

| Area | In scope | Verified | Reported in place | Partly in place | Gap | No existing control |
|---|---|---|---|---|---|---|
| Context of the organization | 4 |  |  |  | 3 | 1 |
| Leadership | 3 |  |  |  | 3 |  |
| Planning | 6 |  | 1 | 1 | 2 | 2 |
| Support | 5 |  | 1 | 1 | 2 | 1 |
| Operation | 4 |  | 2 |  | 2 |  |
| Performance evaluation | 3 |  | 1 |  | 2 |  |
| Improvement | 2 |  | 1 |  |  | 1 |
| Policies related to AI | 3 |  |  |  | 1 | 2 |
| Internal organization | 2 |  |  |  | 2 |  |
| Resources for AI systems | 5 |  | 3 |  | 2 |  |
| Assessing impacts of AI systems | 4 |  |  |  | 4 |  |
| AI system life cycle | 9 |  | 4 | 1 | 3 | 1 |
| Data for AI systems | 5 |  |  |  | 3 | 2 |
| Information for interested parties of AI systems | 4 |  | 1 |  | 2 | 1 |
| Use of AI systems | 3 |  |  | 1 | 1 | 1 |
| Third-party and customer relationships | 3 |  |  |  | 2 | 1 |


## 3. Gaps to close

| Gap | Severity | Area | Finding | Requirements | Owner | Due |
|---|---|---|---|---|---|---|
| GAP-01 | high | AIMS governance | No producer-scope AIMS AI policy yet; scope draft still needs leadership approval. | 5.2, 4.3, A.2.2 | VP Engineering | 2026-11-20 |
| GAP-10 | high | Statement of Applicability | No SoA exists; Annex A applicability and justifications must be decided and approved. | 6.1.3 | Security & Compliance | 2026-11-20 |
| GAP-02 | high | Impact assessment | No AI impact assessments have been completed; methodology/template must be established and used. | 6.1.4, 8.4, A.5.2, A.5.3, A.5.4, A.5.5 | Head of Responsible AI | 2026-12-18 |
| GAP-05 | high | AI suppliers | AI-specific suppliers have not yet been run through the existing vendor program; supplier contract/DPA requirements are incomplete. | A.10.2, A.10.3, 8.1 | Security & Compliance | 2026-12-18 |
| GAP-08 | high | Internal audit | No standalone AI/AIMS internal audit program or completed AI-scoped internal audit exists. | 9.2 | Security & Compliance | 2027-01-22 |
| GAP-11 | medium | Roles | AIMS roles and responsibilities are not documented in a RACI. | 5.3, A.3.2 | VP Engineering | 2026-11-13 |
| GAP-04 | medium | Data governance | Existing classification taxonomy does not yet cover AI artifacts such as corpora, datasets, checkpoints, and delivered models. | A.4.3, A.7.2, A.7.4 | Security & Compliance | 2026-11-25 |
| GAP-06 | medium | Control codification | Some human-review and engineering practices operate in code/process but are not fully reflected in policy text. | A.6.1.3, A.6.2.4, A.6.2.5, A.7.5, A.9.4 | Head of Platform | 2026-11-30 |
| GAP-07 | medium | Regulatory mapping | Formal per-market AI regulatory/contractual mapping has not yet been performed. | 4.1, 4.2, A.8.5 | Legal | 2026-11-30 |
| GAP-12 | medium | Concern reporting | No internal or external channel for reporting AI concerns or adverse impacts. | A.3.3, A.8.3 | Legal | 2026-12-11 |
| GAP-03 | medium | Training & competence | AI-specific training is planned but not yet operating. | 7.2, 7.3, A.4.6 | People Operations | 2026-12-18 |
| GAP-09 | medium | Management review | AI is discussed in quarterly leadership review, but a dedicated standing AI/AIMS review structure needs to be formalized. | 9.3, 5.1 | VP Engineering | 2027-01-29 |


## 4. Requirements with no existing control

Nothing in the information provided covers these 13 requirement(s). Each needs a control, or evidence that one already exists.

| Requirement | Title | Area |
|---|---|---|
| 4.4 | AI management system | Context of the organization |
| 6.2 | AI objectives and planning to achieve them | Planning |
| 6.3 | Planning of changes | Planning |
| 7.4 | Communication | Support |
| 10.1 | Continual improvement | Improvement |
| A.2.3 | Alignment with other organizational policies | Policies related to AI |
| A.2.4 | Review of the AI policy | Policies related to AI |
| A.6.2.7 | AI system technical documentation | AI system life cycle |
| A.7.3 | Acquisition of data | Data for AI systems |
| A.7.6 | Data preparation | Data for AI systems |
| A.8.2 | System documentation and information for users | Information for interested parties of AI systems |
| A.9.3 | Objectives for responsible use of AI system | Use of AI systems |
| A.10.4 | Customers | Third-party and customer relationships |


## 5. (Example Client)'s existing controls

No control register has been imported. To include one, upload the export from your GRC tool or your control spreadsheet to the intake folder.


## 6. Remediation roadmap

| Phase | Dates | Objective | Gaps planned |
|---|---|---|---|
| OCT 2026 | 2026-10-01 – 2026-10-31 | Validate & establish | — |
| NOV 2026 | 2026-11-01 – 2026-11-30 | Build governance | GAP-01, GAP-10, GAP-11, GAP-04, GAP-06, GAP-07 |
| DEC 2026 | 2026-12-01 – 2026-12-31 | Implement & evidence | GAP-02, GAP-05, GAP-12, GAP-03 |
| JAN 2027 | 2027-01-01 – 2027-01-31 | Test the AIMS | GAP-08, GAP-09 |
| FEB 2027 | 2027-02-01 – 2027-02-28 | Stage 1 | — |
| MAR–APR 2027 | 2027-03-01 – 2027-04-30 | Stage 2 & closure | — |



## 7. Basis and limits

- What a control register, policy or earlier report says is a statement, not proof. A requirement is **Verified** only when the engagement team has seen it documented, in use, with records, and tested.
- Earlier audit reports cover their own period and scope, which may differ from this one.
- Mappings between the client's controls and the requirements were read from the client's own register; an analyst checks them.

Information reviewed:
- (none recorded)
