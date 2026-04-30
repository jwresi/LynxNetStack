# Tools Code Snippets

This file contains implementation snippets for the major tools in this project so they can be reused in another codebase.

## 1) Credentials Loader (`.env`)
```python
from dotenv import dotenv_values

def load_creds(env_path):
    cfg = dotenv_values(env_path)
    user = cfg.get("username")
    pw = cfg.get("password")
    if not user or not pw:
        raise RuntimeError(f"Missing username/password in {env_path}")
    return user, pw
```

## 2) MikroTik API Connect + Identity Read
```python
from librouteros import connect

def get_identity(ip, user, pw, timeout=8):
    api = connect(host=ip, username=user, password=pw, port=8728, timeout=timeout)
    for r in api.path("system", "identity").select("name"):
        n = r.get("name")
        return n.decode(errors="ignore") if isinstance(n, bytes) else n
    return None
```

## 3) Subnet TCP 8728 Discovery
```python
import socket
import ipaddress

def tcp_open(ip, port=8728, timeout=0.7):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def discover_api_hosts(subnet_cidr):
    net = ipaddress.ip_network(subnet_cidr, strict=False)
    return [str(ip) for ip in net.hosts() if tcp_open(str(ip), 8728, 0.7)]
```

## 4) Full Device Gather (read-only)
```python
def b2s(v):
    return v.decode(errors="ignore") if isinstance(v, bytes) else v

def gather_device(ip, user, pw, timeout=3):
    api = connect(host=ip, username=user, password=pw, port=8728, timeout=timeout)

    ident = None
    for r in api.path("system", "identity").select("name"):
        ident = b2s(r.get("name"))
        break

    resource = {}
    for r in api.path("system", "resource").select("board-name", "version", "platform"):
        resource = {k: b2s(v) for k, v in r.items()}
        break

    interfaces = []
    for r in api.path("interface").select("name", "type", "running", "disabled", "rx-byte", "tx-byte"):
        interfaces.append({
            "name": b2s(r.get("name")),
            "type": b2s(r.get("type")),
            "running": str(r.get("running")).lower() in ("true", "yes", "1", "on"),
            "disabled": str(r.get("disabled")).lower() in ("true", "yes", "1", "on"),
            "rx_byte": int(r.get("rx-byte") or 0),
            "tx_byte": int(r.get("tx-byte") or 0),
        })

    neighbors = []
    for r in api.path("ip", "neighbor").select("address", "identity", "interface"):
        neighbors.append({
            "address": b2s(r.get("address")),
            "identity": b2s(r.get("identity")),
            "interface": b2s(r.get("interface")),
        })

    return {
        "ip": ip,
        "identity": ident,
        "board_name": resource.get("board-name"),
        "version": resource.get("version"),
        "model": resource.get("platform"),
        "is_crs": bool((resource.get("board-name") or "").upper().startswith("CRS")),
        "interfaces": interfaces,
        "neighbors": neighbors,
    }
```

## 5) SQLite Schema Init (core tables)
```python
import sqlite3

def db_connect(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con

def init_db(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS scans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      started_at TEXT NOT NULL,
      finished_at TEXT,
      subnet TEXT NOT NULL,
      hosts_tested INTEGER NOT NULL DEFAULT 0,
      api_reachable INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS devices (
      scan_id INTEGER NOT NULL,
      ip TEXT NOT NULL,
      identity TEXT,
      board_name TEXT,
      version TEXT,
      is_crs INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (scan_id, ip)
    );
    CREATE TABLE IF NOT EXISTS interfaces (
      scan_id INTEGER NOT NULL,
      ip TEXT NOT NULL,
      name TEXT NOT NULL,
      type TEXT,
      running INTEGER,
      disabled INTEGER,
      rx_byte INTEGER,
      tx_byte INTEGER,
      PRIMARY KEY (scan_id, ip, name)
    );
    CREATE TABLE IF NOT EXISTS neighbors (
      scan_id INTEGER NOT NULL,
      ip TEXT NOT NULL,
      interface TEXT,
      neighbor_identity TEXT,
      neighbor_address TEXT
    );
    CREATE TABLE IF NOT EXISTS bridge_hosts (
      scan_id INTEGER NOT NULL,
      ip TEXT NOT NULL,
      mac TEXT,
      on_interface TEXT,
      vid INTEGER,
      local INTEGER,
      external INTEGER
    );
    CREATE TABLE IF NOT EXISTS one_way_outliers (
      scan_id INTEGER NOT NULL,
      ip TEXT NOT NULL,
      interface TEXT NOT NULL,
      rx_delta INTEGER NOT NULL,
      tx_delta INTEGER NOT NULL,
      direction TEXT NOT NULL,
      severity TEXT NOT NULL,
      note TEXT
    );
    """)
    con.commit()
```

