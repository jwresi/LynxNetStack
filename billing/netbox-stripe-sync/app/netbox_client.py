from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


@dataclass
class NetBoxClient:
    base_url: str
    token: str
    timeout: float = 20.0

    def __post_init__(self) -> None:
        self.plugins_api_root = f"{self.base_url}/api/plugins/netbox-contract"
        self.api_root = f"{self.base_url}/api"
        self.headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, *, plugin: bool = False, **kwargs: Any) -> dict[str, Any]:
        root = self.plugins_api_root if plugin else self.api_root
        url = f"{root}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(method, url, headers=self.headers, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, *, params: dict[str, Any] | None = None, plugin: bool = False) -> list[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("limit", 100)
        params.setdefault("offset", 0)
        results: list[dict[str, Any]] = []
        while True:
            page = self._request("GET", path, plugin=plugin, params=params)
            chunk = page.get("results", [])
            results.extend(chunk)
            if not page.get("next"):
                break
            params["offset"] += params["limit"]
        return results

    def get_invoice(self, invoice_id: int) -> dict[str, Any]:
        return self._request("GET", f"/invoices/{invoice_id}/", plugin=True)

    def find_invoices_by_number(self, number: str) -> list[dict[str, Any]]:
        data = self._request("GET", "/invoices/", plugin=True, params={"number": number})
        return data.get("results", [])

    def patch_invoice(self, invoice_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/invoices/{invoice_id}/", plugin=True, json=payload)

    def get_contract(self, contract_id: int) -> dict[str, Any]:
        return self._request("GET", f"/contracts/{contract_id}/", plugin=True)

    def find_contract_by_external_reference(self, ref: str) -> dict[str, Any] | None:
        data = self._request("GET", "/contracts/", plugin=True, params={"external_reference": ref})
        results = data.get("results", [])
        return results[0] if results else None

    def patch_contract(self, contract_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/contracts/{contract_id}/", plugin=True, json=payload)

    def list_contracts(self) -> list[dict[str, Any]]:
        return self._paginate("/contracts/", plugin=True)

    def list_invoices(self) -> list[dict[str, Any]]:
        return self._paginate("/invoices/", plugin=True)

    def list_tenants(self) -> list[dict[str, Any]]:
        return self._paginate("/tenancy/tenants/")

    def patch_tenant(self, tenant_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/tenancy/tenants/{tenant_id}/", json=payload)

    def list_sites(self) -> list[dict[str, Any]]:
        return self._paginate("/dcim/sites/")

    def list_devices(
        self,
        *,
        tenant_id: int | None = None,
        site_id: int | None = None,
        search: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if tenant_id:
            params["tenant_id"] = tenant_id
        if site_id:
            params["site_id"] = site_id
        if search:
            params["q"] = search
        if status:
            params["status"] = status
        return self._paginate("/dcim/devices/", params=params)

    def get_device(self, device_id: int) -> dict[str, Any]:
        return self._request("GET", f"/dcim/devices/{device_id}/")

    def patch_device(self, device_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/dcim/devices/{device_id}/", json=payload)

    @staticmethod
    def append_comment(existing: str | None, line: str) -> str:
        existing = (existing or "").strip()
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"[stripe-sync {timestamp}] {line}"
        return f"{existing}\n{entry}".strip() if existing else entry
