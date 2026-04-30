import React, { useEffect, useState } from 'react'
import { Users, Server, Activity, AlertCircle, CheckCircle, Zap, Wifi, WifiOff, Building2, Network } from 'lucide-react'
import { checkAllHealth, jake, crm, netbox, type ServiceHealth } from '../services/api'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

function StatCard({ icon: Icon, label, value, sub, color = 'blue' }: any) {
  const map: Record<string, string> = {
    blue:   'text-brand-600 bg-brand-50',
    green:  'text-emerald-600 bg-emerald-50',
    amber:  'text-amber-600 bg-amber-50',
    red:    'text-red-600 bg-red-50',
    purple: 'text-purple-600 bg-purple-50',
  }
  return (
    <div className="card flex items-start gap-4">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${map[color]}`}>
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-bold text-slate-800 tabular-nums">{value ?? <span className="text-slate-300">—</span>}</div>
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400 mt-0.5">{label}</div>
        {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}

function HealthRow({ s }: { s: ServiceHealth }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-surface-3 last:border-0">
      <div className="flex items-center gap-2.5 text-sm">
        {s.ok
          ? <CheckCircle size={13} className="text-emerald-500 shrink-0" />
          : <AlertCircle size={13} className="text-red-400 shrink-0" />}
        <span className={s.ok ? 'text-slate-700' : 'text-slate-400'}>{s.name}</span>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className={s.ok ? 'text-emerald-600' : 'text-red-400'}>{s.ok ? 'online' : 'offline'}</span>
        <span className="text-slate-300">{s.latency}ms</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [jakeStats,   setJakeStats]   = useState<any>(null)
  const [jakeBrief,   setJakeBrief]   = useState<string>('')
  const [crmStats,    setCrmStats]    = useState<any>(null)
  const [nbSites,     setNbSites]     = useState<number>(0)
  const [nbTenants,   setNbTenants]   = useState<number>(0)
  const [nbCircuits,  setNbCircuits]  = useState<number>(0)
  const [health,      setHealth]      = useState<ServiceHealth[]>([])
  const [loading,     setLoading]     = useState(true)

  useEffect(() => {
    Promise.allSettled([
      jake.stats().then(setJakeStats).catch(() => {}),
      jake.brief().then(d => setJakeBrief(d.brief ?? '')).catch(() => {}),
      crm.stats().then(setCrmStats).catch(() => {}),
      netbox.sites().then(d => setNbSites(d.count ?? 0)).catch(() => {}),
      netbox.tenants().then(d => setNbTenants(d.count ?? 0)).catch(() => {}),
      netbox.circuits().then(d => setNbCircuits(d.count ?? 0)).catch(() => {}),
      checkAllHealth().then(setHealth),
    ]).finally(() => setLoading(false))
  }, [])

  const onlineCount = health.filter(h => h.ok).length

  return (
    <div className="space-y-5">

      {/* Jake2 brief banner */}
      {jakeBrief && (
        <div className="card flex items-start gap-3 bg-brand-50 border-brand-200 py-3">
          <Zap size={15} className="text-brand-600 shrink-0 mt-0.5" />
          <p className="text-sm text-brand-800 leading-relaxed">{jakeBrief}</p>
        </div>
      )}

      {/* Live stat grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Wifi}     label="Subscribers Online"  value={jakeStats?.cpes_online}     color="green"  sub="live via Jake2" />
        <StatCard icon={Server}   label="Devices Online"      value={jakeStats?.online_devices}  color="blue"   sub="switches + routers" />
        <StatCard icon={Building2}label="NetBox Tenants"       value={nbTenants}                  color="purple" sub={`${nbCircuits} CX-Circuits`} />
        <StatCard icon={Network}  label="Sites"               value={nbSites}                    color="amber"  sub={`${onlineCount}/${health.length} services up`} />
      </div>

      {/* Middle row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Jake2 quick query */}
        <div className="lg:col-span-2 card space-y-3">
          <div className="flex items-center gap-2">
            <Zap size={14} className="text-brand-600" />
            <span className="text-sm font-semibold text-slate-700">Jake2 — Quick Query</span>
          </div>
          <JakeQuickQuery />
        </div>

        {/* Service health */}
        <div className="card">
          <div className="text-sm font-semibold text-slate-700 mb-3">Service Health</div>
          {health.length === 0
            ? <p className="text-xs text-slate-400">Checking...</p>
            : health.map(s => <HealthRow key={s.name} s={s} />)
          }
        </div>
      </div>

      {/* CRM stats */}
      {crmStats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Users}   label="Total Subscribers" value={crmStats.total_customers}  color="blue" />
          <StatCard icon={Users}   label="Active"            value={crmStats.active_customers} color="green" />
          <StatCard icon={AlertCircle} label="Open Tickets"  value={crmStats.open_tickets}     color="red" />
          <StatCard icon={Activity}    label="Pending Orders" value={crmStats.pending_orders}  color="amber" />
        </div>
      )}
    </div>
  )
}

// Inline quick query widget
function JakeQuickQuery() {
  const [input, setInput] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)

  const QUICK = [
    'how many customers online at nycha',
    'which switches have issues',
    'are there switches on old firmware',
  ]

  const run = async (q: string) => {
    setLoading(true); setAnswer('')
    try {
      const r = await jake.query(q)
      setAnswer(r.answer ?? JSON.stringify(r))
    } catch (e: any) { setAnswer(`Error: ${e.message}`) }
    setLoading(false)
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {QUICK.map(q => (
          <button key={q} onClick={() => run(q)}
            className="text-xs px-2.5 py-1 rounded-full border border-surface-3 hover:border-brand-400 hover:text-brand-700 text-slate-500 transition-colors">
            {q}
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <input className="input text-sm flex-1" placeholder="Ask Jake2..."
          value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && input.trim() && run(input)} />
        <button onClick={() => run(input)} disabled={loading || !input.trim()}
          className="px-3 py-2 rounded-lg bg-brand-600 text-white text-sm disabled:opacity-40 hover:bg-brand-700 transition-colors shrink-0">
          {loading ? '...' : 'Ask'}
        </button>
      </div>
      {answer && (
        <pre className="text-xs bg-surface-1 rounded-lg p-3 max-h-24 overflow-auto text-slate-700 whitespace-pre-wrap">{answer}</pre>
      )}
    </div>
  )
}
