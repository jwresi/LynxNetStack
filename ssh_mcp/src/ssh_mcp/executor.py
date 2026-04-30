from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from typing import Any

from .config import ServerConfig
from .db import Store, ValidationError


@dataclass(slots=True)
class CommandResult:
    phase: str
    command: str
    exit_code: int
    stdout: str
    stderr: str


class SSHExecutor:
    def __init__(self, store: Store, config: ServerConfig):
        self.store = store
        self.config = config

    def run_proposal(self, proposal_id: int, approved_by: str, approval_note: str = "", run_rollback_on_failure: bool = False) -> dict[str, Any]:
        proposal = self.store.approve_proposal(proposal_id, approved_by=approved_by, approval_note=approval_note)
        self._validate_proposal(policy=proposal)
        phases = self._phase_plan(proposal)
        results: list[dict[str, Any]] = []
        failing_result: CommandResult | None = None
        for phase, command in phases:
            result = self._run_single(proposal, phase=phase, command=command, approved_by=approved_by)
            results.append(asdict(result))
            if result.exit_code != 0:
                failing_result = result
                break
        if failing_result and proposal["rollback_command"] and run_rollback_on_failure and self.config.allow_auto_rollback:
            rollback = self._run_single(proposal, phase="rollback", command=proposal["rollback_command"], approved_by=approved_by)
            results.append(rollback.__dict__)
            if rollback.exit_code == 0:
                failing_result = None
        summary = self._summary_from_results(results)
        exit_code = max((item["exit_code"] for item in results), default=1)
        final = self.store.mark_proposal_executed(proposal_id, exit_code=exit_code, summary=summary)
        final["results"] = results
        return final

    def _phase_plan(self, proposal: dict[str, Any]) -> list[tuple[str, str]]:
        phases: list[tuple[str, str]] = []
        if proposal["backup_command"]:
            phases.append(("backup", proposal["backup_command"]))
        main_phase = "apply" if proposal["proposal_type"] == "config_change" else "read"
        for command in proposal["rendered_commands"]:
            phases.append((main_phase, command))
        if proposal["verify_command"]:
            phases.append(("verify", proposal["verify_command"]))
        return phases

    def _validate_proposal(self, policy: dict[str, Any]) -> None:
        hostname = policy["hostname"]
        if self.config.host_allowlist and hostname not in self.config.host_allowlist and policy["device_name"] not in self.config.host_allowlist:
            raise ValidationError(f"Device host '{hostname}' is not in the host allowlist")
        is_write = policy["mode"] != "read"
        if is_write and not self.config.allow_write_actions:
            raise ValidationError("Write actions are disabled by server config")
        if is_write and self.config.writable_vendors and policy["vendor"] not in self.config.writable_vendors:
            raise ValidationError(f"Vendor '{policy['vendor']}' is not in the writable vendor allowlist")

    def _run_single(self, proposal: dict[str, Any], *, phase: str, command: str, approved_by: str) -> CommandResult:
        run_id = self.store.log_command_run(
            proposal_id=proposal["id"],
            session_id=proposal["session_id"],
            device_id=proposal["device_id"],
            phase=phase,
            command_text=command,
            approved_by=approved_by,
        )
        timeout = self.config.default_timeout_sec
        ssh_target = proposal["hostname"]
        port = int(proposal["port"])
        auth_method = proposal.get("auth_method", "ssh_config")
        try:
            if auth_method == "password_env":
                result = self._run_password_env(phase=phase, ssh_target=ssh_target, port=port, command=command, timeout=timeout)
            else:
                result = self._run_ssh_config(phase=phase, ssh_target=ssh_target, port=port, command=command, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            result = CommandResult(
                phase=phase,
                command=command,
                exit_code=124,
                stdout=(exc.stdout or "").strip() if exc.stdout else "",
                stderr=f"Command timed out after {timeout}s",
            )
        self.store.update_command_run(run_id, exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr)
        return result

    def _run_ssh_config(self, *, phase: str, ssh_target: str, port: int, command: str, timeout: int) -> CommandResult:
        cmd = [self.config.ssh_binary, *self.config.ssh_options, "-p", str(port), ssh_target, command]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            phase=phase,
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )

    def _run_password_env(self, *, phase: str, ssh_target: str, port: int, command: str, timeout: int) -> CommandResult:
        password = os.environ.get("SSH_MCP_PASSWORD", "")
        if not password:
            return CommandResult(
                phase=phase,
                command=command,
                exit_code=78,
                stdout="",
                stderr="SSH_MCP_PASSWORD is not set",
            )
        expect_script = f"""
set timeout {timeout}
set password [lindex $argv 0]
set target [lindex $argv 1]
set port [lindex $argv 2]
set remote_command [lindex $argv 3]
spawn ssh -o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -p $port $target $remote_command
expect {{
    -re "(?i)password:" {{ send "$password\r"; exp_continue }}
    timeout {{ puts stderr "Command timed out after {timeout}s"; exit 124 }}
    eof
}}
catch wait result
set exit_code [lindex $result 3]
exit $exit_code
"""
        script_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".exp", delete=False) as handle:
                handle.write(expect_script)
                script_path = handle.name
            completed = subprocess.run(
                ["expect", script_path, password, ssh_target, str(port), command],
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                check=False,
            )
        finally:
            if script_path and os.path.exists(script_path):
                os.unlink(script_path)
        stdout = completed.stdout.replace("\r", "").strip()
        stderr = completed.stderr.replace("\r", "").strip()
        stdout_lines = [line for line in stdout.splitlines() if line.strip() and not line.startswith("spawn ssh ") and "password:" not in line.lower()]
        stdout = "\n".join(stdout_lines).strip()
        return CommandResult(
            phase=phase,
            command=command,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def _summary_from_results(self, results: list[dict[str, Any]]) -> str:
        if not results:
            return "No commands executed."
        failing = next((item for item in results if item["exit_code"] != 0), None)
        if failing:
            return f"{failing['phase']} failed with exit code {failing['exit_code']}: {truncate(failing['stderr'] or failing['stdout'])}"
        return f"Executed {len(results)} command(s) successfully."


def truncate(text: str, limit: int = 240) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