## 6) One-way Outlier Detector
```python
def classify_one_way(rx_delta, tx_delta):
    low = 64 * 1024
    mid = 256 * 1024
    if rx_delta == 0 and tx_delta >= low:
        return "tx_only", ("high" if tx_delta >= mid else "medium")
    if tx_delta == 0 and rx_delta >= low:
        return "rx_only", ("high" if rx_delta >= mid else "medium")
    return None, None
```

## 7) OUI Vendor Grouping
```python
def norm_mac(v):
    if not v:
        return None
    s = str(v).strip().lower().replace("-", ":")
    p = s.split(":")
    if len(p) == 6 and all(len(x) == 2 for x in p):
        return s
    if len(s) == 12 and all(c in "0123456789abcdef" for c in s):
        return ":".join(s[i:i+2] for i in range(0, 12, 2))
    return None

def mac_vendor_group(mac):
    m = norm_mac(mac)
    if not m:
        return "unknown"
    if m.startswith("e8:da:00:"):
        return "vilo"
    if m.startswith(("30:68:93:", "60:83:e7:", "7c:f1:7e:", "d8:44:89:", "dc:62:79:", "e4:fa:c4:")):
        return "tplink"
    return "unknown"
```

## 8) Live MAC Scan API Function
```python
def live_mac_scan(env_path, ip, interface, seconds=3, limit=250):
    user, pw = load_creds(env_path)
    api = connect(host=ip, username=user, password=pw, port=8728, timeout=8)

    identity = None
    for r in api.path("system", "identity").select("name"):
        identity = r.get("name")
        break
    if isinstance(identity, bytes):
        identity = identity.decode(errors="ignore")

    sec = max(1, min(int(seconds), 10))
    rows = []
    for i, r in enumerate(api.rawCmd("/tool/mac-scan", f"=interface={interface}", f"=duration={sec}s")):
        rows.append({
            "mac-address": r.get("mac-address"),
            "address": r.get("address"),
            "age": r.get("age"),
            "interface": interface,
        })
        if i >= limit:
            break

    uniq = sorted({(x.get("mac-address") or "").lower() for x in rows if x.get("mac-address")})
    return {
        "ip": ip,
        "identity": identity,
        "interface": interface,
        "seconds": sec,
        "count": len(rows),
        "unique_macs": len(uniq),
        "macs": uniq[:limit],
        "sample": rows[:80],
    }
```

