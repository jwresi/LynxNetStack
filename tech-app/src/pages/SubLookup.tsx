import React, { useState } from 'react'
import { Search, MapPin, Wifi, AlertCircle } from 'lucide-react'

interface SubResult { name: string; unit: string; building: string; switch_name: string; port: string; ip: string; status: string }

export default function SubLookup() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<SubResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const lookup = async () => {
    if (!query.trim()) return
    setLoading(true); setError(''); setResult(null)
    try {
      const r = await fetch(`/api/jake/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: `subscriber lookup ${query}` })
      })
      const data = await r.json()
      // Parse Jake2 result into display object — shape depends on matched_action
      const res = data.result ?? {}
      setResult({
        name:        res.name ?? data.operator_summary ?? query,
        unit:        res.unit ?? '—',
        building:    res.building ?? res.site_id ?? '—',
        switch_name: res.switch ?? '—',
        port:        res.interface ?? res.port ?? '—',
        ip:          res.ip_address ?? res.ipv4 ?? '—',
        status:      res.status ?? 'unknown',
      })
    } catch (e: any) {
      setError(`Lookup failed: ${e.message}`)
    }
    setLoading(false)
  }

  return (
    <div className="px-4 pt-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Subscriber Lookup</h1>
        <p className="text-sm text-slate-500 mt-0.5">Find by name, unit, address, or MAC</p>
      </div>

      <div className="flex gap-2">
        <input className="input flex-1" placeholder="1B, Jane Doe, 10.0.8.45..." value={query}
          onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && lookup()} />
        <button onClick={lookup} disabled={loading || !query.trim()}
          className="w-12 h-12 rounded-2xl bg-brand-600 flex items-center justify-center text-white disabled:opacity-40 active:bg-brand-700 shrink-0">
          <Search size={18} />
        </button>
      </div>

      {error && (
        <div className="card bg-red-50 border-red-200 flex gap-2 text-red-700 text-sm">
          <AlertCircle size={15} className="shrink-0 mt-0.5" />{error}
        </div>
      )}

      {loading && <div className="text-center text-slate-400 text-sm py-6">Looking up...</div>}

      {result && (
        <div className="card space-y-3">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${result.status === 'active' ? 'bg-emerald-400' : 'bg-slate-300'}`} />
            <span className="font-semibold text-slate-800">{result.name}</span>
          </div>
          {[
            ['Unit',    result.unit],
            ['Building',result.building],
            ['Switch',  result.switch_name],
            ['Port',    result.port],
            ['IP',      result.ip],
            ['Status',  result.status],
          ].map(([k,v]) => (
            <div key={k} className="flex justify-between text-sm border-t border-surface-3 pt-2">
              <span className="text-slate-400">{k}</span>
              <span className="font-mono text-slate-700 text-xs">{v}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
