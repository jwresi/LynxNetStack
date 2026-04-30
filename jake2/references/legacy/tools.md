# Tools Inventory

This project is a read-only MikroTik troubleshooting toolkit for `192.168.44.0/24`.

## Core Tools

### 1) Network Scanner (`network_mapper.py scan`)
- What it does:
  - Scans a subnet for MikroTik API (`tcp/8728`) reachability.
  - Pulls device inventory, interfaces, neighbors, bridge tables, PPP active, and ARP.
  - Detects one-way traffic outliers by comparing interface byte deltas against the previous scan.
- How it works:
  - Uses `librouteros` read operations only (`print/select` style paths).
  - Writes normalized snapshot data into `network_map.db`.
  - Supports concurrent discovery with worker threads.
- Key options:
  - `--subnet` target subnet (default `192.168.44.0/24`)
  - `--workers` concurrency
  - `--host-vid` bridge host VLAN filter (`20` default, `-1` = all)
  - `--keep-scans` retention

### 2) Snapshot Reporter (`network_mapper.py report`)
- What it does:
  - Prints summary metrics from the latest scan.
  - Shows CRS counts, outliers, and key health indicators.
- How it works:
  - Reads latest rows from `network_map.db` and formats console output.

### 3) Graph Exporter (`network_mapper.py export-graph`)
- What it does:
  - Exports topology node/edge data to JSON (ex: `network_graph_latest.json`).
- How it works:
  - Serializes latest device + neighbor snapshot into graph-friendly structure.

## Web/API Server

### 4) Web UI Server (`webui_server.py`)
- What it does:
  - Serves frontend (`webui/`) and REST APIs for scan data + live read-only tools.
- How it works:
  - `ThreadingHTTPServer` + SQLite queries.
  - Uses `.env` (`username`, `password`) for live API probes.

## Data + Topology APIs

### 5) Latest Scan Summary (`GET /api/latest`)
- What it does: Returns current scan metadata + counts.
- How it works: Aggregates from `scans`, `devices`, `one_way_outliers`.

### 6) Device Inventory (`GET /api/devices`)
- What it does: Lists scanned devices with outlier counts.
- How it works: Joins `devices` with grouped outlier totals.

### 7) Device Detail (`GET /api/device?ip=...`)
- What it does: Returns full per-device detail.
- How it works: Reads device row + interfaces + neighbors + bridge hosts + outliers.

### 8) Outlier List (`GET /api/outliers`)
- What it does: Lists `tx_only/rx_only` interfaces by severity.
- How it works: Query against `one_way_outliers` + device identity.

### 9) Topology Graph (`GET /api/graph`)
- What it does: Returns graph nodes/edges for the map page.
- How it works: Uses latest `devices` + `neighbors` and dedupes edges.

## MAC Path/Trace Tools

### 10) MAC Path Rows (`GET /api/mac-path?mac=...`)
- What it does: Raw bridge-host sightings for a MAC.
- How it works: Reads matching `bridge_hosts` (+ optional VLAN filter).

### 11) MAC Chain Builder (`GET /api/mac-chain?mac=...&device_ip=...`)
- What it does:
  - Builds likely hop chain across switches for a MAC.
  - Marks hop health using outlier context.
- How it works:
  - Starts from likely edge switch, follows neighbor relationships.
  - Correlates with outlier table to set `hop_ok/hop_reason`.

## Live Read-Only Probe Tools

### 12) Live MAC Scan (`GET /api/live/mac-scan`)
- What it does:
  - Runs short `/tool/mac-scan` on selected device+interface.
  - Returns seen MACs and samples.
- How it works:
  - Connects to selected switch via MikroTik API.
  - Duration-limited capture.

### 13) MAC Enrichment (part of Live MAC Scan)
- What it does:
  - Enriches scanned MACs with vendor grouping and correlations.
- How it works:
  - Vendor grouping via OUI (Vilo, TP-Link/Aginet, unknown).
  - Correlates to latest `router_ppp_active`, `router_arp`, `bridge_hosts`.

