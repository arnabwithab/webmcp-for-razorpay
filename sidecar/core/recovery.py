from sidecar.core.audit import append_event
from sidecar.core.checkout import create_checkout
from sidecar.utils.logger import logger

PENDING_STATUSES = {"created", "partially_paid"}


def close_as_paid(links, audit_path, link_id: str) -> bool:
    """Mark paid + append payment_paid exactly once (poll and webhook both call this)."""
    link = links.get(link_id)
    if link is None:
        raise LookupError(link_id)
    if link["status"] == "paid":
        return False
    links.update_status(link_id, "paid")
    append_event(
        audit_path,
        session_id=link["session_id"],
        arm=link["arm"],
        task_id=link["task_id"],
        event="payment_paid",
        payload={"link_id": link_id, "amount_paise": link["amount_paise"]},
    )
    logger.info(f"payment_paid link={link_id} task={link['task_id']}")
    return True


def poll_and_close(links, rzp, audit_path, link_id: str) -> dict:
    """Poll-primary close (webhooks unreachable on localhost, spec R4)."""
    link = links.get(link_id)
    if link is None:
        raise LookupError(link_id)
    if link["status"] != "paid":
        remote = rzp.fetch_payment_link(link_id)
        status = remote.get("status", link["status"])
        if status == "paid":
            close_as_paid(links, audit_path, link_id)
        elif status != link["status"]:
            links.update_status(link_id, status)
    return {"status": links.get(link_id)["status"], "shortUrl": link["short_url"]}


def resume_checkout(links, rzp, snapshot_path, audit_path, link_id: str) -> dict:
    """Track 03 ladder: pending -> same shortUrl; expired -> mint fresh + log recovered."""
    link = links.get(link_id)
    if link is None:
        raise LookupError(link_id)

    remote = rzp.fetch_payment_link(link_id)
    status = remote.get("status", "created")

    if status == "paid":
        close_as_paid(links, audit_path, link_id)
        return {"status": "paid", "shortUrl": link["short_url"]}

    if status in PENDING_STATUSES:
        return {"status": "pending", "shortUrl": link["short_url"]}

    # expired (or cancelled): mint a fresh link at snapshot price for the same items
    fresh = create_checkout(
        snapshot_path=snapshot_path,
        links=links,
        rzp=rzp,
        audit_path=audit_path,
        max_amount_paise=10**9,  # cap already applied when the original link was minted
        session_id=link["session_id"],
        arm=link["arm"],
        task_id=link["task_id"],
        items=link["items"],
    )
    links.update_status(link_id, status)  # e.g. "expired"
    append_event(
        audit_path,
        session_id=link["session_id"],
        arm=link["arm"],
        task_id=link["task_id"],
        event="recovered",
        tool="resume-checkout",
        payload={"old_link_id": link_id, "new_link_id": fresh["linkId"]},
    )
    logger.info(f"recovered old={link_id} new={fresh['linkId']}")
    return {"status": "expired", "shortUrl": fresh["shortUrl"], "linkId": fresh["linkId"]}
