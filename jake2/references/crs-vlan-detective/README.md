# crs-vlan-detective (Topology)

This discovers **Layer-2 topology** in a MikroTik-heavy network by walking **LLDP neighbors** recursively starting from one or more seed devices (CCR/CRS).

## Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml
```

## Run topology discovery (live)
```bash
python3 -m crs_vlandetective topology --config ./config.yaml --out ./out --max-depth 8
```

Outputs:
- `out/topology.json`
- `out/topology.dot`

## Render a picture (optional)
If you have Graphviz installed:
```bash
dot -Tpng out/topology.dot -o out/topology.png
open out/topology.png
```

## Notes / Limitations
- LLDP must be enabled on your CCR/CRS ports you want discovered.
- If a neighbor does not advertise a management IP, the script will try ARP by chassis MAC (when available). Otherwise it will create an `unknown@...` placeholder node.
- Credentials are shared for all discovered devices (today). If you have mixed creds, we can add a credential map.
