"""Evidence the customer can attach to a message: photos and a statement screenshot.

The Client agent's ``send_evidence(kinds)`` tool: like a phone's photo picker, one call
attaches one or several files. Each attachment is a simulated file
(no image), described from the customer's REAL situation: its true problem (the
contact's intent, which the advisor may have misread), the order's product, dates and
payment in the database. The LLM chooses what to send and when; it never writes the
content, so it cannot invent proof. A file the customer cannot have yet (a photo of an
order not delivered) is refused, like a real phone would have nothing to show.

The policy asks for this evidence: photos of the product, the packaging and the
shipping label for damaged or wrong items, a screenshot of the statement line for
payment problems (``data/knowledge_base/docs``).
"""

import hashlib
from typing import Any

import pandas as pd

# The four kinds of files and their labels (shown on the attachment card).
EVIDENCE_KINDS = {
    "product_photo": "Photo of the product",
    "packaging_photo": "Photo of the packaging",
    "shipping_label_photo": "Photo of the shipping label",
    "payment_statement": "Screenshot of the statement line",
}

# Simulated details, fixed per customer by a hash of the contact id (like the bank code)
DAMAGE = [
    "cracked across the front",
    "broken into two pieces",
    "dented and scratched",
    "with a part snapped off",
]
BOX_DAMAGE = ["crushed on one corner", "torn open on one side", "wet and dented", "squashed flat on top"]
DEFECT = ["it does not switch on", "a part is missing from the box", "it stopped working after one use"]


def _variant(contact_id: str, options: list[str], salt: str) -> str:
    """Pick one option from a list, always the same for a given customer (a hash of its id)."""
    digest = int(hashlib.sha256(f"{salt}:{contact_id}".encode()).hexdigest(), 16)
    return options[digest % len(options)]


def _day(value: Any) -> str | None:
    """A date as YYYY-MM-DD text, or None."""
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def _known(value: Any) -> bool:
    """True when a value exists (not None, not NaN)."""
    return value is not None and not pd.isna(value)


def _reached(value: Any, as_of: pd.Timestamp) -> bool:
    """True when a date exists and is on or before the chat date (it has already happened)."""
    return value is not None and not pd.isna(value) and pd.Timestamp(value) <= as_of


