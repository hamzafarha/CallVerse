"""End-to-end checks on the real processed data (skipped when it is not built)."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_data


@requires_data
def test_template_conversation_end_to_end():
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
    from callverse.twin import DigitalTwin, runs_to_frame

    frame = runs_to_frame(DigitalTwin().run("baseline", "rules_erlang", "fifo", seeds=2))
    assert len(frame) == 2
    assert frame["service_level"].between(0, 1).all()


@requires_data
def test_api_endpoints():
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
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders
    from callverse.orchestration.live import LiveSession

    contacts = loaders.contacts()
    contact = contacts[contacts["intent"] == "track_order"].iloc[0]
    profile = profile_by_contact_id(contacts, contact["contact_id"], 0)
    events: list[str] = []
    session = LiveSession(profile, lambda kind, data: events.append(kind), mode="template")
    session.begin()
    session.handle({"type": "customer_message", "text": "Where is my order?"})
    session.handle({"type": "customer_message", "text": f"It is {profile.order_id}"})
    session.handle({"type": "end", "csat": 5})
    assert session.finished
    assert {"routing", "message", "review", "done"} <= set(events)
    assert [m["speaker"] for m in session.messages][:2] == ["customer", "advisor"]


@requires_data
def test_live_session_copilot_and_autopilot(keyword_runtime):
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
def test_front_office_endpoints(keyword_runtime):
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
