from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core.shared import PROJECT_ROOT, SITE_ALIAS_MAP, SITE_SERVICE_PROFILES, seed_project_envs


_SIX_DIGIT_SITE_RE = re.compile(r"^\d{6}$")


@dataclass(slots=True)
class SiteContext:
    site_id: str
    name: str
    aliases: list[str]
    service_mode: str | None
    uses_olt: bool
    last_mile: str | None = None


@dataclass(slots=True)
class LiveStats:
    mikrotik_devices_online: int
    switchos_devices_online: int
    cnwave_links_up: int
    cnwave_links_total: int
    tplink_onus_online: int
    dhcp_leases_active: int
    prometheus_available: bool


@dataclass(slots=True)
class NetworkContext:
    generated_at: str
    site_inventory: list[SiteContext]
    live_stats: LiveStats
    sites_needing_attention: list[str]
    active_alert_sites: list[str]
    operator_context_summary: str
    netbox_available: bool
    alertmanager_available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "site_inventory": [asdict(site) for site in self.site_inventory],
            "live_stats": asdict(self.live_stats),
            "sites_needing_attention": list(self.sites_needing_attention),
            "active_alert_sites": list(self.active_alert_sites),
            "operator_context_summary": self.operator_context_summary,
            "netbox_available": self.netbox_available,
            "alertmanager_available": self.alertmanager_available,
        }

    def format_for_prompt(self) -> str:
        live = self.live_stats
        lines = [f"NETWORK STATE (live as of {self.generated_at})"]
        if live.prometheus_available:
            lines.append(
                f"Devices online: {live.mikrotik_devices_online} MikroTik, {live.switchos_devices_online} SwOS"
            )
            lines.append(f"cnWave mesh: {live.cnwave_links_up}/{live.cnwave_links_total} links up")
            lines.append(
                f"Subscribers: {live.tplink_onus_online + live.dhcp_leases_active} online "
                f"({live.tplink_onus_online} ONU + {live.dhcp_leases_active} DHCP)"
            )
        else:
            lines.append("Devices online: 0 MikroTik, 0 SwOS (Prometheus unreachable)")
            lines.append("cnWave mesh: 0/0 links up (Prometheus unreachable)")
            lines.append("Subscribers: 0 online (Prometheus unreachable)")
        lines.append(
            f"Sites needing attention: {', '.join(self.sites_needing_attention) if self.sites_needing_attention else 'none'}"
        )
        lines.append(
            f"Active alert sites: {', '.join(self.active_alert_sites) if self.active_alert_sites else 'none'}"
        )
        lines.append("")
        lines.append("SITE INVENTORY")
        for site in self.site_inventory:
            service_mode = site.service_mode or "unknown"
            bits: list[str] = [f"{site.site_id} {site.name}"]
            if site.aliases:
                bits.append(f"aliases: {', '.join(site.aliases)}")
            bits.append(f"mode={service_mode}")
            if site.last_mile == "ghn_positron":
                bits.append("last_mile=ghn_positron; not fiber/GPON/OLT")
            elif site.uses_olt:
                bits.append("uses OLT")
            else:
                bits.append("no OLT")
            lines.append(" | ".join(bits))
        return "\n".join(lines)


