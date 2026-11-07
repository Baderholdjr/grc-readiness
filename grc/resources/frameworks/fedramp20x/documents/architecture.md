# {{title}}

## Purpose

This standard sets how {{client}} designs and reviews the cloud-native architecture of its cloud service offering. It covers eight Key Security Indicators. Class B and C must show all of them except KSI-CNA-EIS, which is required for Class C and optional for Class B. Class A must show only KSI-CNA-RNT, the one FedRAMP's mandatory Class A list names (FRC-CLA-MFR).

Each indicator is shown with measures and their objectives, run persistently on a known cycle, with machine-readable evidence produced automatically where practical. The measures are summarized in the security decision record (see DOC-FR-PACKAGE).

Architecture owner: [[TODO: role]]. Cloud platform: [[TODO: IaaS or PaaS providers]].

## Functionality and privileges

Key Security Indicator: the functionality and privileges of infrastructure and services are strictly defined (KSI-CNA-DFP).

- Each service has a defined purpose, the ports and protocols it needs, and the identity it runs as, recorded in [[TODO: infrastructure as code or service catalog]].
- Service identities get only the permissions their function needs; wildcard permissions are not used without a recorded exception.
- Unused features, services and default accounts are disabled.

Measures: share of services with a defined function and permission set; count of over-broad permissions found by [[TODO: policy analysis tool]].

## Network traffic and logical networking

Key Security Indicator: machine-based information resources are persistently reviewed to ensure they are configured to limit inbound and outbound network traffic (KSI-CNA-RNT).

Key Security Indicator: logical networking and related capabilities are used and persistently reviewed to enforce traffic flow controls (KSI-CNA-ULN).

- Default deny for inbound and outbound traffic; allowed flows match the documented information flows (see DOC-FR-SCOPE).
- Segmentation by [[TODO: e.g. VPCs, subnets, security groups, service mesh policies]] separates tiers, environments and tenants.
- Outbound traffic goes through [[TODO: egress control]] to approved destinations.
- Network rules are defined as code and checked against policy on every change.

Measures: count of rules allowing traffic from any source or to any destination; deviations between deployed rules and documented flows; blocked versus allowed traffic metrics. Cycle: persistently, on every change and at least [[TODO: cycle]].

## Attack surface

Key Security Indicator: machine-based information resources are persistently reviewed to ensure they have a minimal attack surface and that lateral movement is minimized if compromised (KSI-CNA-MAT).

Key Security Indicator: the use and configuration of third-party machine-based information resources is persistently compared against the original provider's best practices and guidance (KSI-CNA-IBP).

- Internet-facing endpoints are listed and each has an owner and reason.
- Images are minimal, hardened to [[TODO: baseline, e.g. CIS benchmark]], and run without unneeded packages or shells.
- Workload identity and segmentation limit what a compromised component can reach.
- Cloud and third-party services are checked against their provider's security best practices by [[TODO: posture management tool or benchmark]].

Measures: count of internet-facing endpoints against the approved list; benchmark pass rate per third-party service; findings from lateral movement testing. Cycle: persistently, at least [[TODO: cycle]].

## Availability

Key Security Indicator: machine-based information resources are persistently reviewed to ensure they are optimized for high availability and rapid recovery (KSI-CNA-OFA).

Key Security Indicator: the effectiveness of protection against denial of service attacks and other unwanted activity is persistently reviewed (KSI-CNA-RVP).

- Services run across [[TODO: e.g. multiple availability zones]] with health checks and automatic replacement.
- Denial of service protection is provided by [[TODO: DDoS protection, WAF and rate limiting]].
- Recovery objectives are set in DOC-FR-RECOVERY.

Measures: availability per core service (also published under DOC-FR-TRUST); results of failover tests; blocked attack traffic and any degradation during attacks. Cycle: persistently, with reviews at least [[TODO: cycle]].

## Intended state

(Class C; optional for Class B) Key Security Indicator: automated services persistently assess the security of all machine-based information resources and automatically enforce their intended operational state (KSI-CNA-EIS).

- The intended state is defined in [[TODO: infrastructure as code and policy-as-code repository]].
- [[TODO: enforcement tool, e.g. admission controller or configuration enforcement service]] detects drift and restores the intended state or blocks the change.

Measures: count of drift events and time to automatic correction; share of resources under enforcement. Cycle: persistently, continuously where the tooling allows.

## Reviewing protections

The architecture owner reviews the measures in this standard at least [[TODO: cycle]] and after significant changes, and records the decisions taken. Weaknesses found are entered as vulnerabilities (see DOC-FR-VULN). Each indicator's measures, objectives and cycle are kept current in the security decision record.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules.
