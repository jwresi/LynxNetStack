from __future__ import annotations

import csv
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import traceback
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Seed env vars BEFORE any mcp or core imports that resolve module-level
# constants from os.environ (e.g. NYCHA_INFO_CSV in jake_ops_mcp.py).
from core.shared import PROJECT_ROOT, seed_project_envs
seed_project_envs(PROJECT_ROOT)

from core.context_builder import NetworkContextBuilder
from core.dispatch import IntentDispatcher
from core.query_core import run_operator_query
from mcp.jake_ops_mcp import JakeOps


REPO_ROOT = PROJECT_ROOT
WEBUI_ROOT = REPO_ROOT / "webui"
INDEX_PATH = WEBUI_ROOT / "index.html"
UI_ROOT = WEBUI_ROOT / "ui"


def _json_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _port_bound(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ensure_port_available(port: int) -> None:
    if not _port_bound(port):
        return
    proc = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    for raw_pid in pids:
        try:
            os.kill(int(raw_pid), signal.SIGTERM)
        except ProcessLookupError:
            continue
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not _port_bound(port):
            return
        time.sleep(0.1)
    raise RuntimeError(f"Port {port} is still in use after SIGTERM cleanup. Jake WebUI did not start.")


def _query_prometheus_count(metric: str) -> int | None:
    base = str(os.environ.get("PROMETHEUS_URL") or "").rstrip("/")
    if not base:
        return None
    query = urllib.parse.quote(metric)
    req = urllib.request.Request(
        f"{base}/api/v1/query?query={query}",
        headers={"Accept": "application/json", "User-Agent": "jake2-webui/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    results = (((payload.get("data") or {}).get("result")) or [])
    if not results:
        return 0
    try:
        return int(float(results[0]["value"][1]))
    except Exception:
        return None


def _netbox_get(path: str) -> dict[str, Any] | None:
    base = str(os.environ.get("NETBOX_URL") or "").rstrip("/")
    token = str(os.environ.get("NETBOX_TOKEN") or "").strip()
    if not base or not token:
        return None
    req = urllib.request.Request(
        f"{base}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Token {token}",
            "User-Agent": "jake2-webui/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _netbox_paginated(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    next_url: str | None = path
    while next_url:
        payload = _netbox_get(next_url)
        if not payload:
            break
        results = payload.get("results") or []
        for row in results:
            if isinstance(row, dict):
                rows.append(row)
        next_url = payload.get("next")
        if isinstance(next_url, str):
            base = str(os.environ.get("NETBOX_URL") or "").rstrip("/")
            if base and next_url.startswith(base):
                next_url = next_url[len(base) :]
        else:
            next_url = None
    return rows


_NYCHA_READINESS_CSV = REPO_ROOT / "output" / "nycha_readiness_by_phase.csv"


def _get_nycha_readiness() -> dict[str, Any]:
    """Read the latest NYCHA readiness CSV and return structured JSON for Grafana Infinity."""
    buildings: list[dict[str, Any]] = []
    if not _NYCHA_READINESS_CSV.exists():
        return {"buildings": buildings, "error": "readiness CSV not found — run audit batch first"}
    with _NYCHA_READINESS_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                buildings.append({
                    "phase": int(row["Phase"]),
                    "development": row["Development"],
                    "address": row["Address"],
                    "ready_pct": int(row["Ready %"]),
                })
            except (KeyError, ValueError):
                continue
    updated = _NYCHA_READINESS_CSV.stat().st_mtime
    return {
        "buildings": buildings,
        "updated_ts": int(updated),
        "count": len(buildings),
    }


def _netbox_site_ids() -> list[str]:
    rows = _netbox_paginated("/api/dcim/sites/?limit=100")
    site_ids = []
    for row in rows:
        slug = str(row.get("slug") or "").strip()
        if re.fullmatch(r"\d{6}", slug):
            site_ids.append(slug)
    return sorted(set(site_ids))


def _netbox_site_device_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = _netbox_paginated("/api/dcim/devices/?limit=1000")
    allowed_statuses = {"active", "offline"}
    for row in rows:
        site = row.get("site") or {}
        slug = str(site.get("slug") or "").strip()
        if not re.fullmatch(r"\d{6}", slug):
            continue
        status = row.get("status") or {}
        status_value = str(status.get("value") or "").strip().lower()
        if status_value not in allowed_statuses:
            continue
        counts[slug] = counts.get(slug, 0) + 1
    return counts


class TTLCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if time.time() >= expires_at:
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: str, ttl_seconds: int, value: Any) -> Any:
        with self._lock:
            self._entries[key] = (time.time() + ttl_seconds, value)
        return value


class JakeAPIServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int]) -> None:
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.cache = TTLCache()
        self._context_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._context_thread: threading.Thread | None = None
        super().__init__(server_address, JakeAPIHandler)
        seed_project_envs(REPO_ROOT)
        self._context = NetworkContextBuilder.build()
        self._context_thread = threading.Thread(target=self._refresh_context_loop, name="jake-context-refresh", daemon=True)
        self._context_thread.start()

    def get_context(self):
        with self._context_lock:
            return self._context

    def _refresh_context_loop(self) -> None:
        while not self._stop_event.wait(60):
            try:
                context = NetworkContextBuilder.build(force_refresh=True)
            except Exception:
                continue
            with self._context_lock:
                self._context = context

    def server_close(self) -> None:
        self._stop_event.set()
        if self._context_thread is not None:
            self._context_thread.join(timeout=1.0)
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False, cancel_futures=True)
        super().server_close()


