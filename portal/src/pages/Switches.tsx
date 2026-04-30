import React, { useEffect, useState } from 'react'
import { Server, RefreshCw, Cpu } from 'lucide-react'
import { netbox, jake } from '../services/api'

interface Device { id: number; name: string; status: { value: string; label: string }; device_type: { model: string }; primary_ip4: { address: string } | null; site: { name: string; slug: string } }

export default function Switches() {
  const [devices,  setDevices]  = useState<Device[]>([])
  const [loading,  setLoading]  = useState(true)
  const [answer,   setAnswer]   = useState('')
  const [qLoading, setQLoading] = useState(false)

  useEffect(() => {
    netbox.devices('000007').then(d => setDevices(d.results ?? [])).finally(() => setLoading(false))
  }, [])

  const askJake = async (q: string) => {
    setQLoading(true); setAnswer('')
    try { const r = await jake.query(q); setAnswer(r.answer) }
    catch (e: any) { setAnswer(`Error: ${e.message}`) }
    setQLoading(false)
  }

  const switches = devices.filter(d => d.name?.includes('.SW') || d.name?.includes('.RFSW'))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Switches</h2>
          <p className="text-xs text-slate-400 mt-0.5">NYCHA 000007 — {switches.length} switch devices in NetBox</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => askJake('which switches at nycha have problems or high error rates')}
            disabled={qLoading} className="btn-ghost text-xs gap-1.5">
            {qLoading ? '...' : '⚡ Ask Jake2'}
          </button>
        </div>
      </div>

      {answer && <div className="card bg-brand-50 border-brand-200 text-sm text-brand-900 whitespace-pre-wrap">{answer}</div>}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              {['Device', 'Model', 'Mgmt IP', 'Status'].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={4} className="text-center py-8 text-slate-400">Loading devices from NetBox...</td></tr>}
            {switches.map(d => (
              <tr key={d.id} className="table-row">
                <td className="px-4 py-2.5 font-mono text-xs text-slate-800">{d.name}</td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">{d.device_type?.model ?? '—'}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-slate-500">
                  {d.primary_ip4?.address?.split('/')[0] ?? '—'}
                </td>
                <td className="px-4 py-2.5">
                  {d.status.value === 'active'
                    ? <span className="badge-green">{d.status.label}</span>
                    : <span className="badge-amber">{d.status.label}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
