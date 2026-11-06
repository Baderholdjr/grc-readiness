# {{title}}

## Purpose

This document sets {{client}}'s rules for the system's baseline configuration and changes to it, as required for TX-RAMP certification.

## Policy

{{client}} approves and communicates this policy and its procedures to everyone who works on the system. [[TODO: the policy owner]] maintains them.

## Baseline configuration

A baseline configuration for [[TODO: images, infrastructure as code, network devices]] is kept under version control and reviewed every [[TODO]] and after significant changes. Previous versions are kept for rollback.

## Change control

Changes are proposed, analysed for security impact, approved by [[TODO: the change advisory board / code owners]], tested and recorded before deployment. Only authorised people can make changes in production.

## Secure settings and least functionality

Systems are hardened to [[TODO: e.g. CIS Benchmarks]]. Unneeded ports, protocols, services and software are disabled. Only approved software may run, and users cannot install software without approval.

## Inventory

An inventory of system components is kept current, updated when components are added or removed, and reviewed every [[TODO]]. The location of agency data is known and recorded.

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes.
