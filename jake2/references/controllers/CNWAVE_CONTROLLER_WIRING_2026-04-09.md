# cnWave Controller Wiring

Jake now separates two cnWave surfaces:

- exporter metrics
- controller remote commands

Current exporter wiring is already present:

- `CNWAVE_EXPORTER_URL`
- `CNWAVE_PROMETHEUS_MODE=1`

That is enough for:

- RF metrics
- link status
- coarse site radio health

It is not enough for controller-only actions such as:

- `Monitor and Manage -> <radio> -> Tools -> Remote Commands -> Show IPv4 Neighbors`

To wire that path into Jake, set:

- `CNWAVE_CONTROLLER_URL`
- `CNWAVE_CONTROLLER_NEIGHBORS_URL_TEMPLATE`

Optional auth controls:

- `CNWAVE_CONTROLLER_USERNAME`
- `CNWAVE_CONTROLLER_PASSWORD`
- `CNWAVE_CONTROLLER_AUTH_MODE`
- `CNWAVE_CONTROLLER_VERIFY_SSL`

Current Jake behavior:

- query: `show ipv4 neighbors for 721 Fenimore V1000`
- route: `get_live_cnwave_radio_neighbors`
- if controller wiring is missing, Jake now says that explicitly instead of falling back to unrelated RF/site output

Notes:

- `172.27.72.179:9090` is the exporter, not the controller web UI
- plain `http://172.27.72.179` and `https://172.27.72.179` were not reachable from this host during the check, so do not assume the exporter host is also the controller host
