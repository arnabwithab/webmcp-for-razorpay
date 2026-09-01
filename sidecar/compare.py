from statistics import median

METRIC_PAIRS = {
    "discovery_ms": ("task_start", "product_viewed"),
    "decision_ms": ("product_viewed", "cart_updated"),
    "checkout_ms": ("cart_updated", "payment_paid"),
    "total_ms": ("task_start", "payment_paid"),
}


def _task_metrics(events: list[dict]) -> dict | None:
    """Exact event pairs per spec §8. First occurrence of each event wins."""
    ts: dict[str, int] = {}
    for e in sorted(events, key=lambda e: e["ts"]):
        ts.setdefault(e["event"], e["ts"])
    if "task_start" not in ts or "payment_paid" not in ts:
        return None  # task not closed; excluded from medians
    metrics = {}
    for name, (start, end) in METRIC_PAIRS.items():
        if start in ts and end in ts:
            metrics[name] = ts[end] - ts[start]
        else:
            metrics[name] = None
    return metrics


def compare_arms(lines: list[dict]) -> dict:
    """Group audit lines by (task_id, arm); per-task metrics + median across tasks."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for line in lines:
        key = (line.get("task_id"), line.get("arm"))
        groups.setdefault(key, []).append(line)

    tasks = {}
    per_arm: dict[str, list[dict]] = {}
    for (task_id, arm), events in sorted(groups.items()):
        metrics = _task_metrics(events)
        if metrics is None:
            continue
        key = f"{task_id}:{arm}"
        tasks[key] = metrics
        per_arm.setdefault(arm, []).append(metrics)

    medians = {
        arm: {
            name: (
                median(m[name] for m in task_list if m[name] is not None)
                if any(m[name] is not None for m in task_list)
                else None
            )
            for name in METRIC_PAIRS
        }
        for arm, task_list in per_arm.items()
    }
    return {"tasks": tasks, "medians": medians}
