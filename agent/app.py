import json
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from agent.utils.config import settings
from agent.utils.logger import logger

app = FastAPI(title="agent-backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.store_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# spec §7 system prompt, inline
SYSTEM_PROMPT = (
    "You drive a demo storefront for the user. Use only the provided tools; "
    "narrate one short line per action. Never invent SKUs or prices — trust tool results. "
    "After checkout, tell the user to click 'Open payment'. If payment is pending or declined, "
    "offer resume-checkout. If asked anything else: 'I can only help you shop on this store.'"
)


def _to_groq_messages(internal: list[dict]) -> list[dict]:
    """Internal parts-based messages -> OpenAI-style messages with tool_call id pairing."""
    out: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    call_id = None
    n = 0
    for msg in internal:
        for part in msg.get("parts", []):
            if "text" in part:
                out.append(
                    {
                        "role": "user" if msg["role"] == "user" else "assistant",
                        "content": part["text"],
                    }
                )
            elif "functionCall" in part:
                call = part["functionCall"]
                n += 1
                call_id = f"call_{n}"
                out.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": call["name"],
                                    "arguments": json.dumps(call.get("args", {})),
                                },
                            }
                        ],
                    }
                )
            elif "functionResponse" in part:
                resp_part = part["functionResponse"]
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id or "call_0",
                        "name": resp_part["name"],
                        "content": json.dumps(resp_part.get("response", {})),
                    }
                )
    return out


def _from_groq(message: dict) -> dict:
    """OpenAI-style assistant message -> internal parts shape."""
    parts: list[dict] = []
    for call in message.get("tool_calls") or []:
        fn = call["function"]
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        parts.append({"functionCall": {"name": fn["name"], "args": args}})
    if message.get("content"):
        parts.append({"text": message["content"]})
    return {"parts": parts}


def generate_turn(payload: dict) -> dict:
    """One stateless Groq call (OpenAI-compatible). Returns the raw Groq response."""
    resp = httpx.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        json=payload["request_body"],
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


@app.post("/agent/turn")
async def agent_turn(request: Request):
    body = await request.json()
    tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for t in body.get("tools", [])
    ]
    request_body = {
        "model": settings.groq_model,
        "messages": _to_groq_messages(body.get("messages", [])),
        "temperature": 0.2,
    }
    if tools:
        request_body["tools"] = tools

    try:
        raw = generate_turn({"request_body": request_body})
    except Exception as err:
        logger.error(f"groq turn failed: {err}")
        raise HTTPException(status_code=502, detail={"code": "model_error"})

    message = raw.get("choices", [{}])[0].get("message", {})
    return _from_groq(message)


@app.get("/agent", response_class=HTMLResponse)
def agent_panel():
    return """<!doctype html><html><head><meta charset="utf-8"><title>agent</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;padding:12px;background:#fafafa}}
#chat{{height:340px;overflow-y:auto;font-size:13px}}
.msg{{margin:6px 0;padding:8px 10px;border-radius:10px;max-width:90%}}
.user{{background:#0b6bcb;color:#fff;margin-left:auto}}
.model{{background:#e4e4e7}}
.chip{{display:inline-block;background:#fef08a;border-radius:999px;padding:2px 10px;font-size:12px;margin:2px}}
button{{padding:8px 14px;border-radius:999px;border:0;background:#0b6bcb;color:#fff;cursor:pointer}}
input{{width:70%;padding:8px;border-radius:8px;border:1px solid #d4d4d8}}
</style></head>
<body>
<div id="chat"></div>
<div id="chips"></div>
<div style="display:flex;gap:6px;margin-top:8px">
<input id="q" placeholder="what do you want to buy?"><button id="send">Go</button><button id="stop">STOP</button>
</div>
<script src="/static/agent.js"></script>
</body></html>"""


@app.get("/static/agent.js")
def agent_js():
    return FileResponse(STATIC_DIR / "agent.js", media_type="application/javascript")


# spec §5: agent backend serves the loader (file lives in sidecar/static per §9)
@app.get("/static/loader.js")
def loader_js():
    return FileResponse(
        Path(__file__).resolve().parent.parent / "sidecar" / "static" / "loader.js",
        media_type="application/javascript",
    )
