# {{title}}

## Purpose

This procedure sets how ePHI is protected from improper change or destruction, at rest and in transit.

## Integrity

ePHI is protected from improper alteration or destruction by [[TODO: access controls, database constraints, versioning, immutable backups]].

## Authenticating ePHI

[[TODO: Checksums, digital signatures or database audit trails]] show that ePHI hasn't been changed without authorization.

## Transmission security

ePHI sent over networks is protected from unauthorized access: [[TODO: TLS 1.2 or later for all connections; encrypted email or secure file transfer for external sharing]]. Transmissions are protected against undetected modification.

## Encryption decisions

Where encrypting a transmission isn't reasonable and appropriate, the reason and the equivalent measure are documented and approved by the security official.

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes.
