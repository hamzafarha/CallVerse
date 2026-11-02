"""Agentic advisor variant, driven by a scripted LLM (no GPU needed).

The scripted model returns prepared answers in order, so each test controls what the
"LLM" chooses and checks what the code does around it: gating, the forced rules
engine, the safety nets and the reflection check of every draft.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from callverse.agents.advisor.bank_directory import BankDirectory
from callverse.agents.advisor.tools import agentic_tool_names
from callverse.agents.client.profiles import CUSTOMER_BANKS
from callverse.llm import LLMResponse
from tests.conftest import requires_data

pytestmark = requires_data

TRACK_ORDER = "SC000014"  # track_order, tracking shared
TRACK_ORDER_2 = "SC000020"
BOLETO_REFUND = "SC000031"  # refund_status paid by boleto: bank details requested


@dataclass
class ScriptedLLM:
    """Stands in for the local model: plays a script and records the tools it was offered.

    A script step is either a reply text or a list of (tool name, arguments) calls.
    """

    script: list[Any] = field(default_factory=list)
    offered: list[list[str]] = field(default_factory=list)
    choices: list[str | None] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def resolve_model(self, role: str) -> str:
        return "scripted/test-model"

    def chat(self, role: str, messages: list[dict[str, Any]], tools=None, **options: Any) -> LLMResponse:
        self.offered.append([t["function"]["name"] for t in tools or []])
        self.choices.append(options.get("tool_choice"))
        step = self.script.pop(0)
        if isinstance(step, str):
            return LLMResponse(step, [], "scripted/test-model")
        return LLMResponse("", [{"name": n, "arguments": a} for n, a in step], "scripted/test-model")


def fake_banks(url: str, timeout: float) -> list[dict]:
    return [{"code": int(c), "name": f"BANK {c}", "fullName": f"Bank {c} S.A."} for c in CUSTOMER_BANKS]


@pytest.fixture(scope="module")
def runtime():
    from callverse.orchestration.runtime import AgentRuntime

    return AgentRuntime(retriever_kind="keyword")


def conversation(runtime, contact_id: str, llm: ScriptedLLM, tmp_path):
    """Agentic advisor, tools and memory of a chat where the customer just gave the order number."""
    from callverse.agents.advisor.advisor import AdvisorAgent, AdvisorMemory
    from callverse.agents.advisor.tools import AdvisorTools
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders

    profile = profile_by_contact_id(loaders.contacts(), contact_id)
    retriever = runtime.keyword_retriever()
    advisor = AdvisorAgent(retriever, runtime.classifier(), llm, "llm", 3, 4, None, 0, "agentic")
    banks = BankDirectory("https://example.test/banks", tmp_path / "banks.json", downloader=fake_banks)
    tools = AdvisorTools(as_of=profile.contact_timestamp, retriever=retriever, banks=banks)
    memory = AdvisorMemory(
        intent=profile.intent, intent_group=profile.intent_group, order_id=profile.order_id
    )
    messages = [
        {"speaker": "customer", "text": profile.opening_message},
        {"speaker": "advisor", "text": "Could you give me your order number, please?"},
        {"speaker": "customer", "text": f"It's {profile.order_id}"},
    ]
    return advisor, tools, memory, messages, profile


def calls(reply) -> list[tuple[str, str]]:
    return [(c["name"], c["caller"]) for c in reply.tool_calls]


def test_llm_chooses_its_tools_then_the_rules_engine_decides(runtime, tmp_path) -> None:
    llm = ScriptedLLM()
    advisor, tools, memory, messages, profile = conversation(runtime, TRACK_ORDER, llm, tmp_path)
    llm.script = [
        [("lookup_order", {"order_id": profile.order_id})],
        "Thanks for waiting: I have checked your order for you.",
    ]
    reply = advisor.reply(messages, memory, tools)
    assert reply.mode == "llm" and reply.stage == "answer"
    assert calls(reply)[0] == ("lookup_order", "llm")
    assert ("recommend_resolution", "code") in calls(reply)
    assert calls(reply)[-1] == ("check_draft_reply", "code")
    assert llm.offered[0] == agentic_tool_names("investigate", profile.intent_group)
    assert llm.offered[1][:3] == ["search_knowledge_base", "open_ticket", "escalate_to_human"]
    assert llm.choices == ["required", None]  # a tool call is required until the order is opened
    assert memory.decision and memory.answered and not llm.script


def test_safety_net_opens_the_order_and_bad_drafts_fall_back_to_approved_text(runtime, tmp_path) -> None:
    llm = ScriptedLLM()
    advisor, tools, memory, messages, _ = conversation(runtime, TRACK_ORDER_2, llm, tmp_path)
    llm.script = ["Your order arrives tomorrow!", "It will be there tomorrow, I promise.", "Yes, tomorrow."]
    events: list[tuple[str, dict]] = []
    reply = advisor.reply(messages, memory, tools, on_event=lambda step, data: events.append((step, data)))
    assert ("lookup_order", "safety_net") in calls(reply)
    checks = [c["result"]["passed"] for c in reply.tool_calls if c["name"] == "check_draft_reply"]
    assert checks == [False, False]  # the draft, then the rewrite
    assert reply.text == memory.decision["answer"] and reply.mode == "template_fallback"
    assert any(step == "generation" and data.get("reason") == "fact_check" for step, data in events)
    assert not llm.script


def test_safety_net_escalates_when_the_llm_ignores_a_supervisor_request(runtime, tmp_path) -> None:
    llm = ScriptedLLM()
    advisor, tools, memory, messages, _ = conversation(runtime, TRACK_ORDER, llm, tmp_path)
    advisor._policy_decision(memory, tools)  # the order was answered in an earlier turn
    messages += [
        {"speaker": "advisor", "text": memory.decision["answer"]},
        {"speaker": "customer", "text": "This is not acceptable. I want to speak to a supervisor."},
    ]
    llm.script = ["I understand, and I am sorry about this."]
    reply = advisor.reply(messages, memory, tools)
    assert llm.choices == ["required"]  # the playbook says to escalate: a tool call is required
    assert ("escalate_to_human", "safety_net") in calls(reply)
    assert reply.stage == "escalate" and memory.escalated and "1 business day" in reply.text
    assert reply.mode == "llm"  # the draft with the added promise passed the fact check


def test_llm_escalates_a_legal_threat_before_the_order_number(runtime, tmp_path) -> None:
    llm = ScriptedLLM()
    advisor, tools, memory, _, _ = conversation(runtime, TRACK_ORDER, llm, tmp_path)
    memory.order_id = None
    messages = [{"speaker": "customer", "text": "This is absurd, I am filing a complaint with PROCON."}]
    llm.script = [
        [("escalate_to_human", {"reason": "PROCON complaint", "urgency": "high"})],
        "I am sorry. A supervisor will contact you within 1 business day.",
    ]
    reply = advisor.reply(messages, memory, tools)
    assert llm.offered[0] == ["search_knowledge_base", "escalate_to_human"]
    assert llm.choices == ["required", None]
    assert calls(reply)[0] == ("escalate_to_human", "llm")
    assert memory.escalated and reply.stage == "verify"
    assert "order number" in reply.text  # playbook rule 1: verify the order before helping further


def test_a_supervisor_request_before_any_answer_does_not_escalate_yet(runtime, tmp_path) -> None:
    llm = ScriptedLLM()
    advisor, tools, memory, _, _ = conversation(runtime, TRACK_ORDER, llm, tmp_path)
    memory.order_id = None
    messages = [{"speaker": "customer", "text": "Can I speak to a supervisor?"}]
    llm.script = ["I will check your order first, then a supervisor can help. What is your order number?"]
    reply = advisor.reply(messages, memory, tools)
    assert "escalate_to_human" in llm.offered[0]  # available, but the playbook says: answer first
    assert llm.choices == [None] and not memory.escalated
    assert all(c["name"] != "escalate_to_human" for c in reply.tool_calls)


@pytest.mark.parametrize("llm_checks", [True, False])
def test_a_bank_code_is_always_checked(runtime, tmp_path, llm_checks: bool) -> None:
    llm = ScriptedLLM()
    advisor, tools, memory, messages, _ = conversation(runtime, BOLETO_REFUND, llm, tmp_path)
    advisor._policy_decision(memory, tools)
    messages += [
        {"speaker": "advisor", "text": memory.decision["answer"]},
        {"speaker": "customer", "text": "Ok, I'll e-mail the rest. My bank code is 3411, is that accepted?"},
    ]
    llm.script = (
        [[("validate_bank_code", {"bank_code": "3411"})], "I could not find bank code 3411. Please check it."]
        if llm_checks
        else ["Yes, that bank works."]
    )
    reply = advisor.reply(messages, memory, tools)
    assert "validate_bank_code" in llm.offered[0]  # offered because the order was paid by boleto
    checked = [c for c in reply.tool_calls if c["name"] == "validate_bank_code"]
    assert [c["caller"] for c in checked] == ["llm" if llm_checks else "safety_net"]
    assert checked[0]["result"]["valid"] is False
    assert "3411" in reply.text and reply.stage == "bank_check"


def test_template_backup_checks_the_bank_code_too(runtime, monkeypatch, tmp_path) -> None:
    from callverse.agents.advisor import tools as tools_module
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders
    from callverse.orchestration.graph import run_conversation

    directory = BankDirectory("https://example.test/banks", tmp_path / "banks.json", downloader=fake_banks)
    monkeypatch.setattr(tools_module, "bank_directory", lambda: directory)
    profile = profile_by_contact_id(loaders.contacts(), BOLETO_REFUND)
    state = run_conversation(profile, mode="template", runtime=runtime)
    used = [t["name"] for m in state["messages"] if m["speaker"] == "advisor" for t in m["meta"]["tools"]]
    assert "validate_bank_code" in used
    assert profile.bank_code_typed in " ".join(m["text"] for m in state["messages"])
    assert state["kpis"]["llm_tool_calls"] == 0  # no LLM in the template backup
