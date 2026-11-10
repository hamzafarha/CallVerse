"""The contact centre page's backend: the hub that copies every chat to the centre screens, and the advisor
history read from the saved chats (no real data needed)."""

import json

import pytest

from callverse.orchestration.centre import (
    CentreBusy,
    CentreHub,
    advisors_summary,
    centre_channel,
    saved_chats,
)
from callverse.orchestration.live import live_chats_dir


def kinds(messages: list[dict], chat: str | None = None) -> list[str]:
    """The event types a screen received (of one chat, or of all)."""
    return [m["event"]["type"] for m in messages if chat is None or m["chat"] == chat]


def test_hub_copies_every_step_and_replays_the_story_to_a_late_screen():
    """A screen sees each step; one that opens mid-chat first gets the story so far; tokens never go out."""
    hub = CentreHub()
    early: list[dict] = []
    hub.subscribe(early.append)
    feed = hub.open("centre", "Ana B.")
    feed.emit("ready", {"name": "Ana B."})
    feed.emit("token", {"text": "Hel"})  # words one by one: never sent to the centre
    feed.emit("message", {"message": {"speaker": "customer", "text": "Where is my parcel?"}})
    late: list[dict] = []
    hub.subscribe(late.append)  # the centre page opens in the middle of the chat
    assert kinds(early) == ["ready", "message"] and late == early
    assert all(m["chat"] == feed.id and m["channel"] == "centre" for m in early)
    assert [m["seq"] for m in early] == [0, 1]  # step numbers: a reconnecting screen skips what it showed
    feed.emit("done", {"reviewed": True})
    assert kinds(early)[-1] == kinds(late)[-1] == "done"
    # A finished chat is forgotten (its transcript is on disk): a new screen has nothing to replay.
    assert hub.running() == 0
    newcomer: list[dict] = []
    hub.subscribe(newcomer.append)
    feed.emit("message", {"message": {"speaker": "advisor", "text": "Too late"}})  # nothing after "done"
    assert newcomer == [] and kinds(early)[-1] == "done"


def test_one_centre_customer_at_a_time_and_an_error_ends_the_story():
    """The centre's own customers come one at a time; a crash is shown, then the story ends."""
    hub = CentreHub()
    seen: list[dict] = []
    hub.subscribe(seen.append)
    feed = hub.open("centre", "Ana B.", limit=1)
    with pytest.raises(CentreBusy):
        hub.open("centre", "Bruno C.", limit=1)
    hub.open("web", "Camila D.", limit=1)  # another channel has its own count

    def broken() -> None:
        raise RuntimeError("model offline")

    feed.run(broken)
    assert kinds(seen, feed.id) == ["error", "done"]
    assert seen[-2]["event"]["message"] == "model offline"
    hub.open("centre", "Bruno C.", limit=1)  # the centre is free again


def transcript(advisor, overall, fcr, csat, advisor_side="agent", wait=12.0, tokens=100, ended_at=None):
    """A finished chat as LiveSession.finish saves it (only the fields the history reads)."""
    tools = [{"name": "lookup_order"}]
    state = {
        "profile": {"contact_id": "SC000001", "customer_unique_id": "0a1b2c3d", "intent": "track_order"},
        "messages": [
            {"speaker": "customer", "text": "Where is my parcel?", "meta": {"mode": "template"}},
            {"speaker": "advisor", "text": "It is on its way.", "meta": {"tools": tools, "tokens": tokens}},
        ],
        "routing": {"assigned_desk": advisor, "desk_specialty": "wismo", "expected_wait_seconds": wait},
        "scorecard": {"overall": overall, "scores": {"compliance": 5}, "rationale": "Clear."},
        "kpis": {"fcr": fcr, "csat": csat},
        "csat": csat,
        "live": {"customer": "agent", "advisor": advisor_side, "channel": "centre"},
    }
    if ended_at is not None:
        state["ended_at"] = ended_at
    return state


def test_history_groups_the_saved_chats_by_advisor(tmp_path):
    """Newest first, broken files skipped, one line per advisor desk, and the KPI wall totals."""
    folder = tmp_path / "live"
    folder.mkdir()
    files = {
        "a": transcript("advisor-02", 4.0, True, 5, ended_at=100.0),
        "b": transcript("advisor-02", 3.0, False, 3, advisor_side="human", tokens=0, ended_at=200.0),
        "c": transcript("advisor-10", 5.0, True, None, wait=None),  # older file: no end time (file time)
    }
    for name, state in files.items():
        (folder / f"{name}.json").write_text(json.dumps(state), encoding="utf-8")
    (folder / "broken.json").write_text("{not json", encoding="utf-8")

    chats = saved_chats(folder)
    assert [c["id"] for c in chats] == ["c", "b", "a"]
    assert chats[2]["messages"][1]["tools"] == ["lookup_order"] and chats[2]["channel"] == "centre"

    summary = advisors_summary(chats)
    totals = summary["totals"]
    assert totals["chats"] == 3 and totals["by_ai"] == 2 and totals["by_human"] == 1
    assert totals["quality"] == pytest.approx(4.0) and totals["fcr"] == pytest.approx(2 / 3, abs=1e-3)
    assert totals["csat"] == pytest.approx(4.0) and totals["wait_seconds"] == pytest.approx(12.0)
    assert totals["tokens"] == 200
    assert [a["id"] for a in summary["advisors"]] == ["advisor-02", "advisor-10"]  # by desk number
    desk = summary["advisors"][0]
    assert desk["chats"] == 2 and desk["quality"] == pytest.approx(3.5) and desk["specialty"] == "wismo"


def test_the_centre_labels_where_each_chat_comes_from():
    """A person writing (portal) or calling (phone), the Client agent (theater, desk), or the centre."""
    assert centre_channel("web", "human") == "web"
    assert centre_channel("phone", "human") == "phone"
    assert centre_channel("web", "agent") == "agents"
    assert centre_channel("centre", "agent") == "centre"
    assert centre_channel("visitor", "human") == "visitor"


def test_tests_never_write_into_the_real_history(tmp_path):
    """conftest.py points the live chats folder to this test's temporary folder."""
    assert live_chats_dir() == tmp_path / "live_sessions"
