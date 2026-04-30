# Templates

- Place Jinja2 templates here. The backend serves this directory at `/api/templates` and renders via `/api/templates/render`.
- The frontend lists all files in this folder with extensions `.rsc`, `.tmpl`, or `.j2`.
- Variables available from the UI include:
  - `hostname`, `ip`, `mac`, `model`, `mgmtVlan`, `cxVlan`, `secVlan`, `gateway`, `subnet`, `baseNetwork`, `trunkIn`, `trunkOut`, `poePorts`, `now`.

## Included templates

- `crs326_24g.tmpl` — CRS326-24G-2S+RM (24-port non‑PoE)
- `crs418_16g_8poe.tmpl` — CRS418-8P-8G-2S+RM (16-port with 8 PoE)
- `crs354_48g.tmpl` — CRS354-48G-4S+2Q+RM (48-port non‑PoE)
- `crs354_48p.tmpl` — CRS354-48P-4S+2Q+RM (48-port all‑PoE)

These mirror our hardened defaults:
- Bridge `vlan-filtering=yes`, RSTP enabled
- Customer ports: `edge=yes`, `horizon=1`, admit only untagged/priority-tagged
- SFP/QSFP trunks: admit only tagged
- BPDU-Guard on access, loop-protect enabled
- PoE disabled by default on PoE-capable ports
- Drop DHCP on CUSTOMER interface list

Edit or add templates as needed; they will appear automatically in the UI dropdown after reload.
