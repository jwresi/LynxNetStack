import React, { useEffect, useState } from 'react'
import { CheckCircle, AlertCircle, RefreshCw, Server, Zap, Database, Wifi, Terminal, Activity } from 'lucide-react'
import { checkAllHealth, jake, netbox, type ServiceHealth } from '../services/api'

function ServiceCard({ name, url, ok, latency, detail }: ServiceHealth & { url?: string; detail?: string }) {
  return (
    <div className="card flex items-start gap-3">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${ok ? 'bg-emerald-50' : 'bg-red-50'}`}>
        {ok ? <CheckCircle size={16} className="text-emerald-600"/> : <AlertCircle size={16} className="text-red-500"/>}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="font-medium text-slate-800 text-sm">{name}</span>
          <span className={`text-xs font-medium ${ok ? 'text-emerald-600' : 'text-red-500'}`}>{ok ? 'online' : 'offline'}</span>
        </div>
        {url && <div className="text-xs text-slate-400 mt-0.5 font-mono truncate">{url}</div>}
        <div className="text-xs text-slate-400 mt-0.5">{latency}ms response</div>
        {!ok && detail && <div className="text-xs text-red-400 mt-1">{detail}</div>}
      </div>
    </div>
  )
}

export default function SettingsPage() {
  const [health, setHealth]     = useState<ServiceHealth[]>([])
  const [loading, setLoading]   = useState(true)
  const [brief, setBrief]       = useState('')
  const [nbStatus, setNbStatus] = useState<any>(null)

  const check = () => {
    setLoading(true)
    Promise.allSettled([
      checkAllHealth().then(setHealth),
      jake.brief().then(d => setBrief(d.brief ?? '')),
      netbox.status().then(setNbStatus),
    ]).finally(() => setLoading(false))
  }

  useEffect(() => { check() }, [])

  const URLS: Record<string, string> = {
    Jake2: 'http://localhost:8017',
    LynxMSP: 'http://localhost:8000',
    NetBox: 'http://172.27.48.233:8001',
    Provisioner: 'http://localhost:5001',
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-800">Settings & Status</h2>
        <button onClick={check} disabled={loading} className="btn-ghost text-xs gap-1.5">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''}/> Refresh
        </button>
      </div>

      {/* Service health */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">Service Health</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {health.map(s => <ServiceCard key={s.name} {...s} url={URLS[s.name]}/>)}
          {health.length === 0 && <p className="text-sm text-slate-400">Checking services...</p>}
        </div>
      </div>

      {/* Jake2 brief */}
      {brief && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide flex items-center gap-2"><Zap size={14} className="text-brand-600"/> Jake2 Network Brief</h3>
          <div className="card bg-brand-50 border-brand-200">
            <p className="text-sm text-brand-900 leading-relaxed">{brief}</p>
          </div>
        </div>
      )}

      {/* NetBox status */}
      {nbStatus && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide flex items-center gap-2"><Database size={14}/> NetBox</h3>
          <div className="card space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Version</span>
              <span className="font-mono text-xs text-slate-700">{nbStatus.netbox_version ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Python</span>
              <span className="font-mono text-xs text-slate-700">{nbStatus.python_version ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Plugins</span>
              <span className="text-xs text-slate-700">{nbStatus.installed_apps ? Object.keys(nbStatus.installed_apps).length : '—'} installed</span>
            </div>
          </div>
        </div>
      )}

      {/* Quick links */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">Quick Links</h3>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'NetBox Admin', url: 'http://172.27.48.233:8001', icon: Database },
            { label: 'Jake2 WebUI', url: 'http://localhost:8017', icon: Terminal },
            { label: 'Prometheus', url: 'http://172.27.72.179:9090', icon: Activity },
            { label: 'Tech App', url: 'http://localhost:3020', icon: Wifi },
          ].map(l => (
            <a key={l.label} href={l.url} target="_blank" rel="noopener"
              className="card flex items-center gap-3 hover:border-brand-300 hover:shadow-sm transition-all">
              <l.icon size={16} className="text-brand-600 shrink-0"/>
              <div>
                <div className="text-sm font-medium text-slate-700">{l.label}</div>
                <div className="text-xs text-slate-400 font-mono truncate">{l.url}</div>
              </div>
            </a>
          ))}
        </div>
      </div>

      {/* Danger zone */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">Session</h3>
        <div className="card flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-slate-700">Signed in as admin</div>
            <div className="text-xs text-slate-400">LynxMSP operator account</div>
          </div>
          <button onClick={() => { localStorage.removeItem('crm_token'); window.location.reload() }}
            className="text-sm text-red-500 hover:underline">Sign out</button>
        </div>
      </div>
    </div>
  )
}
