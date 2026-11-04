"""End-to-end checks on the real processed data (skipped when it is not built)."""
# Integration tests: several parts work together on the real processed data (orders, contacts, SQLite,
# knowledge base). Skipped when the data is not built (requires_data). TestClient calls the FastAPI app in-
# process, without starting a server. Run: pytest tests/integration -v

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_data


@requires_data
def test_template_conversation_end_to_end():
    """A full conversation (Client -> Workforce -> Advisor -> Quality -> KPIs) with the offline template
    agents ends with a review and KPIs.
    """
    from callverse.agents.client.profiles import sample_profiles
    from callverse.data import loaders
    from callverse.orchestration.graph import run_conversation
    from callverse.orchestration.runtime import AgentRuntime

    runtime = AgentRuntime(retriever_kind="keyword")
    profile = sample_profiles(loaders.contacts(), 1, seed=5)[0]
    state = run_conversation(profile, mode="template", runtime=runtime)
    speakers = [m["speaker"] for m in state["messages"]]
    assert speakers[0] == "customer" and "advisor" in speakers
    assert state["kpis"]["tool_calls"] >= 1
    # The rule-based customer (offline backup) never opens its order page
    assert state["kpis"]["customer_page_checks"] == 0 and state["kpis"]["customer_mismatches"] == 0
    assert state["kpis"]["customer_wait_checks"] == 0 and state["kpis"]["customer_left_waiting"] is False
    assert state["reference"]["outcome"]
    assert set(state["scorecard"]["scores"]) == {
        "compliance",
        "relevance",
        "satisfaction",
        "sentiment",
        "resolution",
    }


@requires_data
def test_twin_runs_a_scenario():
    """The digital twin simulates a scenario week and returns KPIs."""
    from callverse.twin import DigitalTwin, runs_to_frame

    frame = runs_to_frame(DigitalTwin().run("baseline", "rules_erlang", "fifo", seeds=2))
    assert len(frame) == 2
    assert frame["service_level"].between(0, 1).all()


@requires_data
def test_api_endpoints():
    """The main REST endpoints answer correctly."""
    from callverse.api.app import app

    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    assert "scenarios" in client.get("/api/twin/config").json()
    response = client.post(
        "/api/twin/run", json={"scenario": "baseline", "plan": "fixed", "router": "fifo", "seeds": 1}
    )
    assert response.status_code == 200
    assert {k["kpi"] for k in response.json()["kpis"]} >= {"service_level", "labour_cost_eur"}


@pytest.fixture
def keyword_runtime(monkeypatch):
    """Agent runtime with the TF-IDF retriever (no bge-m3 download in tests)."""
    from callverse.orchestration import runtime

    instance = runtime.AgentRuntime(retriever_kind="keyword")
    monkeypatch.setattr(runtime, "_runtime", instance)
    return instance


@requires_data
def test_live_session_human_customer(keyword_runtime):
    """A live session where a person plays the customer: the advisor answers each message."""
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders
    from callverse.orchestration.live import LiveSession

    contacts = loaders.contacts()
    contact = contacts[contacts["intent"] == "track_order"].iloc[0]
    profile = profile_by_contact_id(contacts, contact["contact_id"], 0)
    events: list[str] = []
    session = LiveSession(profile, lambda kind, data: events.append(kind), mode="template")
    session.begin()
    session.handle({"type": "customer_message", "text": "Where is my order?", "via": "voice"})
    session.handle({"type": "customer_message", "text": f"It is {profile.order_id}"})
    session.handle({"type": "end", "csat": 5})
    assert session.finished
    assert {"routing", "message", "review", "done"} <= set(events)
    assert [m["speaker"] for m in session.messages][:2] == ["customer", "advisor"]
    # A spoken message (speech to text) is tagged; a typed one is not.
    customer = [m for m in session.messages if m["speaker"] == "customer"]
    assert customer[0]["meta"].get("input") == "voice" and "input" not in customer[1]["meta"]


@requires_data
def test_live_session_copilot_and_autopilot(keyword_runtime):
    """Advisor desk session: the copilot drafts replies for the human advisor, and autopilot lets the
    Advisor agent answer alone.
    """
    from callverse.agents.client.profiles import sample_profiles
    from callverse.data import loaders
    from callverse.orchestration.live import LiveSession

    profile = sample_profiles(loaders.contacts(), 1, seed=4)[0]
    events: list[str] = []
    session = LiveSession(
        profile, lambda kind, data: events.append(kind), mode="template", customer="agent", advisor="human"
    )
    session.begin()  # the Client agent opens, the copilot drafts
    assert "suggestion" in events
    session.handle({"type": "autopilot", "on": True})  # the agent finishes the chat
    assert session.finished and "review" in events


