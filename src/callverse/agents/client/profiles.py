"""Customer profiles for the Client agent (twin input).

A profile = a real (synthetic) contact of the history: who writes, about which
order, why (the hidden situation of the generator), with which opening message
(a Bitext customer message), plus a persona (impatient / normal / patient) that
drives tone and patience. Repeat contacts on the same order are more often
impatient.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from callverse.config import load_yaml

# Big Brazilian banks (COMPE codes): Banco do Brasil, Santander, Caixa, Bradesco, Itaú,
# Nubank, Inter, C6. A customer refunded by bank transfer names one of them.
CUSTOMER_BANKS = ["001", "033", "104", "237", "341", "260", "077", "336"]
BANK_TYPO_SHARE = 0.2  # share of customers who first type the code with an extra digit


def customer_bank(contact_id: str) -> tuple[str, str]:
    """(bank code, code as first typed) of a customer, fixed by the contact id.

    A hash, not the profile's random generator, so adding banks does not change the
    personas of existing samples. A typo repeats the last digit ("3411"): a 4-digit code
    never exists, so the advisor's bank check has something to catch.
    """
    digest = int(hashlib.sha256(contact_id.encode("utf-8")).hexdigest(), 16)
    code = CUSTOMER_BANKS[digest % len(CUSTOMER_BANKS)]
    typo = (digest // len(CUSTOMER_BANKS)) % 100 < BANK_TYPO_SHARE * 100
    return code, (code + code[-1] if typo else code)

SITUATION_TEXT = {
    "overdue_never_delivered": "Your order has not arrived and the promised delivery date has passed.",
    "delivered_late": "Your order is late: the promised delivery date has passed.",
    "seller_shipped_late": "The tracking has shown no movement for days.",
    "on_time_tracking_check": "You just want to know where your order is.",
    "canceled_or_unavailable": "You paid but the order was canceled or is unavailable; you want your money.",
    "post_delivery_problem": "You received the order but something is wrong with it.",
    "payment_anomaly": "The amount charged looks different from what you expected.",
    "change_before_shipping": "You want to change something in the order before it ships.",
    "invoice_request": "You need the invoice of the order.",
}


@dataclass(frozen=True)
class CustomerProfile:
    """Everything the Client agent knows about the customer it plays."""

    contact_id: str
    order_id: str
    customer_unique_id: str
    contact_timestamp: pd.Timestamp
    intent: str
    intent_group: str
    opening_message: str
    situation: str
    persona: str
    tone: str
    is_repeat_contact: bool
    bank_code: str = ""  # for a refund by bank transfer (boleto)
    bank_code_typed: str = ""  # what the customer types first (sometimes a typo)

    def situation_text(self) -> str:
        return SITUATION_TEXT.get(self.situation, "You have a question about your order.")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["contact_timestamp"] = str(self.contact_timestamp)
        return data


def persona_settings() -> tuple[dict[str, dict[str, Any]], float]:
    raw = load_yaml("agents")["client"]
    return raw["personas"], float(raw["repeat_contact_impatient_share"])


def build_profile(contact: pd.Series, rng: np.random.Generator, is_repeat: bool) -> CustomerProfile:
    """Profile of one contact row (``synthetic_contacts``)."""
    personas, repeat_impatient = persona_settings()
    names = list(personas)
    if is_repeat and rng.random() < repeat_impatient:
        persona = "impatient"
    else:
        shares = np.array([personas[n]["share"] for n in names], dtype=float)
        persona = names[int(rng.choice(len(names), p=shares / shares.sum()))]
    bank_code, bank_code_typed = customer_bank(str(contact["contact_id"]))
    return CustomerProfile(
        contact_id=str(contact["contact_id"]),
        order_id=str(contact["order_id"]),
        customer_unique_id=str(contact["customer_unique_id"]),
        contact_timestamp=pd.Timestamp(contact["contact_timestamp"]),
        intent=str(contact["intent"]),
        intent_group=str(contact["intent_group"]),
        opening_message=str(contact["message_text"]),
        situation=str(contact.get("generator_situation", "")),
        persona=persona,
        tone=str(personas[persona]["tone"]),
        is_repeat_contact=is_repeat,
        bank_code=bank_code,
        bank_code_typed=bank_code_typed,
    )


def sample_profiles(
    contacts: pd.DataFrame,
    n: int,
    seed: int = 0,
    period: tuple[str, str] | None = None,
    intent_group: str | None = None,
) -> list[CustomerProfile]:
    """Random contacts of the history turned into customer profiles."""
    rng = np.random.default_rng(seed)
    frame = contacts.sort_values("contact_timestamp")
    repeat = frame.duplicated("order_id", keep="first")
    frame = frame.assign(is_repeat=repeat.to_numpy())
    if period:
        frame = frame[frame["contact_timestamp"].between(period[0], period[1])]
    if intent_group:
        frame = frame[frame["intent_group"] == intent_group]
    if "bitext_tags" in frame:
        frame = frame[~frame["bitext_tags"].fillna("").str.contains("W")]
    picked = frame.iloc[rng.choice(len(frame), size=min(n, len(frame)), replace=False)]
    return [build_profile(row, rng, bool(row["is_repeat"])) for _, row in picked.iterrows()]



def profile_by_contact_id(contacts: pd.DataFrame, contact_id: str, seed: int = 0) -> CustomerProfile:
    """Profile of a given contact."""
    frame = contacts.sort_values("contact_timestamp")
    repeat = frame.duplicated("order_id", keep="first")
    row = frame[frame["contact_id"] == contact_id]
    if row.empty:
        raise KeyError(f"No contact {contact_id}")
    return build_profile(row.iloc[0], np.random.default_rng(seed), bool(repeat[row.index[0]]))
