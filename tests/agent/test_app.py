import json

import pytest
from fastapi.testclient import TestClient

import agent.app as app_module
import agent.groq as groq_module
from agent.app import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_turn_proxies_groq_with_system_prompt_and_tools(client, monkeypatch):
    captured = {}

    def fake_generate(payload):
        captured.update(payload)
        return {"choices": [{"message": {"role": "assistant", "content": "found it"}}]}

    monkeypatch.setattr(app_module, "generate_turn", fake_generate)
    monkeypatch.setattr(groq_module, "generate_turn", fake_generate)
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "find a red jersey"}]}],
            "tools": [
                {"name": "search-catalog", "description": "d", "parameters": {"type": "object"}}
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"parts": [{"text": "found it"}]}
    sent = captured["request_body"]
    # system prompt inline per spec §7, as first OpenAI-style message
    assert sent["messages"][0]["role"] == "system"
    assert "resume-checkout" in sent["messages"][0]["content"]
    # tools in OpenAI function-call shape
    assert sent["tools"][0]["type"] == "function"
    assert sent["tools"][0]["function"]["name"] == "search-catalog"
    # stateless: only client-sent messages after system
    assert sent["messages"][1] == {"role": "user", "content": "find a red jersey"}


def test_turn_translates_tool_calls_roundtrip(client, monkeypatch):
    def fake_generate(payload):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "add-to-cart",
                                    "arguments": '{"sku": "NJ-01"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }

    monkeypatch.setattr(app_module, "generate_turn", fake_generate)
    monkeypatch.setattr(groq_module, "generate_turn", fake_generate)
    resp = client.post(
        "/agent/turn",
        json={
            "messages": [{"role": "user", "parts": [{"text": "add a jersey"}]}],
            "tools": [],
        },
    )
    assert resp.json() == {
        "parts": [{"functionCall": {"name": "add-to-cart", "args": {"sku": "NJ-01"}}}]
    }


def test_turn_translates_function_response_to_tool_message(client, monkeypatch):
    captured = {}

    def fake_generate(payload):
        captured.update(payload)
        return {"choices": [{"message": {"role": "assistant", "content": "done"}}]}

    monkeypatch.setattr(app_module, "generate_turn", fake_generate)
    monkeypatch.setattr(groq_module, "generate_turn", fake_generate)
    client.post(
        "/agent/turn",
        json={
            "messages": [
                {"role": "user", "parts": [{"text": "hi"}]},
                {"role": "model", "parts": [{"functionCall": {"name": "read-cart", "args": {}}}]},
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"name": "read-cart", "response": {"result": []}}}
                    ],
                },
            ],
            "tools": [],
        },
    )
    msgs = captured["request_body"]["messages"]
    assert msgs[1]["role"] == "user"  # system is msgs[0]
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["tool_calls"][0]["function"]["name"] == "read-cart"
    call_id = msgs[2]["tool_calls"][0]["id"]
    assert msgs[3]["role"] == "tool"
    assert msgs[3]["tool_call_id"] == call_id
    assert json.loads(msgs[3]["content"]) == {"result": []}


def test_turn_never_leaks_key(client, monkeypatch):
    def fake_generate(payload):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    monkeypatch.setattr(app_module, "generate_turn", fake_generate)
    monkeypatch.setattr(groq_module, "generate_turn", fake_generate)
    resp = client.post(
        "/agent/turn",
        json={"messages": [{"role": "user", "parts": [{"text": "hi"}]}], "tools": []},
    )
    assert "groq_dummy" not in resp.text


def test_turn_groq_error_maps_to_502(client, monkeypatch):
    def boom(payload):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(app_module, "generate_turn", boom)
    monkeypatch.setattr(groq_module, "generate_turn", boom)
    resp = client.post("/agent/turn", json={"messages": [], "tools": []})
    assert resp.status_code == 502


def test_agent_panel_served(client):
    resp = client.get("/agent")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "/static/agent.js" in resp.text


def test_agent_js_and_loader_served(client):
    js = client.get("/static/agent.js")
    assert js.status_code == 200
    assert "getTools" in js.text
    loader = client.get("/static/loader.js")
    assert loader.status_code == 200  # spec §5: agent backend serves the loader
    assert "razorpay-agent-kit" in loader.text


def test_cors_store_origin_only(client):
    resp = client.options(
        "/agent/turn",
        headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8000"