@requires_data
def test_desk_queue_time_starts_the_customer_clock(keyword_runtime):
    """The time a customer already waited in the desk queue starts the Client agent's chat timer."""
    from callverse.agents.client.profiles import sample_profiles
    from callverse.data import loaders
    from callverse.orchestration.live import LiveSession

    profile = sample_profiles(loaders.contacts(), 1, seed=4)[0]
    session = LiveSession(
        profile,
        lambda kind, data: None,
        mode="template",
        customer="agent",
        advisor="human",
        waited_seconds=250,
    )
    session.begin()  # routing happens after the opening message
    assert session.session.clock.queue_wait_seconds == 250  # the time shown on the desk's queue card


@requires_data
def test_front_office_endpoints(keyword_runtime):
    """The customer portal and help-centre endpoints answer correctly."""
    from callverse.api.app import app

    client = TestClient(app)
    customers = client.get("/api/portal/customers").json()
    assert len(customers) >= 4 and {"name", "order", "opening_message"} <= set(customers[0])
    detail = client.get(f"/api/portal/customers/{customers[0]['contact_id']}").json()
    assert [step["label"] for step in detail["timeline"]][:2] == ["Order placed", "Payment approved"]
    articles = client.get("/api/kb/articles").json()
    assert articles and not articles[0]["summary"].startswith("doc_id")
    article = client.get(f"/api/kb/articles/{articles[1]['id']}").json()
    assert article["markdown"].startswith("#") and "<!--" not in article["markdown"]
    search = client.get("/api/kb/search", params={"q": "my parcel is late"}).json()
    assert search["results"]
    assert len(client.get("/api/desk/queue", params={"n": 5}).json()) == 5


@requires_data
def test_twin_floor_replay():
    """The live floor endpoint returns one simulated day, contact by contact."""
    from callverse.api.app import app

    floor = TestClient(app).get("/api/twin/floor", params={"scenario": "baseline", "day": 1}).json()
    contacts = floor["contacts"]
    assert len(contacts["id"]) == len(contacts["arrival"]) == len(contacts["live"])
    assert floor["summary"]["contacts"] == sum(contacts["live"])
    assert floor["agents"] and all(len(a["duty"]) == 24 for a in floor["agents"] if a["duty"])
    started = [s for s in contacts["start"] if s is not None]
    assert started and min(started) >= 0


@requires_data
def test_websocket_session(keyword_runtime):
    """A chat over the WebSocket: start message, server events, end."""
    from callverse.api.app import app

    with TestClient(app).websocket_connect("/ws/session") as ws:
        ws.send_json({"type": "start", "customer": "human", "advisor": "agent", "mode": "template"})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "customer_message", "text": "Hello, where is my parcel?"})
        kinds = []
        while "advisor_state" not in kinds:
            kinds.append(ws.receive_json()["type"])
        assert "routing" in kinds and "message" in kinds
        ws.send_json({"type": "end", "csat": 4})
        while "done" not in kinds:
            kinds.append(ws.receive_json()["type"])
        assert "review" in kinds


@pytest.mark.llm
def test_llm_conversation_with_local_models():
    """A conversation with real local LLMs (marker llm: needs a GPU and the downloaded models)."""
    from dataclasses import replace

    from callverse.llm import LLMClient, load_llm_settings
    from callverse.orchestration.runtime import AgentRuntime

    llm = LLMClient(replace(load_llm_settings(), mode="auto"))
    if not llm.available():
        pytest.skip(llm.unavailable_reason() or "local Hugging Face models not available")
    from callverse.agents.client.profiles import sample_profiles
    from callverse.data import loaders
    from callverse.orchestration.graph import run_conversation

    runtime = AgentRuntime(retriever_kind="keyword", llm=llm)
    state = run_conversation(sample_profiles(loaders.contacts(), 1, seed=9)[0], mode="llm", runtime=runtime)
    assert state["kpis"]["advisor_mode"] in {"llm", "template_fallback"}


@requires_data
def test_new_customer_form_options_and_refusals():
    """The new-customer form gets its options, and an impossible request is refused without writing."""
    from callverse.api.app import app

    client = TestClient(app)
    options = client.get("/api/portal/new-customer-options").json()
    assert len(options["problems"]) == 17 and options["dates"]["first"] < options["dates"]["last"]
    assert all(p["example"] for p in options["problems"]) and "credit_card" in options["payment_types"]
    missing_order = {"name": "Ali", "intent": "track_order", "order_source": "invented"}
    assert client.post("/api/portal/customers", json=missing_order).status_code == 422
    assert client.delete("/api/portal/new-customers/NC999999").status_code == 404


