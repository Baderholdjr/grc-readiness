# {{title}}

## Purpose

This procedure sets how {{client}} meets its availability commitments: managing capacity, backing up data and recovering from failure.

## Commitments

Availability commitments to customers: [[TODO: e.g. 99.9% monthly uptime]]. Recovery objectives: RTO [[TODO]], RPO [[TODO]].

## Capacity

Capacity and usage of [[TODO: components]] are monitored, with alerts at [[TODO]]. Capacity is reviewed [[TODO: e.g. monthly]] and added before limits are reached.

## Backup

Data is backed up [[TODO: frequency]] to [[TODO: location]], encrypted, and kept for [[TODO]]. Backup jobs are monitored and failures fixed.

## Recovery infrastructure

The system runs across [[TODO: e.g. multiple availability zones]]. Environmental protections at data centres are provided by [[TODO: the cloud provider]] and covered by its SOC report.

## Recovery testing

Restores are tested at least [[TODO: e.g. quarterly]], and the disaster recovery plan at least annually. Results and fixes are recorded.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
