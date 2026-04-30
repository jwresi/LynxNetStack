import React, { useEffect, useState } from 'react'
import { Server, RefreshCw, ChevronDown } from 'lucide-react'
import { netbox, jake } from '../services/api'

interface Site { id: number; name: string; slug: string }
interface Device { id: number; name: string; status: { value: string; label: string }; device_type: { model: string }; primary_ip4: { address: string } | null; site: { name: string; slug: string } }

export default function Switches() {
  const [sites,    setSites]   = useState<Site[]>([])
  const [devices,  setDevices] = useState<Device[]>([])
  const [siteSlug, setSiteSlug]= useState<string>('all')
  const [loading,  setLoading] = useState(true)
  const [answer,   setAnswer]  = useState('')
  const [qLoading, setQLoading]= useState(false)

  // Load sites on mount
  useEffect(() => {
    netbox.sites().then(d => setSites(d.results ?? []))
  }, [])

  // Reload devices when site selection changes
  useEffect(() => {
    setLoading(true)
    const param = siteSlug !== 'all' ? siteSlug : undefined
    netbox.devices(param).then(d => setDevices(d.results ?? [])).finally(() => setLoading(false))
  }, [siteSlug])

  const askJake = async (q: string) => {
    setQLoading(true); setAnswer('')
    try {
      const site = siteSlug !== 'all' ? siteSlug : 'all sites'
      const r = await jake.query(q.replace('{site}', site))
      setAnswer(r.answer)
    } catch (e: any) { setAnswer(`Error: ${e.message}`) }
    setQLoading(false)
  }

  const selectedSiteName = siteSlug === 'all'
    ? 'All Sites'
    : (sites.find(s => s.slug === siteSlug)?.name ?? siteSlug)

  const switches = devices.filter(d =>
    d.name?.includes('.SW') || d.name?.includes('.RFSW') || d.name?.includes('.R1')
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Switches & Routers</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {selectedSiteName} — {switches.length} devices in NetBox
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {/* Site selector */}
          <div className="relative">
            <select
              value={siteSlug}
              onChange={e => setSiteSlug(e.target.value)}
              className="appearance-none pl-3 pr-8 py-1.5 rounded-lg border border-surface-3 text-sm text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30 cursor-pointer"
            >
              <option value="all">All Sites</option>
              {sites.map(s => (
                <option key={s.id} value={s.slug}>{s.name}</option>
              ))}
            </select>
            <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          </div>
          <button
            onClick={() => askJake(`which switches at {site} have problems or high error rates`)}
            disabled={qLoading}
            className="btn-ghost text-xs gap-1.5"
          >
            {qLoading ? '...' : '⚡ Ask Jake2'}
          </button>
        </div>
      </div>

      {answer && (
        <div className="card bg-brand-50 border-brand-200 text-sm text-brand-900 whitespace-pre-wrap">{answer}</div>
      )}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              {['Device', 'Site', 'Model', 'Mgmt IP', 'Status'].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={5} className="text-center py-8 text-slate-400">
                Loading devices from NetBox...
              </td></tr>
            )}
            {!loading && switches.length === 0 && (
              <tr><td colSpan={5} className="text-center py-8 text-slate-400">
                No devices found
              </td></tr>
            )}
            {switches.map(d => (
              <tr key={d.id} className="table-row">
                <td className="px-4 py-2.5 font-mono text-xs text-slate-800">{d.name}</td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">{d.site?.name ?? '—'}</td>
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
        {!loading && switches.length > 0 && (
          <div className="px-4 py-2 border-t border-surface-3 bg-surface-1 text-xs text-slate-400">
            {switches.length} devices — {devices.length} total in NetBox for {selectedSiteName}
          </div>
        )}
      </div>
    </div>
  )
}
