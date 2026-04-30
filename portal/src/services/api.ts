// Unified API client — wired to live production backends.
//
// Vite proxies (see vite.config.ts):
//   /api/jake    → :8017  Jake2 (live BigMac + production NetBox)
//   /api/crm     → :8000  LynxMSP FastAPI (needs Bearer token)
//   /api/netbox  → 172.27.48.233:8001  Production NetBox (token injected by proxy)
//   /api/prov    → :5001  Provisioner Flask

// ── Auth token store ──────────────────────────────────────────────────────────
let _crmToken: string | null = localStorage.getItem('crm_token')

export function setCrmToken(t: string | null) {
  _crmToken = t
  if (t) localStorage.setItem('crm_token', t)
  else localStorage.removeItem('crm_token')
}

export function getCrmToken() { return _crmToken }

// ── Base request helpers ──────────────────────────────────────────────────────
const req = async (url: string, opts?: RequestInit) => {
  const r = await fetch(url, {
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    ...opts,
  })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

// CRM requests inject Bearer token when available
const crmReq = async (url: string, opts?: RequestInit) => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  }
  if (_crmToken) headers['Authorization'] = `Bearer ${_crmToken}`
  const r = await fetch(url, { headers, ...opts })
  if (r.status === 401) { setCrmToken(null); throw new Error('401 Unauthorized — please log in') }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

// NetBox proxy — token injected at Vite proxy layer
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
  login:        (username: string, password: string) => {
    const body = new URLSearchParams({ username, password })
    return fetch('/api/crm/auth/login', { method: 'POST', body }).then(r => r.json())
  },
  health:       () => req('/api/crm/auth/health'),
  stats:        () => crmReq('/api/crm/dashboard/stats'),
  customers:    (skip = 0, limit = 100) => crmReq(`/api/crm/customers/?skip=${skip}&limit=${limit}`),
  customer:     (id: number)            => crmReq(`/api/crm/customers/${id}`),
  invoices:     (skip = 0, limit = 100) => crmReq(`/api/crm/invoices/?skip=${skip}&limit=${limit}`),
  invoice:      (id: number)            => crmReq(`/api/crm/invoices/${id}`),
  updateInvoice:(id: number, body: any) => crmReq(`/api/crm/invoices/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  servicePlans: ()                      => crmReq('/api/crm/service-plans'),
  createPlan:   (body: any)             => crmReq('/api/crm/service-plans', { method: 'POST', body: JSON.stringify(body) }),
  updatePlan:   (id: number, body: any) => crmReq(`/api/crm/service-plans/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deletePlan:   (id: number)            => crmReq(`/api/crm/service-plans/${id}`, { method: 'DELETE' }),
  tickets:      (skip = 0, limit = 100) => crmReq(`/api/crm/tickets/?skip=${skip}&limit=${limit}`),
  ticket:       (id: number)            => crmReq(`/api/crm/tickets/${id}`),
  createTicket: (body: any)             => crmReq('/api/crm/tickets', { method: 'POST', body: JSON.stringify(body) }),
  updateTicket: (id: number, body: any) => crmReq(`/api/crm/tickets/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  addComment:   (id: number, body: any) => crmReq(`/api/crm/tickets/${id}/comments`, { method: 'POST', body: JSON.stringify(body) }),
  settings:     ()                      => crmReq('/api/crm/settings'),
}

// ── NetBox direct (proxied, auth token injected by vite.config.ts) ────────────
export const netbox = {
  tenants:    (params = '')    => nbReq(`/api/tenancy/tenants/?limit=200${params}`),
  circuits:   (params = '')    => nbReq(`/api/circuits/circuits/?limit=200${params}`),
  circuit:    (id: number)     => nbReq(`/api/circuits/circuits/${id}/`),
  sites:      ()               => nbReq('/api/dcim/sites/?limit=50'),
  devices:    (site?: string)  => nbReq(`/api/dcim/devices/?limit=200${site ? `&site=${site}` : ''}`),
  interfaces: (deviceId: number) => nbReq(`/api/dcim/interfaces/?device_id=${deviceId}&limit=100`),
  ipAddresses:(tenant?: string)=> nbReq(`/api/ipam/ip-addresses/?limit=100${tenant ? `&tenant=${tenant}` : ''}`),
  prefixes:   ()               => nbReq('/api/ipam/prefixes/?limit=50'),
  status:     ()               => nbReq('/api/status/'),
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
