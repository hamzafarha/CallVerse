"""Hugging Face LLM layer: output parsing, streaming gate, chat-template messages.

Pure Python: no model, no GPU.
"""

from callverse.llm.client import LLMResponse, load_llm_settings, repair_json
from callverse.llm.hf_local import (
    StreamGate,
    json_complete,
    normalize_messages,
    parse_tool_calls,
    strip_thinking,
    tools_prompt,
)

TOOLS = {"lookup_order", "search_knowledge_base"}


def test_parse_xml_tool_call():
    call = '{"name": "lookup_order", "arguments": {"order_id": "abc"}}'
    text = f"Let me check.\n<tool_call>\n{call}\n</tool_call>"
    visible, calls = parse_tool_calls(text, TOOLS)
    assert visible == "Let me check."
    assert calls == [{"name": "lookup_order", "arguments": {"order_id": "abc"}}]


def test_parse_granite_list_and_string_arguments():
    text = '<|tool_call|>[{"name": "search_knowledge_base", "arguments": "{\\"query\\": \\"refund\\"}"}]'
    _, calls = parse_tool_calls(text, TOOLS)
    assert calls == [{"name": "search_knowledge_base", "arguments": {"query": "refund"}}]


def test_parse_bare_json_call_and_unknown_tools():
    _, calls = parse_tool_calls('{"name": "lookup_order", "arguments": {"order_id": "1"}}', TOOLS)
    assert calls[0]["name"] == "lookup_order"
    visible, calls = parse_tool_calls('{"name": "delete_everything", "arguments": {}}', TOOLS)
    assert calls == [] and visible  # unknown tools are ignored, the text is kept


def test_plain_answer_and_thinking():
    visible, calls = parse_tool_calls("<think>hmm</think>Your order is on its way.", TOOLS)
    assert visible == "Your order is on its way." and calls == []
    assert strip_thinking("<think>x</think> ok ") == "ok"


def test_json_complete_respects_strings():
    assert not json_complete('{"rationale": "a } inside')
    assert json_complete('{"a": {"b": 1}, "c": "}"}')
    assert json_complete('Sure: {"a": 1} trailing')


def test_stream_gate_hides_tool_calls():
    seen: list[str] = []
    gate = StreamGate(seen.append)
    for piece in ["Your order ", "is late. ", "<tool", '_call>{"name"', ": 1}"]:
        gate(piece)
    gate.finish()
    assert "".join(seen) == "Your order is late. "


def test_stream_gate_passes_text_and_blocks_bare_json():
    seen: list[str] = []
    gate = StreamGate(seen.append)
    for piece in ["Hello", " there, how", " can I help?"]:
        gate(piece)
    gate.finish()
    assert "".join(seen) == "Hello there, how can I help?"
    blocked: list[str] = []
    gate = StreamGate(blocked.append)
    gate('  {"name": "lookup_order"}')
    gate.finish()
    assert blocked == []


def test_normalize_merges_system_and_converts_tools():
    messages = [
        {"role": "system", "content": "A"},
        {"role": "system", "content": "B"},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "lookup_order", "arguments": {"order_id": "1"}}}],
        },
        {"role": "tool", "content": '{"ok": true}', "tool_name": "lookup_order"},
    ]
    native = normalize_messages(messages, native_tools=True)
    assert native[0] == {"role": "system", "content": "A\n\nB"}
    assert native[2]["tool_calls"][0]["type"] == "function"
    assert native[3] == {"role": "tool", "name": "lookup_order", "content": '{"ok": true}'}
    text = normalize_messages(messages, native_tools=False)
    assert "<tool_call>" in text[2]["content"] and text[3]["role"] == "user"
    assert "<tools>" in tools_prompt([{"function": {"name": "x"}}])


def test_json_repair_of_truncated_output():
    assert repair_json('{"a": 4, "r": "text not closed') == {"a": 4, "r": "text not closed"}
    assert repair_json('{"a": 4, "b": {"c": 1') == {"a": 4, "b": {"c": 1}}
    assert LLMResponse('Here: {"x": 1} done', [], "m").json() == {"x": 1}


def test_profiles_point_to_hugging_face_repositories():
    settings = load_llm_settings()
    assert set(settings.models) == {"client", "advisor", "judge"}
    assert all("/" in repo for repo in settings.models.values())  # owner/name on the Hub
    families = {settings.catalog[settings.models[r]]["family"] for r in ("advisor", "judge")}
    assert len(families) == 2  # the judge is from a different family than the advisor