## 9) Live Sniffer API Function (`protocol=all`, optional MAC filter)
```python
def _s(v):
    return v.decode(errors="ignore") if isinstance(v, bytes) else v

def live_sniffer(env_path, ip, interface, protocol="pppoe-discovery", seconds=3, limit=250, mac=None):
    user, pw = load_creds(env_path)
    api = connect(host=ip, username=user, password=pw, port=8728, timeout=8)

    sec = max(1, min(int(seconds), 10))
    proto = (protocol or "pppoe-discovery").strip().lower()
    mac_filter = norm_mac(mac) if mac else None

    try:
        list(api.rawCmd("/tool/sniffer/stop"))
    except Exception:
        pass

    set_args = ["/tool/sniffer/set", f"=filter-interface={interface}", "=filter-direction=any"]
    if proto not in ("all", "any", "*", ""):
        set_args.append(f"=filter-mac-protocol={proto}")
    if mac_filter:
        set_args.append(f"=filter-mac-address={mac_filter}")
    list(api.rawCmd(*set_args))

    rows, dir_counts, proto_counts = [], {}, {}
    for i, r in enumerate(api.rawCmd("/tool/sniffer/quick", f"=duration={sec}s")):
        d = str(_s(r.get("dir")) or "?")
        dir_counts[d] = dir_counts.get(d, 0) + 1
        rp = str(_s(r.get("protocol")) or "?").lower()
        proto_counts[rp] = proto_counts.get(rp, 0) + 1
        rows.append({
            "interface": _s(r.get("interface")),
            "dir": _s(r.get("dir")),
            "src-mac": _s(r.get("src-mac")),
            "dst-mac": _s(r.get("dst-mac")),
            "protocol": _s(r.get("protocol")),
            "vlan": _s(r.get("vlan")),
            "size": _s(r.get("size")),
            "src-address": _s(r.get("src-address")),
            "dst-address": _s(r.get("dst-address")),
        })
        if i >= limit:
            break

    try:
        list(api.rawCmd("/tool/sniffer/stop"))
    except Exception:
        pass

    return {
        "ip": ip,
        "interface": interface,
        "protocol": proto,
        "mac_filter": mac_filter,
        "seconds": sec,
        "count": len(rows),
        "dir_counts": dir_counts,
        "protocol_counts": proto_counts,
        "sample": rows[:120],
    }
```

## 10) MAC Chain Builder (path tracing)
```python
def build_mac_chain(con, scan_id, mac, selected_ip=None):
    rows = [dict(r) for r in con.execute(
        """
        SELECT b.ip,d.identity,b.on_interface,b.vid,b.local,b.external
        FROM bridge_hosts b
        LEFT JOIN devices d ON d.scan_id=b.scan_id AND d.ip=b.ip
        WHERE b.scan_id=? AND b.mac=?
        ORDER BY b.ip,b.on_interface
        """,
        (scan_id, mac),
    )]
    if not rows:
        return {"mac": mac, "chain": [], "rows": []}

    dev_rows = {}
    for r in rows:
        dev_rows.setdefault(r["ip"], []).append(r)

    # pick edge-like start if caller did not force one
    cur = selected_ip if selected_ip in dev_rows else sorted(dev_rows.keys())[0]

    chain, visited = [], set()
    while cur and cur not in visited:
        visited.add(cur)
        best = sorted(dev_rows[cur], key=lambda r: (0 if (r.get("on_interface") or "").startswith("ether") else 1))[0]
        chain.append({
            "ip": cur,
            "identity": best.get("identity") or cur,
            "mac": mac,
            "on_interface": best.get("on_interface"),
            "vid": best.get("vid"),
        })
        # This minimal snippet stops here; production version follows neighbor graph upstream.
        break

    return {"mac": mac, "chain": chain, "rows": rows}
```

## 11) CPE Behavior Classifier
```python
def classify_cpe_behavior(sniff_out):
    sample = sniff_out.get("sample") or []
    proto_counts = sniff_out.get("protocol_counts") or {}
    srcs = [str((r or {}).get("src-address") or "") for r in sample]

    if any(str(k).startswith("pppoe") for k in proto_counts.keys()):
        return "pppoe"
    if any(s.endswith(":68 (bootpc)") for s in srcs):
        return "dhcp_discovering"
    if ("ip:igmp" in proto_counts) and any(s.startswith("169.254.") for s in srcs):
        return "igmp_linklocal_ap_like"
    if int(sniff_out.get("count") or 0) == 0:
        return "silent"
    return "other"
```

## 12) CPE Watch Worker (long-running behavior scan)
```python
import time
from collections import Counter

def run_cpe_watch(env_path, targets, duration_minutes=30, sample_seconds=1):
    end_at = time.time() + max(1, int(duration_minutes * 60))

    by_key = {}
    for t in targets:
        key = (t["mac"], t["ip"], t["iface"])
        by_key[key] = {
            **t,
            "samples": 0,
            "total_packets": 0,
            "class_counts": Counter(),
            "protocol_counts": Counter(),
        }

    while time.time() < end_at:
        for t in targets:
            if time.time() >= end_at:
                break
            rec = by_key[(t["mac"], t["ip"], t["iface"])]
            out = live_sniffer(
                env_path,
                t["ip"],
                t["iface"],
                protocol="all",
                seconds=max(1, min(int(sample_seconds), 3)),
                limit=120,
                mac=t["mac"],
            )
            cls = classify_cpe_behavior(out)
            rec["samples"] += 1
            rec["total_packets"] += int(out.get("count") or 0)
            rec["class_counts"][cls] += 1
            for p, c in (out.get("protocol_counts") or {}).items():
                rec["protocol_counts"][str(p)] += int(c)

    rows = []
    for rec in by_key.values():
        dom = rec["class_counts"].most_common(1)[0][0] if rec["class_counts"] else "silent"
        rows.append({
            **rec,
            "dominant_class": dom,
            "class_counts": dict(rec["class_counts"]),
            "protocol_counts": dict(rec["protocol_counts"]),
        })
    return rows
```

