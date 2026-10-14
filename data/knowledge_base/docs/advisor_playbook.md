---
doc_id: advisor_playbook
title: Advisor Playbook
doc_type: procedure
version: 1
intents: []
---

# Advisor Playbook

Internal procedures for CallVerse advisors. All rules are explicit assumptions.

## Verifying the customer before sharing order details
<!-- intents: track_order, change_order, cancel_order, refund_status -->

Before giving order details or changing an order, confirm two of the following:

- the order number;
- the e-mail address on the account;
- the last 4 digits of the CPF;
- the delivery postcode (CEP).

Never ask for a full card number, card security code or password.

## Answering from the order record
<!-- intents: track_order, delivery_time, refund_status -->

- Always open the order before answering. Quote the status, dates and amounts from the record, never from memory.
- Never promise a delivery or refund date earlier than the one in the system.
- If the knowledge base has no answer, say so and escalate rather than guess.

## Compensation authority
<!-- intents: delivery_issue, damaged_delivery, missing_item, wrong_item -->

| Who | May grant |
|---|---|
| Advisor | Vouchers up to R$ 30 per order; free return labels; re-shipment of lost, damaged, wrong or missing items |
| Supervisor | Vouchers above R$ 30; refunds outside policy time limits |
| Payments team | Duplicate charges, boleto refunds, refunds overdue by their expected date |

Compensation is a goodwill gesture, not a right, except where a policy says so.

## When to escalate
<!-- intents: payment_issue, refund_status, delivery_issue -->

Escalate to a supervisor or the right team when:

- the customer asks for a human supervisor after the advisor has offered a solution;
- the case needs an amount above the advisor's authority;
- a refund or carrier investigation has passed its expected date;
- the customer mentions a legal complaint, consumer-protection agency (PROCON) or the press;
- there are signs of fraud (account takeover, many orders to different addresses).

## Tone and closing the contact
<!-- intents: track_order, delivery_issue, product_issue -->

- Acknowledge the problem and apologise when the store or seller is at fault.
- Explain the next step, who does it and by when.
- Summarise what was agreed at the end, and confirm the customer has no other question.
- Log the contact reason (intent) and the outcome in the case notes.
