# {{title}}

## Purpose

This procedure defines how {{client}} monitors and measures the AI management system and how it audits the AIMS internally.

## Monitoring and measurement

| What is measured | Method | Frequency | Who analyses | Reported to |
|---|---|---|---|---|
| Readiness of every requirement (four-part evidence test) | Automated validation of the GRC record | On every change and weekly | AIMS owner | Management review |
| Freshness of evidence | Automated expiry checks | Weekly | AIMS owner | Management review |
| AI system performance indicators | [[TODO]] | [[TODO]] | AI system owner | [[TODO]] |
| Progress on AI objectives | Objective tracker (DOC-OBJECTIVES) | Quarterly | AIMS owner | Management review |

Each requirement is evaluated against the evidence test:

{{evidence_test_table}}

## Internal audit

1. **Programme.** An audit programme covers the whole AIMS at planned intervals, at least [[TODO: e.g. annually]], prioritising areas by importance and past results. Each audit has scope, criteria, auditors and dates.
2. **Independence.** Auditors do not audit their own work: nobody audits a requirement they own.
3. **Planning.** A workpaper is prepared for each requirement in scope, with test steps.
4. **Sampling.** Samples are drawn reproducibly from defined populations. Default sample sizes:

{{sample_size_table}}

5. **Fieldwork.** Each sampled item is marked pass or exception with a note; each workpaper is concluded and reviewed by a second person.
6. **Reporting.** Results are reported to relevant management; nonconformities and opportunities for improvement are raised per DOC-IMPROVE.

## Records

The programme, workpapers, samples, findings and audit reports are kept in the GRC repository (`engagement/audit/`, `engagement/findings.yaml`) per DOC-DOCINFO.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
