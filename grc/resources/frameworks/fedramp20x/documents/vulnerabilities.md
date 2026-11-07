# {{title}}

## Purpose

This procedure sets how {{client}} detects, evaluates, mitigates, remediates and reports vulnerabilities in its cloud service offering.

A vulnerability here is any weakness that could let someone defeat the offering's protections: software flaws, misconfigurations, exposures, weak credentials, insecure services, and gaps in Key Security Indicators or in the security decision record. It is not limited to scanner findings. An out-of-date statement in the security decision record is a vulnerability too.

Applicability: VDR-CSO-DET applies to every class (for Class A through FedRAMP's mandatory Class A list, FRC-CLA-MFR). VDR-TFR-PDD, VDR-TFR-PCD, VDR-TFR-PSD, VDR-TFR-PVR and VER-TFR-EVU apply to every class with the timeframes shown. VER-TFR-IRI applies to Class C only. All other rules here apply to Class B and C. Where this document says "should", and {{client}} does not follow the rule, the reason and the resulting risk to customers are recorded in the security decision record (see DOC-FR-PACKAGE) and accepted by a senior official.

Owner of the vulnerability register: [[TODO: role]]. Register: [[TODO: vulnerability management tool]].

## Detection

{{client}} must systematically, persistently and promptly discover and identify vulnerabilities in the offering (VDR-CSO-DET), using:

- automated scanning of [[TODO: scanners for hosts, containers, code, dependencies and cloud configuration]];
- threat intelligence from [[TODO: sources]];
- the vulnerability disclosure program (see DOC-FR-GOVERNANCE) and [[TODO: bug bounty, if any]];
- penetration testing [[TODO: cycle and provider]];
- incident response findings and automated control testing;
- supply chain monitoring (see DOC-FR-SUPPLY);
- persistent verification and validation that information resources and processes operate as intended and as documented for FedRAMP Practices.

{{client}} must treat problems or failures in its vulnerability detection and response processes, such as a scanner that stopped running or a missed deadline, as vulnerabilities (VDR-CSO-FAV).

### Detection cycles

| Activity | Class A | Class B | Class C | Rule |
| --- | --- | --- | --- | --- |
| Detection on resources likely to drift (should) | every 3 months | every month | every 14 days | VDR-TFR-PDD |
| Detection on resources not likely to drift (should) | every 6 months | every 6 months | every month | VDR-TFR-PCD |
| Detection on representative samples of similar machine-based resources (should) | every 14 days | every 7 days | every 3 days | VDR-TFR-PSD |
| Verify and validate status of machine-based resources | should, every month | must, every 7 days | must, every 3 days | VDR-TFR-MVX |
| Verify and validate status of non-machine-based resources (Class B and C, must) | n/a | every 3 months | every 3 months | VDR-TFR-NMV |

These are maximum intervals; scanning in the pipeline and continuous tools run more often. Each run is logged so the status is always known.

Non-machine-based resources include policies, procedures, people and training. {{client}} must verify and validate their status at least once every 3 months (VDR-TFR-NMV), by [[TODO: method, e.g. quarterly review of documents, access rosters and training records]].

### Design and automation

{{client}}:

- should make design and architecture choices that mitigate vulnerabilities by default and make detection and response simpler, such as immutable infrastructure and minimal images (VDR-CSO-DFR);
- should use automated services to improve and streamline detection and response (VDR-CSO-ADT);
- should automatically run detection on representative samples of new or significantly changed information resources (VDR-CSO-DAC), for example as a pipeline step before deployment;
- should not weaken the security of information resources to make scanning or assessment easier, such as opening ports or adding standing credentials for a scanner (VDR-CSO-MSP);
- should not deploy or activate new machine-based information resources that have Known Exploited Vulnerabilities (VDR-CSO-AKE); the pipeline blocks images or packages with KEV findings at [[TODO: pipeline gate]].

## Evaluation

{{client}} must systematically, persistently and promptly track, evaluate, monitor, mitigate, remediate, assess exploitation of, report and otherwise manage every detected vulnerability (VDR-CSO-RES). Every finding enters the register.

{{client}} should evaluate every vulnerability within these times of detection (VER-TFR-EVU):

- Class A: 14 days;
- Class B: 7 days;
- Class C: 5 days.

For each vulnerability, considering the context of the offering, {{client}}:

- must decide whether it is a likely exploitable vulnerability: not fully mitigated, reachable by a likely threat actor, and likely to let that actor cause harm (VER-EVA-ELX);
- must decide whether it is an internet-reachable vulnerability: one that a payload from the public internet might trigger (VER-EVA-EIR);
- must assume exploitation can be automated unless it has evidence proving otherwise (VER-EVA-AIA);
- must estimate the Potential Agency Impact and assign a PAIN rating (VER-EVA-EPA), see the next section;
- should decide whether it is a false positive, meaning not actually present in an exploitable state (VER-EVA-EFP); the reason is recorded;
- should group affected resources logically, for example all hosts built from one image, so response is consolidated and the rules apply to the group (VER-EVA-GRV).

{{client}} should weigh at least these factors (VER-EVA-EFA):

- criticality of the affected systems or information;
- reachability: how a threat actor could reach it, and how likely;
- exploitability: how easy and how likely exploitation is;
- detectability: how easily a threat actor could learn of it;
- prevalence: how much of the offering is affected;
- privilege granted or gained by exploiting it;
- proximate vulnerabilities: how it interacts with other detected vulnerabilities, especially partly or fully mitigated ones;
- known threats that could use it.

## Potential Agency Impact rating

{{client}} must assign one of these ratings to the likely impact of exploitation on agencies using the offering (VER-EVA-EPA):

| Rating | Exploitation could be expected to have |
| --- | --- |
| N0 | extremely unlikely to have any adverse effect on agencies |
| N1 | minimal customer effects on one or more agencies |
| N2 | narrow customer effects on one or more agencies |
| N3 | a disruptive customer effect on one agency |
| N4 | a debilitating customer effect on one agency, or a disruptive customer effect on more than one agency |
| N5 | a debilitating customer effect on more than one agency |

Customer effects use FedRAMP's definitions: minimal (noticeable by some users), narrow (some users for less than 12 hours, or extremely limited data), disruptive (many users for less than 24 hours, or large amounts or many types of data), debilitating (most users or most data; unknown effects count as debilitating until shown otherwise).

The rating is revisited after each mitigation. A mitigation that lowers the rating or likelihood makes the vulnerability partially mitigated; one that reduces either the likelihood of exploitation or the rating until it is negligible, while the vulnerability is still detected makes it fully mitigated; a vulnerability no longer detected is remediated.

## Mitigation and remediation timeframes

{{client}} should partially mitigate, fully mitigate or remediate each vulnerability to a lower PAIN rating within these days from evaluation, according to its current rating, internet reachability and likely exploitability (VDR-TFR-PVR).

Class A and Class B:

| Current rating | Internet-reachable and likely exploitable | Not internet-reachable, likely exploitable | Not likely exploitable |
| --- | --- | --- | --- |
| N5 | 4 days | 8 days | 32 days |
| N4 | 8 days | 32 days | 64 days |
| N3 | 32 days | 64 days | 192 days |
| N2 | 96 days | 160 days | 192 days |

Class C:

| Current rating | Internet-reachable and likely exploitable | Not internet-reachable, likely exploitable | Not likely exploitable |
| --- | --- | --- | --- |
| N5 | 2 days | 4 days | 16 days |
| N4 | 4 days | 8 days | 64 days |
| N3 | 16 days | 32 days | 128 days |
| N2 | 48 days | 128 days | 192 days |

Timeframes are counted from evaluation and follow the vulnerability's current rating. A vulnerability that misses its timeframe but that {{client}} still intends to fix is an overdue vulnerability and is reported as such.

{{client}} should mitigate or remediate remaining vulnerabilities, such as N1 and N0 findings, during routine operations as it judges necessary (VDR-TFR-RMN). The routine cycle is [[TODO: e.g. the regular patch cycle]].

(Class C) {{client}} should treat an internet-reachable, likely exploitable vulnerability with a PAIN rating above N3 as a FedRAMP Reportable Incident until it is partially mitigated to N3 or below (VER-TFR-IRI). Such vulnerabilities are then handled under DOC-FR-INCIDENT.

## Known exploited vulnerabilities

A Known Exploited Vulnerability (KEV) is any vulnerability in CISA's Known Exploited Vulnerabilities catalog (CISA BOD 26-04).

{{client}} should remediate KEVs by the due dates in the CISA KEV catalog, even when the vulnerability is already fully mitigated, as required by CISA BOD 26-04 or successor CISA guidance (VDR-TFR-KEV).

- Findings are matched to the KEV catalog automatically by [[TODO: tool or feed]].
- The register shows the CISA due date next to the FedRAMP timeframe; as an internal policy choice (FedRAMP doesn't set this), {{client}} works to the earlier date.
- New resources with KEVs are not deployed (VDR-CSO-AKE).

## Accepted vulnerabilities

{{client}} must categorize as an accepted vulnerability any vulnerability that is not, or will not be, fully mitigated or remediated within 192 days of evaluation (VER-TFR-MAV). A vulnerability {{client}} decides not to fully fix is also an accepted vulnerability.

Each acceptance records the reason, compensating measures and the senior official who accepted it: [[TODO: role who accepts vulnerabilities]]. Accepted vulnerabilities stay in the register, are re-evaluated [[TODO: cycle]], and are summarized in each Ongoing Certification Report (see DOC-FR-CONMON).

## Reporting

{{client}} must report vulnerability detection and response activity, including persistent verification and validation, to all necessary parties persistently, summarizing all activity since the previous report (VER-RPT-PER). These reports are certification data and are shared through the trust center (see DOC-FR-TRUST).

{{client}} must report at least monthly, in a consistent, human-readable format (VER-TFR-MHR). Reports follow the vulnerability detail report schema (https://fedramp.gov/schemas/fedramp-vulnerability-detail-report-schema-2026-06-24.json).

For each detected vulnerability that is not accepted, the report must include where applicable (VER-RPT-VDT):

- {{client}}'s internal tracking identifier;
- time and source of detection, and time the evaluation was completed;
- whether it is internet-reachable and whether it is likely exploitable;
- historical and current PAIN ratings;
- time and rating of each completed reduction in rating;
- estimated time and target rating of the next reduction;
- whether it is, or is likely to become, overdue, with an explanation;
- any supplementary information that helps agencies assess or mitigate the risk to their data;
- final disposition.

For each accepted vulnerability, the report must include (VER-RPT-AVI), following https://fedramp.gov/schemas/fedramp-accepted-vulnerability-info-schema-2026-06-24.json:

- internal tracking identifier;
- time and source of detection, and time the evaluation was completed;
- whether it is internet-reachable and whether it is likely exploitable;
- current PAIN rating;
- why it is accepted;
- any supplementary information that helps agencies assess or mitigate the risk.

{{client}} must not irresponsibly disclose specific sensitive information that would likely lead to exploitation, but must disclose enough for agencies to make informed risk decisions (VER-RPT-NID). Exploit detail, exact vulnerable endpoints and unpatched versions on internet-facing systems are abstracted.

{{client}} should include high-level overviews of all detection and response activity in the period, including the disclosure program, bug bounty, penetration tests and assessments (VER-RPT-HLO).

Historical activity in JSON for automated retrieval by all necessary parties, for example through an API, updated persistently (VER-TFR-MRH), following https://fedramp.gov/schemas/fedramp-historical-ver-activity-schema-2026-06-24.json:

- Class B: should, at least every month;
- Class C: should, at least every 14 days.

The endpoint is [[TODO: API or trust center location]].

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
