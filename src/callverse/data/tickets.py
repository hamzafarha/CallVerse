"""Synthetic support tickets: one per contact, with a rule-based outcome."""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

WISMO_INTENTS = {"track_order", "track_delivery", "delivery_time", "delivery_issue"}
REFUND_INTENTS = {"request_refund", "refund_status"}
CLOSED_STATUSES = {"canceled", "unavailable"}

ORDER_COLUMNS = [
    "order_id",
    "order_status",
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "latest_shipping_limit_date",
    "primary_payment_type",
    "payment_minus_order_value",
    "max_installments",
    "uses_voucher",
    "distinct_sellers",
]


@dataclass(frozen=True)
class TicketConfig:
    """Ticket assumptions, loaded from ``configs/data.yaml`` (generation.tickets)."""

    version: int
    random_seed: int
    channel: str
    investigation_after_days_late: int
    investigation_transit_days: int
    follow_up_business_days: dict[str, int]
    supervisor_request_rate: dict[str, float]
    csat_response_rate: float
    csat_score_shares: dict[str, list[float]]


def load_ticket_config(path: str | Path) -> TicketConfig:
    """Read the ticket assumptions from a YAML file."""
    with open(path, encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)["generation"]["tickets"]
    config = TicketConfig(
        version=int(raw["version"]),
        random_seed=int(raw["random_seed"]),
        channel=str(raw["decisions"]["channel"]),
        investigation_after_days_late=int(raw["investigation_after_days_late"]),
        investigation_transit_days=int(raw["investigation_transit_days"]),
        follow_up_business_days={
            k: int(v) for k, v in raw["follow_up_business_days"].items()
        },
        supervisor_request_rate={
            k: float(v) for k, v in raw["supervisor_request_rate"].items()
        },
        csat_response_rate=float(raw["csat"]["response_rate"]),
        csat_score_shares={
            k: [float(s) for s in v] for k, v in raw["csat"]["score_shares"].items()
        },
    )
    for outcome_class, shares in config.csat_score_shares.items():
        if len(shares) != 5 or not math.isclose(sum(shares), 1.0, abs_tol=1e-6):
            raise ValueError(
                f"CSAT shares of {outcome_class} must be 5 values summing to 1."
            )
    return config


def order_status_at(orders: pd.DataFrame, at: pd.Series) -> pd.Series:
    """Order status as known at time ``at`` (row by row), from the Olist timestamps.

    Olist has no cancellation date, so canceled or unavailable orders are treated as
    such from the start. "processing" and "invoiced" have no timestamp and are folded
    into "approved".
    """

    def reached(column: str) -> pd.Series:
        return orders[column].notna() & (orders[column] <= at)

    final = orders["order_status"]
    conditions = [
        final.isin(CLOSED_STATUSES),
        reached("order_delivered_customer_date"),
        reached("order_delivered_carrier_date"),
        reached("order_approved_at"),
    ]
    choices = [final, "delivered", "shipped", "approved"]
    return pd.Series(
        np.select(conditions, choices, default="created"), index=orders.index
    )


def wismo_outcome(row: pd.Series) -> tuple[str, str, str | None]:
    """Where-is-my-order intents: answer depends on status and lateness."""
    status = row["order_status_at_contact"]
    intent = row["intent"]
    if status in CLOSED_STATUSES:
        return "cancellation_confirmed", "cancellations_and_order_changes__s03", None
    if status == "delivered":
        chunk = (
            "delivery_times_and_delays__s06"
            if intent == "delivery_issue"
            else "order_status_and_tracking__s01"
        )
        return "delivery_confirmed", chunk, None
    if status in {"created", "approved"}:
        if row["opened_at"] > row["latest_shipping_limit_date"]:
            return "seller_contacted", "order_status_and_tracking__s04", "seller"
        return "status_explained", "order_status_and_tracking__s01", None
    # shipped
    if row["needs_investigation"]:
        return "carrier_investigation", "delivery_times_and_delays__s03", "carrier"
    if row["days_past_estimate"] > 0:
        return "delay_acknowledged", "delivery_times_and_delays__s03", None
    if intent in {"track_order", "track_delivery"}:
        return "tracking_shared", "order_status_and_tracking__s02", None
    return "tracking_shared", "delivery_times_and_delays__s01", None


def cancel_refund_outcome(row: pd.Series) -> tuple[str, str, str | None]:
    """Cancellation and refund intents: answer depends on status and payment type."""
    status = row["order_status_at_contact"]
    intent = row["intent"]
    if status in CLOSED_STATUSES:
        if intent == "cancel_order":
            return (
                "cancellation_confirmed",
                "cancellations_and_order_changes__s03",
                None,
            )
        if row["primary_payment_type"] == "boleto":
            return "bank_details_requested", "refund_policy__s05", "payments_team"
        chunk = (
            "refund_policy__s04" if intent == "refund_status" else "refund_policy__s03"
        )
        return "refund_timing_given", chunk, None
    if status in {"created", "approved"}:
        return "order_canceled", "cancellations_and_order_changes__s02", None
    if status == "shipped":
        return "refuse_delivery_advised", "cancellations_and_order_changes__s01", None
    return "return_label_sent", "returns_and_exchanges__s01", None


