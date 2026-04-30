import React, { useEffect, useState } from 'react'
import { MapPin, Server, ChevronDown, RefreshCw, AlertCircle, Wifi, Circle } from 'lucide-react'

// All NetBox calls go through the Vite proxy at /api/netbox
// Token is injected server-side — never in client JS
async function nbGet(path: string) {
  const r = await fetch(`/api/netbox${path}`, {
    headers: { Accept: 'application/json' }
  })
  if (!r.ok) throw new Error(`NetBox ${r.status}: ${r.statusText}`)
  return r.json()
}

interface Site   { id: number; name: string; slug: string }
interface Device { id: number; name: string; primary_ip4: { address: string } | null }
interface Iface  { id: number; name: string; description: string; cable: any; enabled: boolean }
interface Circuit { id: number; cid: string; tenant?: { name: string }; commit_rate: number | null }

export default function PortMap() {
  const [sites,     setSites]     = useState<Site[]>([])
  const [devices,   setDevices]   = useState<Device[]>([])
  const [ifaces,    setIfaces]    = useState<Iface[]>([])
  const [circuits,  setCircuits]  = useState<Circuit[]>([])
  const [site,      setSite]      = useState('')
  const [device,    setDevice]    = useState<Device | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState('')

  // Load sites on mount
  useEffect(() => {
    setLoading(true)
    nbGet('/api/dcim/sites/?limit=50')
      .then(d => setSites(d.results ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  // Load switches when site changes
  useEffect(() => {
    if (!site) { setDevices([]); setDevice(null); setIfaces([]); setCircuits([]); return }
    setLoading(true); setDevice(null); setIfaces([]); setCircuits([])
    nbGet(`/api/dcim/devices/?site=${site}&limit=200`)
      .then(d => setDevices(
        (d.results ?? []).filter((dev: Device) => dev.name?.includes('.SW') || dev.name?.includes('.RFSW'))
      ))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [site])

  const loadPorts = async (dev: Device) => {
    setDevice(dev); setIfaces([]); setCircuits([]); setLoading(true)
    try {
      const [ifaceData, circuitData] = await Promise.all([
        nbGet(`/api/dcim/interfaces/?device_id=${dev.id}&limit=100`),
        nbGet(`/api/circuits/circuits/?type=cx-circuit&limit=200`),
      ])
      setIfaces(ifaceData.results ?? [])
      setCircuits(circuitData.results ?? [])
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }

  const subscriberPorts = ifaces
    .filter(i => /^(ETH|ether)\d+$/i.test(i.name))
    .sort((a, b) => {
      const n = (s: string) => parseInt(s.replace(/\D/g, ''), 10) || 0
      return n(a.name) - n(b.name)
    })
    .slice(0, 48)

  const selectedSiteName = sites.find(s => s.slug === site)?.name ?? ''

  return (
    <div className="px-4 pt-6 pb-24 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Port Map</h1>
        <p className="text-sm text-slate-500 mt-0.5">Unit → switch port from NetBox</p>
      </div>

      {error && (
        <div className="card bg-red-50 border-red-200 flex gap-2 text-red-700 text-sm items-start">
          <AlertCircle size={14} className="shrink-0 mt-0.5"/>
          <span className="flex-1">{error}</span>
          <button onClick={() => setError('')} className="text-red-400 font-bold">✕</button>
        </div>
      )}

      {/* Site selector */}
      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Site</p>
        <div className="relative">
          <select value={site} onChange={e => setSite(e.target.value)} className="input appearance-none pr-8">
            <option value="">— Select a site —</option>
            {sites.map(s => <option key={s.id} value={s.slug}>{s.name}</option>)}
          </select>
          <ChevronDown size={13} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"/>
        </div>
      </div>

      {/* Switch selector */}
      {devices.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
            Switches in {selectedSiteName} ({devices.length})
          </p>
          <div className="space-y-2">
            {devices.map(d => (
              <button key={d.id} onClick={() => loadPorts(d)}
                className={`w-full card flex items-center gap-3 text-left transition-all
                  ${device?.id === d.id ? 'border-brand-400 bg-brand-50' : 'active:scale-[0.99]'}`}>
                <Server size={16} className={device?.id === d.id ? 'text-brand-600' : 'text-slate-400'}/>
                <div className="flex-1 min-w-0">
                  <div className={`font-medium text-sm ${device?.id === d.id ? 'text-brand-700' : 'text-slate-800'}`}>
                    {d.name}
                  </div>
                  {d.primary_ip4 && (
                    <div className="text-xs text-slate-400 font-mono">
                      {d.primary_ip4.address.split('/')[0]}
                    </div>
                  )}
                </div>
                {device?.id === d.id && <ChevronDown size={14} className="text-brand-500 rotate-[-90deg]"/>}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <div className="text-center text-slate-400 text-sm py-6 flex items-center justify-center gap-2">
          <RefreshCw size={14} className="animate-spin"/> Loading...
        </div>
      )}

      {/* Port grid */}
      {device && !loading && subscriberPorts.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
            {device.name} — {subscriberPorts.length} subscriber ports
          </p>
          <div className="grid grid-cols-4 gap-2">
            {subscriberPorts.map(iface => {
              const portNum = iface.name.replace(/\D/g, '')
              const cabled  = !!iface.cable
              return (
                <div key={iface.id}
                  className={`rounded-xl p-2.5 text-center border transition-colors
                    ${cabled
                      ? 'bg-brand-50 border-brand-200'
                      : iface.enabled
                        ? 'bg-surface-1 border-surface-3'
                        : 'bg-slate-50 border-slate-200 opacity-50'}`}>
                  <div className={`text-sm font-bold ${cabled ? 'text-brand-700' : 'text-slate-400'}`}>
                    {portNum}
                  </div>
                  <div className="text-[10px] mt-0.5 truncate">
                    {iface.description
                      ? <span className="text-slate-600">{iface.description}</span>
                      : <span className="text-slate-300">{cabled ? 'cabled' : 'empty'}</span>}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div className="flex gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-brand-100 border border-brand-200 inline-block"/>
              Cabled ({subscriberPorts.filter(i => i.cable).length})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded bg-surface-1 border border-surface-3 inline-block"/>
              Empty ({subscriberPorts.filter(i => !i.cable).length})
            </span>
          </div>
        </div>
      )}

      {/* CX-Circuits for site */}
      {circuits.length > 0 && !loading && (
        <div className="space-y-2 mt-2">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
            CX-Circuits in {selectedSiteName} ({circuits.length})
          </p>
          <div className="card p-0 overflow-hidden">
            {circuits.slice(0, 25).map((c, i) => (
              <div key={i}
                className="flex items-center justify-between px-3 py-2.5 border-b border-surface-3 last:border-0 text-sm">
                <span className="font-mono text-xs text-slate-700">{c.cid}</span>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  {c.tenant?.name && <span>{c.tenant.name}</span>}
                  {c.commit_rate && (
                    <span className="text-slate-400">
                      {c.commit_rate >= 1000 ? `${c.commit_rate/1000}M` : `${c.commit_rate}k`}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {circuits.length > 25 && (
              <div className="px-3 py-2 text-xs text-slate-400">+{circuits.length - 25} more</div>
            )}
          </div>
        </div>
      )}

      {/* Empty states */}
      {site && !loading && devices.length === 0 && (
        <div className="card text-center py-8 text-slate-400 text-sm">
          No switches found for {selectedSiteName} in NetBox
        </div>
      )}
      {device && !loading && subscriberPorts.length === 0 && (
        <div className="card text-center py-8 text-slate-400 text-sm">
          No subscriber ports found on {device.name}
        </div>
      )}
    </div>
  )
}
