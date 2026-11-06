# {{title}}

## Purpose

This document sets {{client}}'s rules for identifying and authenticating users, devices and services, as required for TX-RAMP certification.

## Policy

{{client}} approves and communicates this policy and its procedures to everyone who works on the system. [[TODO: the policy owner]] maintains them.

## Users

Every user has a unique identity. Access to [[TODO: privileged and non-privileged accounts]] requires multi-factor authentication. Identities are issued only after [[TODO: identity proofing / HR verification]].

## Devices and services

Devices and service accounts are identified and authenticated before connecting, using [[TODO: certificates, workload identity]].

## Authenticators

Passwords follow [[TODO: e.g. NIST SP 800-63B: minimum length, banned-password checks]]. Default authenticators are changed before use. Authenticators are protected in storage and transit and replaced when compromised.

## External users

Agency and other non-organisational users are identified and authenticated through [[TODO: e.g. SAML/OIDC federation]].

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes.
