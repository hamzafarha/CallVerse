"""The CallVerse MCP server and the Advisor's MCP client (src/callverse/mcp/).

The server is reached the way any MCP client reaches it (the SDK's Client, in-process): the tests check
what it publishes (tools, resources, prompts), that a call through MCP gives the same result as a direct
call and is recorded the same way, that the Advisor really uses it, and the case and twin tools of the
server for outside apps.
"""

import json

import anyio
import pandas as pd
import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError

from callverse.agents.advisor.tools import LLM_TOOL_NAMES, SCHEMAS_BY_NAME, AdvisorTools, agentic_tool_names
from callverse.mcp.server import advisor_catalog
from tests.conftest import requires_data
from tests.unit.test_agentic_advisor import ScriptedLLM

CONTACT = "SC000014"  # track_order


def menu_of(server, *requests):
    """Connect to ``server``, send each request (an async function of the client), return the answers.

    A request the server refuses comes back as the MCPError the client raised (caught inside the
    connection, so the connection still closes cleanly).
    """

    async def ask(client: Client, request):
        try:
            return await request(client)
        except MCPError as error:
            return error

    async def main():
        async with Client(server) as client:
            return [await ask(client, request) for request in requests]

    return anyio.run(main)


def test_the_server_publishes_the_advisor_tools_with_their_own_descriptions() -> None:
    """tools/list = the 9 tools an LLM may call, with the descriptions the Advisor already used."""
    server = advisor_catalog(lambda: AdvisorTools(as_of=pd.Timestamp("2018-01-01"))).server()
    (listed,) = menu_of(server, lambda c: c.list_tools())
    assert [tool.name for tool in listed.tools] == LLM_TOOL_NAMES
    for tool in listed.tools:
        function = SCHEMAS_BY_NAME[tool.name]["function"]
        assert tool.description == function["description"]
        assert tool.input_schema == function["parameters"]
    assert "check_draft_reply" not in LLM_TOOL_NAMES  # the fact check stays a code step


def test_policies_are_resources_and_unknown_addresses_are_refused() -> None:
    """Each policy document is a resource (callverse://policies/<id>); an unknown address is an error."""
    server = advisor_catalog(lambda: AdvisorTools(as_of=pd.Timestamp("2018-01-01"))).server()
    resources, document = menu_of(
        server, lambda c: c.list_resources(), lambda c: c.read_resource("callverse://policies/refund_policy")
    )
    uris = {str(r.uri) for r in resources.resources}
    assert "callverse://policies/refund_policy" in uris and len(uris) >= 10
    assert document.contents[0].text.startswith("# Refund Policy")
    (refused,) = menu_of(server, lambda c: c.read_resource("callverse://policies/no_such_policy"))
    assert isinstance(refused, MCPError) and "Unknown resource" in str(refused)


@requires_data
def test_a_call_through_mcp_gives_the_same_answer_and_is_recorded_as_usual() -> None:
    """Same result as a direct call; every call (failed ones too) lands in the chat's tool log, via="mcp"."""
    from callverse.agents.client.profiles import find_profile
    from callverse.mcp.client import McpToolbox

    profile = find_profile(CONTACT)
    tools = AdvisorTools(as_of=profile.contact_timestamp)
    direct = json.loads(tools.execute("lookup_order", {"order_id": profile.order_id}))
    steps: list[str] = []
    with McpToolbox(tools, on_event=lambda step, data: steps.append(step)) as box:
        offered = [schema["function"]["name"] for schema in box.schemas(["open_ticket", "lookup_order"])]
        through = json.loads(box.execute("lookup_order", {"order_id": profile.order_id}))
        wrong_arguments = json.loads(box.execute("lookup_order", {"order": "x"}))
        invented = json.loads(box.execute("invented_tool", {}))
    assert offered == ["open_ticket", "lookup_order"]  # the agent's order (gating) is kept
    assert through == direct
    assert "error" in wrong_arguments and "error" in invented
    assert [(c.ok, c.caller, c.via) for c in tools.calls] == [
        (True, "llm", "direct"),
        (True, "llm", "mcp"),
        (False, "llm", "mcp"),
        (False, "llm", "mcp"),
    ]
    assert steps == ["mcp"]  # one connection and one tools/list for the whole turn


