# Loki Noise Filter

## Problem
The mktxp Prometheus exporter scrapes every MikroTik switch via the RouterOS API at each scrape interval. This generates mktxp_user login/logout syslog entries on every device, every scrape cycle. At NYCHA (000007) with 50+ switches this produces ~490 events per 15-minute window, drowning out real operational signal.

## Jake-side filter (active by default)
Jake drops known management noise in `mcp/jake_ops_mcp.py` `_is_noise_line()` before classification. Controlled by env vars:

`JAKE_LOKI_FILTER_NOISE=true`  (default: on)
`JAKE_MGMT_IPS=172.27.72.179,172.27.226.246`

Lines containing `"failed"` or `"error"` are never dropped regardless of settings.

To disable for debugging:

```bash
JAKE_LOKI_FILTER_NOISE=false ./jake "..."
```

## Recommended Vector-side fix
Drop the noise before it reaches Loki entirely.

File: `/opt/grafana/logging_stack/vector/config/vector.toml`
Server: `172.27.72.179`

Add a filter transform after the parse transform:

```toml
[transforms.drop_management_noise]
type = "filter"
inputs = ["parse"]
condition = '''
  !contains(string(.content) ?? "", "mktxp_user") ||
  contains(string(.content) ?? "", "failed") ||
  contains(string(.content) ?? "", "error")
'''
```

Then update your downstream sink to use `drop_management_noise` as its input instead of `parse`.

Restart Vector after the change:

```bash
docker compose -f docker-compose_logs.yml restart vector
```

## Verification after Vector change
Check that NYCHA log volume drops significantly:

```bash
# Before: ~500 entries per 15-minute window
# After: only real operational events

curl -s -G 'http://172.27.72.179:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={host=~"000007.*"}' \
  --data-urlencode 'limit=10' \
  --data-urlencode "start=$(python3 -c \
    'import time; print(int((time.time()-900)*1e9))')" \
  --data-urlencode "end=$(python3 -c \
    'import time; print(int(time.time()*1e9))')" \
  | python3 -m json.tool | head -40
```

Also verify no `mktxp_user` lines appear:

```bash
curl -s 'http://172.27.72.179:3100/loki/api/v1/label/host/values' | python3 -m json.tool
```

## Jake fallback
Even without the Vector change, Jake's in-process filter ensures summaries show real signal. Set `JAKE_LOKI_FILTER_NOISE=false` to see raw unfiltered data for debugging purposes.
