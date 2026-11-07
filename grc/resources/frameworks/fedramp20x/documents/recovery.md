# {{title}}

## Purpose

This plan sets how {{client}} defines recovery objectives for its cloud service offering, keeps recovery plans and backups aligned with them, and tests recovery. It covers four Key Security Indicators that Class B and C must show. They are not in FedRAMP's mandatory Class A list (FRC-CLA-MFR), so Class A need not show them.

Each indicator is shown with measures and their objectives, run persistently on a known cycle, with machine-readable evidence produced automatically where practical. The measures are summarized in the security decision record (see DOC-FR-PACKAGE).

Recovery owner: [[TODO: role]].

## Recovery objectives

Key Security Indicator: Recovery Time Objectives (RTO) and Recovery Point Objectives (RPO) are defined and persistently reviewed for alignment with {{client}}'s business needs and capabilities (KSI-RPL-RRO).

| Service or component | RTO | RPO | Basis |
| --- | --- | --- | --- |
| [[TODO: core service]] | [[TODO: RTO]] | [[TODO: RPO]] | [[TODO: customer commitments or business impact analysis]] |

The objectives are reviewed at least [[TODO: cycle]], when customer commitments change, and after any recovery test or real recovery that missed them. Each review is recorded.

## Recovery plan

Key Security Indicator: the alignment of recovery plans with the defined recovery objectives is persistently reviewed (KSI-RPL-ARP).

The recovery plan at [[TODO: location]] covers:

- the scenarios planned for, for example loss of an availability zone or region, data corruption, ransomware, loss of a key supplier, and loss of the identity provider;
- roles, decision authority and how recovery is declared;
- the runbooks for each scenario, automated where practical;
- communication to agencies, including incident reports where the event is a FedRAMP Reportable Incident (DOC-FR-INCIDENT) and availability updates (DOC-FR-TRUST).

Measures: runbooks whose tested recovery time meets the RTO; plan sections changed after each review. Cycle: persistently, reviewed at least [[TODO: cycle]] and after significant changes.

## Backups

Key Security Indicator: the alignment of machine-based information resource backups with the defined recovery objectives is persistently reviewed (KSI-RPL-ABO).

- Backups of [[TODO: data stores and configuration]] are taken by [[TODO: backup service]] at a frequency that meets the RPO.
- Backups are encrypted, kept in [[TODO: separate account or region]], and protected from deletion or change for [[TODO: retention period]].
- Backup jobs and their success are monitored, and a failed backup is treated as a vulnerability (see DOC-FR-VULN).

Measures: backup success rate; actual backup interval compared with the RPO; resources in the inventory without a backup policy. Cycle: persistently, checked automatically on every backup run.

## Testing recovery

Key Security Indicator: the capability to recover from incidents and contingencies in line with the defined recovery objectives is persistently tested (KSI-RPL-TRC).

- Restore tests of [[TODO: data stores]] run at least [[TODO: cycle]], automated where practical.
- Failover tests of [[TODO: services]] run at least [[TODO: cycle]].
- A full scenario exercise involving the recovery team runs at least [[TODO: cycle]].

Each test records the time achieved against the RTO and the data loss against the RPO. Gaps become tracked actions, and the objectives, plan or backups are changed as needed.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
