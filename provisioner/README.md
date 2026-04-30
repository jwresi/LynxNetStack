# RouterOS NetInstaller Provisioner

A Dockerized provisioning system for MikroTik devices with a React frontend, Flask backend, and a TFTP sidecar. Supports static IP provisioning flows with optional DHCP listener.

Templates
- Place RouterOS templates under `configs/templates/` (served by the backend).
- The frontend lists these and renders with variables before provisioning.
- Included model-specific templates:
  - `crs326_24g.tmpl` (24-port non‑PoE)
  - `crs418_16g_8poe.tmpl` (16-port with 8 PoE)
  - `crs354_48g.tmpl` (48-port non‑PoE)
  - `crs354_48p.tmpl` (48-port all‑PoE)
- Variables commonly used: `hostname`, `ip`, `mac`, `model`, `mgmtVlan`, `cxVlan`, `secVlan`, `gateway`, `subnet`, `baseNetwork`, `trunkIn`, `trunkOut`, `poePorts`, `now`.

## Features
- Two-page UI: `Provision` for techs, `Setup` for admins
- Batch provisioning with CSV validation, pause/cancel/retry, per-device progress + verify (ping/SSH)
- Port map overlay: VLAN role coloring with PoE capability tag (bolt + label)
- Click a port tile to add a custom label (e.g., “Unit 202”); provisioning appends interface rename commands so RouterOS reflects your labels.
- Sample CSV download; “Show incomplete only” filter; Copy Renames helper
- Default-hardened switch configs (CRS3xx):
  - BPDU-Guard on customer ports
  - Loop-Protect on customer Ethernet ports
  - PoE disabled by default on PoE-capable ports
  - Drop DHCP on customer access ports (CUSTOMER list); MGMT/SEC unaffected
- Templates panel (Jinja2) with live preview; Auto-Generate fallback
- Preflight checks + host vs container NIC clarity
- Audit log with export
- MNDP enrichment: backend listens on UDP/5678 and enriches discovery with device `identity` and `model` when RouterOS is running

## Requirements
- Docker Desktop (macOS/Windows) or Docker + Compose (Linux)
- RouterOS package placed at `routeros/routeros.npk` (symlink ok)

## Quick Start (Dev/Local)
- Copy env template: `cp .env.example .env` (or run macOS bootstrap: `./setup.sh`)
- Start services: `make up`
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:5001/api/status`
- Logs: `make logs` — Stop: `make down`

## Ubuntu One‑Command Installer
- Run the guided installer (requires sudo):
  - sudo ./scripts/ubuntu-install.sh
- The wizard will:
  - Install dependencies (python3-venv, tftpd-hpa, jq)
  - Copy the repo to /opt/provisioner and create a virtualenv
  - Create /etc/provisioner.env with your selected interface, CIDR, and DHCP toggle
  - Install and start systemd unit provisioner-backend
  - Configure tftpd-hpa to serve /app/routeros
- After install:
  - Place RouterOS package at /opt/provisioner/routeros/routeros.npk
  - Check: curl -s http://127.0.0.1:5001/api/preflight | jq

## Debian Package
- Build the .deb locally:
  - `chmod +x scripts/build-deb.sh && ./scripts/build-deb.sh 1.0.0`
  - Output: `dist/provisioner_1.0.0_all.deb`
- Install on a host:
  - `sudo dpkg -i dist/provisioner_1.0.0_all.deb`
  - This will:
    - Install files under `/opt/provisioner`
    - Create `/app -> /opt/provisioner` symlink
    - Create `/etc/provisioner.env` (auto-detected NIC/CIDR; edit as needed)
    - Configure and restart `tftpd-hpa` to serve `/app/routeros`
    - Create a Python venv and install backend requirements
    - Install and enable `provisioner-backend.service`
- After install:
  - Put `routeros.npk` in `/opt/provisioner/routeros/`
  - `sudo systemctl restart provisioner-backend`
  - Verify: `curl -s http://127.0.0.1:5001/api/preflight | jq`
- Optional helper:
  - `provisioner-setup` runs the interactive wizard again (requires sudo)

## CI Release
- GitHub Actions builds the .deb on tag pushes and on manual dispatch:
  - Tag release: push a tag like `v1.0.0` to trigger build and attach the .deb to the GitHub Release.
  - Manual run: use the Actions tab, run “Build and Release .deb” and supply a `version`.
- Workflow file: `.github/workflows/deb-release.yml`

