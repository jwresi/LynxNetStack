#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Iterable

from core.shared import load_env_file as shared_load_env_file, seed_project_envs


IAC = 255
DO = 253
DONT = 254
WILL = 251
WONT = 252
SB = 250
SE = 240

PROMPT_RE = re.compile(r"([A-Za-z0-9._-]+(?:\(config[^)]*\))?[>#])")
MORE_RE = re.compile(r"--+ ?[Mm]ore ?--+|<\s*--- More ---\s*>|More:", re.I)
SAFE_COMMAND_RE = re.compile(
    r"^(?:"
    r"\?"
    r"|configure"
    r"|exit"
    r"|end"
    r"|copy\s+running-config\s+startup-config"
    r"|show(?:\s+[A-Za-z0-9:/._?-]+)*"
    r"|interface\s+gpon(?:\s+[A-Za-z0-9:/._?-]+)*"
    r"|ont(?:\s+[A-Za-z0-9:/._?-]+)*"
    r"|terminal\s+length\s+0"
    r"|terminal\s+page-break\s+disable"
    r")$",
    re.I,
)


def load_dotenv(path: Path) -> None:
    shared_load_env_file(path)


def seed_envs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    seed_project_envs(repo_root)


def recv_clean(sock: socket.socket, timeout: float = 8.0) -> str:
    sock.settimeout(timeout)
    chunks: list[bytes] = []
    end = time.time() + timeout
    while time.time() < end:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            break
        if not data:
            break
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b == IAC and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                    opt = data[i + 2]
                    if cmd in (DO, DONT):
                        sock.sendall(bytes([IAC, WONT, opt]))
                    else:
                        sock.sendall(bytes([IAC, DONT, opt]))
                    i += 3
                    continue
                if cmd == SB:
                    end_i = data.find(bytes([IAC, SE]), i + 2)
                    if end_i == -1:
                        break
                    i = end_i + 2
                    continue
                i += 2
                continue
            out.append(b)
            i += 1
        if out:
            chunks.append(bytes(out))
        text = b"".join(chunks).decode("utf-8", "ignore")
        if MORE_RE.search(text):
            sock.sendall(b" ")
            continue
        if PROMPT_RE.search(text) or re.search(r"(?:User|Username|Password)\s*:\s*$", text, re.I):
            return text
    return b"".join(chunks).decode("utf-8", "ignore")


def wait_for(sock: socket.socket, pattern: str, timeout: float = 8.0) -> str:
    text = recv_clean(sock, timeout=timeout)
    if not re.search(pattern, text, re.I | re.M):
        raise RuntimeError(f"Did not receive expected prompt /{pattern}/. Output: {text[-500:]}")
    return text


def send_line(sock: socket.socket, line: str) -> None:
    sock.sendall(line.encode("utf-8") + b"\r\n")


def run_session(host: str, username: str, password: str, commands: Iterable[str], timeout: float = 8.0) -> dict:
    for command in commands:
        if not SAFE_COMMAND_RE.match(command.strip()):
            raise RuntimeError(f"Disallowed OLT command: {command}")
    sock = socket.create_connection((host, 23), timeout=timeout)
    try:
        banner = wait_for(sock, r"(?:User|Username)\s*:", timeout=timeout)
        send_line(sock, username)
        wait_for(sock, r"Password\s*:", timeout=timeout)
        send_line(sock, password)
        post_login = recv_clean(sock, timeout=timeout)
        if not PROMPT_RE.search(post_login):
            raise RuntimeError(f"Did not reach OLT prompt after login. Output: {post_login[-500:]}")
        send_line(sock, "enable")
        enabled = recv_clean(sock, timeout=timeout)
        prompt_match = PROMPT_RE.search(enabled)
        if not prompt_match:
            prompt_match = PROMPT_RE.search(post_login)
        prompt = prompt_match.group(1) if prompt_match else ""
        outputs = []
        if SAFE_COMMAND_RE.match("terminal length 0"):
            send_line(sock, "terminal length 0")
            recv_clean(sock, timeout=timeout)
        for command in commands:
            send_line(sock, command)
            text = recv_clean(sock, timeout=max(timeout, 12.0))
            outputs.append({"command": command, "output": text})
        send_line(sock, "exit")
        return {
            "available": True,
            "host": host,
            "prompt": prompt,
            "outputs": outputs,
            "login_banner": banner[-400:],
        }
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main() -> int:
    seed_envs()
    parser = argparse.ArgumentParser(description="Read-only telnet CLI wrapper for TP-Link OLTs")
    parser.add_argument("--host", required=True)
    parser.add_argument("--username", default=os.environ.get("OLT_TELNET_USER") or os.environ.get("olt_telnet_user") or "admin")
    parser.add_argument("--password", default=os.environ.get("OLT_TELNET_PASSWORD") or os.environ.get("olt_telnet_password") or os.environ.get("password") or "")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("commands", nargs="+")
    args = parser.parse_args()

    if not args.username or not args.password:
        print(json.dumps({"available": False, "error": "Missing olt_user or olt_password"}))
        return 1

    try:
        result = run_session(args.host, args.username, args.password, args.commands, timeout=args.timeout)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(json.dumps({"available": False, "host": args.host, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