class NetworkContextBuilder:
    _lock = threading.Lock()
    _cached_context: NetworkContext | None = None
    _expires_at: float = 0.0
    _cache_ttl_seconds = 60

    @classmethod
    def build(cls, *, force_refresh: bool = False) -> NetworkContext:
        with cls._lock:
            if not force_refresh and cls._cached_context is not None and time.time() < cls._expires_at:
                return cls._cached_context
            context = cls._build_uncached()
            cls._cached_context = context
            cls._expires_at = time.time() + cls._cache_ttl_seconds
            return context

    @classmethod
    def _build_uncached(cls) -> NetworkContext:
        seed_project_envs(PROJECT_ROOT)
        live_stats = cls._build_live_stats()
        netbox_sites, site_device_counts, netbox_available = cls._load_netbox_inventory()
        site_inventory = cls._merge_site_inventory(netbox_sites)
        site_ids = [site.site_id for site in site_inventory]
        active_alert_sites, alertmanager_available = cls._load_active_alert_sites(site_ids)
        per_site_devices = cls._query_prometheus_grouped_counts(
            'sum by (site_id) (mikrotik_device_up == 1)',
            'sum by (site_id) (switchos_device_up == 1)',
        )
        sites_needing_attention = sorted(
            site_id
            for site_id, expected_devices in site_device_counts.items()
            if expected_devices > 0 and int(per_site_devices.get(site_id, 0)) == 0
        )
        generated_at = datetime.now(timezone.utc).isoformat()
        operator_context_summary = cls._build_operator_summary(
            generated_at=generated_at,
            live_stats=live_stats,
            site_inventory=site_inventory,
            sites_needing_attention=sites_needing_attention,
            active_alert_sites=active_alert_sites,
        )
        return NetworkContext(
            generated_at=generated_at,
            site_inventory=site_inventory,
            live_stats=live_stats,
            sites_needing_attention=sites_needing_attention,
            active_alert_sites=active_alert_sites,
            operator_context_summary=operator_context_summary,
            netbox_available=netbox_available,
            alertmanager_available=alertmanager_available,
        )

    @staticmethod
    def _intent_site_vocabulary() -> dict[str, list[str]]:
        config_path = PROJECT_ROOT / "config" / "intent_parser.yaml"
        if not config_path.exists():
            return {}
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
        site_vocabulary = payload.get("site_vocabulary") or {}
        if not isinstance(site_vocabulary, dict):
            return {}
        normalized: dict[str, list[str]] = {}
        for site_id, aliases in site_vocabulary.items():
            if not _SIX_DIGIT_SITE_RE.fullmatch(str(site_id)):
                continue
            normalized[str(site_id)] = [str(alias).strip() for alias in (aliases or []) if str(alias).strip()]
        return normalized

    @classmethod
    def _merge_site_inventory(cls, netbox_sites: dict[str, str]) -> list[SiteContext]:
        parser_vocab = cls._intent_site_vocabulary()
        alias_map: dict[str, set[str]] = {}
        for alias, site_id in SITE_ALIAS_MAP.items():
            alias_map.setdefault(site_id, set()).add(alias)
        for site_id, profile in SITE_SERVICE_PROFILES.items():
            for alias in profile.get("aliases") or []:
                alias_map.setdefault(site_id, set()).add(str(alias))
        for site_id, aliases in parser_vocab.items():
            for alias in aliases:
                alias_map.setdefault(site_id, set()).add(alias)

        site_ids = sorted(set(SITE_SERVICE_PROFILES) | set(alias_map) | set(parser_vocab))
        inventory: list[SiteContext] = []
        for site_id in site_ids:
            profile = SITE_SERVICE_PROFILES.get(site_id) or {}
            name = str(netbox_sites.get(site_id) or profile.get("name") or site_id)
            aliases = sorted({alias.strip() for alias in alias_map.get(site_id, set()) if alias.strip()})
            inventory.append(
                SiteContext(
                    site_id=site_id,
                    name=name,
                    aliases=aliases,
                    service_mode=profile.get("service_mode"),
                    uses_olt=bool(profile.get("uses_olt", False)),
                    last_mile=profile.get("last_mile"),
                )
            )
        return inventory

    @staticmethod
    def _http_json(base_url: str, path: str, *, headers: dict[str, str] | None = None, timeout: float = 5.0) -> Any:
        url = f"{base_url.rstrip('/')}{path}"
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _prometheus_query(query: str) -> dict[str, Any] | None:
        base = str(os.environ.get("PROMETHEUS_URL") or "").rstrip("/")
        if not base:
            return None
        encoded = urllib.parse.quote(query, safe="")
        try:
            payload = NetworkContextBuilder._http_json(
                base,
                f"/api/v1/query?query={encoded}",
                headers={"Accept": "application/json", "User-Agent": "jake2-context/1.0"},
                timeout=5.0,
            )
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _query_prometheus_scalar_count(cls, query: str) -> int | None:
        payload = cls._prometheus_query(query)
        if not payload:
            return None
        results = (((payload.get("data") or {}).get("result")) or [])
        if not results:
            return 0
        try:
            return int(float(results[0]["value"][1]))
        except Exception:
            return None

    @classmethod
    def _query_prometheus_grouped_counts(cls, *queries: str) -> dict[str, int]:
        totals: dict[str, int] = {}
        for query in queries:
            payload = cls._prometheus_query(query)
            if not payload:
                continue
            results = (((payload.get("data") or {}).get("result")) or [])
            for row in results:
                metric = row.get("metric") or {}
                site_id = str(metric.get("site_id") or "").strip()
                if not _SIX_DIGIT_SITE_RE.fullmatch(site_id):
                    continue
                try:
                    value = int(float(row["value"][1]))
                except Exception:
                    continue
                totals[site_id] = totals.get(site_id, 0) + value
        return totals

    @classmethod
    def _build_live_stats(cls) -> LiveStats:
        mikrotik = cls._query_prometheus_scalar_count("sum(mikrotik_device_up == 1)")
        switchos = cls._query_prometheus_scalar_count("sum(switchos_device_up == 1)")
        cnwave_up = cls._query_prometheus_scalar_count("sum(cnwave_online_link_count)")
        cnwave_total = cls._query_prometheus_scalar_count("sum(cnwave_link_count)")
        onus = cls._query_prometheus_scalar_count("sum(tplink_onus_online_total)")
        dhcp = cls._query_prometheus_scalar_count("sum(mikrotik_dhcp_leases_active)")
        available = None not in (mikrotik, switchos, cnwave_up, cnwave_total, onus, dhcp)
        return LiveStats(
            mikrotik_devices_online=int(mikrotik or 0),
            switchos_devices_online=int(switchos or 0),
            cnwave_links_up=int(cnwave_up or 0),
            cnwave_links_total=int(cnwave_total or 0),
            tplink_onus_online=int(onus or 0),
            dhcp_leases_active=int(dhcp or 0),
            prometheus_available=available,
        )

    @classmethod
    def _load_netbox_inventory(cls) -> tuple[dict[str, str], dict[str, int], bool]:
        base = str(os.environ.get("NETBOX_URL") or "").rstrip("/")
        token = str(os.environ.get("NETBOX_TOKEN") or "").strip()
        if not base or not token:
            return {}, {}, False
        headers = {
            "Accept": "application/json",
            "Authorization": f"Token {token}",
            "User-Agent": "jake2-context/1.0",
        }
        try:
            sites_payload = cls._http_json(base, "/api/dcim/sites/?limit=100", headers=headers, timeout=5.0)
            devices_payload = cls._http_json(base, "/api/dcim/devices/?limit=1000", headers=headers, timeout=8.0)
        except Exception:
            return {}, {}, False
        site_names: dict[str, str] = {}
        for row in (sites_payload.get("results") or []):
            slug = str((row or {}).get("slug") or "").strip()
            if _SIX_DIGIT_SITE_RE.fullmatch(slug):
                site_names[slug] = str((row or {}).get("name") or slug)
        device_counts: dict[str, int] = {}
        for row in (devices_payload.get("results") or []):
            site = (row or {}).get("site") or {}
            slug = str(site.get("slug") or "").strip()
            if not _SIX_DIGIT_SITE_RE.fullmatch(slug):
                continue
            status = (row or {}).get("status") or {}
            status_value = str(status.get("value") or "").strip().lower()
            if status_value not in {"active", "offline"}:
                continue
            device_counts[slug] = device_counts.get(slug, 0) + 1
        return site_names, device_counts, True

    @classmethod
    def _load_active_alert_sites(cls, site_ids: list[str]) -> tuple[list[str], bool]:
        base = str(os.environ.get("ALERTMANAGER_URL") or "").rstrip("/")
        if not base:
            return [], False
        try:
            payload = cls._http_json(
                base,
                "/api/v2/alerts?active=true",
                headers={"Accept": "application/json", "User-Agent": "jake2-context/1.0"},
                timeout=5.0,
            )
        except Exception:
            return [], False
        if not isinstance(payload, list):
            return [], True
        known_sites = set(site_ids)
        alert_sites: set[str] = set()
        for row in payload:
            labels = (row or {}).get("labels") or {}
            site_id = str(labels.get("site_id") or "").strip()
            if _SIX_DIGIT_SITE_RE.fullmatch(site_id) and (not known_sites or site_id in known_sites):
                alert_sites.add(site_id)
        return sorted(alert_sites), True

    @staticmethod
    def _build_operator_summary(
        *,
        generated_at: str,
        live_stats: LiveStats,
        site_inventory: list[SiteContext],
        sites_needing_attention: list[str],
        active_alert_sites: list[str],
    ) -> str:
        monitored_sites = len(site_inventory)
        subscribers_online = live_stats.tplink_onus_online + live_stats.dhcp_leases_active
        parts = [
            f"Currently {live_stats.mikrotik_devices_online + live_stats.switchos_devices_online} devices online across {monitored_sites} sites",
            f"cnWave mesh: {live_stats.cnwave_links_up} links up of {live_stats.cnwave_links_total} total",
            f"{subscribers_online} subscribers online",
        ]
        if not live_stats.prometheus_available:
            parts.append("Prometheus unreachable")
        if sites_needing_attention:
            parts.append(f"Sites needing attention: {', '.join(sites_needing_attention)}")
        else:
            parts.append("No sites currently need attention")
        if active_alert_sites:
            parts.append(f"Active alerts at: {', '.join(active_alert_sites)}")
        else:
            parts.append("No active alerts")
        return ". ".join(parts) + f". (Context generated {generated_at})"
