from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from agent.groq import GROQ_URL, SYSTEM_PROMPT, _from_groq, _to_groq_messages, generate_turn
from agent.utils.config import settings
from agent.utils.logger import logger

# re-export for tests that patch app.generate_turn
__all__ = ["generate_turn", "_to_groq_messages", "_from_groq", "GROQ_URL", "SYSTEM_PROMPT"]

app = FastAPI(title="agent-backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.store_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.post("/agent/turn")
async def agent_turn(request: Request):
    body = await request.json()
    # LangGraph orchestration v3: deterministic checkout funnel (no LLM in the loop).
    # One /agent/turn = at most one fresh functionCall for the browser to execute.
    try:
        from agent.graph import get_graph

        state = {
            "messages": body.get("messages", []),
            "tools": body.get("tools", []),
            "ran": {},
            "result": {"parts": []},
            "pending": False,
            "done": False,
        }
        result_state = get_graph().invoke(state, config={"recursion_limit": 30})
        parts = (result_state.get("result") or {}).get("parts", [])
        if not parts:
            text = (
                "Payment link is ready — click Open payment to pay."
                if result_state.get("done")
                else "I couldn't take that further — try searching for a product."
            )
            parts = [{"text": text}]
        return {"parts": parts}
    except Exception as e:
        logger.error(f"graph turn failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail={"code": "model_error"})


@app.get("/agent", response_class=HTMLResponse)
def agent_panel():
    from fastapi.responses import HTMLResponse as _HR

    html = """<!doctype html><html><head><meta charset="utf-8"><title>agent</title>
<style>
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;margin:0;padding:12px 12px 8px;background:#fafafa;display:flex;flex-direction:column;height:100vh}
#chat{flex:1;overflow-y:auto;font-size:13px;min-height:0;padding-right:2px}
#chips{min-height:22px;margin:6px 0 0}
.msg{margin:6px 0;padding:8px 10px;border-radius:10px;max-width:90%}
.user{background:#0b6bcb;color:#fff;margin-left:auto}
.model{background:#e4e4e7}
.chip{display:inline-block;background:#fef08a;border-radius:999px;padding:2px 10px;font-size:12px;margin:2px}
button{padding:8px 14px;border-radius:999px;border:0;background:#0b6bcb;color:#fff;cursor:pointer;flex-shrink:0}
input{flex:1;min-width:0;padding:8px;border-radius:8px;border:1px solid #d4d4d8}
.input-bar{display:flex;gap:6px;margin-top:8px;align-items:center}
</style></head>
<body>
<div id="chat"></div>
<div id="chips"></div>
<div class="input-bar">
<input id="q" placeholder="what do you want to buy?"><button id="send">Go</button><button id="stop">STOP</button>
</div>
<script src="/static/agent.js?v=10"></script>
</body></html>"""
    return _HR(content=html, headers={"Cache-Control": "no-store"})


@app.get("/static/agent.js")
def agent_js():
    return FileResponse(
        STATIC_DIR / "agent.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


# spec §5: agent backend serves the loader (file lives in sidecar/static per §9)
@app.get("/static/loader.js")
def loader_js():
    return FileResponse(
        Path(__file__).resolve().parent.parent / "sidecar" / "static" / "loader.js",
        media_type="application/javascript",
    )
