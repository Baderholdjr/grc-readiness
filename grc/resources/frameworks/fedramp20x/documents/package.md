# {{title}}

## Purpose

This plan sets how {{client}} prepares, applies for, and keeps a FedRAMP 20x certification for its cloud service offering, and how it maintains the certification package, the security decision record and the independent assessment that support it.

The cloud service offering in scope: {{scope_statement}}

Roles and owners:

{{owners_table}}

{{client}} stays responsible and accountable for the accuracy and completeness of everything in the certification package, including anything an independent assessor, an advisor such as {{engagement_lead}}, or an external tool supplies on its behalf (FRC-CSO-MRA). The package owner checks third-party input before it goes into the package.

## Certification class and path

{{client}} identifies its target FedRAMP certification profile and applies all relevant FedRAMP Practices to the offering (FRC-CSO-FCP). The profile is:

- certification type: FedRAMP 20x;
- certification path: Program (direct from FedRAMP);
- certification class: [[TODO: Class A, Class B or Class C]].

Information resources, including third-party information resources, may have different security categories according to the information they handle or affect (FRC-CSO-FCP). See DOC-FR-SCOPE.

{{client}} must not seek both a FedRAMP Rev5 Program certification and a FedRAMP 20x Program certification for the same offering (FRC-CSO-POP). [[TODO: state any existing Rev5 Agency certification for this offering, or "none"]]. FedRAMP strongly discourages holding a Rev5 Agency certification and a 20x Program certification for the same offering at once.

### Class A only

(Class A) Before applying, {{client}} must have completed, within the past 12 months, a certification or equivalent process, including an independent assessment if applicable, under one of these alternative security frameworks (FRC-CLA-ASF):

- FedRAMP Rev5 (including FedRAMP Ready) at any historical impact level;
- SOC 2 Type II;
- GovRAMP at any impact level.

The framework used is [[TODO: framework and completion date]].

(Class A) {{client}} must supply these materials from that assessment to all necessary parties (FRC-CLA-EAM):

- SOC 2 Type II: the complete report, a bridge or gap letter if applicable, verified audit engagement documentation, the estimated schedule for the next report, and supplemental compliance evidence if applicable;
- FedRAMP Ready: the Readiness Assessment Report, the Security Assessment Plan, and any other materials FedRAMP requires;
- GovRAMP: the Readiness Assessment Report, the Security Assessment Plan, and any other materials GovRAMP requires.

(Class A) {{client}} must address all rules in FedRAMP's Class A subset and the additional mandatory Class A rules, and must supply the artifacts or information mapping for each of them in the package (FRC-CLA-MFR). The mandatory list includes FRC-CSO-PKG, FRC-CSO-JSN, FRC-CSO-POP, MAS-CSO-IIR, CDS-CSO-PUB, CDS-CSO-UTC, CDS-UTC-AAD, AFC-CSO-INB, AFC-CSO-RCV, AFC-CSO-CRA, IEC-CSO-EFR, IEC-CSO-FIR, VDR-CSO-DET, CCM-OCR-AVL, CCM-OCR-NRD, IVV-CSX-AIA, SDR-CSX-KSI, KSI-CMT-LMC, KSI-CNA-RNT, KSI-CED-RAT, KSI-IAM-AAM, KSI-IAM-APM, KSI-INR-RIR and KSI-SVC-SIN. The procedures for these rules apply to a Class A offering even where a procedure is written for Class B and C.

(Class A) {{client}} should also address the recommended Class A rules where applicable: CDS-CSO-AVR, CPO-CSX-CPM, IEC-CSO-IIR, IEC-CSO-OIR, VDR-TFR-MVX, VDR-TFR-PCD, VDR-TFR-PDD, VDR-TFR-PSD, VDR-TFR-PVR and VER-TFR-EVU (FRC-CLA-RFR). If {{client}} does not follow one of them, the reason and the resulting risk to customers are recorded in the security decision record and accepted by a senior official.

## The certification package

{{client}} must supply a complete certification package to FedRAMP for initial certification (FRC-CSO-PKG). It contains at least:

