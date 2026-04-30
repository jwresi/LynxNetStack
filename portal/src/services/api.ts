// Unified API client — wired to live production backends.
//
// Vite proxies (see vite.config.ts):
//   /api/jake    → :8017  Jake2 (live BigMac + production NetBox, auth: none)
//   /api/crm     → :8000  LynxMSP FastAPI
//   /api/netbox  → 172.27.48.233:8001  Production NetBox (token injected by proxy)
//   /api/prov    → :5001  Provisioner Flask

const req = async (url: string, opts?: RequestInit) => {
  const r = await fetch(url, { headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, ...opts })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

// NetBox proxy — token injected at the Vite proxy layer, no auth header needed here
const nbReq = (path: string) => req(`/api/netbox${path}`)

// ── Jake2 ─────────────────────────────────────────────────────────────────────
export const jake = {
  query:  (q: string) => req('/api/jake/chat', { method: 'POST', body: JSON.stringify({ message: q }) }),
  stats:  () => req('/api/jake/stats'),
  brief:  () => req('/api/jake/brief'),
  health: () => req('/api/jake/stats'),
}

// ── LynxMSP CRM ───────────────────────────────────────────────────────────────
export const crm = {
  health:       () => req('/api/crm/auth/health'),
  customers:    (skip = 0, limit = 100) => req(`/api/crm/customers/?skip=${skip}&limit=${limit}`),
  customer:     (id: number) => req(`/api/crm/customers/${id}`),
  invoices:     (skip = 0, limit = 50) => req(`/api/crm/invoices/?skip=${skip}&limit=${limit}`),
  servicePlans: () => req('/api/crm/service-plans/'),
  tickets:      (skip = 0, limit = 50) => req(`/api/crm/tickets/?skip=${skip}&limit=${limit}`),
  stats:        () => req('/api/crm/dashboard/stats'),
}

// ── NetBox direct (proxied, auth token set by vite.config.ts) ─────────────────
export const netbox = {
  tenants:    (params = '') => nbReq(`/api/tenancy/tenants/?limit=200${params}`),
  circuits:   (params = '') => nbReq(`/api/circuits/circuits/?limit=200${params}`),
  sites:      ()             => nbReq('/api/dcim/sites/?limit=50'),
  devices:    (site?: string) => nbReq(`/api/dcim/devices/?limit=200${site ? `&site=${site}` : ''}`),
  interfaces: (deviceId: number) => nbReq(`/api/dcim/interfaces/?device_id=${deviceId}&limit=100`),
  ipAddresses:(tenant?: string) => nbReq(`/api/ipam/ip-addresses/?limit=100${tenant ? `&tenant=${tenant}` : ''}`),
  prefixes:   () => nbReq('/api/ipam/prefixes/?limit=50'),
  status:     () => nbReq('/api/status/'),
}

// ── Provisioner ───────────────────────────────────────────────────────────────
export const prov = {
  health:   () => req('/api/prov/api/status'),
  devices:  () => req('/api/prov/api/devices'),
  audit:    () => req('/api/prov/api/audit?limit=50'),
}

// ── Combined health check ─────────────────────────────────────────────────────
export type ServiceHealth = { name: string; ok: boolean; latency: number }

export async function checkAllHealth(): Promise<ServiceHealth[]> {
  const checks = [
    { name: 'Jake2',       fn: jake.stats },
    { name: 'LynxMSP',    fn: crm.health },
    { name: 'NetBox',      fn: netbox.status },
    { name: 'Provisioner', fn: prov.health },
  ]
  return Promise.all(checks.map(async c => {
    const t0 = Date.now()
    try   { await c.fn(); return { name: c.name, ok: true,  latency: Date.now() - t0 } }
    catch { return         { name: c.name, ok: false, latency: Date.now() - t0 } }
  }))
}
