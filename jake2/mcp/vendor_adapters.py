#!/usr/bin/env python3
from __future__ import annotations

import os
import ssl
import json
import base64
import urllib.parse
import urllib.request
from typing import Any

from mcp.tauc_mcp import TaucClient
from mcp.vilo_mcp import ViloClient, getenv_fallback


class TaucOpsAdapter:
    def __init__(self) -> None:
        self._seed_env('CLOUD')
        self._seed_env('ACS')
        self._seed_env('OLT')
        self.cloud = TaucClient('CLOUD')
        self.acs = TaucClient('ACS')
        self.olt = TaucClient('OLT')

    def _seed_env(self, prefix: str) -> None:
        names = [
            f'TAUC_{prefix}_BASE_URL',
            f'TAUC_{prefix}_AUTH_TYPE',
            f'TAUC_{prefix}_ACCESS_KEY',
            f'TAUC_{prefix}_SECRET_KEY',
            f'TAUC_{prefix}_CLIENT_ID',
            f'TAUC_{prefix}_CLIENT_SECRET',
            f'TAUC_{prefix}_CLIENT_CERT',
            f'TAUC_{prefix}_CLIENT_KEY',
            f'TAUC_{prefix}_CLIENT_KEY_PASSWORD',
            f'TAUC_{prefix}_CA_CERT',
            'TAUC_VERIFY_SSL',
        ]
        for name in names:
            value = getenv_fallback(name, 'tauc_mcp')
            if value and not os.environ.get(name):
                os.environ[name] = value

    def summary(self) -> dict[str, Any]:
        return {
            'cloud_configured': self.cloud.configured() if self.cloud else False,
            'acs_configured': self.acs.configured() if self.acs else False,
            'olt_configured': self.olt.configured() if self.olt else False,
        }

    def get_network_name_list(self, status: str, page: int = 0, page_size: int = 100, name_prefix: str | None = None) -> dict[str, Any]:
        if not self.cloud or not self.cloud.configured():
            raise ValueError('TAUC cloud is not configured')
        status = status.upper()
        if status not in {'ONLINE', 'ABNORMAL', 'OFFLINE', 'ALL'}:
            raise ValueError('status must be ONLINE, ABNORMAL, OFFLINE, or ALL')
        payload = self.cloud.request(
            'GET',
            f'/v1/openapi/network-system-management/network-name-list/{status}',
            query={'page': int(page), 'pageSize': int(page_size)},
        )
        results = (((payload or {}).get('result') or {}).get('data')) or []
        if name_prefix:
            needle = str(name_prefix).lower()
            results = [r for r in results if needle in str(r.get('networkName') or '').lower()]
        return {
            'status': status,
            'page': int(page),
            'page_size': int(page_size),
            'name_prefix': name_prefix,
            'count': len(results),
            'results': results,
            'raw': payload,
        }

    def get_network_details(self, network_id: str) -> dict[str, Any]:
        if not self.cloud or not self.cloud.configured():
            raise ValueError('TAUC cloud is not configured')
        return self.cloud.request('GET', f"/v1/openapi/network-system-management/details/{urllib.parse.quote(network_id, safe='')}")

    def get_preconfiguration_status(self, network_id: str) -> dict[str, Any]:
        if not self.cloud or not self.cloud.configured():
            raise ValueError('TAUC cloud is not configured')
        return self.cloud.request('GET', f"/v1/openapi/device-management/aginet/preconfiguration-status/{urllib.parse.quote(network_id, safe='')}")

    def get_pppoe_status(self, network_id: str, refresh: bool = True, include_credentials: bool = False) -> dict[str, Any]:
        if not self.cloud or not self.cloud.configured():
            raise ValueError('TAUC cloud is not configured')
        return self.cloud.request(
            'GET',
            f"/v1/openapi/device-management/aginet/pppoe-credentials/configured-status/{urllib.parse.quote(network_id, safe='')}",
            query={
                'refresh': str(bool(refresh)).lower(),
                'includeCredentials': str(bool(include_credentials)).lower(),
            },
        )

    def get_device_id(self, sn: str, mac: str) -> dict[str, Any]:
        if self.cloud and self.cloud.configured():
            return self.cloud.request('GET', '/v1/openapi/device-information/device-id', query={'sn': sn, 'mac': mac})
        if self.acs and self.acs.configured():
            return self.acs.request('GET', '/v1/openapi/acs/device/device-id', query={'sn': sn, 'mac': mac})
        raise ValueError('TAUC cloud or ACS is not configured')

    def get_device_detail(self, device_id: str) -> dict[str, Any]:
        if self.cloud and self.cloud.configured():
            return self.cloud.request('GET', f"/v1/openapi/device-information/device-info/{urllib.parse.quote(device_id, safe='')}")
        if self.acs and self.acs.configured():
            return self.acs.request('GET', '/v1/openapi/acs/device/detail', query={'deviceId': device_id})
        raise ValueError('TAUC cloud or ACS is not configured')

    def get_device_internet(self, device_id: str) -> dict[str, Any]:
        if not self.acs or not self.acs.configured():
            raise ValueError('TAUC ACS is not configured')
        return self.acs.request('GET', '/v1/openapi/acs/device/internet', query={'deviceId': device_id})

    def get_olt_devices(self, mac: str | None, sn: str | None, status: str | None, page: int = 0, page_size: int = 50) -> dict[str, Any]:
        if not self.olt or not self.olt.configured():
            raise ValueError('TAUC OLT is not configured')
        return self.olt.request('GET', '/v1/openapi/olt/devices', query={'mac': mac, 'sn': sn, 'status': status, 'page': int(page), 'pageSize': int(page_size)})


