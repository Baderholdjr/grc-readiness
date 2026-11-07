# {{title}}

## Purpose

This standard sets how {{client}} gives customers guidance to configure its cloud service offering securely, how secure defaults are set, and how cryptographic modules that protect federal customer data are chosen and documented. These rules apply to Class B and C; CMU-CSO-UVM applies to Class C only.

Where this standard says "should" and {{client}} does not follow the rule, the reason and the resulting risk to customers are recorded in the security decision record (see DOC-FR-PACKAGE) and accepted by a senior official. For a capability {{client}} does not offer, the record explains why it is not available.

## Secure configuration guide for customers

{{client}} must create, maintain and make available recommendations for securely configuring its cloud services: the Secure Configuration Guide (SCG-CSO-RSC). It includes:

- required: instructions to securely access, configure, operate and decommission top-level administrative accounts, which control enterprise access to the whole offering;
- required: explanations of the security-related settings that only top-level administrative accounts can operate, and their security implications;
- recommended: explanations of the security-related settings that only privileged accounts can operate, and their security implications.

The guide is kept at [[TODO: human-readable URL]] and [[TODO: machine-readable URL]], owned by [[TODO: role]], and updated with every release that changes a security setting.

{{client}} must include instructions in the certification package explaining how to obtain and use the guide (SCG-CSO-AUP). The instructions are in the Certification Package Overview and the trust center landing page.

{{client}} should make the guide available publicly (SCG-CSO-PUB). The public link is listed in the public information (see DOC-FR-TRUST).

## Secure defaults

{{client}} should set all settings for top-level administrative accounts and privileged accounts to their recommended secure defaults when the accounts are first provisioned (SCG-CSO-SDF). Defaults include [[TODO: e.g. phishing-resistant MFA required, session timeout, audit logging on, IP restrictions available]].

{{client}} should provide versioning and a release history for the recommended secure defaults for these accounts as they change over time (SCG-ENH-VRH). The history is kept at [[TODO: changelog location]].

## Guide capabilities

{{client}} should offer customers these capabilities:

- compare all current settings of top-level administrative and privileged accounts to the recommended secure defaults (SCG-ENH-CMP): [[TODO: feature name or "not available"]];
- export all security settings in a machine-readable format (SCG-ENH-EXP): [[TODO: feature name or "not available"]];
- view and adjust security settings through an API or similar capability (SCG-ENH-API): [[TODO: API documentation link or "not available"]];
- the guide itself in a machine-readable format that customers or third-party tools can use to compare against current settings (SCG-ENH-MRG): [[TODO: format and location or "not available"]].

## Cryptographic modules

{{client}} must document the cryptographic modules used in each service, or group of services using the same modules, where cryptographic services protect federal customer data, including whether each module is validated under the NIST Cryptographic Module Validation Program (CMVP) or is an update stream of such a module (CMU-CSO-CMD). The list is part of the Certification Package Overview.

| Service or group | Purpose (e.g. data at rest, in transit) | Module and version | CMVP certificate or update stream |
| --- | --- | --- | --- |
| [[TODO: service]] | [[TODO: purpose]] | [[TODO: module]] | [[TODO: certificate number or status]] |

(Class C) {{client}} should use cryptographic modules, or update streams of modules, with active CMVP validations when using cryptographic services to protect federal customer data (CMU-CSO-UVM). An algorithm added by an update stream that was never validated is not covered by the update stream.

{{client}} should configure agency tenants by default to use cryptographic services built on modules, or update streams of modules, with active CMVP validations when such modules are available (CMU-CSO-CAT). The default configuration and the modules it uses are documented in the guide.

Module status is checked against the CMVP list [[TODO: cycle]], and an expired or revoked validation is treated as a vulnerability (see DOC-FR-VULN).

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
