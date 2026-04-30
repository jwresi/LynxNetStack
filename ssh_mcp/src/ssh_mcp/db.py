from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from string import Formatter
from typing import Any


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class ValidationError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value or [])


@dataclass(slots=True)
class Device:
    name: str
    hostname: str
    ip_address: str = ""
    vendor: str = ""
    model: str = ""
    port: int = 22
    auth_method: str = "ssh_config"
    tags: list[str] | None = None
    read_only_default: bool = True


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _db_snapshot(self) -> dict[str, Any]:
        with self.connect() as conn:
            proposal_count = conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
            last_proposal_id = conn.execute("SELECT MAX(id) FROM proposals").fetchone()[0]
            total_changes = conn.total_changes
        return {
            "db_path": str(self.db_path.resolve()),
            "proposal_count": int(proposal_count or 0),
            "last_proposal_id": int(last_proposal_id or 0),
            "total_changes": int(total_changes),
        }

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    hostname TEXT NOT NULL,
                    ip_address TEXT NOT NULL DEFAULT '',
                    vendor TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    port INTEGER NOT NULL DEFAULT 22,
                    auth_method TEXT NOT NULL DEFAULT 'ssh_config',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    read_only_default INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approved_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    intent TEXT NOT NULL,
                    command_template TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'read',
                    risk TEXT NOT NULL DEFAULT 'low',
                    timeout_sec INTEGER NOT NULL DEFAULT 30,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS playbooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    vendor TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    issue TEXT NOT NULL DEFAULT '',
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_name TEXT NOT NULL,
                    incident_id TEXT NOT NULL DEFAULT '',
                    device_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    FOREIGN KEY(device_id) REFERENCES devices(id)
                );

                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_type TEXT NOT NULL,
                    session_id INTEGER,
                    device_id INTEGER NOT NULL,
                    intent TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'read',
                    risk TEXT NOT NULL DEFAULT 'low',
                    status TEXT NOT NULL DEFAULT 'pending_approval',
                    reason TEXT NOT NULL DEFAULT '',
                    rendered_commands_json TEXT NOT NULL DEFAULT '[]',
                    backup_command TEXT NOT NULL DEFAULT '',
                    verify_command TEXT NOT NULL DEFAULT '',
                    rollback_command TEXT NOT NULL DEFAULT '',
                    requested_by TEXT NOT NULL DEFAULT 'agent',
                    approved_by TEXT NOT NULL DEFAULT '',
                    approval_note TEXT NOT NULL DEFAULT '',
                    execution_summary TEXT NOT NULL DEFAULT '',
                    execution_exit_code INTEGER,
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    executed_at TEXT,
                    denied_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id),
                    FOREIGN KEY(device_id) REFERENCES devices(id)
                );

                CREATE TABLE IF NOT EXISTS command_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id INTEGER NOT NULL,
                    session_id INTEGER,
                    device_id INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    command_text TEXT NOT NULL,
                    exit_code INTEGER,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    approved_by TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(proposal_id) REFERENCES proposals(id),
                    FOREIGN KEY(session_id) REFERENCES sessions(id),
                    FOREIGN KEY(device_id) REFERENCES devices(id)
                );
                """
            )

    def create_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        device = Device(**payload)
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO devices
                (name, hostname, ip_address, vendor, model, port, auth_method, tags_json, read_only_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device.name,
                    device.hostname,
                    device.ip_address,
                    device.vendor,
                    device.model,
                    device.port,
                    device.auth_method,
                    _json(device.tags),
                    1 if device.read_only_default else 0,
                    utcnow(),
                ),
            )
            row = conn.execute("SELECT * FROM devices WHERE id = ?", (cur.lastrowid,)).fetchone()
        if not row:
            raise ValidationError("Device insert failed")
        return self._device_row(row)

    def get_device(self, device_ref: int | str) -> dict[str, Any]:
        query = "SELECT * FROM devices WHERE id = ?" if isinstance(device_ref, int) else "SELECT * FROM devices WHERE name = ?"
        with self.connect() as conn:
            row = conn.execute(query, (device_ref,)).fetchone()
        if not row:
            raise ValidationError(f"Unknown device: {device_ref}")
        return self._device_row(row)

    def list_devices(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
        return [self._device_row(row) for row in rows]

    def add_approved_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = ["intent", "command_template"]
        missing = [field for field in required if not payload.get(field)]
        if missing:
            raise ValidationError(f"Missing approved command fields: {', '.join(missing)}")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO approved_commands
                (vendor, model, intent, command_template, mode, risk, timeout_sec, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("vendor", ""),
                    payload.get("model", ""),
                    payload["intent"],
                    payload["command_template"],
                    payload.get("mode", "read"),
                    payload.get("risk", "low"),
                    int(payload.get("timeout_sec", 30)),
                    payload.get("notes", ""),
                    utcnow(),
                ),
            )
            row = conn.execute("SELECT * FROM approved_commands WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def list_approved_commands(self, vendor: str = "", model: str = "", intent: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if vendor:
            clauses.append("(vendor = ? OR vendor = '')")
            params.append(vendor)
        if model:
            clauses.append("(model = ? OR model = '')")
            params.append(model)
        if intent:
            clauses.append("intent = ?")
            params.append(intent)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM approved_commands {where} ORDER BY vendor, model, intent, id", params).fetchall()
        return [dict(row) for row in rows]

    def add_playbook(self, payload: dict[str, Any]) -> dict[str, Any]:
        steps = payload.get("steps", [])
        if not payload.get("name"):
            raise ValidationError("Missing playbook name")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO playbooks
                (name, vendor, model, issue, steps_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"],
                    payload.get("vendor", ""),
                    payload.get("model", ""),
                    payload.get("issue", ""),
                    _json(steps),
                    utcnow(),
                ),
            )
            row = conn.execute("SELECT * FROM playbooks WHERE id = ?", (cur.lastrowid,)).fetchone()
        result = dict(row)
        result["steps"] = json.loads(result.pop("steps_json"))
        return result

    def list_playbooks(self, vendor: str = "", model: str = "", issue: str = "") -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if vendor:
            clauses.append("(vendor = ? OR vendor = '')")
            params.append(vendor)
        if model:
            clauses.append("(model = ? OR model = '')")
            params.append(model)
        if issue:
            clauses.append("issue LIKE ?")
            params.append(f"%{issue}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM playbooks {where} ORDER BY name", params).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["steps"] = json.loads(item.pop("steps_json"))
            items.append(item)
        return items

    def start_session(self, session_name: str, device_name: str | None = None, incident_id: str = "") -> dict[str, Any]:
        device_id = None
        if device_name:
            device_id = self.get_device(device_name)["id"]
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sessions (session_name, incident_id, device_id, status, created_at)
                VALUES (?, ?, ?, 'open', ?)
                """,
                (session_name, incident_id, device_id, utcnow()),
            )
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def get_session(self, session_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise ValidationError(f"Unknown session: {session_id}")
        return dict(row)

    def create_proposal(
        self,
        *,
        proposal_type: str,
        device_name: str,
        session_id: int | None,
        intent: str,
        mode: str,
        risk: str,
        reason: str,
        rendered_commands: list[str],
        backup_command: str = "",
        verify_command: str = "",
        rollback_command: str = "",
        requested_by: str = "agent",
    ) -> dict[str, Any]:
        if not rendered_commands:
            raise ValidationError("Proposal must include at least one command")
        device = self.get_device(device_name)
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO proposals
                (
                    proposal_type, session_id, device_id, intent, mode, risk, status, reason,
                    rendered_commands_json, backup_command, verify_command, rollback_command,
                    requested_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_type,
                    session_id,
                    device["id"],
                    intent,
                    mode,
                    risk,
                    reason,
                    _json(rendered_commands),
                    backup_command,
                    verify_command,
                    rollback_command,
                    requested_by,
                    utcnow(),
                ),
            )
            proposal_id = cur.lastrowid
        proposal = self.get_proposal(proposal_id)
        if proposal["id"] != proposal_id:
            raise ValidationError(f"Proposal verification failed for id {proposal_id}")
        return proposal

    def get_proposal(self, proposal_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT p.*, d.name AS device_name, d.hostname, d.ip_address, d.vendor, d.model, d.port, d.auth_method, d.read_only_default
                FROM proposals p
                JOIN devices d ON d.id = p.device_id
                WHERE p.id = ?
                """,
                (proposal_id,),
            ).fetchone()
        if not row:
            raise ValidationError(f"Unknown proposal: {proposal_id}")
        result = dict(row)
        result["rendered_commands"] = json.loads(result.pop("rendered_commands_json"))
        return result

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT p.id
                FROM proposals p
                WHERE p.status = 'pending_approval'
                ORDER BY p.created_at
                """
            ).fetchall()
        return [self.get_proposal(row["id"]) for row in rows]

    def diagnostics(self) -> dict[str, Any]:
        snapshot = self._db_snapshot()
        with self.connect() as conn:
            pending_rows = conn.execute(
                """
                SELECT p.id, p.intent, p.status, p.created_at, d.name AS device_name
                FROM proposals p
                JOIN devices d ON d.id = p.device_id
                WHERE p.status = 'pending_approval'
                ORDER BY p.id DESC
                LIMIT 10
                """
            ).fetchall()
        snapshot["pending_proposals"] = [dict(row) for row in pending_rows]
        return snapshot

    def approve_proposal(self, proposal_id: int, approved_by: str, approval_note: str = "") -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if proposal["status"] != "pending_approval":
            raise ValidationError(f"Proposal {proposal_id} is not waiting for approval")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE proposals
                SET status = 'approved', approved_by = ?, approval_note = ?, approved_at = ?
                WHERE id = ?
                """,
                (approved_by, approval_note, utcnow(), proposal_id),
            )
        return self.get_proposal(proposal_id)

    def mark_proposal_denied(self, proposal_id: int, approved_by: str, approval_note: str = "") -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if proposal["status"] != "pending_approval":
            raise ValidationError(f"Proposal {proposal_id} is not waiting for approval")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE proposals
                SET status = 'denied', approved_by = ?, approval_note = ?, denied_at = ?
                WHERE id = ?
                """,
                (approved_by, approval_note, utcnow(), proposal_id),
            )
        return self.get_proposal(proposal_id)

    def mark_proposal_executed(self, proposal_id: int, exit_code: int, summary: str) -> dict[str, Any]:
        status = "executed" if exit_code == 0 else "execution_failed"
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE proposals
                SET status = ?, execution_exit_code = ?, execution_summary = ?, executed_at = ?
                WHERE id = ?
                """,
                (status, exit_code, summary, utcnow(), proposal_id),
            )
        return self.get_proposal(proposal_id)

    def log_command_run(
        self,
        *,
        proposal_id: int,
        session_id: int | None,
        device_id: int,
        phase: str,
        command_text: str,
        approved_by: str,
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO command_runs
                (
                    proposal_id, session_id, device_id, phase, command_text, exit_code,
                    stdout, stderr, started_at, completed_at, approved_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    session_id,
                    device_id,
                    phase,
                    command_text,
                    exit_code,
                    stdout,
                    stderr,
                    started_at or utcnow(),
                    completed_at,
                    approved_by,
                ),
            )
        return cur.lastrowid

    def update_command_run(self, run_id: int, *, exit_code: int, stdout: str, stderr: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE command_runs
                SET exit_code = ?, stdout = ?, stderr = ?, completed_at = ?
                WHERE id = ?
                """,
                (exit_code, stdout, stderr, utcnow(), run_id),
            )

    def get_command_history(self, device: str = "", incident_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if device:
            clauses.append("d.name = ?")
            params.append(device)
        if incident_id:
            clauses.append("s.incident_id = ?")
            params.append(incident_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT cr.*, d.name AS device_name, s.incident_id
                FROM command_runs cr
                JOIN devices d ON d.id = cr.device_id
                LEFT JOIN sessions s ON s.id = cr.session_id
                {where}
                ORDER BY cr.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def seed_defaults(self) -> dict[str, int]:
        inserted = {"devices": 0, "approved_commands": 0, "playbooks": 0}
        defaults = [
            {
                "name": "Savoy-SW01",
                "hostname": "savoy-sw01",
                "ip_address": "192.0.2.10",
                "vendor": "LinuxSwitch",
                "model": "Generic",
                "tags": ["core", "switch"],
            },
            {
                "name": "MT-Edge-01",
                "hostname": "mt-edge-01",
                "ip_address": "192.0.2.20",
                "vendor": "MikroTik",
                "model": "CCR",
                "tags": ["edge", "router"],
            },
        ]
        for device in defaults:
            try:
                self.create_device(device)
                inserted["devices"] += 1
            except sqlite3.IntegrityError:
                pass

        command_defaults = [
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "dhcp_flap_triage",
                "command_template": "/ip dhcp-server lease print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Inspect lease churn before any change.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "ospf_adjacency_readonly",
                "command_template": "/routing ospf neighbor print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Read-only OSPF neighbor status.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "identity_read",
                "command_template": "/system/identity print",
                "mode": "read",
                "risk": "low",
                "notes": "Basic device identity check used in RouterOS triage.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "resource_read",
                "command_template": "/system/resource print",
                "mode": "read",
                "risk": "low",
                "notes": "Baseline resource and platform details.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "interfaces_read",
                "command_template": "/interface print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Full interface inventory and state.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "neighbors_read",
                "command_template": "/ip neighbor print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Topology and directly discovered neighbors.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "bridge_ports_read",
                "command_template": "/interface bridge port print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Bridge port membership and PVID state.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "bridge_vlans_read",
                "command_template": "/interface bridge vlan print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Bridge VLAN table for access and trunk validation.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "bridge_hosts_read",
                "command_template": "/interface bridge host print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "MAC learning table for host tracing.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "ppp_active_read",
                "command_template": "/ppp active print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Active PPP session state.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "arp_read",
                "command_template": "/ip arp print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "ARP table for host correlation.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "ip_addresses_read",
                "command_template": "/ip address print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Configured IP addresses by interface.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "routes_read",
                "command_template": "/ip route print detail without-paging",
                "mode": "read",
                "risk": "low",
                "notes": "Routing table review during path troubleshooting.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "mac_scan_short",
                "command_template": "/tool/mac-scan interface={interface} duration={duration}",
                "mode": "read",
                "risk": "medium",
                "notes": "Short MAC scan on a selected interface. Read-only but more active than a plain print.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "sniffer_status_read",
                "command_template": "/tool/sniffer print",
                "mode": "read",
                "risk": "low",
                "notes": "Current sniffer settings and state.",
            },
            {
                "vendor": "MikroTik",
                "model": "",
                "intent": "monitor_traffic_once",
                "command_template": "/interface/monitor-traffic {interface} once",
                "mode": "read",
                "risk": "low",
                "notes": "One-shot traffic snapshot on an interface.",
            },
            {
                "vendor": "LinuxSwitch",
                "model": "",
                "intent": "interface_counters",
                "command_template": "ip -s link show {interface}",
                "mode": "read",
                "risk": "low",
                "notes": "Interface counters for a Linux-based switch.",
            },
            {
                "vendor": "Cambium",
                "model": "",
                "intent": "radio_health",
                "command_template": "show radio status",
                "mode": "read",
                "risk": "low",
                "notes": "Baseline radio health check.",
            },
        ]
        for item in command_defaults:
            existing = self.list_approved_commands(vendor=item["vendor"], model=item["model"], intent=item["intent"])
            if not existing:
                self.add_approved_command(item)
                inserted["approved_commands"] += 1

        playbook_defaults = [
            {
                "name": "mikrotik-ospf-adjacency-loss",
                "vendor": "MikroTik",
                "issue": "OSPF adjacency loss",
                "steps": [
                    {"step": 1, "action": "Run read-only neighbor status", "tool": "propose_show_command", "intent": "ospf_adjacency_readonly"},
                    {"step": 2, "action": "Check interface counters", "tool": "propose_show_command", "command": "/interface ethernet print stats without-paging"},
                    {"step": 3, "action": "Review recent command history", "tool": "get_command_history"},
                ],
            },
            {
                "name": "linux-switch-dhcp-flap",
                "vendor": "LinuxSwitch",
                "issue": "DHCP flaps",
                "steps": [
                    {"step": 1, "action": "Check interface counters", "tool": "propose_show_command", "intent": "interface_counters", "params": {"interface": "eth0"}},
                    {"step": 2, "action": "Review local logs", "tool": "propose_show_command", "command": "journalctl -u dhcpd -n 100 --no-pager"},
                ],
            },
            {
                "name": "mikrotik-topology-baseline",
                "vendor": "MikroTik",
                "issue": "Topology baseline and L2 health",
                "steps": [
                    {"step": 1, "action": "Start a troubleshooting session", "tool": "start_session"},
                    {"step": 2, "action": "Confirm device identity", "tool": "propose_show_command", "intent": "identity_read"},
                    {"step": 3, "action": "Capture system resource baseline", "tool": "propose_show_command", "intent": "resource_read"},
                    {"step": 4, "action": "Review interface inventory and state", "tool": "propose_show_command", "intent": "interfaces_read"},
                    {"step": 5, "action": "Inspect discovered neighbors", "tool": "propose_show_command", "intent": "neighbors_read"},
                    {"step": 6, "action": "Review bridge ports", "tool": "propose_show_command", "intent": "bridge_ports_read"},
                    {"step": 7, "action": "Review bridge VLAN table", "tool": "propose_show_command", "intent": "bridge_vlans_read"},
                    {"step": 8, "action": "Review command history for recent changes", "tool": "get_command_history"},
                ],
            },
            {
                "name": "mikrotik-customer-port-trace",
                "vendor": "MikroTik",
                "issue": "Customer port trace and host mapping",
                "steps": [
                    {"step": 1, "action": "Start a troubleshooting session", "tool": "start_session"},
                    {"step": 2, "action": "Inspect bridge host table", "tool": "propose_show_command", "intent": "bridge_hosts_read"},
                    {"step": 3, "action": "Check ARP correlations", "tool": "propose_show_command", "intent": "arp_read"},
                    {"step": 4, "action": "Review active PPP sessions", "tool": "propose_show_command", "intent": "ppp_active_read"},
                    {"step": 5, "action": "Inspect neighbor topology around the suspected uplink", "tool": "propose_show_command", "intent": "neighbors_read"},
                    {"step": 6, "action": "Run a short MAC scan on the selected interface", "tool": "propose_show_command", "intent": "mac_scan_short", "params": {"interface": "ether1", "duration": "5s"}},
                    {"step": 7, "action": "Review command history for this device or incident", "tool": "get_command_history"},
                ],
            },
            {
                "name": "mikrotik-pppoe-discovery-triage",
                "vendor": "MikroTik",
                "issue": "PPPoE discovery or access-port troubleshooting",
                "steps": [
                    {"step": 1, "action": "Start a troubleshooting session", "tool": "start_session"},
                    {"step": 2, "action": "Review PPP active sessions", "tool": "propose_show_command", "intent": "ppp_active_read"},
                    {"step": 3, "action": "Check ARP table for host correlation", "tool": "propose_show_command", "intent": "arp_read"},
                    {"step": 4, "action": "Inspect bridge hosts on the candidate access port", "tool": "propose_show_command", "intent": "bridge_hosts_read"},
                    {"step": 5, "action": "Take a one-shot traffic sample on the access interface", "tool": "propose_show_command", "intent": "monitor_traffic_once", "params": {"interface": "ether1"}},
                    {"step": 6, "action": "Inspect sniffer status before a live read-only capture", "tool": "propose_show_command", "intent": "sniffer_status_read"},
                    {"step": 7, "action": "If needed, stage a bounded short MAC scan on the access interface", "tool": "propose_show_command", "intent": "mac_scan_short", "params": {"interface": "ether1", "duration": "5s"}},
                    {"step": 8, "action": "Review prior executed commands before escalating", "tool": "get_command_history"},
                ],
            },
        ]
        for item in playbook_defaults:
            existing = self.list_playbooks(vendor=item["vendor"], issue=item["issue"])
            if not existing:
                self.add_playbook(item)
                inserted["playbooks"] += 1
        return inserted

    def resolve_command_template(self, device_name: str, intent: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        device = self.get_device(device_name)
        candidates = self.list_approved_commands(vendor=device["vendor"], model=device["model"], intent=intent)
        if not candidates:
            raise ValidationError(f"No approved command template for intent '{intent}' on device '{device_name}'")
        command = candidates[0]
        rendered = render_template(command["command_template"], params or {})
        command["rendered_command"] = rendered
        return command

    def _device_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json"))
        item["read_only_default"] = bool(item["read_only_default"])
        return item


def render_template(template: str, params: dict[str, Any]) -> str:
    missing = [field_name for _, field_name, _, _ in Formatter().parse(template) if field_name and field_name not in params]
    if missing:
        raise ValidationError(f"Missing template params: {', '.join(sorted(set(missing)))}")
    return template.format(**params)