### 14) Port CPE Candidate Extractor (part of Live MAC Scan)
- What it does:
  - Identifies probable CPE MACs for selected switch port.
- How it works:
  - Uses `bridge_hosts` locality flags (`external` + not `local`) and matching correlations.

### 15) Live Sniffer (`GET /api/live/sniffer`)
- What it does:
  - Runs short `/tool/sniffer/quick` on selected device+interface.
  - Supports protocol filter (`pppoe-discovery`, `pppoe`, `arp`, `all`, etc.) and optional `mac` filter.
- How it works:
  - Stops any prior sniffer state, sets filters, runs bounded quick capture.
  - Returns direction counts, protocol counts, and sample packet metadata (MACs, VLAN, src/dst address fields).

## Long-Window CPE Behavior Tools

### 16) CPE Watch Job Start (`POST /api/cpe-watch/start`)
- What it does:
  - Starts long-duration behavior scan over target CPE set.
- How it works:
  - Background thread loops over target MAC/port pairs, repeatedly running short live sniffer reads.
  - Classifies each sample (`pppoe`, `dhcp_discovering`, `igmp_linklocal_ap_like`, `silent`, `other`).
- Payload:
  - `duration_minutes` (1..180)
  - `sample_seconds` (1..3)
  - `scope` (`all_oui` or `ppp_active`)

### 17) CPE Watch Job Status (`GET /api/cpe-watch/status?id=...`)
- What it does:
  - Returns live progress for CPE watch jobs.
- How it works:
  - Reads in-memory job state (`targets_total`, `requests_done`, `rounds`, progress text).

### 18) CPE Watch Latest Results (`GET /api/cpe-watch/latest`)
- What it does:
  - Returns latest completed CPE watch result set.
- How it works:
  - Loads `cpe_watch_latest.json` and returns rows (all or non-silent slice).
- Query params:
  - `non_silent=1|0`
  - `limit`

### 19) CPE Watch TSV Outputs
- What it does:
  - Persists full and non-silent result tables.
- Files:
  - `cpe_behavior_30m.tsv`
  - `cpe_behavior_30m_non_silent.tsv`
  - `cpe_watch_latest.json`

## Scan Job Orchestration

### 20) Full Network Scan Start (`POST /api/scan`)
- What it does: Starts a new full subnet scan job.
- How it works: Launches `network_mapper.py scan` in background subprocess.

### 21) Full Network Scan Status (`GET /api/scan-status?id=...`)
- What it does: Returns running/done/error state for scan job.
- How it works: Reads in-memory job state + captured stdout/stderr tail.

## Frontend Tool Pages (`webui/`)

### 22) Overview
- Uses `/api/latest`, `/api/scan`, `/api/scan-status`.

### 23) Devices
- Uses `/api/devices`, `/api/device`.

### 24) Path Trace
- Uses `/api/mac-chain` and renders hop chain with health arrows.

### 25) Network Map
- Uses `/api/graph` and overlays highlighted MAC path using `/api/mac-chain`.
- Building-grouped deterministic layout for readability.

### 26) Live Tools
- Live MAC Scan UI: `/api/live/mac-scan`
- Live Sniffer UI: `/api/live/sniffer`
- Device/port selector sync between both tools.

### 27) CPE Watch
- Start/poll/view long behavior scans:
  - `/api/cpe-watch/start`
  - `/api/cpe-watch/status`
  - `/api/cpe-watch/latest`

### 28) Outliers
- Uses `/api/outliers` for one-way interface anomaly list.

## Shared Mechanisms

### 29) OUI/Vendor Grouping
- Vilo: `E8:DA:00`
- TP-Link/Aginet groups: `30:68:93`, `60:83:E7`, `7C:F1:7E`, `D8:44:89`, `DC:62:79`, `E4:FA:C4`
- Used in enrichment and CPE behavior workflows.

### 30) Read-Only Safety Model
- No config writes in mapper/live tools by default.
- Tools rely on RouterOS read paths and short-lived sniffer/mac-scan probes.
- Any change operations are separate/manual and not part of these automated tools.
