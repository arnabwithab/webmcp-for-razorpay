from sidecar.compare import compare_arms


# helper to build a task timeline: (task_id, arm, offsets in ms)
def _audit_lines(tasks):
    lines = []
    for task_id, arm, offsets in tasks:
        for event, offset in offsets:
            lines.append(
                {
                    "ts": 1_000_000 + offset,
                    "session_id": "s1",
                    "arm": arm,
                    "task_id": task_id,
                    "event": event,
                }
            )
    return lines


def test_compare_metrics_and_medians():
    # manual task A: total 1000ms; agent task B: total 400ms
    lines = _audit_lines(
        [
            (
                "t1",
                "manual",
                [
                    ("task_start", 0),
                    ("product_viewed", 300),
                    ("cart_updated", 600),
                    ("payment_paid", 1000),
                ],
            ),
            (
                "t2",
                "agent",
                [
                    ("task_start", 0),
                    ("product_viewed", 100),
                    ("cart_updated", 200),
                    ("payment_paid", 400),
                ],
            ),
        ]
    )
    result = compare_arms(lines)
    assert result["tasks"]["t1:manual"]["total_ms"] == 1000
    assert result["tasks"]["t1:manual"]["discovery_ms"] == 300
    assert result["tasks"]["t1:manual"]["decision_ms"] == 300
    assert result["tasks"]["t1:manual"]["checkout_ms"] == 400
    assert result["tasks"]["t2:agent"]["total_ms"] == 400
    assert result["medians"]["manual"]["total_ms"] == 1000
    assert result["medians"]["agent"]["total_ms"] == 400


def test_compare_median_across_tasks():
    lines = _audit_lines(
        [
            (
                "t1",
                "agent",
                [
                    ("task_start", 0),
                    ("product_viewed", 100),
                    ("cart_updated", 100),
                    ("payment_paid", 100),
                ],
            ),
            (
                "t2",
                "agent",
                [
                    ("task_start", 0),
                    ("product_viewed", 200),
                    ("cart_updated", 300),
                    ("payment_paid", 200),
                ],
            ),
            (
                "t3",
                "agent",
                [
                    ("task_start", 0),
                    ("product_viewed", 900),
                    ("cart_updated", 900),
                    ("payment_paid", 900),
                ],
            ),
        ]
    )
    result = compare_arms(lines)
    assert result["medians"]["agent"]["total_ms"] == 200  # median of 100,200,900


def test_compare_ignores_tasks_missing_close():
    lines = _audit_lines(
        [
            ("t1", "manual", [("task_start", 0), ("product_viewed", 100)]),
        ]
    )
    result = compare_arms(lines)
    assert result["tasks"] == {}
    assert result["medians"].get("manual") is None


def test_compare_multiple_products_uses_first_viewed():
    lines = _audit_lines(
        [
            (
                "t1",
                "agent",
                [
                    ("task_start", 0),
                    ("product_viewed", 50),
                    ("product_viewed", 120),
                    ("cart_updated", 200),
                    ("payment_paid", 500),
                ],
            ),
        ]
    )
    result = compare_arms(lines)
    assert result["tasks"]["t1:agent"]["discovery_ms"] == 50