POST_DELIVERY_OUTCOMES = {
    "damaged_delivery": (
        "replacement_or_refund_offered",
        "damaged_wrong_missing_items__s01",
    ),
    "wrong_item": ("replacement_or_refund_offered", "damaged_wrong_missing_items__s02"),
    "product_issue": ("return_label_sent", "damaged_wrong_missing_items__s04"),
    "return_product": ("return_label_sent", "returns_and_exchanges__s01"),
    "return_product_online": ("return_label_sent", "returns_and_exchanges__s03"),
    "exchange_product": ("exchange_started", "returns_and_exchanges__s04"),
}


def post_delivery_outcome(row: pd.Series) -> tuple[str, str, str | None]:
    """Problems after delivery; before delivery the advisor explains the status."""
    if row["order_status_at_contact"] != "delivered":
        return "status_explained", "order_status_and_tracking__s01", None
    if row["intent"] == "missing_item":
        if row["distinct_sellers"] > 1:
            return "separate_parcels_explained", "order_status_and_tracking__s05", None
        return "seller_check_opened", "damaged_wrong_missing_items__s03", "seller"
    outcome, chunk = POST_DELIVERY_OUTCOMES[row["intent"]]
    return outcome, chunk, None


def order_admin_outcome(row: pd.Series) -> tuple[str, str, str | None]:
    """Order changes, invoices and payment problems."""
    status = row["order_status_at_contact"]
    intent = row["intent"]
    if intent == "payment_issue":
        if row["primary_payment_type"] == "not_defined":
            return "escalated_payments", "payment_policy__s05", "payments_team"
        if abs(row["payment_minus_order_value"]) > 1 and row["max_installments"] > 1:
            return "installments_explained", "payment_policy__s05", None
        if row["uses_voucher"]:
            return "voucher_split_explained", "payment_policy__s06", None
        return "escalated_payments", "payment_policy__s05", "payments_team"
    if status in CLOSED_STATUSES:
        if intent == "request_invoice":
            return "no_invoice_canceled", "invoices__s03", None
        return "cancellation_confirmed", "cancellations_and_order_changes__s03", None
    if intent == "change_order":
        if status in {"created", "approved"}:
            return (
                "cancel_and_reorder_advised",
                "cancellations_and_order_changes__s05",
                None,
            )
        return "exchange_advised", "cancellations_and_order_changes__s05", None
    # request_invoice
    if status in {"shipped", "delivered"}:
        return "invoice_sent", "invoices__s02", None
    return "invoice_pending_explained", "invoices__s01", None


def decide_outcome(row: pd.Series) -> tuple[str, str, str | None]:
    """Outcome, knowledge-base chunk used, and the party the case is handed to."""
    if row["intent"] in WISMO_INTENTS:
        return wismo_outcome(row)
    if row["intent"] in REFUND_INTENTS or row["intent"] == "cancel_order":
        return cancel_refund_outcome(row)
    if row["intent"] in POST_DELIVERY_OUTCOMES or row["intent"] == "missing_item":
        return post_delivery_outcome(row)
    return order_admin_outcome(row)


def add_business_days(timestamps: pd.Series, days: pd.Series) -> pd.Series:
    """Shift timestamps by whole business days (Mon-Fri), keeping the time of day.

    Zero days leaves the timestamp unchanged, even on a weekend.
    """
    dates = timestamps.dt.normalize()
    shifted = np.busday_offset(
        dates.to_numpy().astype("datetime64[D]"),
        days.to_numpy().astype(int),
        roll="forward",
    )
    moved = timestamps + (pd.to_datetime(shifted) - dates.to_numpy())
    return moved.where(days.to_numpy() > 0, timestamps)


