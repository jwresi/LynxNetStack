# Deploying jake.lynxnet.co

Full deployment guide for the unified LynxNetStack stack on a ZeroTier-connected
server behind Cloudflare.

---

## Architecture recap

```
Internet → Cloudflare (DNS proxy, public TLS)
               │
               │ HTTPS → origin cert
               ▼
          Your server (ZeroTier node)
               │ :80 / :443
               ▼
          nginx container  ← single entry point
               ├── /            → jake2
               ├── /crm         → lynxmsp
               ├── /provision   → provisioner
               ├── /billing     → netbox-stripe-sync
               └── /tikfig      → tikfig
```

kea-sync runs on jumpB separately — it is NOT part of this compose stack.

---

## Prerequisites

On the target server:

- Docker Engine 24+ and Docker Compose v2
- Port 80 and 443 open on the server firewall
- ZeroTier joined to the ResiBridge network
- DNS: `jake.lynxnet.co` → this server's IP (set in Cloudflare)

---

## Step 1 — Clone the repo

```bash
git clone https://github.com/jwresi/LynxNetStack.git /opt/lynxnetstack
cd /opt/lynxnetstack
```

---

## Step 2 — Get the Cloudflare origin certificate

Cloudflare issues a free origin cert that is valid for up to 15 years. It is
only trusted between Cloudflare's edge and your origin — not by browsers
directly. This is fine because all public traffic goes through Cloudflare.

1. Log in to the Cloudflare dashboard → **lynxnet.co** domain
2. Go to **SSL/TLS → Origin Server → Create Certificate**
3. Leave the defaults (RSA 2048, `*.lynxnet.co` + `lynxnet.co`, 15 years)
4. Click **Create**
5. Copy the **Origin Certificate** → save as `nginx/certs/origin.crt`
6. Copy the **Private Key** → save as `nginx/certs/origin.key`

```bash
# On the server:
nano /opt/lynxnetstack/nginx/certs/origin.crt   # paste certificate
nano /opt/lynxnetstack/nginx/certs/origin.key   # paste private key
chmod 600 /opt/lynxnetstack/nginx/certs/origin.key
```

In Cloudflare dashboard → **SSL/TLS → Overview**, set encryption mode to
**Full (strict)**. This tells Cloudflare to validate the origin cert rather
than accept any cert.

---

## Step 3 — Configure environment

```bash
cp .env.example .env
nano .env
```

Required values to fill in:

| Variable | Where to get it |
|---|---|
| `NETBOX_API_TOKEN` | NetBox UI → user profile → API Tokens |
| `LYNXMSP_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `STRIPE_API_KEY` | Stripe dashboard (use `sk_test_...` until ready for live) |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard → Webhooks → your endpoint |

```bash
cp jake2/config/.env.example jake2/config/.env
nano jake2/config/.env
# Fill in: NETBOX_TOKEN, BIGMAC_URL, SSH_MCP_USERNAME/PASSWORD,
#          OLLAMA_ENDPOINT, and any vendor credentials

cp billing/netbox-stripe-sync/.env.example billing/netbox-stripe-sync/.env
nano billing/netbox-stripe-sync/.env
# Fill in: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, NETBOX_TOKEN, NETBOX_URL
```

---

## Step 4 — RouterOS package (provisioner)

The provisioner backend expects a RouterOS `.npk` upgrade package for
NetInstall provisioning:

```bash
# Copy the package to the provisioner directory
cp /path/to/routeros-7.x.x-mipsbe.npk provisioner/routeros/routeros.npk
```

If you do not need NetInstall provisioning yet, create an empty placeholder:

```bash
mkdir -p provisioner/routeros
touch provisioner/routeros/routeros.npk
```

---

## Step 5 — Configure Cloudflare DNS

In the Cloudflare dashboard for `lynxnet.co`:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `jake` | `<server IP>` | Proxied (orange cloud) |

The orange cloud is required — it routes traffic through Cloudflare's edge
where your HTTPS certificate lives.

---

## Step 6 — Build and start

```bash
cd /opt/lynxnetstack
docker compose build
docker compose up -d
```

Watch startup logs:

```bash
docker compose logs -f nginx
docker compose logs -f jake2
```

Check all containers are healthy:

```bash
docker compose ps
```

Expected output:

```
NAME                    STATUS              PORTS
nginx                   running             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
jake2                   running (healthy)
lynxmsp-backend         running (healthy)
lynxmsp-frontend        running
provisioner-backend     running
provisioner-frontend    running
tikfig                  running
netbox-stripe-sync      running
```

---

## Step 7 — Verify

```bash
# Health check (bypasses Cloudflare — direct to origin)
curl -k https://<server-ip>/healthz