class JakeAPIHandler(BaseHTTPRequestHandler):
    server: JakeAPIServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._serve_file(INDEX_PATH, "text/html; charset=utf-8", head_only=True)
            return
        if parsed.path == "/ui/app.js":
            self._serve_file(UI_ROOT / "app.js", "application/javascript; charset=utf-8", head_only=True)
            return
        if parsed.path == "/ui/styles.css":
            self._serve_file(UI_ROOT / "styles.css", "text/css; charset=utf-8", head_only=True)
            return
        if parsed.path == "/api/stats":
            self._send_json(self._get_stats(), head_only=True)
            return
        if parsed.path == "/api/brief":
            self._send_json(self._get_brief(), head_only=True)
            return
        if parsed.path == "/api/context":
            self._send_json(self.server.get_context().to_dict(), head_only=True)
            return
        self._send_json({"error": True, "message": "Not found"}, status=HTTPStatus.NOT_FOUND, head_only=True)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        for key, value in _json_headers().items():
            self.send_header(key, value)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._serve_file(INDEX_PATH, "text/html; charset=utf-8")
            return
        if parsed.path == "/ui/app.js":
            self._serve_file(UI_ROOT / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/ui/styles.css":
            self._serve_file(UI_ROOT / "styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/stats":
            self._send_json(self._get_stats())
            return
        if parsed.path == "/api/brief":
            self._send_json(self._get_brief())
            return
        if parsed.path == "/api/context":
            self._send_json(self.server.get_context().to_dict())
            return
        if parsed.path == "/api/nycha/readiness":
            self._send_json(_get_nycha_readiness())
            return
        self._send_json({"error": True, "message": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/chat":
            self._send_json({"error": True, "message": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            self._send_json({"answer": "Jake encountered an error: invalid JSON body", "error": True}, status=HTTPStatus.BAD_REQUEST)
            return
        message = str(payload.get("message") or "").strip()
        history = payload.get("history")
        if not isinstance(history, list):
            history = []
        if not message:
            self._send_json({"answer": "Jake encountered an error: message is required", "error": True}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            dispatcher = IntentDispatcher(context=self.server.get_context())
            future = self.server.executor.submit(dispatcher.dispatch, JakeOps(), message, history)
            dispatch_result = future.result(timeout=90)
            if dispatch_result.synthesized_response is not None:
                answer = dispatch_result.synthesized_response
            elif dispatch_result.execution:
                answer = str(dispatch_result.execution.get("operator_summary") or dispatch_result.response or "")
            else:
                answer = dispatch_result.response
            self._send_json({"answer": answer, "raw_result": dispatch_result.execution})
        except TimeoutError:
            self._send_json({"answer": "Jake encountered an error: request timed out after 90 seconds", "error": True}, status=HTTPStatus.GATEWAY_TIMEOUT)
        except Exception as exc:
            traceback.print_exc()
            self._send_json({"answer": f"Jake encountered an error: {exc}", "error": True}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_file(self, path: Path, content_type: str, *, head_only: bool = False) -> None:
        if not path.exists():
            self._send_json({"error": True, "message": "Not found"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in _json_headers().items():
            self.send_header(key, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], *, status: int = HTTPStatus.OK, head_only: bool = False) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in _json_headers().items():
            self.send_header(key, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _get_stats(self) -> dict[str, int]:
        cached = self.server.cache.get("stats", 60)
        if cached is not None:
            return cached
        payload = {
            "online_devices": 0,
            "online_links": 0,
            "total_links": 0,
            "cpes_online": 0,
            "alerts_open": 0,
        }
        try:
            mikrotik_online = _query_prometheus_count("sum(mikrotik_device_up == 1)") or 0
            switchos_online = _query_prometheus_count("sum(switchos_device_up == 1)") or 0
            payload["online_devices"] = int(mikrotik_online + switchos_online)

            payload["online_links"] = int(_query_prometheus_count("sum(cnwave_online_link_count)") or 0)
            payload["total_links"] = int(_query_prometheus_count("sum(cnwave_link_count)") or 0)

            tplink_online = _query_prometheus_count("sum(tplink_onus_online_total)") or 0
            dhcp_online = _query_prometheus_count("sum(mikrotik_dhcp_leases_active)") or 0
            payload["cpes_online"] = int(tplink_online + dhcp_online)

            def _load_alert_count() -> int:
                ops = JakeOps()
                if not ops.alerts or not ops.netbox:
                    return 0
                seen: set[tuple[str, str]] = set()
                total = 0
                inventory = ops.list_sites_inventory(limit=500).get("sites", [])
                for row in inventory:
                    site_id = str(row.get("site_id") or "").strip()
                    if not site_id:
                        continue
                    for alert in ops.get_site_alerts(site_id).get("alerts", []):
                        labels = alert.get("labels") or {}
                        fingerprint = str(alert.get("fingerprint") or "")
                        key = (fingerprint, json.dumps(labels, sort_keys=True))
                        if key in seen:
                            continue
                        seen.add(key)
                        total += 1
                return total

            try:
                future = self.server.executor.submit(_load_alert_count)
                payload["alerts_open"] = int(future.result(timeout=5) or 0)
            except Exception:
                payload["alerts_open"] = 0
        except Exception:
            return self.server.cache.set("stats", 60, payload)
        return self.server.cache.set("stats", 60, payload)

    def _get_brief(self) -> dict[str, str]:
        cached = self.server.cache.get("brief", 300)
        if cached is not None:
            return cached
        context = self.server.get_context()
        payload = {"brief": context.operator_context_summary if context is not None else ""}
        return self.server.cache.set("brief", 300, payload)


def run_server(host: str = "127.0.0.1", port: int = 8017) -> JakeAPIServer:
    seed_project_envs(REPO_ROOT)
    ensure_port_available(port)
    server = JakeAPIServer((host, port))
    return server


def main() -> None:
    server = run_server()
    print("Jake WebUI running at http://127.0.0.1:8017", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
