from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ServerConfig:
    db_path: Path
    ssh_binary: str = "ssh"
    ssh_options: list[str] = field(
        default_factory=lambda: [
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
        ]
    )
    default_timeout_sec: int = 30
    read_only_by_default: bool = True
    allow_write_actions: bool = True
    allow_auto_rollback: bool = False
    host_allowlist: list[str] = field(default_factory=list)
    writable_vendors: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "ServerConfig":
        root = Path(os.environ.get("SSH_MCP_ROOT", Path.cwd()))
        config_path = Path(os.environ.get("SSH_MCP_CONFIG", root / "config" / "ssh_mcp.json"))
        db_path = Path(os.environ.get("SSH_MCP_DB_PATH", root / "data" / "ssh_mcp.sqlite3"))
        config = cls(db_path=db_path)
        if config_path.exists():
            payload = json.loads(config_path.read_text())
            config.ssh_binary = payload.get("ssh_binary", config.ssh_binary)
            config.ssh_options = payload.get("ssh_options", config.ssh_options)
            config.default_timeout_sec = int(payload.get("default_timeout_sec", config.default_timeout_sec))
            config.read_only_by_default = bool(payload.get("read_only_by_default", config.read_only_by_default))
            config.allow_write_actions = bool(payload.get("allow_write_actions", config.allow_write_actions))
            config.allow_auto_rollback = bool(payload.get("allow_auto_rollback", config.allow_auto_rollback))
            config.host_allowlist = list(payload.get("host_allowlist", config.host_allowlist))
            config.writable_vendors = list(payload.get("writable_vendors", config.writable_vendors))
        config.db_path.parent.mkdir(parents=True, exist_ok=True)
        return config
