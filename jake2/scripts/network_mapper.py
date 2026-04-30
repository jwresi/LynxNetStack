#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sqlite3
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from librouteros import connect


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def b2s(value):
    if isinstance(value, bytes):
        return value.decode(errors="ignore")
    return value


def to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "1", "on"}


def mac_norm(value):
    if not value:
        return None
    text = str(value).strip().lower().replace("-", ":")
    parts = text.split(":")
    if len(parts) == 6 and all(len(part) == 2 for part in parts):
        return text
    return None


def load_env_values(env_path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in Path(env_path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_creds(env_path: str) -> tuple[str, str]:
    cfg = load_env_values(env_path)
    user = cfg.get("username")
    password = cfg.get("password")
    if not user or not password:
        raise RuntimeError(f"Missing username/password in {env_path}")
    return str(user), str(password)


def db_connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS scans (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          subnet TEXT NOT NULL,
          hosts_tested INTEGER NOT NULL DEFAULT 0,
          api_reachable INTEGER NOT NULL DEFAULT 0,
          notes TEXT
        );

        CREATE TABLE IF NOT EXISTS devices (
          scan_id INTEGER NOT NULL,
          ip TEXT NOT NULL,
          identity TEXT,
          board_name TEXT,
          model TEXT,
          version TEXT,
          architecture TEXT,
          uptime TEXT,
          is_crs INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (scan_id, ip),
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS interfaces (
          scan_id INTEGER NOT NULL,
          ip TEXT NOT NULL,
          name TEXT NOT NULL,
          type TEXT,
          running INTEGER,
          disabled INTEGER,
          slave INTEGER,
          mtu INTEGER,
          actual_mtu INTEGER,
          rx_byte INTEGER,
          tx_byte INTEGER,
          rx_packet INTEGER,
          tx_packet INTEGER,
          last_link_up_time TEXT,
          PRIMARY KEY (scan_id, ip, name),
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS neighbors (
          scan_id INTEGER NOT NULL,
          ip TEXT NOT NULL,
          interface TEXT,
          neighbor_address TEXT,
          neighbor_identity TEXT,
          platform TEXT,
          version TEXT,
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bridge_ports (
          scan_id INTEGER NOT NULL,
          ip TEXT NOT NULL,
          interface TEXT,
          pvid INTEGER,
          ingress_filtering INTEGER,
          frame_types TEXT,
          trusted INTEGER,
          hw INTEGER,
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bridge_vlans (
          scan_id INTEGER NOT NULL,
          ip TEXT NOT NULL,
          vlan_ids TEXT,
          tagged TEXT,
          untagged TEXT,
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bridge_hosts (
          scan_id INTEGER NOT NULL,
          ip TEXT NOT NULL,
          mac TEXT,
          on_interface TEXT,
          vid INTEGER,
          local INTEGER,
          external INTEGER,
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS router_ppp_active (
          scan_id INTEGER NOT NULL,
          router_ip TEXT NOT NULL,
          name TEXT,
          service TEXT,
          caller_id TEXT,
          address TEXT,
          uptime TEXT,
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS router_arp (
          scan_id INTEGER NOT NULL,
          router_ip TEXT NOT NULL,
          address TEXT,
          mac TEXT,
          interface TEXT,
          dynamic INTEGER,
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS one_way_outliers (
          scan_id INTEGER NOT NULL,
          ip TEXT NOT NULL,
          interface TEXT NOT NULL,
          rx_delta INTEGER NOT NULL,
          tx_delta INTEGER NOT NULL,
          direction TEXT NOT NULL,
          severity TEXT NOT NULL,
          note TEXT,
          FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_devices_identity ON devices(identity);
        CREATE INDEX IF NOT EXISTS idx_neighbors_scan_ip ON neighbors(scan_id, ip);
        CREATE INDEX IF NOT EXISTS idx_bridge_hosts_scan_ip_mac ON bridge_hosts(scan_id, ip, mac);
        CREATE INDEX IF NOT EXISTS idx_interfaces_scan_ip_name ON interfaces(scan_id, ip, name);
        CREATE INDEX IF NOT EXISTS idx_outliers_scan ON one_way_outliers(scan_id);
        """
    )
    con.commit()


def tcp_open(ip: str, port: int = 8728, timeout: float = 0.7) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def gather_device(ip: str, user: str, password: str, timeout: float = 3.0) -> dict:
    api = connect(host=ip, username=user, password=password, port=8728, timeout=timeout)

    identity = None
    for row in api.path("system", "identity").select("name"):
        identity = b2s(row.get("name"))
        break

    resource = {}
    for row in api.path("system", "resource").select(
        "board-name", "version", "architecture-name", "uptime", "platform"
    ):
        resource = {key: b2s(value) for key, value in row.items()}
        break

    board_name = resource.get("board-name")
    is_crs = bool(board_name and str(board_name).upper().startswith("CRS"))

    interfaces = []
    for row in api.path("interface").select(
        "name",
        "type",
        "running",
        "disabled",
        "slave",
        "mtu",
        "actual-mtu",
        "rx-byte",
        "tx-byte",
        "rx-packet",
        "tx-packet",
        "last-link-up-time",
    ):
        interfaces.append(
            {
                "name": b2s(row.get("name")),
                "type": b2s(row.get("type")),
                "running": to_bool(row.get("running")),
                "disabled": to_bool(row.get("disabled")),
                "slave": to_bool(row.get("slave")),
                "mtu": to_int(row.get("mtu"), None),
                "actual_mtu": to_int(row.get("actual-mtu"), None),
                "rx_byte": to_int(row.get("rx-byte"), 0),
                "tx_byte": to_int(row.get("tx-byte"), 0),
                "rx_packet": to_int(row.get("rx-packet"), 0),
                "tx_packet": to_int(row.get("tx-packet"), 0),
                "last_link_up_time": b2s(row.get("last-link-up-time")),
            }
        )

    neighbors = []
    try:
        for row in api.path("ip", "neighbor").select(
            "address", "identity", "interface", "platform", "version"
        ):
            neighbors.append(
                {
                    "address": b2s(row.get("address")),
                    "identity": b2s(row.get("identity")),
                    "interface": b2s(row.get("interface")),
                    "platform": b2s(row.get("platform")),
                    "version": b2s(row.get("version")),
                }
            )
    except Exception:
        pass

    bridge_ports = []
    bridge_vlans = []
    bridge_hosts = []

    try:
        for row in api.path("interface", "bridge", "port").select(
            "interface", "pvid", "ingress-filtering", "frame-types", "trusted", "hw"
        ):
            bridge_ports.append(
                {
                    "interface": b2s(row.get("interface")),
                    "pvid": to_int(row.get("pvid"), None),
                    "ingress_filtering": to_bool(row.get("ingress-filtering")),
                    "frame_types": b2s(row.get("frame-types")),
                    "trusted": to_bool(row.get("trusted")),
                    "hw": to_bool(row.get("hw")),
                }
            )
    except Exception:
        pass

    try:
        for row in api.path("interface", "bridge", "vlan").select("vlan-ids", "tagged", "untagged"):
            bridge_vlans.append(
                {
                    "vlan_ids": b2s(row.get("vlan-ids")),
                    "tagged": b2s(row.get("tagged")),
                    "untagged": b2s(row.get("untagged")),
                }
            )
    except Exception:
        pass

    try:
        for row in api.path("interface", "bridge", "host").select(
            "mac-address", "on-interface", "vid", "local", "external"
        ):
            bridge_hosts.append(
                {
                    "mac": mac_norm(row.get("mac-address")),
                    "on_interface": b2s(row.get("on-interface")),
                    "vid": to_int(row.get("vid"), None),
                    "local": to_bool(row.get("local")),
                    "external": to_bool(row.get("external")),
                }
            )
    except Exception:
        pass

    ppp_active = []
    arp = []
    try:
        for row in api.path("ppp", "active").select("name", "service", "caller-id", "address", "uptime"):
            ppp_active.append(
                {
                    "name": b2s(row.get("name")),
                    "service": b2s(row.get("service")),
                    "caller_id": mac_norm(row.get("caller-id")),
                    "address": b2s(row.get("address")),
                    "uptime": b2s(row.get("uptime")),
                }
            )
    except Exception:
        pass

    try:
        for row in api.path("ip", "arp").select("address", "mac-address", "interface", "dynamic"):
            arp.append(
                {
                    "address": b2s(row.get("address")),
                    "mac": mac_norm(row.get("mac-address")),
                    "interface": b2s(row.get("interface")),
                    "dynamic": to_bool(row.get("dynamic")),
                }
            )
    except Exception:
        pass

    return {
        "ip": ip,
        "identity": identity,
        "board_name": board_name,
        "model": resource.get("platform"),
        "version": resource.get("version"),
        "architecture": resource.get("architecture-name"),
        "uptime": resource.get("uptime"),
        "is_crs": is_crs,
        "interfaces": interfaces,
        "neighbors": neighbors,
        "bridge_ports": bridge_ports,
        "bridge_vlans": bridge_vlans,
        "bridge_hosts": bridge_hosts,
        "ppp_active": ppp_active,
        "arp": arp,
    }


def latest_scan_id(con: sqlite3.Connection):
    row = con.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None


def previous_interface_counters(con: sqlite3.Connection, scan_id):
    if not scan_id:
        return {}
    rows = con.execute("SELECT ip,name,rx_byte,tx_byte FROM interfaces WHERE scan_id=?", (scan_id,)).fetchall()
    return {(ip, name): (rx or 0, tx or 0) for ip, name, rx, tx in rows}


def classify_one_way(rx_delta: int, tx_delta: int):
    low = 64 * 1024
    mid = 256 * 1024
    if rx_delta == 0 and tx_delta >= low:
        return "tx_only", ("high" if tx_delta >= mid else "medium")
    if tx_delta == 0 and rx_delta >= low:
        return "rx_only", ("high" if rx_delta >= mid else "medium")
    return None, None


def save_scan(con: sqlite3.Connection, scan_id: int, devices: list[dict], prev_counters: dict, host_vid):
    for device in devices:
        con.execute(
            """
            INSERT INTO devices(scan_id,ip,identity,board_name,model,version,architecture,uptime,is_crs)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                scan_id,
                device["ip"],
                device.get("identity"),
                device.get("board_name"),
                device.get("model"),
                device.get("version"),
                device.get("architecture"),
                device.get("uptime"),
                1 if device.get("is_crs") else 0,
            ),
        )

        for interface in device.get("interfaces", []):
            con.execute(
                """
                INSERT INTO interfaces(
                  scan_id,ip,name,type,running,disabled,slave,mtu,actual_mtu,rx_byte,tx_byte,rx_packet,tx_packet,last_link_up_time
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    scan_id,
                    device["ip"],
                    interface.get("name"),
                    interface.get("type"),
                    1 if interface.get("running") else 0,
                    1 if interface.get("disabled") else 0,
                    1 if interface.get("slave") else 0,
                    interface.get("mtu"),
                    interface.get("actual_mtu"),
                    interface.get("rx_byte") or 0,
                    interface.get("tx_byte") or 0,
                    interface.get("rx_packet") or 0,
                    interface.get("tx_packet") or 0,
                    interface.get("last_link_up_time"),
                ),
            )

            prev = prev_counters.get((device["ip"], interface.get("name")))
            if prev and interface.get("type") == "ether" and interface.get("running") and not interface.get("disabled"):
                rx_delta = max(0, (interface.get("rx_byte") or 0) - prev[0])
                tx_delta = max(0, (interface.get("tx_byte") or 0) - prev[1])
                direction, severity = classify_one_way(rx_delta, tx_delta)
                if direction:
                    con.execute(
                        """
                        INSERT INTO one_way_outliers(scan_id,ip,interface,rx_delta,tx_delta,direction,severity,note)
                        VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (
                            scan_id,
                            device["ip"],
                            interface.get("name"),
                            rx_delta,
                            tx_delta,
                            direction,
                            severity,
                            "running-ether one-way byte delta vs previous scan",
                        ),
                    )

        for neighbor in device.get("neighbors", []):
            con.execute(
                """
                INSERT INTO neighbors(scan_id,ip,interface,neighbor_address,neighbor_identity,platform,version)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    scan_id,
                    device["ip"],
                    neighbor.get("interface"),
                    neighbor.get("address"),
                    neighbor.get("identity"),
                    neighbor.get("platform"),
                    neighbor.get("version"),
                ),
            )

        for bridge_port in device.get("bridge_ports", []):
            con.execute(
                """
                INSERT INTO bridge_ports(scan_id,ip,interface,pvid,ingress_filtering,frame_types,trusted,hw)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    scan_id,
                    device["ip"],
                    bridge_port.get("interface"),
                    bridge_port.get("pvid"),
                    1 if bridge_port.get("ingress_filtering") else 0,
                    bridge_port.get("frame_types"),
                    1 if bridge_port.get("trusted") else 0,
                    1 if bridge_port.get("hw") else 0,
                ),
            )

        for bridge_vlan in device.get("bridge_vlans", []):
            con.execute(
                """
                INSERT INTO bridge_vlans(scan_id,ip,vlan_ids,tagged,untagged)
                VALUES(?,?,?,?,?)
                """,
                (scan_id, device["ip"], bridge_vlan.get("vlan_ids"), bridge_vlan.get("tagged"), bridge_vlan.get("untagged")),
            )

        for bridge_host in device.get("bridge_hosts", []):
            vid = bridge_host.get("vid")
            if host_vid is not None and vid not in (host_vid, None):
                continue
            con.execute(
                """
                INSERT INTO bridge_hosts(scan_id,ip,mac,on_interface,vid,local,external)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    scan_id,
                    device["ip"],
                    bridge_host.get("mac"),
                    bridge_host.get("on_interface"),
                    vid,
                    1 if bridge_host.get("local") else 0,
                    1 if bridge_host.get("external") else 0,
                ),
            )

        for ppp_session in device.get("ppp_active", []):
            con.execute(
                """
                INSERT INTO router_ppp_active(scan_id,router_ip,name,service,caller_id,address,uptime)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    scan_id,
                    device["ip"],
                    ppp_session.get("name"),
                    ppp_session.get("service"),
                    ppp_session.get("caller_id"),
                    ppp_session.get("address"),
                    ppp_session.get("uptime"),
                ),
            )

        for arp_row in device.get("arp", []):
            con.execute(
                """
                INSERT INTO router_arp(scan_id,router_ip,address,mac,interface,dynamic)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    scan_id,
                    device["ip"],
                    arp_row.get("address"),
                    arp_row.get("mac"),
                    arp_row.get("interface"),
                    1 if arp_row.get("dynamic") else 0,
                ),
            )


def purge_old_scans(con: sqlite3.Connection, keep_scans: int) -> None:
    rows = con.execute("SELECT id FROM scans ORDER BY id DESC").fetchall()
    old_ids = [row[0] for row in rows[keep_scans:]]
    if old_ids:
        con.executemany("DELETE FROM scans WHERE id=?", [(scan_id,) for scan_id in old_ids])


def run_scan(args) -> None:
    user, password = load_creds(args.env)
    subnet = ipaddress.ip_network(args.subnet, strict=False)
    ips = [str(ip) for ip in subnet.hosts()]

    con = db_connect(args.db)
    init_db(con)

    started = utc_now()
    cur = con.execute(
        "INSERT INTO scans(started_at,subnet,hosts_tested,notes) VALUES(?,?,?,?)",
        (started, args.subnet, len(ips), "read-only api discovery"),
    )
    scan_id = cur.lastrowid
    con.commit()

    prev_id = latest_scan_id(con)
    if prev_id == scan_id:
        row = con.execute("SELECT id FROM scans WHERE id < ? ORDER BY id DESC LIMIT 1", (scan_id,)).fetchone()
        prev_id = row[0] if row else None
    prev_counters = previous_interface_counters(con, prev_id)

    open_ips: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(tcp_open, ip, 8728, args.tcp_timeout): ip for ip in ips}
        for future in as_completed(futures):
            ip = futures[future]
            if future.result():
                open_ips.append(ip)

    devices: list[dict] = []
    failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(gather_device, ip, user, password, args.api_timeout): ip for ip in sorted(open_ips)}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                devices.append(future.result())
            except Exception as exc:
                failures.append((ip, str(exc)))

    host_vid = None if args.host_vid == -1 else args.host_vid
    save_scan(con, scan_id, devices, prev_counters, host_vid)
    con.execute("UPDATE scans SET finished_at=?, api_reachable=? WHERE id=?", (utc_now(), len(devices), scan_id))
    purge_old_scans(con, args.keep_scans)
    con.commit()

    summary = {
        "scan_id": scan_id,
        "subnet": args.subnet,
        "hosts_tested": len(ips),
        "tcp_8728_open": len(open_ips),
        "api_reachable": len(devices),
        "failures": len(failures),
        "router_like": sum(1 for device in devices if not device.get("is_crs")),
        "crs_switches": sum(1 for device in devices if device.get("is_crs")),
        "one_way_outliers": con.execute("SELECT COUNT(*) FROM one_way_outliers WHERE scan_id=?", (scan_id,)).fetchone()[0],
    }
    print(json.dumps(summary, indent=2))
    if failures:
        print("recent_failures:")
        for ip, error in failures[:20]:
            print(f"  {ip}: {error}")


def report_latest(args) -> None:
    con = db_connect(args.db)
    init_db(con)
    row = con.execute("SELECT id,started_at,finished_at,subnet,hosts_tested,api_reachable FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        print("No scans in database.")
        return
    scan_id = row[0]
    print(f"latest_scan_id={scan_id} started={row[1]} finished={row[2]} subnet={row[3]}")
    print(f"hosts_tested={row[4]} api_reachable={row[5]}")

    dev = con.execute(
        "SELECT COUNT(*), SUM(is_crs), SUM(CASE WHEN is_crs=0 THEN 1 ELSE 0 END) FROM devices WHERE scan_id=?",
        (scan_id,),
    ).fetchone()
    print(f"devices_total={dev[0]} crs_switches={dev[1] or 0} non_crs={dev[2] or 0}")

    print("\nLikely Uplinks By Device:")
    rows = con.execute(
        """
        SELECT d.ip, d.identity, n.interface, n.neighbor_identity, n.neighbor_address
        FROM devices d
        JOIN neighbors n ON n.scan_id=d.scan_id AND n.ip=d.ip
        WHERE d.scan_id=?
          AND n.neighbor_identity IS NOT NULL
          AND n.neighbor_identity<>''
          AND (
            lower(coalesce(n.interface,'')) LIKE 'sfp%'
            OR lower(coalesce(n.interface,'')) LIKE 'roof%'
            OR lower(coalesce(n.interface,'')) LIKE 'wlan%'
            OR lower(coalesce(n.interface,'')) LIKE 'ether24%'
          )
        ORDER BY d.ip, n.interface, n.neighbor_identity
        """,
        (scan_id,),
    ).fetchall()
    by_dev: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for ip, identity, interface, neighbor_identity, neighbor_address in rows:
        by_dev[(ip, identity or "?")].append((interface or "?", neighbor_identity or "?", neighbor_address or "n/a"))
    shown = 0
    for (ip, identity), links in by_dev.items():
        print(f"{ip} {identity}")
        dedup = []
        seen = set()
        for link in links:
            if link in seen:
                continue
            seen.add(link)
            dedup.append(link)
        for interface, neighbor_identity, neighbor_address in dedup[:4]:
            print(f"  {interface} -> {neighbor_identity} ({neighbor_address})")
        if len(dedup) > 4:
            print(f"  ... +{len(dedup) - 4} more")
        shown += 1
        if shown >= args.limit:
            break

    print("\nOne-way Outliers (latest):")
    out_rows = con.execute(
        """
        SELECT o.ip, d.identity, o.interface, o.direction, o.severity, o.rx_delta, o.tx_delta
        FROM one_way_outliers o
        LEFT JOIN devices d ON d.scan_id=o.scan_id AND d.ip=o.ip
        WHERE o.scan_id=?
        ORDER BY CASE o.severity WHEN 'high' THEN 0 ELSE 1 END, o.ip, o.interface
        LIMIT ?
        """,
        (scan_id, args.limit),
    ).fetchall()
    if not out_rows:
        print("none")
        return
    for row in out_rows:
        print(f"{row[0]} {row[1] or '?'} {row[2]} {row[3]} {row[4]} rx_delta={row[5]} tx_delta={row[6]}")


def path_lookup(args) -> None:
    con = db_connect(args.db)
    init_db(con)
    row = con.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        raise RuntimeError("No scans found")
    scan_id = row[0]
    mac = mac_norm(args.mac)
    if not mac:
        raise RuntimeError("Invalid MAC format")

    query = """
      SELECT b.ip, d.identity, b.on_interface, b.vid, b.local, b.external
      FROM bridge_hosts b
      LEFT JOIN devices d ON d.scan_id=b.scan_id AND d.ip=b.ip
      WHERE b.scan_id=? AND b.mac=?
    """
    params: list = [scan_id, mac]
    if args.vid is not None:
        query += " AND b.vid=?"
        params.append(args.vid)
    query += " ORDER BY b.ip, b.on_interface"
    rows = con.execute(query, tuple(params)).fetchall()

    print(f"scan_id={scan_id} mac={mac} matches={len(rows)}")
    for row in rows:
        print(f"{row[0]} {row[1] or '?'} {row[2] or '?'} vid={row[3]} local={bool(row[4])} external={bool(row[5])}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jake2-local MikroTik network mapper with SQLite backend")
    parser.add_argument("--db", default="data/network_map.db", help="SQLite database path")
    parser.add_argument("--env", default="config/.env", help="Credentials env file path")

    sub = parser.add_subparsers(dest="cmd", required=True)

    scan_parser = sub.add_parser("scan", help="Run full subnet discovery + snapshot")
    scan_parser.add_argument("--subnet", default="192.168.44.0/24")
    scan_parser.add_argument("--workers", type=int, default=48)
    scan_parser.add_argument("--tcp-timeout", type=float, default=0.7)
    scan_parser.add_argument("--api-timeout", type=float, default=3.0)
    scan_parser.add_argument("--keep-scans", type=int, default=20)
    scan_parser.add_argument(
        "--host-vid",
        type=int,
        default=20,
        help="Store bridge host rows only for this VLAN ID (and null VID). Use -1 to keep all.",
    )

    report_parser = sub.add_parser("report", help="Report latest snapshot and one-way outliers")
    report_parser.add_argument("--limit", type=int, default=120)

    path_parser = sub.add_parser("path", help="Find where a MAC is learned in latest snapshot")
    path_parser.add_argument("--mac", required=True, help="MAC address, e.g. E8:DA:00:14:E9:B3")
    path_parser.add_argument("--vid", type=int, default=None, help="Optional VLAN ID filter")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "scan":
        run_scan(args)
    elif args.cmd == "report":
        report_latest(args)
    elif args.cmd == "path":
        path_lookup(args)


if __name__ == "__main__":
    main()
