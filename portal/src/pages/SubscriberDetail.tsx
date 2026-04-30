import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Wifi, MapPin, Server, Receipt, Ticket, Zap, Activity, Phone, Mail, AlertCircle } from 'lucide-react'
import { crm, jake, netbox } from '../services/api'

interface Customer {
  id: number; name: string; email: string; phone: string; address: string; status: string
  service_plan?: { id: number; name: string; download_speed: number; upload_speed: number; monthly_price: number; technology?: string }
}
interface Invoice { id: number; amount: number; status: string; due_date: string }
interface Ticket  { id: number; title: string; status: string; priority: string; created_at: string }

export default function SubscriberDetail() {
  const { id } = useParams<{ id: string }>()
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [tickets,  setTickets]  = useState<Ticket[]>([])
  const [aiAnswer, setAiAnswer] = useState('')
  const [aiLoading,setAiLoading]= useState(false)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState('')

  useEffect(() => {
    if (!id) return
    setLoading(true)
    Promise.allSettled([
      crm.customer(+id).then(setCustomer),
      crm.invoices().then(d =>
        setInvoices((Array.isArray(d) ? d : []).filter((i: any) =>
          i.customer_id === +id || i.customer?.id === +id
        ))
      ),
      crm.tickets().then(d =>
        setTickets((Array.isArray(d) ? d : []).filter((t: any) =>
          t.customer_id === +id || t.customer?.id === +id
        ))
      ),
    ])
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [id])

  const askJake = async () => {
    if (!customer) return
    setAiLoading(true); setAiAnswer('')
    try {
      const r = await jake.query(
        `subscriber status check: name=${customer.name}, address=${customer.address}`
      )
      setAiAnswer(r.answer)
    } catch (e: any) { setAiAnswer(`Error: ${e.message}`) }
    setAiLoading(false)
  }

  if (loading) return <div className="card text-center py-12 text-slate-400">Loading...</div>

  if (!customer) return (
    <div className="space-y-4">
      <Link to="/subscribers" className="btn-ghost text-xs gap-1.5 inline-flex"><ArrowLeft size={13}/> Subscribers</Link>
      <div className="card text-center py-12 text-slate-400">Subscriber not found</div>
    </div>
  )

  const statusColor = customer.status === 'active'
    ? 'badge-green'
    : customer.status === 'suspended' ? 'badge-red' : 'badge-gray'

  const openInvoices  = invoices.filter(i => i.status !== 'paid')
  const openTickets   = tickets.filter(t => t.status !== 'resolved' && t.status !== 'closed')
  const totalBalance  = openInvoices.reduce((s, i) => s + (i.amount || 0), 0)

  return (
    <div className="space-y-5 max-w-3xl">
      <Link to="/subscribers" className="btn-ghost text-xs gap-1.5 inline-flex">
        <ArrowLeft size={13}/> Subscribers
      </Link>

      {error && (
        <div className="card bg-red-50 border-red-200 text-red-700 text-sm flex gap-2">
          <AlertCircle size={14} className="shrink-0 mt-0.5"/> {error}
        </div>
      )}

      {/* Header card */}
      <div className="card flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-brand-100 flex items-center justify-center
                          text-brand-700 font-bold text-lg shrink-0">
            {customer.name?.[0]?.toUpperCase()}
          </div>
          <div>
            <div className="font-bold text-slate-800 text-lg leading-tight">{customer.name}</div>
            <div className="flex items-center gap-3 mt-1 flex-wrap">
              <span className="flex items-center gap-1 text-xs text-slate-500">
                <Mail size={11}/> {customer.email}
              </span>
              <span className="flex items-center gap-1 text-xs text-slate-500">
                <Phone size={11}/> {customer.phone}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {openTickets.length > 0 && (
            <span className="badge-red">{openTickets.length} open ticket{openTickets.length>1?'s':''}</span>
          )}
          {totalBalance > 0 && (
            <span className="badge-amber">${totalBalance.toFixed(2)} outstanding</span>
          )}
          <span className={statusColor}>{customer.status}</span>
        </div>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="card space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <MapPin size={14}/> Address
          </div>
          <p className="text-sm text-slate-600 leading-relaxed">{customer.address || '—'}</p>
        </div>

        <div className="card space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Wifi size={14}/> Service Plan
          </div>
          {customer.service_plan ? (
            <div className="space-y-1">
              <div className="font-medium text-slate-800">{customer.service_plan.name}</div>
              <div className="text-xs text-slate-500">
                {customer.service_plan.download_speed}/{customer.service_plan.upload_speed} Mbps
                {customer.service_plan.technology && ` · ${customer.service_plan.technology}`}
              </div>
              <div className="text-sm font-semibold text-brand-600">
                ${customer.service_plan.monthly_price}/mo
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-400">No plan assigned</p>
          )}
        </div>
      </div>

      {/* Jake2 network diagnostic */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Zap size={14} className="text-brand-600"/> Jake2 Network Status
          </div>
          <button onClick={askJake} disabled={aiLoading}
            className="btn-ghost text-xs gap-1 py-1 px-2">
            {aiLoading
              ? <><Activity size={12} className="animate-spin"/> Querying...</>
              : 'Query network'}
          </button>
        </div>
        {aiAnswer
          ? <pre className="text-xs bg-surface-1 rounded-lg p-3 max-h-32 overflow-auto text-slate-700 whitespace-pre-wrap">{aiAnswer}</pre>
          : <p className="text-xs text-slate-400">Click "Query network" to ask Jake2 about this subscriber's connection.</p>}
      </div>

      {/* Invoices */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Receipt size={14}/> Invoices
          </div>
          <Link to="/invoices" className="text-xs text-brand-600 hover:underline">View all</Link>
        </div>
        {invoices.length === 0 ? (
          <p className="text-xs text-slate-400">No invoices</p>
        ) : (
          <div className="space-y-2">
            {invoices.map(inv => (
              <div key={inv.id}
                className="flex items-center justify-between text-sm border-b border-surface-3 pb-2 last:border-0 last:pb-0">
                <div>
                  <span className="font-medium text-slate-700">${(inv.amount ?? 0).toFixed(2)}</span>
                  <span className="text-slate-400 text-xs ml-2">
                    due {inv.due_date ? new Date(inv.due_date).toLocaleDateString() : '—'}
                  </span>
                </div>
                <span className={
                  inv.status === 'paid' ? 'badge-green' :
                  inv.status === 'overdue' ? 'badge-red' : 'badge-amber'
                }>{inv.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tickets */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Ticket size={14}/> Support Tickets
          </div>
          <Link to="/tickets" className="text-xs text-brand-600 hover:underline">View all</Link>
        </div>
        {tickets.length === 0 ? (
          <p className="text-xs text-slate-400">No tickets</p>
        ) : (
          <div className="space-y-2">
            {tickets.map(t => (
              <div key={t.id}
                className="flex items-start justify-between border-b border-surface-3 pb-2 last:border-0 last:pb-0">
                <div>
                  <div className="text-sm font-medium text-slate-700">{t.title}</div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    {t.created_at ? new Date(t.created_at).toLocaleDateString() : ''}
                    {t.priority && ` · ${t.priority} priority`}
                  </div>
                </div>
                <span className={
                  t.status === 'open' ? 'badge-red' :
                  t.status === 'in_progress' ? 'badge-amber' :
                  'badge-green'
                }>{t.status?.replace('_', ' ')}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