- the Certification Package Overview (CPO-CSO-OVR);
- implementation, validation and assessment information for each relevant FedRAMP rule and Key Security Indicator, in the security decision record (SDR-CSO-FRR);
- a real or example Ongoing Certification Report (CCM-OCR-AVL), see DOC-FR-CONMON.

### Certification Package Overview

(Class B and C) The overview must be supplied in both human-readable and JSON formats and must include at least the information required by (CPO-CSO-OVR). A Class A package, which FRC-CSO-PKG also requires, includes the overview as far as these items apply:

- CPO-CSO-MTD, metadata (below);
- CDS-CSO-PUB, CDS-CSO-SVC and CDS-CSO-IRP, public information, the service list and relevant policies (DOC-FR-TRUST);
- MAS-CSO-IIR, MAS-CSO-FLO and MAS-CSO-TPR, the Minimum Assessment Scope (DOC-FR-SCOPE);
- CMU-CSO-CMD, cryptographic modules (DOC-FR-SCG);
- IVV-CSO-ICP, independent assessment results (below).

(Class B and C) The overview metadata must include the name, title and contact information of the official responsible and accountable for the package, the version, the date and time of the last update, and the source of the update (CPO-CSO-MTD). The accountable official is [[TODO: name and title of the accountable official]].

(Class B and C) The overview must also include the overall summary of the FedRAMP independent assessment, as supplied by the assessor (CPO-CSO-OSA).

### Machine-readable formats

When a FedRAMP rule names a FedRAMP JSON schema, {{client}} must supply the information in JSON that validates against that schema, unless the rule says otherwise (FRC-CSO-JSN). The overview uses https://fedramp.gov/schemas/fedramp-certification-package-overview-schema-2026-06-24.json. Each JSON file is validated against its schema by [[TODO: validation tool or pipeline step]] before it is published.

Public JSON data must work with modern web frameworks (FRC-CSO-JSN):

- Cross-Origin Resource Sharing (CORS) allows web applications on other domains to read the public JSON data directly;
- responses set at least `Content-Type: application/json` and `X-Content-Type-Options: nosniff`.

### Keeping the package current

The package owner persistently maintains the package so it is up to date and complete (CPO-CSX-CPM):

- Class A: should, at least once every 3 months;
- Class B: must, at least once every month;
- Class C: must, at least once every 2 weeks.

The maintenance cycle is run by [[TODO: scheduled job or calendar owner]] and each run is logged with its date and result.

## Security decision records

The security decision record (SDR) replaces the traditional system security plan. It records how each applicable FedRAMP Practice is addressed, the rationale, the resulting risk to customers, assessment findings and supporting artifacts. It is kept in [[TODO: SDR repository or tool]].

(Class B and C; a Class A package includes it as far as it applies) For each applicable FedRAMP rule, the SDR must hold, in both human-readable and JSON formats (SDR-CSO-FRR):

- how the rule is followed, or the reason and the resulting risk to customers for not following it;
- verification that the implementation is appropriate for the rule, or that the reason for not implementing it is accepted by a senior official;
- validation that the implementation is in place and working as intended, or that the reason for not implementing it is accepted by a senior official;
- independent verification and independent validation;
- any responses or clarifications to the independent verification or validation comments;
- rule-specific artifacts, if any.

The SDR uses https://fedramp.gov/schemas/fedramp-security-decision-record-schema-2026-06-24.json. Its metadata must include the version, the date and time of the last update, and the source of the update (SDR-CSO-MTD).

