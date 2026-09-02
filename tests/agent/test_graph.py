"""Router + single-tool block behavior — the demo-critical agent loop."""

import agent.groq as groq_module
from agent.graph import get_graph


def _tool(name):
    return {"name": name, "description": "d", "parameters": {"type": "object", "properties": {}}}


TOOLS = [
    _tool(n)
    for n in (
        "search-catalog",
        "show-product",
        "add-to-cart",
        "read-cart",
        "checkout",
        "resume-checkout",
    )
]


def _call(name, args):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }


def _text(content):
    return {"role": "assistant", "content": content}


def _invoke(monkeypatch, messages, tools=TOOLS, response=None):
    def fake_generate(payload):
        return {"choices": [{"message": response if response else _text("ok")}]}

    monkeypatch.setattr(groq_module, "generate_turn", fake_generate)
    return get_graph().invoke({"messages": messages, "tools": tools, "history": []})


def _user(text):
    return {"role": "user", "parts": [{"text": text}]}


def _fn_call(name, args):
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}


def _fn_resp(name, response):
    return {"role": "user", "parts": [{"functionResponse": {"name": name, "response": response}}]}


def test_fresh_search_query_routes_search_catalog(monkeypatch):
    state = _invoke(
        monkeypatch,
        [_user("find me a rust bomber jacket")],
        response=_call("search-catalog", '{"query": "rust bomber jacket"}'),
    )
    assert state["result"]["parts"] == [
        {"functionCall": {"name": "search-catalog", "args": {"query": "rust bomber jacket"}}}
    ]


def test_search_response_advances_to_show_product(monkeypatch):
    # one utterance, second /agent/turn: search already ran, results are in history
    messages = [
        _user("find me a rust bomber jacket"),
        _fn_call("search-catalog", {"query": "rust bomber jacket"}),
        _fn_resp(
            "search-catalog",
            {
                "result": {
                    "ok": True,
                    "count": 1,
                    "items": [{"sku": "FASH-M04", "name": "Rust Bomber Jacket"}],
                }
            },
        ),
    ]
    state = _invoke(monkeypatch, messages, response=_call("show-product", '{"sku": "FASH-M04"}'))
    assert state["result"]["parts"] == [
        {"functionCall": {"name": "show-product", "args": {"sku": "FASH-M04"}}}
    ]


def test_shown_product_stops_with_text(monkeypatch):
    messages = [
        _user("find me a rust bomber jacket"),
        _fn_call("search-catalog", {"query": "rust bomber jacket"}),
        _fn_resp("search-catalog", {"result": {"ok": True, "count": 1, "items": []}}),
        _fn_call("show-product", {"sku": "FASH-M04"}),
        _fn_resp("show-product", {"result": {"ok": True, "sku": "FASH-M04"}}),
    ]
    state = _invoke(monkeypatch, messages, response=_text("Opened the Rust Bomber Jacket."))
    assert state["result"]["parts"] == [{"text": "Opened the Rust Bomber Jacket."}]


def test_empty_tools_routes_to_text_fallback(monkeypatch):
    state = _invoke(monkeypatch, [_user("find me a rust bomber jacket")], tools=[])
    assert state["result"]["parts"] == [{"text": "ok"}]


def test_add_to_cart_intent_routes_add_tool(monkeypatch):
    state = _invoke(
        monkeypatch,
        [_user("add it to cart")],
        response=_call("add-to-cart", '{"sku": "FASH-M04"}'),
    )
    assert state["result"]["parts"] == [
        {"functionCall": {"name": "add-to-cart", "args": {"sku": "FASH-M04"}}}
    ]


def test_add_to_cart_failure_recovers_via_show_product(monkeypatch):
    messages = [
        _user("add it to cart"),
        _fn_call("add-to-cart", {"sku": "FASH-M04"}),
        _fn_resp(
            "add-to-cart",
            {"result": {"ok": False, "error": "not on the product page — call show-product first"}},
        ),
    ]
    state = _invoke(monkeypatch, messages, response=_call("show-product", '{"sku": "FASH-M04"}'))
    assert state["result"]["parts"] == [
        {"functionCall": {"name": "show-product", "args": {"sku": "FASH-M04"}}}
    ]


def test_checkout_intent_routes_checkout_tool(monkeypatch):
    state = _invoke(monkeypatch, [_user("checkout")], response=_call("checkout", "{}"))
    assert state["result"]["parts"] == [{"functionCall": {"name": "checkout", "args": {}}}]


def test_cart_question_routes_read_cart(monkeypatch):
    state = _invoke(monkeypatch, [_user("what's in my cart")], response=_call("read-cart", "{}"))
    assert state["result"]["parts"] == [{"functionCall": {"name": "read-cart", "args": {}}}]


def test_unavailable_tool_falls_back_to_text(monkeypatch):
    state = _invoke(monkeypatch, [_user("checkout")], tools=[_tool("search-catalog")])
    assert state["result"]["parts"] == [{"text": "ok"}]


def test_single_tool_block_sends_only_that_tool(monkeypatch):
    captured = {}

    def fake_generate(payload):
        captured.update(payload)
        return {"choices": [{"message": _call("show-product", '{"sku": "FASH-M04"}')}]}

    monkeypatch.setattr(groq_module, "generate_turn", fake_generate)
    messages = [
        _user("find me a rust bomber jacket"),
        _fn_call("search-catalog", {"query": "rust bomber jacket"}),
        _fn_resp("search-catalog", {"result": {"ok": True, "count": 1, "items": []}}),
    ]
    state = get_graph().invoke({"messages": messages, "tools": TOOLS, "history": []})
    body = captured["request_body"]
    assert [t["function"]["name"] for t in body["tools"]] == ["show-product"]
    assert "tool_choice" not in body  # gpt-oss-20b ignores it (log evidence)
    assert state["result"]["parts"] == [
        {"functionCall": {"name": "show-product", "args": {"sku": "FASH-M04"}}}
    ]


def test_partial_state_does_not_crash_router(monkeypatch):
    # frontend only sends {messages, tools} — missing keys must not crash
    monkeypatch.setattr(
        groq_module,
        "generate_turn",
        lambda payload: {"choices": [{"message": _text("ok")}]},
    )
    get_graph().invoke({"messages": [_user("hi")], "tools": [], "history": []})
