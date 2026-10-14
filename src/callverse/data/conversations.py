"""Template-based chat logs for synthetic tickets."""

import numpy as np
import pandas as pd

VERIFY_CHUNK = "advisor_playbook__s01"
ESCALATION_CHUNK = "advisor_playbook__s04"
CLOSING_CHUNK = "advisor_playbook__s05"

STATUS_TEXT = {
    "created": "placed, and we are waiting for the payment confirmation",
    "approved": "paid and being prepared by the seller",
    "shipped": "with the carrier",
    "delivered": "delivered",
    "canceled": "canceled",
    "unavailable": "canceled because the seller could not fulfil it",
}

PAYMENT_TEXT = {
    "credit_card": "credit card",
    "boleto": "boleto",
    "voucher": "voucher",
    "debit_card": "debit card",
    "not_defined": "an unidentified payment method",
}

REFUND_TIMING = {
    "credit_card": "The reversal will show on your next 1 or 2 card statements.",
    "debit_card": "The money will be back in your account in 5 to 10 business days.",
    "voucher": "You will get a new voucher of the same value within 2 business days.",
    "not_defined": "Our payments team will confirm the refund method by e-mail.",
}

GREETINGS = [
    "Hello, thank you for contacting us. I'm happy to help.",
    "Hi! Thanks for reaching out, I'll look into this for you.",
    "Good day, and thank you for your message. Let me help you with that.",
]
VERIFY_REQUESTS = [
    "Could you please confirm your order number and the e-mail on your account?",
    "To find your order, could you give me the order number and your account e-mail?",
    "First, may I have your order number and the e-mail linked to your account?",
]
VERIFY_REPLIES = [
    "Sure, the order number is {order_id} and the e-mail is the one I'm writing from.",
    "Order {order_id}, same e-mail as this account.",
    "It's {order_id}. The e-mail is the one on my account.",
    "Yes: {order_id}.",
]
REACTIONS = {
    "resolved_in_chat": [
        "Great, thank you!",
        "Ok, that's clear. Thanks.",
        "Perfect, thanks for your help.",
        "Alright, thank you for checking.",
    ],
    "follow_up": [
        "Ok. I hope it gets sorted quickly.",
        "Alright, I'll wait for your e-mail then.",
        "Ok, thanks. Please keep me posted.",
        "Fine, but I really need this solved soon.",
    ],
    "escalated": [
        "Ok, thank you.",
        "Alright, I'll wait to hear from them.",
    ],
}
SUPERVISOR_REQUESTS = [
    "This is not acceptable. I want to speak to a supervisor.",
    "I'd like to talk to your supervisor about this, please.",
    "Can I speak to someone more senior? I'm not happy with this.",
]
SUPERVISOR_REPLIES = [
    "I understand. I have passed your case to my supervisor, who will contact you "
    "within 1 business day.",
    "Of course. I've escalated your case to a supervisor; you will hear from them "
    "within 1 business day.",
]
CLOSINGS = [
    "To sum up, {summary} Is there anything else I can help you with?",
    "So, {summary} Can I help you with anything else today?",
]
SUPERVISOR_SUMMARY = " A supervisor will also contact you within 1 business day."
GOODBYES = ["No, that's all. Bye!", "No, thank you.", "That's everything, thanks."]


def fmt_date(timestamp: pd.Timestamp) -> str:
    """Date as written in a chat, for example '12 March 2018'."""
    return f"{timestamp.day} {timestamp:%B %Y}"