(Every class; for Class A it is on FedRAMP's mandatory Class A list, FRC-CLA-MFR) For each applicable Key Security Indicator, the SDR must give short, simple summaries of (SDR-CSX-KSI):

- the measures, and their objectives, that demonstrate the indicator, or the reason and resulting risk to customers for not having measures;
- the cycle of any measure that is implemented persistently;
- verification that the measures demonstrate the indicator, or that the reason for not having them is accepted;
- verification that the automation in place is accurate and sufficient, or that automation is not necessary for a measure;
- validation that the measures are accurately produced and are in place and working as intended, or that the reason for not having them is valid.

Historical metrics for each applicable Key Security Indicator (SDR-CSX-KMT):

- Class B: should include a summary of each metric over the past 30 days and up to the past year where available;
- Class C: must include the same summaries, plus all daily metric data, including the status of persistent validation, up to the past year where available.

For an initial certification, if the offering has not yet run long enough to have this history, {{client}} must have the mechanisms in place and agree to meet the requirement (SDR-CSX-KMT).

### Not following a rule

Every SHOULD rule that {{client}} does not follow, and every MUST rule or indicator that is not met, is recorded in the SDR with the reason and the resulting risk to customers, and accepted by [[TODO: senior official who accepts risk]]. That record is what the other FedRAMP documents in this library mean by "recorded in the security decision record".

## Independent assessment

(Class B and C) {{client}} must persistently complete an independent verification and validation assessment of all applicable FedRAMP rules with a FedRAMP Recognized independent assessment service, or FedRAMP, at least once per year (IVV-CSO-FIA). The current assessor is [[TODO: FedRAMP Recognized independent assessment service]].

Annual assessment by class (IVV-CSX-AIA):

- Class A: must meet the expectations of the underlying alternative security framework as part of the persistent independent assessment;
- Class B and C: must include all Key Security Indicators in a FedRAMP independent assessment at least once per year.

During verification and validation, {{client}}:

- (Class B and C) must give all necessary assessors evidence that the documented measures are implemented; this is the result of verification, for example showing firewall rules deployed from a source of truth (IVV-CSO-SEI);
- (Class B and C) must give all necessary assessors evidence that the implemented measures are effective; this is the result of validation, for example metrics showing traffic actually blocked (IVV-CSO-SEE);
- (Class B and C) must document and explain any use of representative samples during verification and validation (IVV-CSO-DUS);
- (Class B and C) should give assessors technical explanations, demonstrations and supporting information about the capabilities used to meet FedRAMP rules, as needed for the assessor to complete its work (IVV-CSO-STE). If {{client}} does not, the reason and resulting risk to customers are recorded in the SDR and accepted by a senior official.

(Class B and C) The results of each FedRAMP independent assessment must go into the certification package without inappropriate modification (IVV-CSO-ICP).

## Automated validation

Key Security Indicators are verified and validated with automated methods, persistently (FRC-CSX-VVK):

- Class B: should have at least 1 automated method for each indicator;
- Class C: must have at least 2 automated methods for each indicator.

The automated methods are listed per indicator in the SDR and run by [[TODO: validation platform or pipeline]].

(Class B and C) {{client}} should also use automated methods to persistently verify and validate the accuracy and completeness of the SDR entries for FedRAMP rules, where that makes sense for the rule (FRC-CSX-VVR). If {{client}} does not, the reason and resulting risk to customers are recorded in the SDR and accepted by a senior official.

(Class B and C) {{client}} should apply all Key Security Indicators to all aspects of the offering inside the Minimum Assessment Scope (FRC-CSX-MAS). Any part where an indicator is not applied is recorded in the SDR with the reason and resulting risk, accepted by a senior official.

## Applying and maintaining

Before applying, {{client}} must be listed in the FedRAMP Marketplace, meeting MKT-CSO-MLR, MKT-CSO-PML, MKT-IIP-AGU and MKT-IIP-DCP (FRC-APP-MLF). Marketplace listing status: [[TODO: listing status and date]].

To apply, {{client}}:

1. completes the FedRAMP Certification Application Form in full to request an initial assessment by FedRAMP (FRC-APP-AFC);
2. supplies a fresh initial certification package showing the current status of the offering, verified and validated by {{client}} within the previous 7 days (FRC-APP-FCP);
3. (Class B and C) supplies a fresh initial FedRAMP independent assessment completed by a FedRAMP Recognized independent assessment service within the previous 3 months (FRC-APP-FIA);
4. submits the application itself: {{client}} must not use a third party, including its independent assessment service or advisor, to apply on its behalf (FRC-APP-NTP).

The application is submitted by [[TODO: named employee of the client]]. After certification, the package is maintained on the cycle in "Keeping the package current", and the independent assessment is repeated at least yearly.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
