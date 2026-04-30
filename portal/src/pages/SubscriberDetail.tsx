import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Wifi, MapPin, Server, Receipt, Ticket, Zap, Activity, AlertCircle } from 'lucide-react'
import { crm, jake, netbox } from '../services/api'

export default function SubscriberDetail() {
  const { id } = useParams<{ id: string }>()
  const [customer, setCustomer] = useState<any>(null)
  const [invoices, setInvoices] = useState<any[]>([])
  const [tickets,  setTickets]  = useState<any[]>([])
  const [circuit,  setCircuit]  = useState<any>(null)
  const [loading,  setLoading]  = useState(true)
  const [aiAnswer, setAiAnswer] = useState('')
  const [aiLoading,setAiLoading]= useState(false)
  const [error,    setError]    = useState('')

  useEffect(() => {
    if (!id) return
    setLoading(true)
    Promise.allSettled([
      crm.customer(+id).then(setCustomer),
      crm.invoices().then(d => setInvoices((Array.isArray(d) ? d : []).filter((i:any) => i.customer_id === +id || i.customer?.id === +id))),
      crm.tickets().then(d => setTickets((Array.isArray(d) ? d : []).filter((t:any) => t.customer_id === +id || t.customer?.id === +id))),
      // Try to find matching NetBox circuit by customer name
      netbox.circuits('&type=cx-circuit').then(d => {
        const results = d.results ?? []
        if (results.length > 0) setCircuit(results[0])
      }),
    ]).catch(e => setError(String(e))).finally(() => setLoading(false))
  }, [id])

  const askJake = async () => {
    if (!customer) return
    setAiLoading(true); setAiAnswer('')
    try {
      const r = await jake.query(`subscriber status for ${customer.name} at address ${customer.address}`)
      setAiAnswer(r.answer)
    } catch (e: any) { setAiAnswer(`Error: ${e.message}`) }
    setAiLoading(false)
  }

  if (loading) return <div className="card text-center py-12 text-slate-400">Loading subscriber...</div>
  if (!customer) return <div className="card text-center py-12 text-slate-400">Subscriber not found</div>

  const statusColor = customer.status === 'active' ? 'badge-green' : customer.status === 'suspended' ? 'badge-red' : 'badge-gray'

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-center gap-3">
        <Link to="/subscribers" className="btn-ghost text-xs gap-1.5"><ArrowLeft size={13}/> Subscribers</Link>
      </div>

      {/* Header */}
      <div className="card flex items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-brand-100 flex items-center justify-center text-brand-700 font-bold text-lg">
            {customer.name?.[0]}
          </div>
          <div>
            <div className="font-bold text-slate-800 text-lg">{customer.name}</div>
            <div className="text-sm text-slate-500">{customer.email}</div>
            <div className="text-sm text-slate-500">{customer.phone}</div>
          </div>
        </div>
        <span className={statusColor}>{customer.status}</span>
      </div>

      {/* Details grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="card space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><MapPin size={14}/> Address</div>
          <p className="text-sm text-slate-600">{customer.address || '—'}</p>
          {customer.service_plan && (
            <>
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 pt-2 border-t border-surface-3"><Wifi size={14}/> Service Plan</div>
              <div className="text-sm text-slate-600">{customer.service_plan.name}</div>
              <div className="text-xs text-slate-400">{customer.service_plan.download_speed}/{customer.service_plan.upload_speed} Mbps · ${customer.service_plan.monthly_price}/mo</div>
            </>
          )}
        </div>

        <div className="card space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><Server size={14}/> NetBox Circuit</div>
          {circuit ? (
            <>
              <div className="font-mono text-xs text-slate-700">{circuit.cid}</div>
              <div className="text-xs text-slate-400">Provider: {circuit.provider?.name} · {circuit.commit_rate ? `${circuit.commit_rate/1000} Mbps` : '—'}</div>
              <div className={`text-xs ${circuit.status?.value === 'active' ? 'text-emerald-600' : 'text-slate-400'}`}>
                {circuit.status?.label ?? '—'}
              </div>
            </>
          ) : (
            <p className="text-xs text-slate-400">No CX-Circuit linked yet. Run populate_cx_circuits.py to create.</p>
          )}
        </div>
      </div>

      {/* Jake2 diagnostic */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><Zap size={14} className="text-brand-600"/> Jake2 Network Status</div>
          <button onClick={askJake} disabled={aiLoading} className="btn-ghost text-xs gap-1">
            {aiLoading ? <><Activity size={12} className="animate-spin"/> Querying...</> : 'Query network'}
          </button>
        </div>
        {aiAnswer && <pre className="text-xs bg-surface-1 rounded-lg p-3 max-h-32 overflow-auto text-slate-700 whitespace-pre-wrap">{aiAnswer}</pre>}
        {!aiAnswer && !aiLoading && <p className="text-xs text-slate-400">Click "Query network" to ask Jake2 about this subscriber's connection status.</p>}
      </div>

      {/* Invoices */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><Receipt size={14}/> Invoices ({invoices.length})</div>
        {invoices.length === 0 ? <p className="text-xs text-slate-400">No invoices</p> : (
          <div className="space-y-2">
            {invoices.map((inv:any) => (
              <div key={inv.id} className="flex items-center justify-between text-sm border-b border-surface-3 pb-2 last:border-0 last:pb-0">
                <span className="text-slate-600">${(inv.amount??0).toFixed(2)} · {inv.due_date ? new Date(inv.due_date).toLocaleDateString() : '—'}</span>
                <span className={inv.status==='paid'?'badge-green':inv.status==='overdue'?'badge-red':'badge-amber'}>{inv.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tickets */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><Ticket size={14}/> Tickets ({tickets.length})</div>
        {tickets.length === 0 ? <p className="text-xs text-slate-400">No tickets</p> : (
          <div className="space-y-2">
            {tickets.map((t:any) => (
              <div key={t.id} className="flex items-start justify-between text-sm border-b border-surface-3 pb-2 last:border-0 last:pb-0">
                <div>
                  <div className="text-slate-700 font-medium">{t.title}</div>
                  <div className="text-xs text-slate-400">{t.created_at ? new Date(t.created_at).toLocaleDateString() : ''}</div>
                </div>
                <span className={t.status==='open'?'badge-red':t.status==='in_progress'?'badge-amber':'badge-green'}>{t.status?.replace('_',' ')}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