@requires_data
def test_phone_call_is_shared_by_the_phone_and_the_desk(keyword_runtime):
    """A phone call: the phone (customer) and the desk (advisor) follow the same conversation, the desk can
    take over from the AI, and the Quality agent grades the call at the end."""
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders
    from callverse.orchestration.calls import CallHub

    contacts = loaders.contacts()
    contact = contacts[contacts["intent"] == "track_order"].iloc[0]
    profile = profile_by_contact_id(contacts, contact["contact_id"], 0)
    hub = CallHub()
    call = hub.open(profile, "Amira", mode="template")
    phone: list[dict] = []
    desk: list[dict] = []
    call.subscribe(phone.append)
    call.handle({"type": "customer_message", "text": "Where is my order?", "via": "voice"}, "customer")
    assert hub.calls()[0]["status"] == "talking" and hub.calls()[0]["autopilot"]
    call.subscribe(desk.append)  # joins late: first receives the story so far
    assert [e["type"] for e in desk] == [e["type"] for e in phone]
    with pytest.raises(ValueError):  # the AI answers until the desk takes over
        call.handle({"type": "advisor_message", "text": "Hello"}, "advisor")
    with pytest.raises(ValueError):  # the phone cannot speak for the advisor
        call.handle({"type": "advisor_message", "text": "Hello"}, "customer")
    call.handle({"type": "autopilot", "on": False}, "advisor")
    call.handle({"type": "customer_message", "text": f"It is {profile.order_id}"}, "customer")
    assert any(e["type"] == "suggestion" for e in desk)  # the copilot drafts for the human advisor
    call.handle({"type": "advisor_message", "text": "Thanks, I am checking your parcel now."}, "advisor")
    call.handle({"type": "end", "csat": 4}, "customer")
    assert call.live.finished
    assert any(e["type"] == "review" for e in phone) and any(e["type"] == "review" for e in desk)
    customer = [m for m in call.live.messages if m["speaker"] == "customer"]
    assert customer[0]["meta"]["channel"] == "phone" and customer[0]["meta"]["input"] == "voice"
    assert hub.calls()[0]["status"] == "ended" and hub.calls()[0]["quality"] is not None


@requires_data
def test_phone_websocket_start_and_desk_join():
    """Over the WebSocket: the phone starts a call, the desk joins it by id and sees it in the call list."""
    from callverse.api.app import app
    from callverse.data import loaders

    client = TestClient(app)
    contact_id = loaders.contacts().iloc[0]["contact_id"]
    with client.websocket_connect("/ws/session") as phone:
        phone.send_json({"type": "start", "channel": "phone", "contact_id": contact_id, "mode": "template"})
        ready = phone.receive_json()
        assert ready["type"] == "ready" and ready["session_id"].startswith("PH-") and ready["autopilot"]
        with client.websocket_connect("/ws/session") as desk:
            desk.send_json({"type": "join", "session_id": ready["session_id"], "role": "advisor"})
            assert desk.receive_json()["session_id"] == ready["session_id"]
        assert any(c["id"] == ready["session_id"] for c in client.get("/api/phone/calls").json())
    assert client.get("/api/phone/info").json()["links"][0].startswith("https://")


@requires_data
def test_mcp_server_is_listed_by_the_api_and_answers_over_http():
    """GET /api/mcp reads the menu through MCP; /mcp speaks MCP over HTTP while the API runs (lifespan)."""
    from callverse.api.app import app

    with TestClient(app) as client:  # `with` runs the lifespan, which starts the /mcp connection manager
        menu = client.get("/api/mcp").json()
        assert {"lookup_order", "open_case", "simulate_week"} <= {t["name"] for t in menu["tools"]}
        assert {t["group"] for t in menu["tools"]} == {"advisor", "case", "twin"}
        assert menu["advisor"]["tool_transport"] in {"mcp", "direct"}
        assert menu["connect"]["claude_desktop_config"]["mcpServers"]["callverse"]["args"] == ["mcp"]
        # The first message of a classic MCP client (JSON-RPC "initialize"), sent over Streamable HTTP.
        hello = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        headers = {"Accept": "application/json, text/event-stream", "Host": "127.0.0.1:8000"}
        answer = client.post("/mcp", json=hello, headers=headers)
        assert answer.status_code == 200 and '"tools"' in answer.text
        # A request from another site's web page is refused (DNS-rebinding protection).
        assert client.post("/mcp", json=hello, headers={**headers, "Host": "evil.example"}).status_code >= 400
    assert TestClient(app).post("/mcp", json=hello).status_code == 503  # API not started: no MCP endpoint
