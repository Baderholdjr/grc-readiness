# {{title}}

## Purpose

This procedure builds security into how {{client}} develops, tests and changes software and systems.

## Requirements and architecture

Security requirements are identified and approved for new or changed applications; secure architecture and engineering principles are documented in [[TODO]] and applied in design reviews.

## Secure coding

Developers follow secure coding guidance [[TODO]]; code is reviewed before merge; static analysis and dependency scanning run in CI [[TODO: tools]].

## Security testing

Security testing (e.g. automated tests, penetration tests at least [[TODO]]) is planned and carried out before release; results are tracked to resolution.

## Environments and test data

Development, test and production are separated, with production access restricted. Production data is not used in testing unless approved and protected [[TODO]].

## Outsourced development

Outsourced development is directed and reviewed under contract requirements (DOC-IS-SUPPLIER). [[TODO]]

## Change management

Changes to production follow change management: request, review and approval (by someone other than the author), testing, and rollback planning. Emergency changes are reviewed after the fact. [[TODO: tooling, e.g. pull requests with required reviews]]

## Audit testing

Audit and assurance tests on operational systems are agreed in advance with system owners to limit disruption.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
