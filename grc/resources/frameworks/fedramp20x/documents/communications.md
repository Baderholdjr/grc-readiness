# {{title}}

## Purpose

This procedure sets how {{client}} receives and acts on messages from FedRAMP through its FedRAMP Security Inbox (FSI).

The rules below apply to Class B and C. For Class A, AFC-CSO-INB, AFC-CSO-RCV and AFC-CSO-CRA are also mandatory, because FedRAMP lists them in its mandatory Class A rules (FRC-CLA-MFR).

## FedRAMP security inbox

{{client}} must establish and maintain an email address to receive messages from FedRAMP; this is the FedRAMP Security Inbox (AFC-CSO-INB).

- Address: [[TODO: FSI email address, a role mailbox not tied to one person]].
- Owner: [[TODO: role that owns the inbox]].
- Monitored by: [[TODO: team or on-call rotation]], [[TODO: monitoring hours and coverage]].

The inbox is a shared role mailbox, not a personal address, so that it survives staff changes.

If the address changes, {{client}} must immediately notify FedRAMP of the new address (AFC-CSO-NOC). The inbox owner sends the change through FedRAMP's "[CSP] Notification of Changes" form before the old address stops working, and records the date sent.

## Receiving messages

{{client}} must treat any email from an @fedramp.gov or @gsa.gov address as sent by FedRAMP by default (AFC-CSO-TFG). If such a message is confirmed to come from someone other than FedRAMP, the FSI rules no longer apply to it, and it is handled as possible phishing under DOC-FR-INCIDENT.

{{client}} must receive and react to FedRAMP email without disruption and without requiring any extra action from FedRAMP (AFC-CSO-RCV). That means:

- no CAPTCHA, challenge-response, customer portal login or ticket form in front of the inbox;
- spam and quarantine filters allow @fedramp.gov and @gsa.gov senders, configured in [[TODO: mail platform]];
- auto-replies never ask FedRAMP to do anything to get the message through.

The mailbox configuration is checked automatically [[TODO: cycle]] by [[TODO: tool or script]], and a failure is treated as a vulnerability (see DOC-FR-VULN).

{{client}} should promptly and automatically acknowledge receipt of each FedRAMP message in the FSI (AFC-CSO-ACK). The acknowledgement is sent by [[TODO: auto-acknowledge mechanism]]. If {{client}} does not follow this, the reason and the resulting risk to customers are recorded in the security decision record (see DOC-FR-PACKAGE) and accepted by a senior official.

Every message is logged in [[TODO: tracking system]] with time received, designation, required action, due time, owner and closure.

## Emergency and important messages

FedRAMP marks some messages with a designation. The person monitoring the inbox reads the designation first.

- Emergency and Emergency Test: {{client}} must route these to a senior security official for awareness (AFC-CSO-EMR). The senior security official is [[TODO: name or role]], reached through [[TODO: routing method, e.g. mail rule plus paging]]. The routing rule is part of the mailbox configuration that is checked automatically.
- Important: handled as in "Required actions" below.
- Other messages: assigned to an owner and answered within [[TODO: internal target]].

## Required actions

{{client}} must complete the required actions in Emergency and Emergency Test messages within the timeframe stated in the message (AFC-CSO-CRA). Timeframes may differ by certification class, so the timeframe in the message is the one that applies.

{{client}} should complete the required actions in Important messages within the timeframe stated in the message (AFC-CSO-IMA). If it does not, the reason and the resulting risk to customers are recorded in the security decision record and accepted by a senior official.

For each required action:

1. the inbox monitor logs the action and due time and assigns an owner;
2. the owner completes the action and keeps the evidence;
3. the owner replies to FedRAMP when the message asks for a reply;
4. the inbox owner checks open actions [[TODO: cycle]] and escalates any at risk of missing the deadline to the senior security official.

## Review

The owner reviews this document at least every {{doc_review_days}} days, after significant changes, and when FedRAMP publishes new consolidated rules. An Emergency Test message is also used to check that this procedure works.
