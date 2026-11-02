"""Advisor tools for agentic tool calling: fact check, bank directory, gating, history."""

import json
import sqlite3

import pandas as pd
import pytest

from callverse.agents.advisor.bank_directory import BankDirectory, BankDirectoryUnavailable
from callverse.agents.advisor.draft_check import Sources, check_draft, find_dates, find_timings, parse_amount
from callverse.agents.advisor.tools import SCHEMAS_BY_NAME, AdvisorTools, agentic_tool_names
from tests.conftest import requires_data

ORDER = "e481f51cbdc54678b7cc49136f2d6af7"
APPROVED = (
    "I'm sorry: your order is still with the carrier and the estimated date (20 May 2018) passed "
    "5 days ago. The parcel is still moving, so please allow 3 more business days."
)


def sources() -> Sources:
    facts = {
        "order_id": ORDER,
        "estimated_delivery": "2018-05-20",
        "order_value_brl": 129.9,
        "days_past_estimated_date": 5,
    }
    return Sources.collect([facts], [APPROVED], ORDER)


# ------------------------------------------------------------------ draft check
def test_draft_with_sourced_facts_passes() -> None:
    draft = (
        "Your order was due on May 20, 2018 and is 5 days late (R$ 129,90). "
        "Please allow three more business days."
    )
    assert check_draft(draft, sources()).passed


@pytest.mark.parametrize(
    ("draft", "problem"),
    [
        ("It will arrive on 15 May.", "date"),
        ("It will arrive tomorrow.", "tomorrow"),
        ("You will get R$ 150 back.", "amount"),
        ("Please allow 2 business days.", "timing"),
        ("Order 0123456789abcdef0123456789abcdef is late.", "order number"),
        ("Please send me your card number.", "card number"),
        ("Olá, obrigado, seu pedido está a caminho, por favor aguarde.", "English"),
    ],
)
def test_draft_problems_are_caught(draft: str, problem: str) -> None:
    check = check_draft(draft, sources())
    assert not check.passed and any(problem in p for p in check.problems)


def test_negations_and_ordinary_words_are_not_flagged() -> None:
    draft = "We will never ask for your password. Maybe the Marketing team can help."
    assert check_draft(draft, sources()).passed


def test_extraction_helpers() -> None:
    assert find_dates("on 12/03/2018")[0][1] == {(2018, 3, 12), (2018, 12, 3)}
    assert find_timings("within forty-eight hours")[0][1] == (48, "hour")
    assert find_timings("5 working days")[0][1] == (5, "business day")
    assert parse_amount("1.234,56") == parse_amount("1,234.56") == 1234.56
    assert parse_amount("30") == 30


# --------------------------------------------------------------- bank directory
def fake_banks(url: str, timeout: float) -> list[dict]:
    return [
        {"code": 341, "name": "ITAU", "fullName": "Itaú Unibanco S.A.", "ispb": "60701190"},
        {"code": None, "name": "an institution without a code"},
    ]


def test_bank_directory_downloads_once_then_reads_the_cache(tmp_path) -> None:
    downloads: list[str] = []

    def downloader(url: str, timeout: float) -> list[dict]:
        downloads.append(url)
        return fake_banks(url, timeout)

    cache = tmp_path / "banks.json"
    first = BankDirectory("https://example.test/banks", cache, downloader=downloader)
    assert first.lookup("341")["full_name"] == "Itaú Unibanco S.A."
    assert first.lookup("999") is None
    second = BankDirectory("https://example.test/banks", cache, downloader=downloader)
    assert second.lookup("341") is not None
    assert len(downloads) == 1  # the second directory read the file, not the API
    assert json.loads(cache.read_text(encoding="utf-8"))["banks"] == [
        {"code": "341", "name": "ITAU", "full_name": "Itaú Unibanco S.A.", "ispb": "60701190"}
    ]


def test_bank_directory_offline_without_cache(tmp_path) -> None:
    def offline(url: str, timeout: float) -> list[dict]:
        raise OSError("no network")

    with pytest.raises(BankDirectoryUnavailable):
        BankDirectory("https://example.test/banks", tmp_path / "banks.json", downloader=offline).load()


# ---------------------------------------------------------------------- gating
def test_gating_offers_at_most_five_tools_per_stage() -> None:
    for group in ["wismo", "cancel_refund", "post_delivery", "order_admin", None]:
        names = agentic_tool_names("investigate", group)
        assert names[0] == "lookup_order" and len(names) <= 5
        assert all(name in SCHEMAS_BY_NAME for name in names)
    assert agentic_tool_names("verify") == ["search_knowledge_base", "escalate_to_human"]
    assert "validate_bank_code" not in agentic_tool_names("follow_up")
    assert agentic_tool_names("follow_up", paid_by_boleto=True)[-1] == "validate_bank_code"
    with pytest.raises(ValueError):
        agentic_tool_names("closing")


# ----------------------------------------------------------------------- tools
def make_tools(tmp_path) -> AdvisorTools:
    banks = BankDirectory("https://example.test/banks", tmp_path / "banks.json", downloader=fake_banks)
    return AdvisorTools(as_of=pd.Timestamp("2018-05-25 10:00"), banks=banks)


