# {{title}}

## Purpose

This document sets {{client}}'s rules for accounts on the system and what they can reach, as required for TX-RAMP certification.

## Policy

{{client}} approves and communicates this policy and its procedures to everyone who works on the system. [[TODO: the policy owner]] maintains them.

## Account management

Account types are defined for [[TODO: users, administrators, service accounts]]. Accounts are created only after approval by [[TODO: the account owner's manager and the system owner]], disabled within [[TODO: e.g. 24 hours]] of a leaver's last day, and disabled after [[TODO: e.g. 90 days]] without use. Shared and group accounts are [[TODO: not allowed / approved case by case]].

## Least privilege and separation of duties

People get only the access their role needs. Conflicting duties (for example approving and deploying your own change) are split between people. Privileged functions are limited to [[TODO: roles]] and their use is logged.

## Sign-in protection

After [[TODO: e.g. 5]] failed sign-in attempts the account locks for [[TODO: e.g. 30 minutes]]. Users see the system-use notice before signing in. Sessions lock after [[TODO: e.g. 15 minutes]] of inactivity and end after [[TODO]].

## Remote, wireless and mobile access

Remote access uses [[TODO: e.g. SSO with MFA, VPN or bastion hosts]] through managed access points. Wireless and mobile devices that reach the system are [[TODO: managed through MDM]]. Use of external systems to process agency data is [[TODO: prohibited unless approved]].

## Information flow and publicly accessible content

Data flows between [[TODO: environments, tenants, interconnected systems]] are controlled by [[TODO: e.g. security groups, firewalls, API gateways]]. Only authorized staff post public content, and it is reviewed for non-public information first.

## Access reviews

System owners review accounts and privileges every [[TODO: e.g. 90 days]] and remove what is not needed. Reviews are recorded.

## Review

The owner reviews this document at least every {{doc_review_days}} days and after significant changes.