Notes
- DHCP listener should only be enabled on an isolated provisioning VLAN with no other DHCP servers.
- The backend writes configs under /app/configs (symlink to /opt/provisioner/configs).
- To change settings later, edit /etc/provisioner.env and systemctl restart provisioner-backend.
 - Optional (SSH import): set `ROUTEROS_SSH_USER` and `ROUTEROS_SSH_PASS` to enable post‑boot config upload via SSH.

## Production Deployment
- Prepare `.env` with your values:
  - `NETINSTALL_INTERFACE` (e.g., `en0`)
  - `NETWORK_RANGE` (e.g., `192.168.44.0/24`)
  - `API_PORT=5001`, `FRONTEND_PORT=3000`
- Place RouterOS package at `routeros/routeros.npk` (bind-mounted read-only)
- Bring up:
  - `docker compose build && docker compose up -d`
- Optional DHCP listener (requires privileges, trusted network only):
  - `ENABLE_DHCP_LISTENER=1 docker compose up -d`

### Host Interface Selection
- The frontend Interface dropdown uses host interfaces exported by `./setup.sh` into `configs/host_interfaces.json`.
- To refresh the list (e.g., after plugging/unplugging adapters), re-run `./setup.sh` or update `configs/host_interfaces.json` and refresh the UI.
- Note on Docker Desktop (macOS/Windows): containers run inside a VM; raw DHCP/ARP broadcasts do not traverse to the host NIC. For full provisioning (DHCP/TFTP/ARP), prefer Linux with `backend` running in host network mode, or run the backend directly on the host: `make backend`.

## Configuration
- `.env` is the source of truth. Examples:
  - `NETINSTALL_INTERFACE=en0`
  - `NETWORK_RANGE=192.168.44.0/24`
  - `API_PORT=5001`, `FRONTEND_PORT=3000`
- Frontend auto-detects backend at `:5001` if served on `:3000`.

## UI Overview
- Provision page: device queue (MAC/Hostname/IP/Model), Advanced (VLAN + port map), CSV import, Sample CSV, Provision All (pause/cancel/retry), verify (ping/SSH), Copy Renames.
- Setup page: Preflight, Global Settings (Gateway/Base/Subnet/NTP/Interface, DHCP toggle), Templates (preview/render), Audit (tail/export), Restart Backend.

## Switch Configuration Defaults
- Customer access ports (VLAN 20 by default):
  - `edge=yes`, `frame-types=admit-only-untagged-and-priority-tagged`, `horizon=1`
  - `bpdu-guard=yes` (bridge), `loop-protect=on` (ethernet)
  - DHCP blocked via `in-interface-list=CUSTOMER` (SEC/MGMT excluded)
- MGMT (VLAN 10) and SEC (VLAN 30) access ports: `edge=yes`, admit-only-untagged
- Trunks: SFP+1 is TrunkIn; others TrunkOut (tagged-only)
- PoE: PoE-capable ports are disabled by default in generated configs

## Security Hardening
- Backend uses `NET_ADMIN` and binds UDP 67/69 via containers; keep the host firewalled and on a trusted network segment.
- Do not expose TFTP or DHCP to the public internet.
- Keep RouterOS packages out of git; store locally at `routeros/`.
- Customer access defaults (BPDU-Guard, Loop-Protect, DHCP drop, PoE off) are built into generated configs.

## Testing
- Backend unit tests (pytest) included under `backend/tests/`. Run:
  - `python3 -m venv .venv && .venv/bin/python -m pip install -U pip`
  - `.venv/bin/pip install -r backend/requirements.txt pytest`
  - `.venv/bin/pytest -q`

## Troubleshooting
- Linux host networking applied automatically (Makefile) to get full L2.
- If frontend shows “Backend Offline”, ensure backend is reachable and refresh; UI derives API base automatically.
- If discovery shows MAC only: ensure MNDP (MikroTik Neighbor Discovery) is allowed on the provisioning VLAN; the backend listens on UDP/5678 and will populate `identity`/`model` from MNDP broadcasts.

## Raspberry Pi 4 (Linux) Deployment
- Docker with host networking (recommended on Pi):
  - `make pi-build && make pi-up`
  - Backend and TFTP run with `network_mode: host` (see `docker-compose.pi.yml`) to capture DHCP/ARP/TFTP traffic on the real NIC.
  - Set `.env`: `NETINSTALL_INTERFACE=eth0`, `ENABLE_DHCP_LISTENER=1`.
- Native (no Docker) alternative:
  - See `pi/README.md` for systemd service and `tftpd-hpa` setup.