def test_validate_bank_code(tmp_path) -> None:
    tools = make_tools(tmp_path)
    assert tools.validate_bank_code("341")["bank_name"] == "Itaú Unibanco S.A."
    assert tools.validate_bank_code("1")["valid"] is False  # 001 is not in the fake list
    assert "3 digits" in tools.validate_bank_code("3411")["reason"]
    assert all(call.ok for call in tools.calls)  # an unknown code is an answer, not a failure


def test_escalation_happens_once_and_callers_are_recorded(tmp_path) -> None:
    tools = make_tools(tmp_path)
    first = json.loads(tools.execute("escalate_to_human", {"reason": "PROCON complaint", "urgency": "high"}))
    assert first["handed_to"] == "supervisor" and "1 business day" in first["tell_customer"]
    with tools.called_by("safety_net"):
        again = tools.escalate_to_human("customer asked for a supervisor")
    assert again["already_escalated"] and len(tools.opened_tickets) == 1
    assert [call.caller for call in tools.calls] == ["llm", "safety_net"]
    assert "error" in json.loads(tools.execute("escalate_to_human", {"reason": "x", "urgency": "now"}))


def test_check_draft_reply_ignores_its_own_earlier_results(tmp_path) -> None:
    tools = make_tools(tmp_path)
    assert not tools.check_draft_reply("It arrives on 15 May.")["passed"]
    # The first result quotes "15 May" in its problems: that must not become a source.
    assert not tools.check_draft_reply("It arrives on 15 May.")["passed"]
    assert tools.check_draft_reply("It arrives on 20 May.", approved_answer=APPROVED)["passed"]


def test_tool_calls_have_a_one_line_summary(tmp_path) -> None:
    from callverse.agents.advisor.tools import summarize_tool_call

    tools = make_tools(tmp_path)
    tools.validate_bank_code("341")
    tools.validate_bank_code("3411")
    tools.escalate_to_human("PROCON complaint", urgency="high")
    tools.check_draft_reply("It arrives on 15 May.")
    assert [call.summary for call in tools.calls] == [
        "341 = Itaú Unibanco S.A.",
        "3411 is not a bank code",
        "NEW-001 handed to supervisor",
        "draft rejected: The date '15 May' is not in the order record, the approved answer or the policy.",
    ]
    assert summarize_tool_call("lookup_order", False, {"error": "No order x."}) == "No order x."


@requires_data
def test_customer_history_never_shows_the_future() -> None:
    from callverse.config import database_path

    with sqlite3.connect(database_path()) as connection:
        order_id, opened_at = connection.execute(
            "SELECT t.order_id, t.opened_at FROM tickets t WHERE EXISTS (SELECT 1 FROM orders o "
            "WHERE o.customer_unique_id = t.customer_unique_id AND o.order_id <> t.order_id "
            "AND o.order_purchase_timestamp < t.opened_at) LIMIT 1"
        ).fetchone()
    tools = AdvisorTools(as_of=pd.Timestamp(opened_at))
    history = tools.get_customer_history(order_id)
    assert history["previous_orders"], history
    assert all(o["purchased_on"] <= opened_at[:10] for o in history["previous_orders"])
    assert all(t["opened_on"] <= opened_at[:10] for t in history["previous_tickets"])
    assert all(o["order_id"] != order_id for o in history["previous_orders"])
    assert "error" in tools.get_customer_history("0" * 32)


# ------------------------------------------------------- simulated customer side
def test_customer_bank_is_fixed_by_the_contact_and_sometimes_mistyped() -> None:
    from callverse.agents.client.profiles import CUSTOMER_BANKS, customer_bank

    banks = [customer_bank(f"SC{i:06d}") for i in range(500)]
    assert customer_bank("SC000001") == customer_bank("SC000001")
    assert all(code in CUSTOMER_BANKS for code, _ in banks)
    typos = [typed for code, typed in banks if typed != code]
    assert 0.1 < len(typos) / len(banks) < 0.3 and all(len(typed) == 4 for typed in typos)


def test_customer_gives_the_bank_code_and_fixes_a_typo() -> None:
    from callverse.agents.client.profiles import CustomerProfile, customer_bank
    from callverse.agents.client.simulator import ClientAgent

    contact = next(c for c in (f"SC{i:06d}" for i in range(500)) if len(customer_bank(c)[1]) == 4)
    code, typed = customer_bank(contact)
    profile = CustomerProfile(
        contact, ORDER, "u1", pd.Timestamp("2018-05-25"), "request_refund", "cancel_refund",
        "I want my money back", "canceled_or_unavailable", "normal", "polite", False, code, typed,
    )  # fmt: skip
    client = ClientAgent(None, "template")
    messages = [
        {"speaker": "customer", "text": f"Refund please, order {ORDER}"},
        {"speaker": "advisor", "text": "Please reply to our e-mail with your bank, branch, account number."},
    ]
    first = client.respond(profile, messages, 2)
    assert typed in first.text and first.mode == "rule"
    messages += [
        {"speaker": "customer", "text": first.text},
        {"speaker": "advisor", "text": f"I could not find bank code {typed}. Could you check it, please?"},
    ]
    second = client.respond(profile, messages, 3)
    assert second.text.endswith(f"{code}.") and typed not in second.text
