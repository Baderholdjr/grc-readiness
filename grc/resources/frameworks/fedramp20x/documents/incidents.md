# {{title}}

## Purpose

This procedure sets how {{client}} evaluates incidents affecting its cloud service offering, rates their impact on agencies, reports FedRAMP Reportable Incidents, and learns from them. It sits alongside {{client}}'s general incident response plan at [[TODO: location of the incident response plan]].

An incident is an occurrence that actually or imminently jeopardizes, without lawful authority, the integrity, confidentiality or availability of information or an information system, or that violates or imminently threatens to violate law, security policies, security procedures or acceptable use policies (44 USC 3552).

Applicability: IEC-CSO-EFR and IEC-CSO-FIR apply to every class (EFR through FedRAMP's mandatory Class A list, FRC-CLA-MFR). IEC-CSO-IIR and IEC-CSO-OIR are MUST for Class B and C and SHOULD for Class A. The remaining IEC rules apply to Class B and C. Class B and C must show the three Key Security Indicators; Class A must show only KSI-INR-RIR, the one in FedRAMP's mandatory Class A list.

## Evaluating reportability

{{client}} must promptly evaluate each incident to decide whether it affects, or is likely to affect, the confidentiality or integrity of federal customer data. If so, it is a FedRAMP Reportable Incident and is reported under this procedure (IEC-CSO-EFR).

- The incident lead records the evaluation in [[TODO: incident tracking tool]] with the time it was completed and the reason for the decision.
- Federal customer data means data agencies or their users upload or store in the service; it does not include account information, service metadata or telemetry {{client}} generates.
- When unsure, the incident is treated as reportable until the evaluation shows otherwise.

The evidence set keeps an incident log with one or more evaluations and their reasons. Simulated incidents may be used until real ones exist.

## Rating the impact

(Class B and C) {{client}} must treat each FedRAMP Reportable Incident as Potential Agency Impact N-rating (PAIN) 5 unless it promptly estimates the rating as below (IEC-CSO-DPR).

(Class B and C) {{client}} should promptly estimate the likely adverse impact on agency customers and assign a PAIN rating; this is incident rating (IEC-CSO-EFI):

| Rating | Likely effect |
| --- | --- |
| N1 | minimal customer effect on 1 or more agencies |
| N2 | narrow customer effect on 1 or more agencies |
| N3 | disruptive customer effect on 1 agency |
| N4 | debilitating customer effect on 1 agency, or disruptive customer effect on more than 1 agency |
| N5 | debilitating customer effect on more than 1 agency |

Customer effects, as FedRAMP defines them:

- minimal: noticeable only by some users, such as reduced performance;
- narrow: interrupts use for some users for less than 12 hours, or compromises an extremely limited amount and type of federal customer data;
- disruptive: interrupts use for many users for less than 24 hours, or compromises large amounts or many types of federal customer data;
- debilitating: interrupts use for most users, or compromises most federal customer data. An unknown effect is treated as debilitating until shown otherwise.

The rating and its explanation are recorded and revisited as facts change. If {{client}} does not rate incidents, every reportable incident stays at N5, and the reason and resulting risk to customers are recorded in the security decision record (see DOC-FR-PACKAGE) and accepted by a senior official.

## Initial Ongoing and Final Incident Reports

Reports go to all affected parties: FedRAMP at fedramp_security@fedramp.gov, each affected agency through its own incident reporting procedure, and optionally the trust center. Reports carry the FedRAMP ID and follow the incident report schema (https://fedramp.gov/schemas/fedramp-incident-report-schema-2026-06-24.json). Agency incident contacts are kept in [[TODO: location of agency incident contacts]].

Reports are responsible: they give agencies what they need to act without exposing details that would help an attacker.

### Initial Incident Report

After identifying a FedRAMP Reportable Incident, {{client}} notifies all affected parties with an Initial Incident Report (IEC-CSO-IIR), giving as much of the following as is known:

- contact information for the federal incident response coordinator: [[TODO: role and contact]];
- {{client}}'s internal tracking identifier;
- a description of the incident;
- a timeline: start time, time and source of detection, time the reportability evaluation was completed, and other major milestones;
- the historical and current PAIN rating, with the explanation of the evaluation;
- the functional impact on agencies, including confidentiality or integrity impact and the federal customer data types affected;
- the estimated recovery plan, milestones and timelines;
- the list of likely affected agencies.

### Ongoing Incident Reports

While response continues, {{client}} notifies all affected parties of ongoing activity as new information becomes available, including updates (or no change) to everything previously reported and, as available: observed activity, indicators of compromise, related CVE identifiers, root cause, and response and recovery activities (IEC-CSO-OIR).

### Final Incident Report

Once the incident is resolved and recovery is complete, {{client}} must notify all affected parties with a Final Incident Report, with final updates to everything previously reported (IEC-CSO-FIR).

### Timeframes by class and PAIN rating

| Report | Class | N1 | N2 | N3 | N4 | N5 |
| --- | --- | --- | --- | --- | --- | --- |
| Initial (IEC-CSO-IIR) | A (should), B (must) | 1 business day | 1 business day | 6 hours | 6 hours | 6 hours |
| Initial (IEC-CSO-IIR) | C (must) | 1 business day | 24 hours | 1 hour | 1 hour | 1 hour |
| Ongoing (IEC-CSO-OIR) | A (should), B (must) | 1 business day | 1 business day | 1 business day | 1 business day | 1 business day |
| Ongoing (IEC-CSO-OIR) | C (must) | 1 business day | 24 hours | 6 hours | 6 hours | 6 hours |
| Final (IEC-CSO-FIR) | A and B (must) | 3 business days | 3 business days | 3 business days | 3 business days | 3 business days |
| Final (IEC-CSO-FIR) | C (must) | 1 business day | 1 business day | 6 hours | 6 hours | 6 hours |

{{client}} applies these as: initial report within the timeframe after the incident is identified as reportable; ongoing reports at least that often while response continues; final report within the timeframe after recovery is complete. [[TODO: confirm this reading with the assessor]].

For Class A, if {{client}} does not send initial or ongoing reports, the reason and resulting risk are recorded in the security decision record and accepted by a senior official.

### Automation

(Class B and C) {{client}} should use automation to minimize human intervention in reporting FedRAMP Reportable Incidents (IEC-CSO-AIR). Reports are generated from the incident record by [[TODO: tool or integration]] rather than hand-written emails. If {{client}} does not do this, the reason and resulting risk are recorded in the security decision record and accepted by a senior official.

## After action reports

Key Security Indicator: incident after action reports are generated and lessons learned are persistently incorporated (KSI-INR-AAR).

- Measures: an after action report exists for every [[TODO: which incidents, e.g. every reportable incident and every incident above a set severity]] within [[TODO: days after closure]]; each lesson becomes a tracked action with an owner; the share of actions closed on time.
- Cycle: persistently, on every qualifying incident, with open actions checked [[TODO: cycle]].
- Evidence: machine-readable records from [[TODO: incident and ticketing tools]], collected automatically where practical.

Lessons from FedRAMP Reportable Incidents are also summarized in the next Ongoing Certification Report (see DOC-FR-CONMON).

## Reviewing procedures and past incidents

Key Security Indicator: the effectiveness of documented incident response procedures is persistently reviewed (KSI-INR-RIR).

- Measures: exercises or tabletop tests of this procedure and the incident response plan [[TODO: cycle]]; time to evaluate reportability and time to each report compared with the timeframes above; findings tracked to closure.
- Cycle: persistently, at least [[TODO: cycle]] and after every reportable incident.
- Evidence: machine-readable exercise and timing records, automated where practical.

Key Security Indicator: past incidents are persistently reviewed for patterns or vulnerabilities that were not previously apparent (KSI-INR-RPI).

- Measures: a trend review of incidents by cause, affected resource and detection source [[TODO: cycle]]; new patterns entered as vulnerabilities (see DOC-FR-VULN).
- Cycle: persistently, [[TODO: cycle]].
- Evidence: the review output and resulting tickets, kept in machine-readable form.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
