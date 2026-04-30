# ssh_mcp

`ssh_mcp` is a small stdio MCP server for approval-gated SSH operations. It is designed for AnythingLLM-style agent flows where the agent can propose commands, wait for explicit approval, then execute and log them with a durable history.

The server keeps its own local command memory in SQLite:

- device inventory
- approved troubleshooting command templates by vendor/model
- pending approval queue
- command/session audit trail
- optional playbooks for common incidents

## What it implements

The tool flow matches the pattern you described:

1. `propose_show_command(device, intent)` or `propose_config_change(device, commands, reason)`
2. Human reviews the exact command, target host, reason, and risk
3. `approve_and_run(proposal_id)` or `approve_and_apply(proposal_id)`
4. Server executes over SSH and logs output in SQLite

Read-only troubleshooting commands and config changes are kept separate. Config changes support:

- explicit approval every time
- optional pre-change backup
- optional post-change verification
- optional rollback command
- host allowlist and writable vendor allowlist
- per-command session logging

## Project layout

- [src/ssh_mcp/server.py](/Users/jono/projects/ssh_mcp/src/ssh_mcp/server.py)
- [src/ssh_mcp/db.py](/Users/jono/projects/ssh_mcp/src/ssh_mcp/db.py)
- [src/ssh_mcp/executor.py](/Users/jono/projects/ssh_mcp/src/ssh_mcp/executor.py)
- [config/ssh_mcp.example.json](/Users/jono/projects/ssh_mcp/config/ssh_mcp.example.json)

## Quick start

Use Python 3.11+.

```bash
cd /Users/jono/projects/ssh_mcp
cp config/ssh_mcp.example.json config/ssh_mcp.json
python3 -m pip install -e .
python3 -m ssh_mcp.server
```

The SQLite database defaults to `data/ssh_mcp.sqlite3`.

## AnythingLLM MCP wiring

Point AnythingLLM at this server as a stdio MCP process. The exact UI fields may vary by AnythingLLM version, but the command should be equivalent to:

```json
{
  "command": "python3",
  "args": ["-m", "ssh_mcp.server"],
  "env": {
    "SSH_MCP_ROOT": "/Users/jono/projects/ssh_mcp",
    "SSH_MCP_CONFIG": "/Users/jono/projects/ssh_mcp/config/ssh_mcp.json",
    "SSH_MCP_DB_PATH": "/Users/jono/projects/ssh_mcp/data/ssh_mcp.sqlite3"
  }
}
```

If you install the package in editable mode, `ssh-mcp` is also available as an entrypoint.

## Tool surface

- `create_device`
- `list_devices`
- `add_approved_command`
- `list_approved_commands`
- `add_playbook`
- `list_playbooks`
- `start_session`
- `propose_show_command`
- `approve_and_run`
- `propose_config_change`
- `approve_and_apply`
- `deny_proposal`
- `get_pending_approvals`
- `get_command_history`
- `seed_sample_data`

## Example flows

Seed example inventory, playbooks, and vendor commands:

```json
{
  "name": "seed_sample_data",
  "arguments": {}
}
```

Stage a read-only MikroTik OSPF check:

```json
{
  "name": "propose_show_command",
  "arguments": {
    "device_name": "MT-Edge-01",
    "intent": "ospf_adjacency_readonly",
    "reason": "Check current neighbor state before any change",
    "requested_by": "anythingllm"
  }
}
```

Approve and execute it:

```json
{
  "name": "approve_and_run",
  "arguments": {
    "proposal_id": 1,
    "approved_by": "jono",
    "approval_note": "Read-only troubleshooting approved"
  }
}
```

Stage a write change with backup and verification:

```json
{
  "name": "propose_config_change",
  "arguments": {
    "device_name": "MT-Edge-01",
    "commands": [
      "/routing ospf interface-template set [find where interfaces=ether1] cost=20"
    ],
    "reason": "Temporary metric increase during maintenance",
    "backup_command": "/routing ospf interface-template print detail without-paging",
    "verify_command": "/routing ospf interface-template print detail without-paging",
    "rollback_command": "/routing ospf interface-template set [find where interfaces=ether1] cost=10",
    "requested_by": "anythingllm"
  }
}
```

Retrieve recent history for a device:

```json
{
  "name": "get_command_history",
  "arguments": {
    "device": "Savoy-SW01",
    "limit": 10
  }
}
```

## Safety model

- Read-only mode is the expected default for troubleshooting.
- Config changes always require a separate explicit approval call.
- The server can restrict execution by host allowlist.
- The server can restrict write actions by vendor allowlist.
- Every executed command is logged with stdout, stderr, exit code, phase, approver, and timestamps.
- Auto-rollback is disabled by default.

## Notes

This server does not assume a built-in global approval toggle in AnythingLLM. The approval gate is implemented directly in the MCP tool design, which is the safer pattern for SSH and network-device operations.
