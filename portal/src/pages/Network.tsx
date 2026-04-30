import React, { useEffect, useState } from 'react'
import { Server, Wifi, AlertTriangle, CheckCircle, RefreshCw, Activity, MapPin } from 'lucide-react'
import { jake, netbox } from '../services/api'

interface Site { id: number; name: string; slug: string; status: { value: string }; description: string }
interface Device { id: number; name: string; status: { value: string }; device_type: { model: string }; primary_ip4: { address: string } | null; site: { name: string } }

export default function Network() {
  const [brief,   setBrief]   = useState('')
  const [sites,   setSites]   = useState<Site[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [query,   setQuery]   = useState('')
  const [answer,  setAnswer]  = useState('')
  const [loading, setLoading] = useState(true)
  const [qLoading,setQLoading]= useState(false)

  useEffect(() => {
    Promise.allSettled([
      jake.brief().then(d => setBrief(d.brief ?? '')),
      netbox.sites().then(d => setSites(d.results ?? [])),
      netbox.devices().then(d => setDevices(d.results ?? [])),
    ]).finally(() => setLoading(false))
  }, [])

  const ask = async (q?: string) => {
    const question = q ?? query; if (!question.trim()) return
    setQLoading(true); setAnswer('')
    try { const r = await jake.query(question); setAnswer(r.answer) }
    catch (e: any) { setAnswer(`Error: ${e.message}`) }
    setQLoading(false)
  }

  const activeDevices = devices.filter(d => d.status.value === 'active').length
  const activeSites   = sites.filter(s => s.status.value === 'active').length

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-4">
        <div className="card text-center">
          <div className="text-2xl font-bold text-brand-600">{loading ? '—' : activeSites}</div>
          <div className="text-xs text-slate-400 mt-1 uppercase tracking-wide">Active Sites</div>
        </div>
        <div className="card text-center">
          <div className="text-2xl font-bold text-emerald-600">{loading ? '—' : activeDevices}</div>
          <div className="text-xs text-slate-400 mt-1 uppercase tracking-wide">Devices in NetBox</div>
        </div>
        <div className="card text-center">
          <div className="text-2xl font-bold text-purple-600">{loading ? '—' : devices.length}</div>
          <div className="text-xs text-slate-400 mt-1 uppercase tracking-wide">Total Devices</div>
        </div>
      </div>

      {/* Jake2 network query */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-brand-600" />
          <span className="text-sm font-semibold text-slate-700">Network Intelligence</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {['which switches have issues', 'are there switches on old firmware', 'show me nycha site status', 'what is online at chenoweth'].map(q => (
            <button key={q} onClick={() => ask(q)}
              className="text-xs px-2.5 py-1 rounded-full border border-surface-3 hover:border-brand-400 hover:text-brand-700 text-slate-500 transition-colors">
              {q}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input className="input text-sm" placeholder="Ask Jake2 about the network..."
            value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && ask()} />
          <button onClick={() => ask()} disabled={qLoading || !query.trim()}
            className="px-3 py-2 rounded-lg bg-brand-600 text-white text-sm disabled:opacity-40 hover:bg-brand-700 shrink-0">
            {qLoading ? '...' : 'Ask'}
          </button>
        </div>
        {answer && <pre className="text-xs bg-surface-1 rounded-lg p-3 max-h-40 overflow-auto text-slate-700 whitespace-pre-wrap">{answer}</pre>}
      </div>

      {/* Sites table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3 flex items-center gap-2">
          <MapPin size={14} className="text-slate-400" />
          <span className="text-sm font-semibold text-slate-700">Sites from NetBox</span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              {['Site', 'Slug', 'Status', 'Description'].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={4} className="text-center py-8 text-slate-400">Loading...</td></tr>}
            {sites.map(s => (
              <tr key={s.id} className="table-row">
                <td className="px-4 py-2.5 font-medium text-slate-800">{s.name}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{s.slug}</td>
                <td className="px-4 py-2.5">
                  {s.status.value === 'active'
                    ? <span className="badge-green">active</span>
                    : <span className="badge-gray">{s.status.value}</span>}
                </td>
                <td className="px-4 py-2.5 text-xs text-slate-400 truncate max-w-xs">{s.description || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
