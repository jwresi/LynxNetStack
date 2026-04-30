from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .netbox_client import NetBoxClient


INVOICE_STATUS_MAP = {
    "invoice.paid": "posted",
    "invoice.payment_succeeded": "posted",
    "invoice.payment_failed": "draft",
    "invoice.marked_uncollectible": "draft",
    "invoice.voided": "canceled",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _resolve_invoice(nb: NetBoxClient, invoice_obj: dict[str, Any]) -> dict[str, Any] | None:
    metadata = invoice_obj.get("metadata", {}) or {}
    invoice_id = metadata.get("netbox_invoice_id")
    if invoice_id:
        return nb.get_invoice(int(invoice_id))

    number_candidates = [
        metadata.get("netbox_invoice_number"),
        metadata.get("invoice_number"),
        invoice_obj.get("number"),
    ]

    for number in number_candidates:
        if not number:
            continue
        matches = nb.find_invoices_by_number(str(number))
        if matches:
            return matches[0]
    return None


def _resolve_contract(nb: NetBoxClient, subscription_obj: dict[str, Any]) -> dict[str, Any] | None:
    metadata = subscription_obj.get("metadata", {}) or {}
    contract_id = metadata.get("netbox_contract_id")
    if contract_id:
        return nb.get_contract(int(contract_id))

    subscription_id = subscription_obj.get("id")
    if subscription_id:
        return nb.find_contract_by_external_reference(str(subscription_id))
    return None


def handle_invoice_event(nb: NetBoxClient, event_type: str, invoice_obj: dict[str, Any]) -> dict[str, Any]:
    invoice = _resolve_invoice(nb, invoice_obj)
    if not invoice:
        return {"updated": False, "reason": "invoice_not_found"}

    payload: dict[str, Any] = {}
    mapped_status = INVOICE_STATUS_MAP.get(event_type)
    if mapped_status:
        payload["status"] = mapped_status

    line = (
        f"event={event_type} "
        f"stripe_invoice={_to_str(invoice_obj.get('id'))} "
        f"stripe_subscription={_to_str(invoice_obj.get('subscription'))} "
        f"amount_paid={_to_str(invoice_obj.get('amount_paid'))} "
        f"currency={_to_str(invoice_obj.get('currency'))}"
    )
    payload["comments"] = nb.append_comment(invoice.get("comments"), line)

    updated = nb.patch_invoice(invoice["id"], payload)
    return {"updated": True, "invoice_id": updated["id"], "status": updated.get("status")}


def _contract_status_from_subscription(subscription_status: str) -> str:
    inactive = {"canceled", "unpaid", "incomplete_expired"}
    return "canceled" if subscription_status in inactive else "active"


def handle_subscription_event(
    nb: NetBoxClient, event_type: str, subscription_obj: dict[str, Any]
) -> dict[str, Any]:
    contract = _resolve_contract(nb, subscription_obj)
    if not contract:
        return {"updated": False, "reason": "contract_not_found"}

    sub_status = _to_str(subscription_obj.get("status"))
    payload = {
        "status": _contract_status_from_subscription(sub_status),
        "comments": nb.append_comment(
            contract.get("comments"),
            (
                f"event={event_type} stripe_subscription={_to_str(subscription_obj.get('id'))} "
                f"subscription_status={sub_status} at={_iso_now()}"
            ),
        ),
    }
    updated = nb.patch_contract(contract["id"], payload)
    return {"updated": True, "contract_id": updated["id"], "status": updated.get("status")}
