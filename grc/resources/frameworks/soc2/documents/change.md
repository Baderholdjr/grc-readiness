# {{title}}

## Purpose

This procedure sets how changes to {{client}}'s infrastructure, software, data and procedures are authorized, built, tested, approved and released.

## Scope of changes

It covers application code, infrastructure and configuration, database changes, and changes to security tooling. [[TODO: exclusions, if any]]

## Authorization and review

Every change is tracked in [[TODO: e.g. a pull request linked to a ticket]] and reviewed and approved by someone other than its author before it is merged. Branch protection enforces this on [[TODO: repositories]].

## Testing

Changes pass automated tests [[TODO: and security scans]] before deployment. Significant changes are tested in [[TODO: staging]].

## Deployment

Only the deployment pipeline deploys to production; engineers do not deploy by hand. Deployments are logged.

## Emergency changes

Emergency changes may be deployed before review when [[TODO: criteria]], and are reviewed and approved within [[TODO: e.g. one business day]].

## Infrastructure and configuration

Infrastructure is defined as code where possible and follows the same review and approval steps.

## Review

The owner reviews this procedure at least every {{doc_review_days}} days.
