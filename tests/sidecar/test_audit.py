import json
from pathlib import Path

from sidecar.core.audit import append_event, verify_audit

SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "sidecar"


def _read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_append_event_chains_hashes(tmp_path):
    audit = tmp_path / "audit.jsonl"
    e1 = append_event(audit, session_id="s1", arm="agent", task_id="t1", event="task_start")
    e2 = append_event(audit, session_id="s1", arm="agent", task_id="t1", event="product_viewed")

    lines = audit.read_text().splitlines()
    assert len(lines) == 2
    first, second = json.loads(lines[0]), json.loads(lines[1])
    # server ts authoritative
    assert isinstance(first["ts"], int)
    assert second["prev_hash"] == e1["line_hash"]
    assert e2["prev_hash"] == e1["line_hash"]


def test_verify_audit_ok_and_tamper(tmp_path):
    audit = tmp_path / "audit.jsonl"
    append_event(audit, session_id="s1", arm="manual", task_id="t1", event="task_start")
    append_event(audit, session_id="s1", arm="manual", task_id="t1", event="cart_updated")

    ok, reason = verify_audit(audit)
    assert ok, reason

    lines = audit.read_text().splitlines()
    tampered = json.loads(lines[0])
    tampered["event"] = "tampered"
    lines[0] = json.dumps(tampered)
    audit.write_text("\n".join(lines) + "\n")

    ok, reason = verify_audit(audit)
    assert not ok
    assert reason


def test_verify_audit_empty_file_ok(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text("")
    ok, reason = verify_audit(audit)
    assert ok