def lognormal_seconds(
    mean: np.ndarray, cv: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Lognormal draws with the given means and coefficients of variation."""
    sigma_squared = np.log(1 + cv**2)
    mu = np.log(mean) - sigma_squared / 2
    return rng.lognormal(mu, np.sqrt(sigma_squared))


def generate_tickets(
    contacts: pd.DataFrame,
    orders: pd.DataFrame,
    config: TicketConfig,
    service_times: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    """One ticket per contact, with outcome, handle time, resolution time and CSAT.

    ``service_times`` maps each intent group to (mean handle seconds, CV), taken from
    the simulation config so tickets and simulation agree.
    """
    rng = np.random.default_rng(config.random_seed)
    tickets = contacts[
        [
            "contact_id",
            "order_id",
            "customer_unique_id",
            "intent",
            "intent_group",
            "contact_timestamp",
        ]
    ].rename(columns={"contact_timestamp": "opened_at"})
    tickets = tickets.merge(
        orders[ORDER_COLUMNS], on="order_id", how="left", validate="many_to_one"
    )
    if tickets["order_status"].isna().any():
        raise ValueError("Some contacts refer to orders missing from the order table.")

    tickets.insert(0, "ticket_id", tickets["contact_id"].str.replace("SC", "TK", n=1))
    tickets["channel"] = config.channel
    tickets["order_status_at_contact"] = order_status_at(tickets, tickets["opened_at"])
    tickets["days_past_estimate"] = (
        tickets["opened_at"].dt.normalize()
        - tickets["order_estimated_delivery_date"].dt.normalize()
    ).dt.days
    days_in_transit = (
        tickets["opened_at"] - tickets["order_delivered_carrier_date"]
    ).dt.days
    tickets["needs_investigation"] = tickets["order_status_at_contact"].eq(
        "shipped"
    ) & (
        (tickets["days_past_estimate"] > config.investigation_after_days_late)
        | (
            (tickets["days_past_estimate"] > 0)
            & (days_in_transit > config.investigation_transit_days)
        )
    )

    decisions = tickets.apply(decide_outcome, axis=1, result_type="expand")
    tickets[["outcome", "kb_chunk_id", "handed_to"]] = decisions
    follow_up = tickets["outcome"].isin(config.follow_up_business_days)
    escalated = tickets["outcome"].eq("escalated_payments")
    tickets["outcome_class"] = np.select(
        [escalated, follow_up], ["escalated", "follow_up"], default="resolved_in_chat"
    )

    # Supervisor requests, drawn per outcome class
    request_rate = (
        tickets["outcome_class"].map(config.supervisor_request_rate).fillna(0)
    )
    tickets["supervisor_requested"] = rng.random(len(tickets)) < request_rate
    tickets.loc[tickets["supervisor_requested"], ["handed_to", "outcome_class"]] = [
        "supervisor",
        "escalated",
    ]

    # Handle time from the simulation's lognormal per intent group
    unknown_groups = set(tickets["intent_group"]) - set(service_times)
    if unknown_groups:
        raise ValueError(f"No handle time for intent groups {sorted(unknown_groups)}.")
    mean = tickets["intent_group"].map(lambda g: service_times[g][0]).to_numpy(float)
    cv = tickets["intent_group"].map(lambda g: service_times[g][1]).to_numpy(float)
    tickets["handle_seconds"] = np.round(lognormal_seconds(mean, cv, rng)).astype(int)
    tickets["chat_closed_at"] = tickets["opened_at"] + pd.to_timedelta(
        tickets["handle_seconds"], unit="s"
    )

    # Resolution: at the end of the chat, or after the follow-up work
    days = tickets["outcome"].map(config.follow_up_business_days).fillna(0)
    days += np.where(
        tickets["supervisor_requested"],
        config.follow_up_business_days["supervisor_callback"],
        0,
    )
    tickets["resolved_at"] = add_business_days(tickets["chat_closed_at"], days)
    # A carrier investigation ends early if the parcel is delivered in the meantime
    delivered_during = tickets["outcome"].eq("carrier_investigation") & tickets[
        "order_delivered_customer_date"
    ].between(tickets["chat_closed_at"], tickets["resolved_at"])
    tickets.loc[delivered_during, "resolved_at"] = tickets.loc[
        delivered_during, "order_delivered_customer_date"
    ]
    tickets["first_contact_resolution"] = tickets["outcome_class"].eq(
        "resolved_in_chat"
    )

    # Post-chat survey
    answered = rng.random(len(tickets)) < config.csat_response_rate
    scores = pd.Series(pd.NA, index=tickets.index, dtype="Int64")
    for outcome_class, shares in config.csat_score_shares.items():
        rows = answered & tickets["outcome_class"].eq(outcome_class).to_numpy()
        scores[rows] = rng.choice(np.arange(1, 6), size=int(rows.sum()), p=shares)
    tickets["csat_score"] = scores

    tickets["is_synthetic"] = True
    tickets["generator_version"] = config.version
    tickets["generator_seed"] = config.random_seed
    return tickets[
        [
            "ticket_id",
            "contact_id",
            "order_id",
            "customer_unique_id",
            "channel",
            "intent",
            "intent_group",
            "opened_at",
            "order_status_at_contact",
            "days_past_estimate",
            "outcome",
            "outcome_class",
            "handed_to",
            "kb_chunk_id",
            "supervisor_requested",
            "handle_seconds",
            "chat_closed_at",
            "resolved_at",
            "first_contact_resolution",
            "csat_score",
            "is_synthetic",
            "generator_version",
            "generator_seed",
        ]
    ]