def make_evidence(kind: str, profile: Any) -> dict[str, Any]:
    """The attachment of one kind for this customer, or ``{"error": ...}`` when it
    cannot exist yet (the tool result either way)."""
    from callverse.agents.advisor.tools import AdvisorTools

    # Validation 1: an unknown kind is refused.
    if kind not in EVIDENCE_KINDS:
        return {"error": f"unknown kind {kind!r}; use one of {', '.join(EVIDENCE_KINDS)}"}
    # The order record as of the chat date (the twin replays history).
    as_of = pd.Timestamp(profile.contact_timestamp)
    facts = AdvisorTools(as_of=as_of).order_facts(profile.order_id, profile.intent)
    if facts is None:
        return {"error": "order not found"}
    intent = profile.intent
    product = str(facts.get("primary_category_english") or "product").replace("_", " ")
    delivered = _reached(facts.get("order_delivered_customer_date"), as_of)
    cid = profile.contact_id

    # Validation 2: no photo of a parcel that has not arrived yet.
    if kind in {"product_photo", "packaging_photo"} and not delivered:
        return {"error": "you have not received the parcel yet, so there is nothing to photograph"}
    if kind == "product_photo":
        # The photo shows the customer's TRUE problem (its real intent), even if the advisor misunderstood it.
        items = int(facts["item_count"]) if _known(facts.get("item_count")) else 1
        description = {
            "damaged_delivery": f"the {product} is {_variant(cid, DAMAGE, 'damage')}",
            "wrong_item": f"the item in the box is a different product, not the {product} I ordered",
            "product_issue": f"the {product}: {_variant(cid, DEFECT, 'defect')}",
            "missing_item": (
                f"the parcel content: {items - 1} of the {items} items ordered"
                if items > 1
                else "the parcel content: only the packing list, no item"
            ),
        }.get(intent, f"the {product}, unused, in its original packaging")
    elif kind == "packaging_photo":
        description = (
            f"the box is {_variant(cid, BOX_DAMAGE, 'box')}"
            if intent == "damaged_delivery"
            else "the box is intact"
        )
    elif kind == "shipping_label_photo":
        # Validation 3: no shipping label before the order was shipped.
        if not _reached(facts.get("order_delivered_carrier_date"), as_of):
            return {"error": "the order has not been shipped yet, so there is no shipping label"}
        description = (
            f"order {profile.order_id[:8]}..., handed to the carrier on "
            f"{_day(facts['order_delivered_carrier_date'])}, to "
            f"{str(facts.get('customer_city', '')).title()}/{facts.get('customer_state', '')}"
        )
    else:  # payment_statement
        # Validation 4: no statement line before the payment was taken.
        if not _reached(facts.get("order_approved_at"), as_of):
            return {"error": "no payment has been taken yet, so there is no statement line"}
        total = float(facts["payment_total"]) if _known(facts.get("payment_total")) else 0.0
        payment = str(facts.get("primary_payment_type") or "")
        installments = int(facts["max_installments"]) if _known(facts.get("max_installments")) else 1
        paid_on = _day(facts["order_approved_at"])
        # What the statement shows depends on how the customer paid: boleto (a Brazilian bank slip), card in
        # installments (one installment a month), or card in one go.
        if payment == "boleto":
            description = f"boleto of R$ {total:.2f} paid on {paid_on}"
        elif installments > 1:
            description = (
                f"card line of R$ {total / installments:.2f} on {paid_on}: installment 1 of "
                f"{installments} (R$ {total:.2f} in total)"
            )
        else:
            description = f"card line of R$ {total:.2f} on {paid_on}"
        if _known(facts.get("uses_voucher")) and bool(facts["uses_voucher"]):
            description += ", part of the order paid with a voucher"

    # A stable fake file name (IMG_1234.jpg), the same for the same customer and kind.
    digest = int(hashlib.sha256(f"{kind}:{cid}".encode()).hexdigest(), 16)
    prefix, extension = ("Screenshot", "png") if kind == "payment_statement" else ("IMG", "jpg")
    return {
        "kind": kind,
        "label": EVIDENCE_KINDS[kind],
        "file": f"{prefix}_{digest % 9000 + 1000}.{extension}",
        "description": description,
        "simulated": True,  # a described file, not a real image
    }


def send_files(kinds: Any, profile: Any, sent: set[str]) -> dict[str, Any]:
    """Run ``send_evidence``: attach each kind once (validation: known kind, not sent
    before in this chat, possible for this order); the others are refused with a reason."""
    if isinstance(kinds, str):  # tolerate a single kind instead of a list
        kinds = [kinds]
    attached: list[dict[str, Any]] = []
    refused: list[dict[str, str]] = []
    # dict.fromkeys keeps the order and removes duplicates.
    for kind in dict.fromkeys(str(k) for k in kinds or []):  # each kind once, in order
        if kind in sent:
            refused.append({"kind": kind, "error": f"you already sent your {EVIDENCE_KINDS[kind].lower()}"})
            continue
        file = make_evidence(kind, profile)
        if "error" in file:
            refused.append({"kind": kind, "error": file["error"]})
        else:
            attached.append(file)
    if not attached and not refused:
        refused.append({"kind": "", "error": "no file selected"})
    return {"attached": attached, "refused": refused}


def attachments_text(message: dict[str, Any]) -> str:
    """The message as the other side sees it: its text, then one line per attachment."""
    text = str(message.get("text", ""))
    files = (message.get("meta") or {}).get("attachments") or []
    # Example: "[Attached photo of the product (IMG_8829.jpg): the furniture decor is broken into two
    # pieces]".
    lines = [f"[Attached {f['label'].lower()} ({f['file']}): {f['description']}]" for f in files]
    return "\n".join([text, *lines]) if lines else text


def summarize_evidence(result: dict[str, Any]) -> str:
    """One line for the UI."""
    parts = []
    if result.get("attached"):
        # For example "sent 3 files (product, packaging, shipping label)".
        names = ", ".join(f["label"].lower().replace("photo of the ", "") for f in result["attached"])
        count = len(result["attached"])
        parts.append(f"sent {count} file{'s' if count > 1 else ''} ({names})")
    parts += [f"{r['kind'] or 'file'} refused: {r['error']}" for r in result.get("refused", [])]
    return "; ".join(parts)