def answer_and_summary(t: pd.Series) -> tuple[str, str]:
    """Advisor's main answer and one-sentence summary for the ticket's outcome."""
    status = STATUS_TEXT.get(t["order_status_at_contact"], t["order_status_at_contact"])
    estimate = fmt_date(t["order_estimated_delivery_date"])
    payment = t["primary_payment_type"]
    outcome = t["outcome"]

    if outcome == "tracking_shared":
        return (
            f'Your order is {status}. The tracking code is in "My orders" and in the '
            f"shipping e-mail. The estimated delivery date is {estimate}, and most "
            "orders arrive before it.",
            f"your order is on its way and should arrive by {estimate}.",
        )
    if outcome == "delay_acknowledged":
        days = int(t["days_past_estimate"])
        return (
            f"I'm sorry: your order is still {status} and the estimated date "
            f"({estimate}) passed {days} day{'s' if days > 1 else ''} ago. The parcel "
            "is still moving, so please allow 3 more business days. If it has not "
            "arrived by then, contact us and we will open an investigation with the "
            "carrier.",
            "your parcel is late but still moving; please allow 3 more business days.",
        )
    if outcome == "carrier_investigation":
        return (
            f"I'm very sorry. Your order is {status} but has been in transit for a "
            f"long time and the estimated date ({estimate}) has passed. I have opened "
            "an investigation with the carrier; it takes up to 5 business days. If the "
            "parcel is lost, you can choose a free re-shipment or a full refund.",
            "I opened a carrier investigation; you will get an answer within 5 "
            "business days.",
        )
    if outcome == "seller_contacted":
        return (
            f"Your order is {status}, but the seller has not handed it to the carrier "
            "on time. I have contacted the seller and asked them to ship it; we will "
            f"e-mail you the new expected date. The current estimate is {estimate}.",
            "I asked the seller to ship your order; we will e-mail you the new date.",
        )
    if outcome == "status_explained":
        return (
            f"Your order is currently {status}. The estimated delivery date is "
            f"{estimate}. You will receive an e-mail at each step.",
            f"your order is {status} and is expected by {estimate}.",
        )
    if outcome == "delivery_confirmed":
        return (
            "The carrier confirmed delivery on "
            f"{fmt_date(t['order_delivered_customer_date'])}. "
            "Please check with neighbours or reception; if you still cannot find it in "
            "2 days, we will open an investigation.",
            "the parcel is shown as delivered; contact us again in 2 days if missing.",
        )
    if outcome == "cancellation_confirmed":
        refund = (
            "As it was paid by boleto, we will need your bank details for the refund."
            if payment == "boleto"
            else REFUND_TIMING.get(payment, "")
        )
        return (
            f"Your order has been {status}, so nothing more will be shipped. "
            "Any amount "
            f"paid is refunded automatically. {refund}".strip(),
            "the order is canceled and the refund is automatic.",
        )
    if outcome == "order_canceled":
        return (
            f"Your order is still {status}, so I have canceled it for you free of "
            "charge. You will receive a confirmation e-mail, and any payment is "
            "refunded automatically.",
            "I canceled your order and the refund is automatic.",
        )
    if outcome == "refuse_delivery_advised":
        return (
            f"Your order is already {status}, so it can no longer be canceled. You can "
            "refuse the delivery when the carrier arrives, or return it free of charge "
            "within 7 days of receiving it; you will then get a full refund.",
            "you can refuse the delivery or return it within 7 days for a full refund.",
        )
    if outcome == "refund_timing_given":
        return (
            f"Your order was {status} and your refund has been approved. You paid by "
            f"{PAYMENT_TEXT.get(payment, payment)}: {REFUND_TIMING.get(payment, '')}",
            "your refund is approved and on its way.",
        )
    if outcome == "bank_details_requested":
        return (
            f"Your order was {status}. As you paid by boleto, the refund is made by "
            "bank transfer. Please reply to our e-mail with your bank, branch, account "
            "number and the account holder's CPF; the transfer is made within 10 "
            "business days after we receive them.",
            "please send your bank details by e-mail so we can transfer your refund.",
        )
    if outcome == "return_label_sent":
        return (
            "You can return the product free of charge within 7 days of delivery. I "
            "have started the return: a prepaid label will be e-mailed within 1 "
            "business day. Drop the parcel at any post office; the refund is approved "
            "within 3 business days after the seller receives it.",
            "I started your return; the prepaid label arrives by e-mail within 1 "
            "business day.",
        )
    if outcome == "replacement_or_refund_offered":
        return (
            "I'm sorry about this. Please reply with photos of the product, the "
            "packaging and the shipping label. You can choose a free replacement or a "
            "full refund, and the return shipping is free.",
            "send us the photos and choose a replacement or a refund; return is free.",
        )
    if outcome == "exchange_started":
        return (
            "No problem. Unused products can be exchanged for another size or colour "
            "within 30 days. I have started the exchange: the replacement ships as "
            "soon as the item you return is scanned at the post office.",
            "I started your exchange; the new item ships once your return is scanned.",
        )
    if outcome == "separate_parcels_explained":
        return (
            f"Your order contains items from {int(t['distinct_sellers'])} sellers, and "
            "each seller ships its own parcel, sometimes on different days. Please "
            "check \"My orders\" for the other parcel. If an item is still missing, "
            "tell us within 7 days of delivery.",
            "your items come in separate parcels from different sellers.",
        )
    if outcome == "seller_check_opened":
        return (
            "I'm sorry an item is missing. I have asked the seller to confirm what "
            "was packed; they have 2 business days. We will then re-ship the missing "
            "item or refund it.",
            "the seller is checking the parcel content, and we will re-ship or refund.",
        )
    if outcome == "installments_explained":
        return (
            f"I checked your payment: the order was paid by "
            f"{PAYMENT_TEXT.get(payment, payment)} in installments, so your statement "
            "shows one installment and not the full amount. Installment plans may "
            "include interest, shown at checkout.",
            "the amount on your statement is one installment of the order.",
        )
    if outcome == "voucher_split_explained":
        return (
            "Your order was paid partly with a voucher, so the card was only charged "
            "for the remaining amount.",
            "part of the order was paid with your voucher.",
        )
    if outcome == "escalated_payments":
        return (
            "I can see something unusual in the payment of this order. I have passed "
            "it to our payments team, who will contact you within 2 business days. "
            "Please keep a screenshot of the statement line.",
            "our payments team will contact you within 2 business days.",
        )
    if outcome == "cancel_and_reorder_advised":
        return (
            f"Items in a placed order cannot be changed. Your order is {status}, so "
            'you can still cancel it free of charge in "My orders" and place a new '
            "order with the right product.",
            "you can cancel the order for free and place a new one.",
        )
    if outcome == "exchange_advised":
        return (
            f"Your order is already {status}, so it can no longer be changed. Once you "
            "receive it, you can request an exchange for another size or colour "
            "within 30 days.",
            "you can request an exchange once you receive the order.",
        )
    if outcome == "invoice_sent":
        return (
            'Your invoice is available: open "My orders", select the order and '
            'choose "Invoice" to download the PDF. I have also sent a copy to your '
            "e-mail.",
            'the invoice is in "My orders" and in your e-mail.',
        )
    if outcome == "invoice_pending_explained":
        return (
            f"Your order is {status}. The invoice is issued by the seller just before "
            'shipping, and you will be able to download it from "My orders" then.',
            "the invoice will be available when the order ships.",
        )
    if outcome == "no_invoice_canceled":
        return (
            "This order was canceled before it was invoiced, so no invoice exists.",
            "no invoice exists for a canceled order.",
        )
    raise ValueError(f"No chat template for outcome '{outcome}'.")


