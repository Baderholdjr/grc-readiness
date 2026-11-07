# {{title}}

## Purpose

This record defines the Minimum Assessment Scope (MAS) of {{client}}'s cloud service offering: the boundary that FedRAMP assesses and certifies. Anything not entirely inside the MAS is a third-party information resource.

Scope statement: {{scope_statement}}

The MAS rules below apply to Class B and C. A Class A offering must still identify its information resources, because MAS-CSO-IIR is in FedRAMP's mandatory Class A list (FRC-CLA-MFR).

## Information resources

{{client}} must identify the set of information resources to assess for FedRAMP certification. It includes every information resource that is likely to handle federal customer data, or likely to affect the confidentiality, integrity or availability of federal customer data handled by the offering. This set is the cloud service offering (MAS-CSO-IIR).

Information resources are both machine-based (hardware, software, cloud services, code) and non-machine-based (policies, procedures, people). Both kinds are in scope.

The current inventory:

{{inventory_table}}

How the inventory is produced:

- the machine-readable list of components is generated automatically from [[TODO: authoritative source, e.g. cloud provider APIs or infrastructure as code state]] by [[TODO: script or tool]];
- a human-readable explanation of how that output is derived is kept with it;
- the code of the generating process is kept in [[TODO: repository]] and supplied as evidence.

A resource is included when in doubt. Each exclusion is recorded with the reason. The inventory is regenerated [[TODO: cycle, e.g. on every deployment and at least daily]] and checked against the MAS whenever a significant change is evaluated (see DOC-FR-SCN).

## Information flows and security categories

{{client}} must clearly identify, document and explain the information flows and the security categories for all information resources, or sets of information resources, in the offering (MAS-CSO-FLO). Different resources may have different security categories according to the information they handle or affect.

For each flow the record shows:

- source and destination resources;
- the type of information carried, including whether it is federal customer data;
- protocol, port and the protection used in transit;
- the security category (Low, Moderate or High, per FIPS 199) of each resource or set of resources.

The permitted connections are produced as machine-readable output by [[TODO: e.g. network policy export or flow-log analysis]], with a human-readable explanation of how it is derived and the code that produces it. Diagrams are kept at [[TODO: location of data flow diagrams]].

## Third-party information resources

Because MAS-CSO-IIR applies, {{client}} must address the potential impact to federal customer data from each third-party information resource the offering uses, by documenting (MAS-CSO-TPR):

- its general usage and configuration;
- the explanation or justification for using it;
- mitigation measures in place to reduce the potential impact to federal customer data;
- compensating controls in place to reduce that impact.

Current third parties:

{{suppliers_table}}

The third-party list is kept as machine-readable output with a human-readable explanation and the code that generates it, like the inventory. A new third-party resource is evaluated before it handles federal customer data. Supply chain monitoring is in DOC-FR-SUPPLY.

## Metadata

Because MAS-CSO-IIR applies, {{client}} must include metadata, including metadata about federal customer data, in the MAS (MAS-CSO-MDI). Metadata includes [[TODO: e.g. account information, service logs, telemetry, analytics, tags, file names]].

For each metadata store the record shows where it is held, what it describes, and which resources handle it. The list is produced as machine-readable output with a human-readable explanation and the generating code, like the inventory.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
