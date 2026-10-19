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


@pytest.mark.llm
def test_llm_conversation_needs_ollama():
    from callverse.llm import get_llm

    if not get_llm().available():
        pytest.skip("Ollama not running")
    from callverse.agents.client.profiles import sample_profiles
    from callverse.data import loaders
    from callverse.orchestration.graph import run_conversation

    state = run_conversation(sample_profiles(loaders.contacts(), 1, seed=9)[0], mode="llm")
    assert state["kpis"]["advisor_mode"] in {"llm", "template_fallback"}