# Via Cloudflare
curl https://jake.lynxnet.co/healthz
```

Then open in a browser:

| URL | Service |
|---|---|
| `https://jake.lynxnet.co/` | Jake2 NOC assistant |
| `https://jake.lynxnet.co/crm` | LynxMSP CRM |
| `https://jake.lynxnet.co/provision` | Switch provisioner |
| `https://jake.lynxnet.co/billing` | Stripe/NetBox billing sync |
| `https://jake.lynxnet.co/tikfig` | RouterOS config generator |

---

## Stripe webhook endpoint

Once `jake.lynxnet.co` is live, register the Stripe webhook:

1. Stripe dashboard → **Developers → Webhooks → Add endpoint**
2. URL: `https://jake.lynxnet.co/billing/webhooks/stripe`
3. Events: `invoice.payment_succeeded`, `invoice.payment_failed`,
   `customer.subscription.updated`, `customer.subscription.deleted`
4. Copy the **Signing secret** → set as `STRIPE_WEBHOOK_SECRET` in
   `billing/netbox-stripe-sync/.env`
5. Restart: `docker compose restart netbox-stripe-sync`

---

## Updates

```bash
cd /opt/lynxnetstack
git pull
docker compose build
docker compose up -d
```

Rolling restart (zero downtime for stateless services):

```bash
docker compose up -d --no-deps --build jake2
```

---

## Logs and monitoring

```bash
# All services
docker compose logs -f

# One service
docker compose logs -f jake2

# nginx access log (shows all requests by subpath)
docker compose logs -f nginx
```

---

## ZeroTier allowlist

The nginx config restricts access to Cloudflare IPs plus your ZeroTier range
(`172.27.0.0/16`). If you need direct access from a different network during
setup, temporarily comment out the `include cloudflare-ips.conf;` line in
`nginx/nginx.conf` and rebuild:

```bash
# nginx/nginx.conf — comment out the include line
# include /etc/nginx/cloudflare-ips.conf;

docker compose build nginx
docker compose up -d --no-deps nginx
```

Remember to re-enable it before going live.

---

## Updating the Cloudflare IP allowlist

Cloudflare's IP ranges change occasionally. To refresh:

```bash
curl -s https://www.cloudflare.com/ips-v4 | \
  awk '{print "allow " $0 ";"}' > nginx/cloudflare-ips.conf
echo "" >> nginx/cloudflare-ips.conf
echo "allow 172.27.0.0/16;  # ZeroTier" >> nginx/cloudflare-ips.conf
echo "deny all;" >> nginx/cloudflare-ips.conf

docker compose build nginx
docker compose up -d --no-deps nginx
```

---

## Troubleshooting

### `502 Bad Gateway` on a subpath

The upstream container is not running or not healthy.

```bash
docker compose ps                        # which container is down
docker compose logs -f <container-name> # why
docker compose restart <container-name>
```

### `SSL_ERROR_RX_RECORD_TOO_LONG` in browser

Cloudflare SSL mode is set to **Flexible** instead of **Full (strict)**.
Change it in the Cloudflare dashboard.

### `403 Forbidden` from nginx

Your IP is not in the Cloudflare range and not in the ZeroTier range. Either
you are hitting the origin directly from a non-ZT IP, or the Cloudflare IP
list is stale. See [Updating the Cloudflare IP allowlist](#updating-the-cloudflare-ip-allowlist).

### React app shows blank page at `/crm` or `/provision`

The frontend was built with the wrong `REACT_APP_API_URL`. Rebuild:

```bash
docker compose build --no-cache lynxmsp-frontend
docker compose up -d --no-deps lynxmsp-frontend
```

### `origin.crt` or `origin.key` missing

```
nginx: [emerg] cannot load certificate "/etc/nginx/certs/origin.crt"
```

The cert files were not placed in `nginx/certs/` before building. Place them
and rebuild: `docker compose build nginx && docker compose up -d --no-deps nginx`