class ViloOpsAdapter:
    def __init__(self) -> None:
        self.client = ViloClient()

    def configured(self) -> bool:
        return bool(self.client and self.client.configured())

    def summary(self) -> dict[str, Any]:
        return self.client.diagnostics() if self.client else {'configured': False}

    def get_inventory(self, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.get_inventory(page_index, page_size)

    def search_inventory(self, filter_group: list[dict[str, Any]] | None = None, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.search_inventory(filter_group or [], page_index, page_size)

    def get_subscribers(self, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.get_subscribers(page_index, page_size)

    def search_subscribers(self, filter_group: list[dict[str, Any]] | None = None, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.search_subscribers(filter_group or [], page_index, page_size)

    def get_networks(self, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.get_networks(page_index, page_size)

    def search_networks(self, filter_group: list[dict[str, Any]] | None = None, sort_group: list[dict[str, Any]] | None = None, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.search_networks(filter_group or [], sort_group or [], page_index, page_size)

    def get_devices(self, network_id: str) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.get_vilos(network_id)

    def search_devices(self, network_id: str, sort_group: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not self.configured():
            raise ValueError('Vilo API is not configured')
        return self.client.search_vilos(network_id, sort_group or [])


class CnwaveControllerAdapter:
    def __init__(self) -> None:
        self.base_url = (
            getenv_fallback('CNWAVE_CONTROLLER_URL', 'cnwave_exporter_mcp')
            or os.environ.get('CNWAVE_CONTROLLER_URL')
            or ''
        ).rstrip('/')
        self.username = (
            os.environ.get('CNWAVE_CONTROLLER_USERNAME')
            or getenv_fallback('CNWAVE_CONTROLLER_USERNAME', 'cnwave_exporter_mcp')
            or os.environ.get('CAMBIUM_USERNAME')
            or ''
        )
        self.password = (
            os.environ.get('CNWAVE_CONTROLLER_PASSWORD')
            or getenv_fallback('CNWAVE_CONTROLLER_PASSWORD', 'cnwave_exporter_mcp')
            or os.environ.get('CAMBIUM_PASSWORD')
            or ''
        )
        self.neighbors_url_template = (
            os.environ.get('CNWAVE_CONTROLLER_NEIGHBORS_URL_TEMPLATE')
            or getenv_fallback('CNWAVE_CONTROLLER_NEIGHBORS_URL_TEMPLATE', 'cnwave_exporter_mcp')
            or ''
        )
        self.auth_mode = (
            os.environ.get('CNWAVE_CONTROLLER_AUTH_MODE')
            or getenv_fallback('CNWAVE_CONTROLLER_AUTH_MODE', 'cnwave_exporter_mcp')
            or 'basic'
        ).strip().lower()
        verify_ssl = (
            os.environ.get('CNWAVE_CONTROLLER_VERIFY_SSL')
            or getenv_fallback('CNWAVE_CONTROLLER_VERIFY_SSL', 'cnwave_exporter_mcp')
            or 'false'
        ).strip().lower()
        self.verify_ssl = verify_ssl in {'1', 'true', 'yes', 'on'}

    def configured(self) -> bool:
        return bool(self.base_url)

    def diagnostics(self) -> dict[str, Any]:
        missing: list[str] = []
        if not self.base_url:
            missing.append('CNWAVE_CONTROLLER_URL')
        if not self.neighbors_url_template:
            missing.append('CNWAVE_CONTROLLER_NEIGHBORS_URL_TEMPLATE')
        if self.auth_mode == 'basic':
            if not self.username:
                missing.append('CNWAVE_CONTROLLER_USERNAME or CAMBIUM_USERNAME')
            if not self.password:
                missing.append('CNWAVE_CONTROLLER_PASSWORD or CAMBIUM_PASSWORD')
        return {
            'configured': self.configured(),
            'remote_neighbors_ready': self.configured() and not missing,
            'base_url': self.base_url,
            'neighbors_url_template': self.neighbors_url_template,
            'auth_mode': self.auth_mode,
            'verify_ssl': self.verify_ssl,
            'username_present': bool(self.username),
            'password_present': bool(self.password),
            'missing': missing,
        }

    def get_ipv4_neighbors(self, radio_name: str, radio_ip: str | None = None) -> dict[str, Any]:
        info = self.diagnostics()
        if not info['configured']:
            return {
                'configured': False,
                'available': False,
                'error': 'cnwave_controller_not_configured',
                'detail': 'CNWAVE_CONTROLLER_URL is not set.',
                'controller': info,
            }
        if not info['remote_neighbors_ready']:
            return {
                'configured': True,
                'available': False,
                'error': 'cnwave_remote_neighbors_not_wired',
                'detail': 'Controller base URL is set, but the remote-neighbors request template is not fully configured.',
                'controller': info,
            }
        url = self.neighbors_url_template.format(
            base_url=self.base_url,
            radio_name=urllib.parse.quote(str(radio_name or '').strip(), safe=''),
            radio_ip=urllib.parse.quote(str(radio_ip or '').strip(), safe=''),
        )
        headers: dict[str, str] = {'Accept': 'application/json, text/plain;q=0.9, */*;q=0.8'}
        if self.auth_mode == 'basic' and self.username and self.password:
            token = base64.b64encode(f'{self.username}:{self.password}'.encode()).decode()
            headers['Authorization'] = f'Basic {token}'
        context = None if self.verify_ssl else ssl._create_unverified_context()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=context, timeout=12) as resp:
                raw = resp.read().decode('utf-8', 'ignore')
                content_type = str(resp.headers.get('Content-Type') or '')
            try:
                parsed: Any = json.loads(raw)
            except Exception:
                parsed = raw
            return {
                'configured': True,
                'available': True,
                'url': url,
                'content_type': content_type,
                'raw': raw[:4000],
                'parsed': parsed,
                'controller': info,
            }
        except Exception as exc:
            return {
                'configured': True,
                'available': False,
                'error': 'cnwave_controller_request_failed',
                'detail': str(exc),
                'url': url,
                'controller': info,
            }
