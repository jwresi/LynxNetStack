import React, { useEffect, useState } from 'react'
import { Wifi, MapPin, Activity, ChevronRight, AlertCircle, CheckCircle } from 'lucide-react'

const BACKENDS = [
  { name: 'Provisioner', url: '/api/prov/api/status' },
  { name: 'Jake2',       url: '/api/jake/health' },
  { name: 'Tikfig',      url: '/api/tikfig/api/config' },
]

export default function HomeScreen() {
  const [status, setStatus] = useState<Record<string, boolean>>({})

  useEffect(() => {
    BACKENDS.forEach(async b => {
      try { await fetch(b.url); setStatus(s => ({ ...s, [b.name]: true })) }
      catch { setStatus(s => ({ ...s, [b.name]: false })) }
    })
  }, [])

  const quickActions = [
    { label: 'Onboard CPE',      sub: 'Scan & register a new device', icon: Wifi,     to: '/onboard', color: 'bg-brand-600' },
    { label: 'Port Map',         sub: 'Unit → switch port lookup',    icon: MapPin,   to: '/portmap', color: 'bg-emerald-600' },
    { label: 'Subscriber Lookup',sub: 'Find a subscriber by address', icon: Activity, to: '/lookup',  color: 'bg-purple-600' },
  ]

  return (
    <div className="px-4 pt-6 space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800">LynxStack</h1>
        <p className="text-sm text-slate-500 mt-0.5">Field Tech Companion</p>
      </div>

      {/* Quick actions */}
      <div className="space-y-3">
        <p className="section-header">Quick Actions</p>
        {quickActions.map(a => (
          <a key={a.label} href={a.to}
            className="card flex items-center gap-4 active:scale-[0.98] transition-transform">
            <div className={`w-11 h-11 rounded-xl ${a.color} flex items-center justify-center shrink-0`}>
              <a.icon size={20} className="text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-slate-800 text-sm">{a.label}</div>
              <div className="text-xs text-slate-400 mt-0.5">{a.sub}</div>
            </div>
            <ChevronRight size={16} className="text-slate-300 shrink-0" />
          </a>
        ))}
      </div>

      {/* Backend status */}
      <div className="space-y-2">
        <p className="section-header">Backend Status</p>
        <div className="card space-y-2">
          {BACKENDS.map(b => (
            <div key={b.name} className="flex items-center justify-between text-sm">
              <span className="text-slate-600">{b.name}</span>
              {status[b.name] === undefined
                ? <span className="text-slate-300 text-xs">checking...</span>
                : status[b.name]
                  ? <span className="flex items-center gap-1 text-emerald-600 text-xs"><CheckCircle size={12} />online</span>
                  : <span className="flex items-center gap-1 text-red-500 text-xs"><AlertCircle size={12} />offline</span>
              }
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