## 13) Minimal HTTP API Route Pattern
```python
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json

class AppHandler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)

        if p.path == "/api/live/sniffer":
            ip = (q.get("ip") or [None])[0]
            interface = (q.get("interface") or [None])[0]
            protocol = (q.get("protocol") or ["all"])[0]
            mac = (q.get("mac") or [None])[0]
            if not ip or not interface:
                return self._json({"error": "missing ip/interface"}, 400)
            try:
                out = live_sniffer(".env", ip, interface, protocol, 3, 250, mac)
            except Exception as e:
                return self._json({"error": str(e)}, 500)
            return self._json(out)

        return self._json({"error": "not found"}, 404)
```

## 14) Frontend: Start CPE Watch + Poll Status
```js
async function jget(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

async function startCpeWatch() {
  const start = await jget('/api/cpe-watch/start', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      duration_minutes: 30,
      sample_seconds: 1,
      scope: 'all_oui',
    }),
  });

  const jobId = start.job_id;
  let status;
  do {
    await new Promise((r) => setTimeout(r, 3000));
    status = await jget(`/api/cpe-watch/status?id=${encodeURIComponent(jobId)}`);
    console.log('CPE watch status:', status);
  } while (status.status === 'running');

  const latest = await jget('/api/cpe-watch/latest?non_silent=1&limit=300');
  console.log('Latest CPE watch:', latest);
}
```

## 15) Frontend: Live Sniffer Call
```js
async function runLiveSniffer(ip, iface, protocol = 'all', mac = '') {
  const params = new URLSearchParams({ ip, interface: iface, protocol, seconds: '3' });
  if (mac) params.set('mac', mac);
  const data = await jget(`/api/live/sniffer?${params.toString()}`);
  return data;
}
```

## 16) Frontend: Live MAC Scan Call
```js
async function runLiveMacScan(ip, iface, seconds = 3) {
  const params = new URLSearchParams({
    ip,
    interface: iface,
    seconds: String(seconds),
  });
  const data = await jget(`/api/live/mac-scan?${params.toString()}`);
  return data;
}
```

## 17) TSV Writer for Sharing Results
```python
import csv, json

def write_rows_tsv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["name","mac","ip","iface","dominant_class","total_packets","class_counts","protocol_counts"])
        for r in rows:
            w.writerow([
                r.get("name", ""),
                r.get("mac", ""),
                r.get("ip", ""),
                r.get("iface", ""),
                r.get("dominant_class", ""),
                r.get("total_packets", 0),
                json.dumps(r.get("class_counts", {}), separators=(",",":")),
                json.dumps(r.get("protocol_counts", {}), separators=(",",":")),
            ])
```

## 18) Safe Read-Only Guardrails (recommended wrapper)
```python
READ_ONLY_ENDPOINTS = {
    # examples
    ("system", "identity"),
    ("system", "resource"),
    ("interface",),
    ("ip", "neighbor"),
    ("interface", "bridge", "host"),
    ("tool", "mac-scan"),
    ("tool", "sniffer"),
}

# Keep write/modify commands out of reusable modules.
# In production, enforce an allowlist around all RouterOS API calls.
```

---

## Notes For Reuse
- These snippets are extracted from working code in this project and trimmed for portability.
- If your coworker ports them to another stack, keep:
  - credential loading
  - read-only API patterns
  - timeout handling
  - job status persistence for long-running scans
- For high-volume scans, use worker queues and per-device rate limiting.
