import React, { useEffect, useState } from 'react'
import { MapPin, Server, ChevronDown, RefreshCw, AlertCircle } from 'lucide-react'

const NB = 'http://172.27.48.233:8001'
const TOKEN = '8fd77834b1412f49a09e768be1b379f5416f33c3'

async function nbGet(path: string) {
  const r = await fetch(`${NB}${path}`, { headers: { Authorization: `Token ${TOKEN}`, Accept: 'application/json' } })
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json()
}

interface Site { id: number; name: string; slug: string }
interface Device { id: number; name: string; primary_ip4: { address: string } | null }
interface Iface { id: number; name: string; description: string; cable: any }
interface Circuit { cid: string; tenant?: { name: string } }

export default function PortMap() {
  const [sites,    setSites]    = useState<Site[]>([])
  const [devices,  setDevices]  = useState<Device[]>([])
  const [ifaces,   setIfaces]   = useState<Iface[]>([])
  const [circuits, setCircuits] = useState<Circuit[]>([])
  const [site,     setSite]     = useState('')
  const [device,   setDevice]   = useState<Device | null>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  useEffect(() => {
    nbGet('/api/dcim/sites/?limit=50').then(d => setSites(d.results ?? [])).catch(e => setError(e.message))
  }, [])

  useEffect(() => {
    if (!site) { setDevices([]); setDevice(null); return }
    setLoading(true)
    nbGet(`/api/dcim/devices/?site=${site}&limit=200`)
      .then(d => setDevices((d.results ?? []).filter((d: Device) => d.name?.includes('.SW'))))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
    setDevice(null); setIfaces([]); setCircuits([])
  }, [site])

  const loadPorts = async (dev: Device) => {
    setDevice(dev); setLoading(true); setIfaces([]); setCircuits([])
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

  // Build port→circuit map via cable traversal would require extra API calls
  // Instead show all CX-Circuits for context
  const subscriberPorts = ifaces.filter(i => i.name.startsWith('ETH') || i.name.startsWith('ether')).slice(0, 48)

  return (
    <div className="px-4 pt-6 pb-24 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Port Map</h1>
        <p className="text-sm text-slate-500 mt-0.5">Unit → switch port lookup from NetBox</p>
      </div>

      {error && (
        <div className="card bg-red-50 border-red-200 flex gap-2 text-red-700 text-sm">
          <AlertCircle size={14} className="shrink-0 mt-0.5"/> {error}
          <button onClick={() => setError('')} className="ml-auto text-red-400">✕</button>
        </div>
      )}

      {/* Site selector */}
      <div className="space-y-1">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Site</p>
        <div className="relative">
          <select value={site} onChange={e => setSite(e.target.value)} className="input appearance-none pr-8">
            <option value="">— Select site —</option>
            {sites.map(s => <option key={s.id} value={s.slug}>{s.name}</option>)}
          </select>
          <ChevronDown size={13} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"/>
        </div>
      </div>

      {/* Switch selector */}
      {devices.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Switch</p>
          <div className="space-y-2">
            {devices.map(d => (
              <button key={d.id} onClick={() => loadPorts(d)}
                className={`w-full card flex items-center gap-3 text-left transition-all ${device?.id === d.id ? 'border-brand-400 bg-brand-50' : 'active:scale-[0.99]'}`}>
                <Server size={16} className={device?.id === d.id ? 'text-brand-600' : 'text-slate-400'}/>
                <div>
                  <div className={`font-medium text-sm ${device?.id === d.id ? 'text-brand-700' : 'text-slate-800'}`}>{d.name}</div>
                  {d.primary_ip4 && <div className="text-xs text-slate-400 font-mono">{d.primary_ip4.address.split('/')[0]}</div>}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && <div className="text-center text-slate-400 text-sm py-6">Loading...</div>}

      {/* Port grid */}
      {device && !loading && subscriberPorts.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{device.name} — {subscriberPorts.length} ports</p>
          <div className="grid grid-cols-4 gap-2">
            {subscriberPorts.map(iface => {
              const portNum = iface.name.replace(/^ETH|^ether/, '')
              const hasSubscriber = !!iface.cable
              return (
                <div key={iface.id}
                  className={`rounded-xl p-2 text-center border ${hasSubscriber ? 'bg-brand-50 border-brand-200' : 'bg-surface-1 border-surface-3'}`}>
                  <div className={`text-sm font-bold ${hasSubscriber ? 'text-brand-700' : 'text-slate-400'}`}>{portNum}</div>
                  {iface.description && <div className="text-[10px] text-slate-500 truncate mt-0.5">{iface.description}</div>}
                  {!iface.description && <div className="text-[10px] text-slate-300 mt-0.5">{hasSubscriber ? 'cabled' : 'empty'}</div>}
                </div>
              )
            })}
          </div>

          {/* CX-Circuits for this site */}
          {circuits.length > 0 && (
            <div className="space-y-2 mt-4">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">CX-Circuits ({circuits.length})</p>
              <div className="card p-0 overflow-hidden">
                {circuits.slice(0, 20).map((c, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 border-b border-surface-3 last:border-0 text-sm">
                    <span className="font-mono text-xs text-slate-700">{c.cid}</span>
                    <span className="text-slate-500 text-xs">{c.tenant?.name ?? '—'}</span>
                  </div>
                ))}
                {circuits.length > 20 && <div className="px-3 py-2 text-xs text-slate-400">+{circuits.length - 20} more</div>}
              </div>
            </div>
          )}
        </div>
      )}

      {site && !loading && devices.length === 0 && (
        <div className="card text-center py-8 text-slate-400 text-sm">No switches found for this site in NetBox</div>
      )}
    </div>
  )
}
