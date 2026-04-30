import React, { useEffect, useState, useCallback } from 'react'
import { Search, UserCheck, UserX, ChevronRight, RefreshCw, Building2, Wifi, Users } from 'lucide-react'
import { crm, netbox, jake } from '../services/api'
import { Link } from 'react-router-dom'

interface Customer {
  id: number; name: string; email: string; phone: string; address: string
  status: string; service_plan?: { name: string; download_speed: number; monthly_price: number }
}

interface Circuit {
  id: number; cid: string
  status: { value: string; label: string }
  tenant: { id: number; name: string } | null
  commit_rate: number | null
}

function speedLabel(kbps: number | null) {
  if (!kbps) return null
  if (kbps >= 1_000_000) return `${kbps / 1_000_000} Gbps`
  if (kbps >= 1_000)     return `${kbps / 1_000} Mbps`
  return `${kbps} kbps`
}

export default function Subscribers() {
  const [tab, setTab]           = useState<'crm' | 'netbox'>('crm')
  const [customers, setCustomers] = useState<Customer[]>([])
  const [circuits,  setCircuits]  = useState<Circuit[]>([])
  const [loading,   setLoading]   = useState(true)
  const [search,    setSearch]    = useState('')
  const [error,     setError]     = useState('')
  const [jakeQuery, setJakeQuery] = useState('')
  const [jakeAns,   setJakeAns]   = useState('')
  const [jakeLoading, setJakeLoading] = useState(false)

  const loadCrm = useCallback(() => {
    setLoading(true); setError('')
    crm.customers()
      .then(d => setCustomers(Array.isArray(d) ? d : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const loadNetbox = useCallback(() => {
    setLoading(true); setError('')
    netbox.circuits('&type=cx-circuit')
      .then(d => setCircuits(d.results ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { tab === 'crm' ? loadCrm() : loadNetbox() }, [tab, loadCrm, loadNetbox])

  const lookupJake = async () => {
    if (!jakeQuery.trim()) return
    setJakeLoading(true); setJakeAns('')
    try {
      const r = await jake.query(`subscriber lookup ${jakeQuery}`)
      setJakeAns(r.answer)
    } catch (e: any) { setJakeAns(`Error: ${e.message}`) }
    setJakeLoading(false)
  }

  const filteredCustomers = customers.filter(c => {
    if (!search) return true
    const q = search.toLowerCase()
    return c.name.toLowerCase().includes(q) ||
      c.email.toLowerCase().includes(q) ||
      c.address.toLowerCase().includes(q)
  })

  const filteredCircuits = circuits.filter(c => {
    if (!search) return true
    const q = search.toLowerCase()
    return c.cid.toLowerCase().includes(q) || c.tenant?.name.toLowerCase().includes(q)
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Subscribers</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {tab === 'crm'
              ? `${customers.length} in LynxMSP CRM`
              : `${circuits.length} CX-Circuits in NetBox`}
          </p>
        </div>
        <button onClick={() => tab === 'crm' ? loadCrm() : loadNetbox()}
          className="btn-ghost text-xs gap-1.5">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''}/> Refresh
        </button>
      </div>

      {/* Tab selector */}
      <div className="flex gap-1 bg-surface-1 rounded-lg p-1 border border-surface-3 w-fit">
        <button onClick={() => setTab('crm')}
          className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors flex items-center gap-1.5
            ${tab === 'crm' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}>
          <Users size={11}/> CRM Subscribers
        </button>
        <button onClick={() => setTab('netbox')}
          className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors flex items-center gap-1.5
            ${tab === 'netbox' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}>
          <Building2 size={11}/> NetBox Circuits
        </button>
      </div>

      {/* Jake2 lookup */}
      <div className="card flex gap-2 items-center p-3">
        <Wifi size={14} className="text-brand-500 shrink-0"/>
        <input className="input flex-1 border-0 focus:ring-0 text-sm bg-transparent px-1"
          placeholder="Ask Jake2 about a subscriber (name, unit, IP, MAC)..."
          value={jakeQuery} onChange={e => setJakeQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && lookupJake()}/>
        <button onClick={lookupJake} disabled={jakeLoading || !jakeQuery.trim()}
          className="px-3 py-1.5 rounded-lg bg-brand-600 text-white text-xs disabled:opacity-40">
          {jakeLoading ? '...' : 'Ask'}
        </button>
      </div>
      {jakeAns && (
        <div className="card bg-brand-50 border-brand-200 text-sm text-brand-900 whitespace-pre-wrap">{jakeAns}</div>
      )}

      {/* Search */}
      <div className="card p-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/>
          <input className="input pl-8"
            placeholder={tab === 'crm' ? 'Filter by name, email, address...' : 'Filter by CID or unit...'}
            value={search} onChange={e => setSearch(e.target.value)}/>
        </div>
      </div>

      {error && (
        <div className="card bg-red-50 border-red-200 text-red-700 text-sm">{error}</div>
      )}

      {/* CRM Customers table */}
      {tab === 'crm' && (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3 bg-surface-1">
                {['Name', 'Email', 'Address', 'Plan', 'Status', ''].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={6} className="text-center py-10 text-slate-400">Loading subscribers...</td></tr>
              )}
              {!loading && filteredCustomers.length === 0 && (
                <tr><td colSpan={6} className="text-center py-10 text-slate-400">No subscribers found</td></tr>
              )}
              {filteredCustomers.map(c => (
                <tr key={c.id} className="table-row">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{c.name}</div>
                    <div className="text-xs text-slate-400">{c.phone}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{c.email}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs max-w-xs truncate">{c.address}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {c.service_plan
                      ? `${c.service_plan.name} · $${c.service_plan.monthly_price}/mo`
                      : '—'}
                  </td>
                  <td className="px-4 py-3">
                    {c.status === 'active'
                      ? <span className="badge-green"><UserCheck size={10}/> active</span>
                      : c.status === 'suspended'
                        ? <span className="badge-red"><UserX size={10}/> suspended</span>
                        : <span className="badge-gray">{c.status}</span>}
                  </td>
                  <td className="px-4 py-3">
                    <Link to={`/subscribers/${c.id}`}
                      className="text-slate-400 hover:text-brand-600 transition-colors">
                      <ChevronRight size={15}/>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && filteredCustomers.length > 0 && (
            <div className="px-4 py-2 border-t border-surface-3 bg-surface-1 text-xs text-slate-400">
              {filteredCustomers.length} of {customers.length} subscribers
            </div>
          )}
        </div>
      )}

      {/* NetBox Circuits table */}
      {tab === 'netbox' && (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3 bg-surface-1">
                {['Circuit CID', 'Unit/Tenant', 'Speed', 'Status'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={4} className="text-center py-10 text-slate-400">Loading from NetBox...</td></tr>
              )}
              {!loading && filteredCircuits.length === 0 && (
                <tr><td colSpan={4} className="text-center py-10 text-slate-400">
                  {circuits.length === 0
                    ? 'No CX-Circuits found — run populate_cx_circuits.py to populate'
                    : 'No matches'}
                </td></tr>
              )}
              {filteredCircuits.map(c => (
                <tr key={c.id} className="table-row">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{c.cid}</td>
                  <td className="px-4 py-3 font-medium text-slate-800">{c.tenant?.name ?? '—'}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{speedLabel(c.commit_rate) ?? '—'}</td>
                  <td className="px-4 py-3">
                    {c.status.value === 'active'
                      ? <span className="badge-green"><UserCheck size={10}/> active</span>
                      : <span className="badge-gray">{c.status.label}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && filteredCircuits.length > 0 && (
            <div className="px-4 py-2 border-t border-surface-3 bg-surface-1 text-xs text-slate-400">
              {filteredCircuits.length} of {circuits.length} circuits
            </div>
          )}
        </div>
      )}
    </div>
  )
}
