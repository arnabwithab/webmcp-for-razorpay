import hashlib
import json
import time
from pathlib import Path

from sidecar.utils.logger import logger

GENESIS_HASH = "0" * 64


def _head_hash(audit_path: Path) -> str:
    if not audit_path.exists():
        return GENESIS_HASH
    lines = [line for line in audit_path.read_text().splitlines() if line.strip()]
    if not lines:
        return GENESIS_HASH
    return hashlib.sha256(lines[-1].encode()).hexdigest()


def append_event(
    audit_path: Path,
    session_id: str,
    arm: str,
    task_id: str,
    event: str,
    tool: str | None = None,
    payload: dict | None = None,
) -> dict:
    prev_hash = _head_hash(audit_path)
    record = {
        "ts": int(time.time() * 1000),
        "session_id": session_id,
        "arm": arm,
        "task_id": task_id,
        "event": event,
        "prev_hash": prev_hash,
    }
    if tool is not None:
        record["tool"] = tool
    if payload is not None:
        record["payload"] = payload

    line = json.dumps(record, separators=(",", ":"))
    with audit_path.open("a") as f:
        f.write(line + "\n")

    record["line_hash"] = hashlib.sha256(line.encode()).hexdigest()
    logger.info(f"audit event={event} task={task_id} arm={arm}")
    return record


def verify_audit(audit_path: Path) -> tuple[bool, str]:
    if not audit_path.exists():
        return True, "no audit file yet"
    prev = GENESIS_HASH
    for i, line in enumerate(audit_path.read_text().splitlines()):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return False, f"line {i}: not valid json"
        if record.get("prev_hash") != prev:
            return False, f"line {i}: prev_hash mismatch (chain broken)"
        prev = hashlib.sha256(line.encode()).hexdigest()
    return True, "chain intact"


if __name__ == "__main__":
    audit_path = Path(__file__).resolve().parents[1] / "audit.jsonl"
    ok, reason = verify_audit(audit_path)
    print(reason)
    raise SystemExit(0 if ok else 1)
