import React, { useEffect, useState, useCallback } from 'react'
import { Search, UserCheck, UserX, ChevronRight, RefreshCw, Building2, Wifi } from 'lucide-react'
import { netbox, jake } from '../services/api'
import { Link } from 'react-router-dom'

interface Circuit {
  id: number
  cid: string
  status: { value: string; label: string }
  tenant: { id: number; name: string; slug: string } | null
  commit_rate: number | null
}

interface Tenant {
  id: number
  name: string
  slug: string
  group: { name: string; slug: string } | null
  description: string
}

function speedLabel(kbps: number | null) {
  if (!kbps) return null
  if (kbps >= 1_000_000) return `${kbps / 1_000_000} Gbps`
  if (kbps >= 1_000)     return `${kbps / 1_000} Mbps`
  return `${kbps} kbps`
}

export default function Subscribers() {
  const [circuits,  setCircuits]  = useState<Circuit[]>([])
  const [tenants,   setTenants]   = useState<Tenant[]>([])
  const [loading,   setLoading]   = useState(true)
  const [search,    setSearch]    = useState('')
  const [error,     setError]     = useState('')
  const [jakeQuery, setJakeQuery] = useState('')
  const [jakeAns,   setJakeAns]   = useState('')
  const [jakeLoading, setJakeLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true); setError('')
    Promise.allSettled([
      netbox.circuits('&type=cx-circuit').then(d => setCircuits(d.results ?? [])),
      netbox.tenants('&group__isnull=false').then(d => setTenants(d.results ?? [])),
    ]).then(results => {
      const errs = results.filter(r => r.status === 'rejected') as PromiseRejectedResult[]
      if (errs.length) setError(errs.map(e => e.reason?.message).join(', '))
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const lookupJake = async () => {
    if (!jakeQuery.trim()) return
    setJakeLoading(true); setJakeAns('')
    try {
      const r = await jake.query(`subscriber lookup ${jakeQuery}`)
      setJakeAns(r.answer)
    } catch (e: any) { setJakeAns(`Error: ${e.message}`) }
    setJakeLoading(false)
  }

  const filtered = circuits.filter(c => {
    if (!search) return true
    const q = search.toLowerCase()
    return c.cid.toLowerCase().includes(q) ||
      c.tenant?.name.toLowerCase().includes(q) ||
      c.tenant?.group?.name.toLowerCase().includes(q)
  })

  // Build tenant map for quick lookup
  const tenantMap = Object.fromEntries(tenants.map(t => [t.id, t]))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Subscribers</h2>
          <p className="text-xs text-slate-400 mt-0.5">CX-Circuits from NetBox — {circuits.length} total</p>
        </div>
        <button onClick={load} className="btn-ghost text-xs gap-1.5">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* Jake2 subscriber lookup */}
      <div className="card flex gap-2 items-center p-3">
        <Wifi size={14} className="text-brand-500 shrink-0" />
        <input className="input flex-1 border-0 focus:ring-0 text-sm bg-transparent px-1"
          placeholder="Ask Jake2 about a subscriber (name, unit, IP, MAC)..."
          value={jakeQuery} onChange={e => setJakeQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && lookupJake()} />
        <button onClick={lookupJake} disabled={jakeLoading || !jakeQuery.trim()}
          className="px-3 py-1.5 rounded-lg bg-brand-600 text-white text-xs disabled:opacity-40">
          {jakeLoading ? '...' : 'Ask'}
        </button>
      </div>
      {jakeAns && <div className="card bg-brand-50 border-brand-200 text-sm text-brand-900 whitespace-pre-wrap">{jakeAns}</div>}

      {/* Search */}
      <div className="card p-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input pl-8" placeholder="Filter by CID, unit, building..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      {error && <div className="card bg-red-50 border-red-200 text-red-700 text-sm">{error}</div>}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              {['Circuit CID', 'Building', 'Unit', 'Speed', 'Status'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="text-center py-10 text-slate-400">Loading from NetBox...</td></tr>}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={5} className="text-center py-10 text-slate-400">
                {error ? 'Could not reach NetBox' : circuits.length === 0 ? 'No CX-Circuits found — run populate_cx_circuits.py first' : 'No matches'}
              </td></tr>
            )}
            {filtered.map(c => {
              const tenant = c.tenant ? tenantMap[c.tenant.id] : null
              const building = tenant?.group?.name ?? '—'
              const unit = c.tenant?.name ?? '—'
              const isActive = c.status.value === 'active'
              return (
                <tr key={c.id} className="table-row">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{c.cid}</td>
                  <td className="px-4 py-3 text-slate-600 text-xs">
                    <span className="flex items-center gap-1.5"><Building2 size={11} />{building}</span>
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-800">{unit}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{speedLabel(c.commit_rate) ?? '—'}</td>
                  <td className="px-4 py-3">
                    {isActive
                      ? <span className="badge-green"><UserCheck size={10} />active</span>
                      : <span className="badge-gray">{c.status.label}</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!loading && filtered.length > 0 && (
          <div className="px-4 py-2 border-t border-surface-3 bg-surface-1 text-xs text-slate-400">
            Showing {filtered.length} of {circuits.length} circuits
          </div>
        )}
      </div>
    </div>
  )
}
