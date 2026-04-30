from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from .config import ServerConfig
from .db import Store, ValidationError, render_template
from .executor import SSHExecutor

TOOLS = [
    {
        "name": "get_server_info",
        "description": "Return active server config and DB diagnostics for troubleshooting.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_proposal_by_id",
        "description": "Return a proposal row directly from the configured SQLite DB by id.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal_id"],
            "properties": {"proposal_id": {"type": "integer"}},
        },
    },
    {
        "name": "create_device",
        "description": "Add a device to the inventory.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "hostname"],
            "properties": {
                "name": {"type": "string"},
                "hostname": {"type": "string"},
                "ip_address": {"type": "string"},
                "vendor": {"type": "string"},
                "model": {"type": "string"},
                "port": {"type": "integer", "default": 22},
                "auth_method": {"type": "string", "default": "ssh_config"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "read_only_default": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "list_devices",
        "description": "List inventory devices.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_approved_command",
        "description": "Register an approved command template by vendor/model and intent.",
        "inputSchema": {
            "type": "object",
            "required": ["intent", "command_template"],
            "properties": {
                "vendor": {"type": "string"},
                "model": {"type": "string"},
                "intent": {"type": "string"},
                "command_template": {"type": "string"},
                "mode": {"type": "string", "enum": ["read", "write"], "default": "read"},
                "risk": {"type": "string", "default": "low"},
                "timeout_sec": {"type": "integer", "default": 30},
                "notes": {"type": "string"},
            },
        },
    },
    {
        "name": "list_approved_commands",
        "description": "List approved command templates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "model": {"type": "string"},
                "intent": {"type": "string"},
            },
        },
    },
    {
        "name": "add_playbook",
        "description": "Add a reusable troubleshooting playbook.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "steps"],
            "properties": {
                "name": {"type": "string"},
                "vendor": {"type": "string"},
                "model": {"type": "string"},
                "issue": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "object"}},
            },
        },
    },
    {
        "name": "list_playbooks",
        "description": "List playbooks filtered by vendor, model, or issue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor": {"type": "string"},
                "model": {"type": "string"},
                "issue": {"type": "string"},
            },
        },
    },
    {
        "name": "start_session",
        "description": "Create an incident session for proposal grouping and audit history.",
        "inputSchema": {
            "type": "object",
            "required": ["session_name"],
            "properties": {
                "session_name": {"type": "string"},
                "device_name": {"type": "string"},
                "incident_id": {"type": "string"},
            },
        },
    },
    {
        "name": "propose_show_command",
        "description": "Stage a read-only SSH command for approval and later execution.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name"],
            "properties": {
                "device_name": {"type": "string"},
                "session_id": {"type": "integer"},
                "intent": {"type": "string"},
                "command": {"type": "string"},
                "params": {"type": "object"},
                "reason": {"type": "string"},
                "requested_by": {"type": "string", "default": "agent"},
                "risk": {"type": "string", "default": "low"},
            },
        },
    },
    {
        "name": "approve_and_run",
        "description": "Approve and execute a pending read-only proposal.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal_id", "approved_by"],
            "properties": {
                "proposal_id": {"type": "integer"},
                "approved_by": {"type": "string"},
                "approval_note": {"type": "string"},
            },
        },
    },
    {
        "name": "propose_config_change",
        "description": "Stage a write/config proposal with backup, verify, and rollback commands.",
        "inputSchema": {
            "type": "object",
            "required": ["device_name", "commands", "reason"],
            "properties": {
                "device_name": {"type": "string"},
                "session_id": {"type": "integer"},
                "intent": {"type": "string"},
                "commands": {"type": "array", "items": {"type": "string"}},
                "params": {"type": "object"},
                "reason": {"type": "string"},
                "requested_by": {"type": "string", "default": "agent"},
                "risk": {"type": "string", "default": "high"},
                "backup_command": {"type": "string"},
                "verify_command": {"type": "string"},
                "rollback_command": {"type": "string"},
            },
        },
    },
    {
        "name": "approve_and_apply",
        "description": "Approve and execute a pending config change proposal.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal_id", "approved_by"],
            "properties": {
                "proposal_id": {"type": "integer"},
                "approved_by": {"type": "string"},
                "approval_note": {"type": "string"},
                "run_rollback_on_failure": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "deny_proposal",
        "description": "Deny a pending proposal without executing it.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal_id", "approved_by"],
            "properties": {
                "proposal_id": {"type": "integer"},
                "approved_by": {"type": "string"},
                "approval_note": {"type": "string"},
            },
        },
    },
    {
        "name": "get_pending_approvals",
        "description": "List pending proposals awaiting approval.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_command_history",
        "description": "List recent command execution history by device or incident.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device": {"type": "string"},
                "incident_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "seed_sample_data",
        "description": "Seed example devices, approved commands, and playbooks.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class MCPServer:
    def __init__(self) -> None:
        self.config = ServerConfig.load()
        self.store = Store(self.config.db_path)
        self.executor = SSHExecutor(self.store, self.config)
        self._wire_mode = "auto"
        self._log(
            "startup",
            {
                "db_path": str(self.config.db_path.resolve()),
                "config_path": str(self.config.db_path.parent.parent / "config" / "ssh_mcp.json"),
                "host_allowlist": self.config.host_allowlist,
            },
        )

    def run(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                return
            if "method" in message and message.get("id") is None:
                self._handle_notification(message)
                continue
            self._handle_request(message)

    def _handle_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "ssh-mcp", "version": "0.1.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "prompts/list":
                result = {"prompts": []}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params", {})
                result = self._call_tool(params.get("name", ""), params.get("arguments", {}))
            else:
                raise ValidationError(f"Unsupported method: {method}")
            self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as exc:  # noqa: BLE001
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32000,
                        "message": str(exc),
                        "data": traceback.format_exc(),
                    },
                }
            )

    def _handle_notification(self, message: dict[str, Any]) -> None:
        if message.get("method") == "notifications/initialized":
            return

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "create_device":
            payload = self.store.create_device(arguments)
        elif name == "get_server_info":
            payload = self._server_info()
        elif name == "get_proposal_by_id":
            payload = self.store.get_proposal(int(arguments["proposal_id"]))
        elif name == "list_devices":
            payload = self.store.list_devices()
        elif name == "add_approved_command":
            payload = self.store.add_approved_command(arguments)
        elif name == "list_approved_commands":
            payload = self.store.list_approved_commands(
                vendor=arguments.get("vendor", ""),
                model=arguments.get("model", ""),
                intent=arguments.get("intent", ""),
            )
        elif name == "add_playbook":
            payload = self.store.add_playbook(arguments)
        elif name == "list_playbooks":
            payload = self.store.list_playbooks(
                vendor=arguments.get("vendor", ""),
                model=arguments.get("model", ""),
                issue=arguments.get("issue", ""),
            )
        elif name == "start_session":
            payload = self.store.start_session(
                session_name=arguments["session_name"],
                device_name=arguments.get("device_name"),
                incident_id=arguments.get("incident_id", ""),
            )
        elif name == "propose_show_command":
            payload = self._propose_show_command(arguments)
        elif name == "approve_and_run":
            payload = self.executor.run_proposal(
                proposal_id=int(arguments["proposal_id"]),
                approved_by=arguments["approved_by"],
                approval_note=arguments.get("approval_note", ""),
            )
        elif name == "propose_config_change":
            payload = self._propose_config_change(arguments)
        elif name == "approve_and_apply":
            payload = self.executor.run_proposal(
                proposal_id=int(arguments["proposal_id"]),
                approved_by=arguments["approved_by"],
                approval_note=arguments.get("approval_note", ""),
                run_rollback_on_failure=bool(arguments.get("run_rollback_on_failure", False)),
            )
        elif name == "deny_proposal":
            payload = self.store.mark_proposal_denied(
                proposal_id=int(arguments["proposal_id"]),
                approved_by=arguments["approved_by"],
                approval_note=arguments.get("approval_note", ""),
            )
        elif name == "get_pending_approvals":
            payload = self.store.list_pending_proposals()
        elif name == "get_command_history":
            payload = self.store.get_command_history(
                device=arguments.get("device", ""),
                incident_id=arguments.get("incident_id", ""),
                limit=int(arguments.get("limit", 20)),
            )
        elif name == "seed_sample_data":
            payload = self.store.seed_defaults()
        else:
            raise ValidationError(f"Unknown tool: {name}")
        return self._tool_response(payload)

    def _propose_show_command(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params = arguments.get("params", {}) or {}
        if arguments.get("intent"):
            cmd_def = self.store.resolve_command_template(arguments["device_name"], arguments["intent"], params)
            rendered_commands = [cmd_def["rendered_command"]]
            reason = arguments.get("reason", cmd_def.get("notes", "Approved read-only command"))
            risk = arguments.get("risk", cmd_def["risk"])
        elif arguments.get("command"):
            rendered_commands = [render_template(arguments["command"], params)]
            reason = arguments.get("reason", "Ad hoc read-only troubleshooting command")
            risk = arguments.get("risk", "medium")
        else:
            raise ValidationError("propose_show_command requires either intent or command")
        proposal = self.store.create_proposal(
            proposal_type="show_command",
            device_name=arguments["device_name"],
            session_id=arguments.get("session_id"),
            intent=arguments.get("intent", "ad_hoc"),
            mode="read",
            risk=risk,
            reason=reason,
            rendered_commands=rendered_commands,
            requested_by=arguments.get("requested_by", "agent"),
        )
        self._log(
            "proposal_created",
            {
                "tool": "propose_show_command",
                "proposal_id": proposal["id"],
                "device": proposal["device_name"],
                "intent": proposal["intent"],
                "status": proposal["status"],
                "db": self.store.diagnostics(),
            },
        )
        return proposal

    def _propose_config_change(self, arguments: dict[str, Any]) -> dict[str, Any]:
        params = arguments.get("params", {}) or {}
        rendered_commands = [render_template(command, params) for command in arguments.get("commands", [])]
        proposal = self.store.create_proposal(
            proposal_type="config_change",
            device_name=arguments["device_name"],
            session_id=arguments.get("session_id"),
            intent=arguments.get("intent", "config_change"),
            mode="write",
            risk=arguments.get("risk", "high"),
            reason=arguments["reason"],
            rendered_commands=rendered_commands,
            backup_command=render_template(arguments.get("backup_command", ""), params) if arguments.get("backup_command") else "",
            verify_command=render_template(arguments.get("verify_command", ""), params) if arguments.get("verify_command") else "",
            rollback_command=render_template(arguments.get("rollback_command", ""), params) if arguments.get("rollback_command") else "",
            requested_by=arguments.get("requested_by", "agent"),
        )
        self._log(
            "proposal_created",
            {
                "tool": "propose_config_change",
                "proposal_id": proposal["id"],
                "device": proposal["device_name"],
                "intent": proposal["intent"],
                "status": proposal["status"],
                "db": self.store.diagnostics(),
            },
        )
        return proposal

    def _server_info(self) -> dict[str, Any]:
        return {
            "db_path": str(self.config.db_path.resolve()),
            "ssh_binary": self.config.ssh_binary,
            "default_timeout_sec": self.config.default_timeout_sec,
            "read_only_by_default": self.config.read_only_by_default,
            "allow_write_actions": self.config.allow_write_actions,
            "allow_auto_rollback": self.config.allow_auto_rollback,
            "host_allowlist": self.config.host_allowlist,
            "writable_vendors": self.config.writable_vendors,
            "db": self.store.diagnostics(),
        }

    def _log(self, event: str, payload: dict[str, Any]) -> None:
        print(json.dumps({"event": event, "payload": payload}), file=sys.stderr, flush=True)

    def _tool_response(self, payload: Any) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": False}

    def _read_message(self) -> dict[str, Any] | None:
        first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None

        stripped = first_line.strip()
        if stripped.startswith(b"{"):
            self._wire_mode = "lines"
            return json.loads(stripped.decode("utf-8"))

        headers: dict[str, str] = {}
        line = first_line
        while True:
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("utf-8").partition(":")
            headers[key.strip().lower()] = value.strip()
            line = sys.stdin.buffer.readline()
            if not line:
                return None
        self._wire_mode = "content-length"
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        body = sys.stdin.buffer.read(length)
        return json.loads(body.decode("utf-8"))

    def _write_message(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload)
        if self._wire_mode == "lines":
            sys.stdout.write(body + "\n")
            sys.stdout.flush()
            return
        encoded = body.encode("utf-8")
        sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("utf-8"))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


def main() -> None:
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
