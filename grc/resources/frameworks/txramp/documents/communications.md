# {{title}}

## Purpose

This document sets {{client}}'s rules for the system's boundary and the data moving across it, as required for TX-RAMP certification.

## Policy

{{client}} approves and communicates this policy and its procedures to everyone who works on the system. [[TODO: the policy owner]] maintains them.

## Boundary protection

The system boundary is defined and protected with [[TODO: firewalls, security groups, WAF]]. Public-facing components are in separate subnetworks. Traffic is denied by default and allowed by exception.

## Encryption

Data in transit is protected with [[TODO: TLS 1.2 or later]]. Data at rest is encrypted with [[TODO: FIPS-validated encryption, keys in KMS]]. Keys are created, rotated and destroyed under a documented process.

## Separation and availability

User functions are separated from system management functions. The system is protected against denial of service with [[TODO]].

## Sessions and name resolution

Network sessions end after [[TODO]] of inactivity. DNS services provide authenticated, secure name resolution.

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes.
