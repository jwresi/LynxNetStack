import React, { useEffect, useState } from 'react'
import { CheckCircle, AlertCircle, Zap, Server, Database, RefreshCw } from 'lucide-react'

interface SvcStatus { name: string; url: string; ok: boolean; latency: number }

const SERVICES = [
  { name: 'Jake2',       url: 'http://localhost:8017/api/stats' },
  { name: 'Provisioner', url: 'http://localhost:5001/api/status' },
  { name: 'LynxMSP',    url: 'http://localhost:8000/auth/health' },
  { name: 'NetBox',      url: 'http://172.27.48.233:8001/api/status/' },
]

export default function TechSettings() {
  const [statuses, setStatuses] = useState<SvcStatus[]>([])
  const [loading, setLoading]   = useState(false)
  const [nbVersion, setNbVersion] = useState('')
  const [jakeStats, setJakeStats] = useState<any>(null)

  const check = async () => {
    setLoading(true)
    const results = await Promise.all(SERVICES.map(async s => {
      const t0 = Date.now()
      try {
        const r = await fetch(s.url, { headers: { Authorization: s.url.includes('172.27.48.233') ? 'Token 8fd77834b1412f49a09e768be1b379f5416f33c3' : '' } })
        if (s.url.includes('172.27.48.233')) { try { const d = await r.json(); setNbVersion(d.netbox_version ?? '') } catch {} }
        if (s.url.includes('8017')) { try { const d = await r.json(); setJakeStats(d) } catch {} }
        return { name: s.name, url: s.url, ok: r.ok, latency: Date.now() - t0 }
      } catch {
        return { name: s.name, url: s.url, ok: false, latency: Date.now() - t0 }
      }
    }))
    setStatuses(results)
    setLoading(false)
  }

  useEffect(() => { check() }, [])

  const onlineCount = statuses.filter(s => s.ok).length

  return (
    <div className="px-4 pt-6 pb-24 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Settings</h1>
          <p className="text-sm text-slate-500 mt-0.5">{onlineCount}/{statuses.length} services online</p>
        </div>
        <button onClick={check} disabled={loading}
          className="w-10 h-10 rounded-xl border border-surface-3 flex items-center justify-center text-slate-500 active:bg-surface-2">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''}/>
        </button>
      </div>

      {/* Service status */}
      <div className="space-y-2">
        <p className="section-header">Backend Services</p>
        {statuses.map(s => (
          <div key={s.name} className="card flex items-center justify-between py-3">
            <div className="flex items-center gap-3">
              {s.ok ? <CheckCircle size={16} className="text-emerald-500"/> : <AlertCircle size={16} className="text-red-400"/>}
              <div>
                <div className="font-medium text-slate-800 text-sm">{s.name}</div>
                <div className="text-[11px] text-slate-400 font-mono">{s.url.replace('http://','').split('/')[0]}</div>
              </div>
            </div>
            <div className="text-right">
              <div className={`text-xs font-medium ${s.ok ? 'text-emerald-600' : 'text-red-500'}`}>{s.ok ? 'online' : 'offline'}</div>
              <div className="text-[11px] text-slate-400">{s.latency}ms</div>
            </div>
          </div>
        ))}
      </div>

      {/* Jake2 live stats */}
      {jakeStats && (
        <div className="space-y-2">
          <p className="section-header">Network Live Stats</p>
          <div className="card space-y-3">
            {[
              ['Devices Online',      jakeStats.online_devices],
              ['CPEs Online',         jakeStats.cpes_online],
              ['Links Up',            `${jakeStats.online_links}/${jakeStats.total_links}`],
              ['Active Alerts',       jakeStats.alerts_open],
            ].map(([k, v]) => (
              <div key={k as string} className="flex items-center justify-between text-sm">
                <span className="text-slate-500">{k}</span>
                <span className="font-semibold text-slate-800">{v ?? '—'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* NetBox info */}
      {nbVersion && (
        <div className="space-y-2">
          <p className="section-header">NetBox</p>
          <div className="card flex items-center justify-between text-sm">
            <span className="text-slate-500">Version</span>
            <span className="font-mono text-slate-700">{nbVersion}</span>
          </div>
        </div>
      )}

      {/* Quick links */}
      <div className="space-y-2">
        <p className="section-header">Quick Links</p>
        {[
          { label: 'Operator Portal',  url: 'http://localhost:3010' },
          { label: 'NetBox',           url: 'http://172.27.48.233:8001' },
          { label: 'Jake2 WebUI',      url: 'http://localhost:8017' },
          { label: 'Prometheus',       url: 'http://172.27.72.179:9090' },
        ].map(l => (
          <a key={l.label} href={l.url} target="_blank" rel="noopener"
            className="card flex items-center justify-between py-3 active:bg-surface-1">
            <span className="text-sm font-medium text-slate-700">{l.label}</span>
            <span className="text-xs text-slate-400 font-mono">{l.url.replace('http://','')}</span>
          </a>
        ))}
      </div>
    </div>
  )
}
