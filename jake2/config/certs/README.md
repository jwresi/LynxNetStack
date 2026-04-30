# Client TLS Certificates

`config/certs/` is the intended home for client TLS certificates used by Jake2 runtime integrations.

Rules:

- Live certs and private keys are never committed to this repo.
- Place required files here manually on the local machine.
- Reference them through env vars in `config/.env`, not with hardcoded absolute paths.
- Typical consumers include the TAUC client-cert flows in `mcp/tauc_mcp.py`.

Common env vars:

- `TAUC_CLIENT_CERT`
- `TAUC_CLIENT_KEY`
- `TAUC_CLOUD_CLIENT_CERT`
- `TAUC_CLOUD_CLIENT_KEY`
- `TAUC_ACS_CLIENT_CERT`
- `TAUC_ACS_CLIENT_KEY`
- `TAUC_OLT_CLIENT_CERT`
- `TAUC_OLT_CLIENT_KEY`
- `TAUC_*_CA_CERT`