def build_chat(ticket: pd.Series, rng: np.random.Generator) -> list[dict[str, object]]:
    """Messages of one ticket (speaker, text, knowledge-base chunk), without times."""

    def pick(options: list[str]) -> str:
        return options[int(rng.integers(len(options)))]

    answer, summary = answer_and_summary(ticket)
    messages: list[dict[str, object]] = [
        {"speaker": "customer", "text": ticket["message_text"], "kb_chunk_id": None},
        {
            "speaker": "advisor",
            "text": f"{pick(GREETINGS)} {pick(VERIFY_REQUESTS)}",
            "kb_chunk_id": VERIFY_CHUNK,
        },
        {
            "speaker": "customer",
            "text": pick(VERIFY_REPLIES).format(order_id=ticket["order_id"]),
            "kb_chunk_id": None,
        },
        {"speaker": "advisor", "text": answer, "kb_chunk_id": ticket["kb_chunk_id"]},
    ]
    if ticket["supervisor_requested"]:
        messages += [
            {
                "speaker": "customer",
                "text": pick(SUPERVISOR_REQUESTS),
                "kb_chunk_id": None,
            },
            {
                "speaker": "advisor",
                "text": pick(SUPERVISOR_REPLIES),
                "kb_chunk_id": ESCALATION_CHUNK,
            },
        ]
    else:
        reaction = pick(REACTIONS[ticket["outcome_class"]])
        messages.append({"speaker": "customer", "text": reaction, "kb_chunk_id": None})
    if ticket["supervisor_requested"]:
        summary += SUPERVISOR_SUMMARY
    closing = pick(CLOSINGS).format(summary=summary)
    messages.append(
        {"speaker": "advisor", "text": closing, "kb_chunk_id": CLOSING_CHUNK}
    )
    if rng.random() < 0.6:
        messages.append(
            {"speaker": "customer", "text": pick(GOODBYES), "kb_chunk_id": None}
        )
    return messages


def generate_chat_messages(
    tickets: pd.DataFrame,
    contacts: pd.DataFrame,
    orders: pd.DataFrame,
    random_seed: int,
) -> pd.DataFrame:
    """One row per chat message for every ticket.

    The first message is sent at ``opened_at`` and the last at ``chat_closed_at``;
    gaps in between are proportional to message length plus a random pause.
    """
    rng = np.random.default_rng(random_seed)
    facts = tickets.merge(
        contacts[["contact_id", "message_text"]], on="contact_id", validate="one_to_one"
    ).merge(
        orders[
            [
                "order_id",
                "order_estimated_delivery_date",
                "order_delivered_customer_date",
                "primary_payment_type",
                "distinct_sellers",
            ]
        ],
        on="order_id",
        how="left",
        validate="many_to_one",
    )
    rows = []
    for ticket in facts.itertuples(index=False):
        ticket_series = pd.Series(ticket._asdict())
        messages = build_chat(ticket_series, rng)
        # Time before each message after the first: typing time + a random pause
        weights = np.array([len(str(m["text"])) for m in messages[1:]], dtype=float)
        weights = weights + rng.exponential(60, len(weights))
        offsets = np.concatenate([[0.0], np.cumsum(weights) / weights.sum()])
        offsets *= ticket.handle_seconds
        for turn, (message, offset) in enumerate(zip(messages, offsets), start=1):
            rows.append(
                {
                    "message_id": f"{ticket.ticket_id}-{turn:02d}",
                    "ticket_id": ticket.ticket_id,
                    "turn": turn,
                    "speaker": message["speaker"],
                    "sent_at": ticket.opened_at + pd.Timedelta(seconds=round(offset)),
                    "text": message["text"],
                    "kb_chunk_id": message["kb_chunk_id"],
                }
            )
    return pd.DataFrame(rows)
