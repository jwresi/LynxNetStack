from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import stripe
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings
from .netbox_client import NetBoxClient
from .store import EventStore
from .stripe_handlers import handle_invoice_event, handle_subscription_event


settings = Settings.from_env()
store = EventStore(settings.event_store_path)
netbox = NetBoxClient(settings.netbox_base_url, settings.netbox_token)

app = FastAPI(title="NetBox Stripe Sync", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


class TenantUpdate(BaseModel):
    name: str | None = None
    comments: str | None = None
    description: str | None = None


class DeviceCheckoutRequest(BaseModel):
    device_id: int
    tenant_id: int | None = None
    site_id: int | None = None
    note: str = Field(default="", max_length=500)


@app.get("/api/app/bootstrap")
def bootstrap() -> dict[str, Any]:
    contracts = netbox.list_contracts()
    invoices = netbox.list_invoices()
    tenants = netbox.list_tenants()
    sites = netbox.list_sites()
    return {
        "summary": {
            "contracts": len(contracts),
            "invoices": len(invoices),
            "customers": len(tenants),
            "sites": len(sites),
        },
        "tenants": tenants,
        "sites": sites,
        "contracts": contracts,
        "invoices": invoices,
    }


@app.get("/api/app/customers")
def customers() -> list[dict[str, Any]]:
    return netbox.list_tenants()


@app.patch("/api/app/customers/{tenant_id}")
def update_customer(tenant_id: int, payload: TenantUpdate) -> dict[str, Any]:
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields provided")
    return netbox.patch_tenant(tenant_id, patch)


@app.get("/api/app/contracts")
def contracts() -> list[dict[str, Any]]:
    return netbox.list_contracts()


@app.get("/api/app/invoices")
def invoices() -> list[dict[str, Any]]:
    return netbox.list_invoices()


@app.get("/api/app/sites")
def sites() -> list[dict[str, Any]]:
    return netbox.list_sites()


@app.get("/api/app/hardware")
def hardware(
    tenant_id: int | None = Query(default=None),
    site_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    return netbox.list_devices(tenant_id=tenant_id, site_id=site_id, search=search, status=status)


@app.post("/api/app/hardware/checkout")
def checkout_hardware(payload: DeviceCheckoutRequest) -> dict[str, Any]:
    device = netbox.get_device(payload.device_id)
    current_comments = device.get("comments")
    move_line = (
        f"checkout tenant_id={payload.tenant_id} site_id={payload.site_id} "
        f"note={payload.note.strip() or '-'}"
    )
    patch_payload = {
        "tenant": payload.tenant_id,
        "site": payload.site_id if payload.site_id else device.get("site", {}).get("id"),
        "comments": netbox.append_comment(current_comments, move_line),
    }
    return netbox.patch_device(payload.device_id, patch_payload)


@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    payload = await request.body()

    try:
        if settings.stripe_webhook_secret:
            if not stripe_signature:
                raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=stripe_signature,
                secret=settings.stripe_webhook_secret,
            )
        else:
            event = json.loads(payload.decode("utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {exc}") from exc

    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Missing event id/type")

    if store.seen(event_id):
        return {"status": "ignored", "reason": "duplicate", "event_id": event_id}

    obj = event.get("data", {}).get("object", {}) or {}
    try:
        if event_type.startswith("invoice."):
            result = handle_invoice_event(netbox, event_type, obj)
        elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
            result = handle_subscription_event(netbox, event_type, obj)
        else:
            result = {"updated": False, "reason": "event_not_handled"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc

    store.mark(event_id, _utc_now())
    return {"status": "processed", "event_id": event_id, "event_type": event_type, "result": result}
