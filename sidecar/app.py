import hashlib
import hmac
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sidecar.compare import compare_arms
from sidecar.core.audit import append_event, verify_audit
from sidecar.core.checkout import CheckoutError, LinkStore, create_checkout
from sidecar.core.razorpay import RazorpayClient
from sidecar.core.recovery import close_as_paid, poll_and_close, resume_checkout
from sidecar.snapshot import SNAPSHOT_PATH
from sidecar.utils.config import settings
from sidecar.utils.logger import logger

ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = ROOT / "audit.jsonl"
LINKS = LinkStore(Path(__file__).resolve().parent / "links.json")
rzp = RazorpayClient()

app = FastAPI(title="razorpay-sidecar", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    # agent origin needed: the agent iframe runs its own kit instance (flag-less
    # fallback); in the flagged WebMCP demo, tools execute in the store context
    allow_origins=[settings.store_origin, settings.agent_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount(
    "/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static"
)
app.mount("/kit", StaticFiles(directory=Path(__file__).resolve().parent.parent / "kit"), name="kit")


class EventIn(BaseModel):
    session_id: str
    arm: str
    task_id: str
    event: str
    tool: str | None = None
    payload: dict | None = None


class CheckoutIn(BaseModel):
    session_id: str
    arm: str
    task_id: str
    items: list[dict]


class ResumeIn(BaseModel):
    linkId: str


@app.post("/event")
def post_event(body: EventIn):
    record = append_event(
        AUDIT_PATH,
        session_id=body.session_id,
        arm=body.arm,
        task_id=body.task_id,
        event=body.event,
        tool=body.tool,
        payload=body.payload,
    )
    logger.info(
        f"event {body.event} arm={body.arm} task={body.task_id} session={body.session_id} tool={body.tool}"
    )
    return {"ts": record["ts"], "task_id": body.task_id, "event": body.event}


@app.get("/audit")
def get_audit():
    if not AUDIT_PATH.exists():
        return []
    lines = [line for line in AUDIT_PATH.read_text().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


@app.post("/checkout/create")
def post_checkout_create(body: CheckoutIn):
    try:
        return create_checkout(
            snapshot_path=SNAPSHOT_PATH,
            links=LINKS,
            rzp=rzp,
            audit_path=AUDIT_PATH,
            max_amount_paise=settings.max_amount_paise,
            session_id=body.session_id,
            arm=body.arm,
            task_id=body.task_id,
            items=body.items,
        )
    except CheckoutError as err:
        raise HTTPException(
            status_code=422, detail={"code": err.code, "message": str(err), **err.extra}
        )


@app.post("/checkout/resume")
def post_checkout_resume(body: ResumeIn):
    try:
        return resume_checkout(LINKS, rzp, SNAPSHOT_PATH, AUDIT_PATH, body.linkId)
    except LookupError:
        raise HTTPException(status_code=404, detail={"code": "unknown_link"})


@app.get("/poll/{link_id}")
def get_poll(link_id: str):
    try:
        return poll_and_close(LINKS, rzp, AUDIT_PATH, link_id)
    except LookupError:
        raise HTTPException(status_code=404, detail={"code": "unknown_link"})


@app.post("/webhook")
async def post_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        logger.warning("webhook rejected: bad signature")
        raise HTTPException(status_code=400, detail={"code": "bad_signature"})

    body = json.loads(raw)
    event = body.get("event")
    entity = body.get("payload", {}).get("payment_link", {}).get("entity", {})
    link_id = entity.get("id")

    if event == "payment_link.paid" and link_id and LINKS.get(link_id):
        close_as_paid(LINKS, AUDIT_PATH, link_id)
    elif event == "payment_link.expired" and link_id:
        LINKS.update_status(link_id, "expired")
    return {"ok": True}


def _read_audit_lines() -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    return [json.loads(line) for line in AUDIT_PATH.read_text().splitlines() if line.strip()]


@app.get("/compare", response_class=HTMLResponse)
def get_compare():
    result = compare_arms(_read_audit_lines())
    data_json = json.dumps(result).replace("</", "<\\/")
    rows = "".join(
        f"<tr><td>{key}</td><td>{m['discovery_ms']}</td><td>{m['decision_ms']}</td>"
        f"<td>{m['checkout_ms']}</td><td><b>{m['total_ms']}</b></td></tr>"
        for key, m in result["tasks"].items()
    )
    return f"""<!doctype html><html><head><title>/compare</title>
<style>body{{font-family:monospace;margin:2rem}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:.4rem .8rem;text-align:right}}</style></head>
<body><h1>checkout race — per-task + medians</h1>
<p>same rail, same catalog; agent time includes model latency; single take.</p>
<table><tr><th>task:arm</th><th>discovery</th><th>decision</th><th>checkout</th><th>total</th></tr>
{rows}</table>
<p>median totals (ms): {' | '.join(f'{arm}={m["total_ms"] if m else "-"}' for arm, m in result["medians"].items())}</p>
<script id="compare-data" type="application/json">{data_json}</script>
</body></html>"""


@app.get("/audit/verify")
def get_audit_verify():
    ok, reason = verify_audit(AUDIT_PATH)
    return {"ok": ok, "reason": reason}
