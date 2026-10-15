# {{title}}

## Purpose

This document records what the SOC 2 examination covers, what {{client}} has committed to its customers, and how commitments and changes are communicated. It is the basis for the system description the service auditor will review.

## System boundary

{{scope_statement}}

The system is made up of infrastructure, software, people, procedures and data. Components in scope:

{{inventory_table}}

Subservice organizations (for example the cloud host) and the controls {{client}} expects from them are listed in the Vendor and Subservice Organization Management procedure.

## Commitments and requirements

Principal service commitments made to customers (in contracts, terms of service and the security page): [[TODO: e.g. encryption of customer data, availability targets, breach notification within N hours, data deletion on termination]].

System requirements that support these commitments: [[TODO: e.g. internal SLAs, retention periods, recovery objectives]].

## Information for controls

{{client}} keeps the information needed to run its controls: an up-to-date inventory of system components, data flow diagrams, and the monitoring data controls rely on. [[TODO: where each is kept]]

## External communication

Customers are told about [[TODO: e.g. security responsibilities they keep, planned changes, incidents that affect them]] through [[TODO: e.g. the status page, release notes, account managers]]. Outside parties report problems to [[TODO: security contact]].

## Review

The owner reviews this document at least every {{doc_review_days}} days, and whenever services, commitments or the system boundary change.
