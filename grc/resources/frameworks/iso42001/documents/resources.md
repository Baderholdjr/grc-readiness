# {{title}}

## Purpose

This procedure keeps an up-to-date record of the resources {{client}}'s AI systems depend on, so that risks and impacts can be understood and the AIMS can be audited.

## What is recorded

For each AI system, the inventory records its components and resources:

| Resource type | Examples | Recorded details |
|---|---|---|
| Data | Training, validation, test and production data | Source, owner, intended use, sensitivity, provenance (DOC-DATA) |
| Tooling | Frameworks, MLOps platforms, evaluation tools | Name, version, owner |
| System and computing | Cloud services, model hosting, storage | Provider, region, owner |
| Models | In-house and third-party models | Version, provider, model card |
| Human | Roles and skills needed to build and run the system | Roles, competence (DOC-PEOPLE) |

Current inventory:

{{inventory_table}}

## Keeping it current

- System owners update the inventory through a reviewed change whenever a resource is added, changed or retired.
- New AI systems are added before development starts; impact assessment is then required (DOC-IMPACT).
- The AIMS owner reconciles the inventory against [[TODO: e.g. cloud accounts / procurement records]] every [[TODO]] months.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