@requires_data
@pytest.mark.parametrize("transport", ["mcp", "direct"])
def test_the_agentic_advisor_reaches_its_tools_through_the_configured_transport(transport: str) -> None:
    """With "mcp" the LLM's choices travel through the server; pipeline steps stay direct either way."""
    from callverse.agents.advisor.advisor import AdvisorAgent, AdvisorMemory
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders
    from callverse.orchestration.runtime import AgentRuntime

    runtime = AgentRuntime(retriever_kind="keyword")
    retriever = runtime.keyword_retriever()
    profile = profile_by_contact_id(loaders.contacts(), CONTACT)
    llm = ScriptedLLM(
        script=[[("lookup_order", {"order_id": profile.order_id})], "I have checked your order for you."]
    )
    advisor = AdvisorAgent(retriever, runtime.classifier(), llm, "llm", 3, 4, None, 0, "agentic", transport)
    tools = AdvisorTools(as_of=profile.contact_timestamp, retriever=retriever)
    memory = AdvisorMemory(
        intent=profile.intent, intent_group=profile.intent_group, order_id=profile.order_id
    )
    messages = [
        {"speaker": "customer", "text": profile.opening_message},
        {"speaker": "advisor", "text": "Could you give me your order number, please?"},
        {"speaker": "customer", "text": f"It's {profile.order_id}"},
    ]
    steps: list[str] = []
    reply = advisor.reply(messages, memory, tools, on_event=lambda step, data: steps.append(step))
    chosen = [c for c in reply.tool_calls if c["caller"] == "llm"]
    assert [c["name"] for c in chosen] == ["lookup_order"] and chosen[0]["via"] == transport
    assert all(c["via"] == "direct" for c in reply.tool_calls if c["caller"] != "llm")
    assert ("mcp" in steps) == (transport == "mcp")
    assert llm.offered[0] == agentic_tool_names("investigate", profile.intent_group)
    assert memory.decision is not None


@requires_data
def test_outside_apps_open_a_case_and_the_order_tools_follow_its_date() -> None:
    """open_case moves the tools to the contact's moment; the case is a resource; prompts are filled."""
    from callverse.agents.client.profiles import find_profile
    from callverse.mcp.desk import CASE_URI, CaseDesk, desk_catalog

    desk = CaseDesk()
    server = desk_catalog(desk).server()

    async def order_of(client: Client):
        case = await client.call_tool("open_case", {"contact_id": CONTACT.lower()})
        return case, await client.call_tool("lookup_order", {"order_id": case.structured_content["order_id"]})

    listed, (case, order), missing, current, prompt = menu_of(
        server,
        lambda c: c.list_tools(),
        order_of,
        lambda c: c.call_tool("open_case", {"contact_id": "XX0001"}),
        lambda c: c.read_resource(CASE_URI),
        lambda c: c.get_prompt("answer_customer", {"contact_id": CONTACT}),
    )
    names = [tool.name for tool in listed.tools]
    assert names[: len(LLM_TOOL_NAMES)] == LLM_TOOL_NAMES
    assert {"open_case", "list_twin_scenarios", "forecast_next_week", "simulate_week"} <= set(names)
    assert not case.is_error and case.structured_content["contact_id"] == CONTACT
    assert "intent" not in case.structured_content  # the true problem type stays hidden (answer key)
    assert not order.is_error and missing.is_error
    assert desk.tools().as_of == find_profile(CONTACT).contact_timestamp
    assert desk.tools().calls[-1].via == "mcp"
    assert json.loads(current.contents[0].text)["contact_id"] == CONTACT
    assert CONTACT in prompt.messages[0].content.text
    (refused,) = menu_of(server, lambda c: c.get_prompt("plan_staffing", {}))
    assert isinstance(refused, MCPError) and "scenario" in str(refused)


@requires_data
def test_the_twin_tools_simulate_a_week_and_refuse_unknown_plans() -> None:
    """simulate_week runs the digital twin; a wrong plan is refused before anything runs."""
    from callverse.mcp.desk import CaseDesk

    desk = CaseDesk()
    assert "error" in desk.simulate_week({"scenario": "baseline", "plan": "magic"})
    week = desk.simulate_week({"scenario": "baseline", "plan": "cpsat", "router": "fifo", "seeds": 1})
    assert 0 <= week["kpis"]["service_level"] <= 1 and week["kpis"]["agent_hours"] > 0
    assert "error" in desk.simulate_week({"scenario": "no_such_week"})
