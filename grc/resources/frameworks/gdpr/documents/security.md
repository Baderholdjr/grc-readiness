# {{title}}

## Purpose

This standard sets how {{client}} protects the personal data it processes, as a controller or a processor, under Art. 32.

## Risk-based security

Security measures are chosen from a documented risk assessment of each processing activity. The assessment weighs the state of the art, the cost of implementation, and the nature, scope, context and purposes of the processing against the likelihood and severity of harm to people. It looks in particular at accidental or unlawful destruction, loss, alteration, unauthorised disclosure of, or access to, personal data (Art. 32(2)). The assessment is kept in [[TODO: the risk register or tool]] and repeated when processing or systems change.

## Encryption and pseudonymisation

- Personal data is encrypted in transit with [[TODO: e.g. TLS 1.2 or later]] and at rest with [[TODO: e.g. AES-256 through the cloud provider's key management]].
- Data used for analytics, testing or research is pseudonymised where the purpose allows, with the re-identification key held separately by [[TODO: the key owner]].
- Where encryption or pseudonymisation is not used for data that the risk assessment says needs it, the reason and the compensating measure are documented.

## Resilience and restore

Systems that process personal data keep their confidentiality, integrity, availability and resilience on an ongoing basis through access control, monitoring and redundancy. Backups of [[TODO: systems in scope]] are taken [[TODO: frequency]] and protected like the live data. {{client}} can restore availability of and access to personal data in a timely manner after a physical or technical incident, within [[TODO: recovery time objective]].

## Testing

The effectiveness of these measures is regularly tested, assessed and evaluated (Art. 32(1)(d)):

- vulnerability scans [[TODO: frequency]] and penetration tests [[TODO: frequency]];
- restore tests at least [[TODO: frequency]];
- a compliance review of this standard at least yearly.

Findings are tracked to closure with an owner and a due date.

## People with access

Everyone with access to personal data, including staff, contractors and processors acting under {{client}}'s authority, processes it only on {{client}}'s instructions unless Union or Member State law requires otherwise (Art. 32(4)). They are bound by confidentiality, trained on data protection when they join and [[TODO: frequency]] after, and given only the access their role needs.

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes. A security incident, a new system or a new type of processing triggers an earlier review.
