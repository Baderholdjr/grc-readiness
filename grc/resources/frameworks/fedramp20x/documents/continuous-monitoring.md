# {{title}}

## Purpose

This procedure sets how {{client}} reports on its cloud service offering to agency customers after certification: the Ongoing Certification Report (OCR) every 3 months, the feedback on each report, and the Quarterly Review meeting.

These rules apply to Class B and C. For Class A, CCM-OCR-AVL and CCM-OCR-NRD are also mandatory (FRC-CLA-MFR).

## Ongoing Certification Reports

{{client}} must supply an OCR to all necessary parties every 3 months, covering the whole period since the previous report, in a consistent, human-readable format (CCM-OCR-AVL). Each report must include high-level summaries of at least the following, where applicable:

- changes to FedRAMP certification data;
- planned changes to certification data during at least the next 3 months;
- accepted vulnerabilities (see DOC-FR-VULN);
- transformative changes (see DOC-FR-SCN);
- updated recommendations or best practices for security, configuration, usage or similar aspects of the offering;
- a list of all agencies directly using the product;
- FedRAMP Reportable Incidents, or an attestation that none occurred;
- lessons learned, and changes planned or made, as a result of FedRAMP Reportable Incidents, if any occurred.

The report also follows the OCR schema (https://fedramp.gov/schemas/fedramp-ongoing-certification-report-schema-2026-06-24.json) and carries the FedRAMP ID. It is delivered through [[TODO: delivery method, e.g. trust center plus notice to agency contacts]]. Before the first real report, a sample report with all required information goes in the certification package.

Report owner: [[TODO: role]]. Inputs come from the vulnerability, change, incident and trust center records, gathered by [[TODO: report generation tool or script]].

### Cycle

{{client}} should set a regular 3-month cycle for OCRs that is spread away from the beginning, middle or end of each quarter, so agencies are not flooded at the same time (CCM-OCR-SOR). {{client}}'s cycle: [[TODO: release dates, e.g. the 3rd week of Feb, May, Aug, Nov]]. Widely used providers are encouraged to agree the timing with customers. If {{client}} does not follow this, the reason and the resulting risk to customers are recorded in the security decision record (see DOC-FR-PACKAGE) and accepted by a senior official.

{{client}} must publish the target date of its next OCR with its other public certification data (CCM-OCR-NRD). The date is updated on the public information page (see DOC-FR-TRUST) when each report is released.

## Agency feedback

{{client}} must provide an asynchronous way for all necessary parties to give feedback or ask questions about each OCR (CCM-OCR-FBM). The mechanism is [[TODO: e.g. a monitored mailbox or a trust center discussion feature]], and how to reach it is stated in each report.

{{client}} must supply an anonymized and desensitized summary of the feedback, questions and answers about each OCR, either as an addendum to that report or in the next report (CCM-OCR-AFS). The summary removes agency names, people's names and sensitive details. The report owner updates the addendum [[TODO: cycle, e.g. every 2 weeks]] during the quarter, which reduces repeated questions.

## Quarterly Reviews

Quarterly Review meeting (CCM-QTR-MTG):

- Class B: should host a synchronous Quarterly Review every 3 months, open to all necessary parties, covering the parts of the most recent OCRs {{client}} judges most relevant to agencies;
- Class C: must host it.

For Class B, if {{client}} does not hold Quarterly Reviews, the reason and resulting risk are recorded in the security decision record and accepted by a senior official.

When reviews are held:

- {{client}} must supply all necessary parties with a registration link or a downloadable calendar file with the meeting details (CCM-QTR-REG): [[TODO: registration URL or calendar file location]].
- {{client}} must publicly supply the target date of the next Quarterly Review with its other public certification data (CCM-QTR-NRD).
- {{client}} should schedule each review at least 3 business days after releasing an OCR and within 10 business days of that release (CCM-QTR-SAR).
- {{client}} should add other information it judges to be of interest, use or relevance to agencies (CCM-QTR-ACT), for example [[TODO: topics such as roadmap security features or configuration tips]].
- {{client}} should record or transcribe each review and supply the recording or transcript to all necessary parties (CCM-QTR-RTR), stored at [[TODO: location]].
- {{client}} should not invite third parties unless they have specific relevance, because agencies take part less when third parties attend; the independent assessor counts as relevant by default (CCM-QTR-RTP).

If {{client}} does not follow CCM-QTR-SAR, CCM-QTR-ACT, CCM-QTR-RTR or CCM-QTR-RTP, the reason and resulting risk are recorded in the security decision record and accepted by a senior official.

Host: [[TODO: role who runs the review]].

## Sensitive information

{{client}} must not irresponsibly disclose sensitive information in an OCR that would likely have an adverse effect on the offering (CCM-OCR-LSI), nor in a Quarterly Review (CCM-QTR-NID).

Before release, a second person checks the report and the review material for credentials, exploitable technical detail, unremediated weakness specifics and personal information about staff. Specifics that could lead to compromise are abstracted; accurate risk information is kept. In the live meeting, the host declines questions whose answers would expose such detail and offers a follow-up through the trust center instead.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
