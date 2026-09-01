import pytest
from fastapi.testclient import TestClient

import agent.app as app_module
from agent.app import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_turn_proxies_gemini_with_system_prompt_and_tools(client, monkeypatch):
    captured = {}

    def fake_generate(payload):
        captured.update(payload)
        return {"candidates": [{"content": {"parts": [{"text": "found it"}]}}]}

    monkeypatch.setattr(app_module, "generate_turn", fake_generate)
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
    # system prompt inline per spec §7
    assert "resume-checkout" in sent["system_instruction"]["parts"][0]["text"]
    assert sent["tools"][0]["function_declarations"][0]["name"] == "search-catalog"
    # stateless: contents mirror client-sent messages only
    assert sent["contents"][0]["role"] == "user"


def test_turn_never_leaks_key(client, monkeypatch):
    def fake_generate(payload):
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    monkeypatch.setattr(app_module, "generate_turn", fake_generate)
    resp = client.post(
        "/agent/turn",
        json={"messages": [{"role": "user", "parts": [{"text": "hi"}]}], "tools": []},
    )
    body = resp.text
    assert "gemini_dummy" not in body
    assert "key=" not in body


def test_turn_gemini_error_maps_to_502(client, monkeypatch):
    def boom(payload):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(app_module, "generate_turn", boom)
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
