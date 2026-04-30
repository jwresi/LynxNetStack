import React, { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle, Clock, RefreshCw, Plus, X, Check, Loader } from 'lucide-react'
import { crm } from '../services/api'

interface Invoice {
  id: number; amount: number; status: string; due_date: string; created_at: string
  customer?: { id: number; name: string; email: string }
  customer_id?: number
}

function StatusBadge({ s }: { s: string }) {
  if (s === 'paid')    return <span className="badge-green"><CheckCircle size={10}/> paid</span>
  if (s === 'overdue') return <span className="badge-red"><AlertCircle size={10}/> overdue</span>
  if (s === 'unpaid')  return <span className="badge-amber"><Clock size={10}/> unpaid</span>
  return <span className="badge-gray">{s}</span>
}

function NewInvoiceModal({ onSave, onClose }: { onSave: () => void; onClose: () => void }) {
  const [form, setForm] = useState({ customer_id: '1', amount: '', due_date: '' })
  const [customers, setCustomers] = useState<any[]>([])
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const f = (k: string) => (e: React.ChangeEvent<any>) => setForm(p => ({ ...p, [k]: e.target.value }))

  useEffect(() => {
    crm.customers().then(d => setCustomers(Array.isArray(d) ? d : [])).catch(() => {})
  }, [])

  const save = async () => {
    if (!form.amount || !form.due_date) return
    setSaving(true); setErr('')
    try {
      await crm.createInvoice({
        customer_id: +form.customer_id,
        amount: +form.amount,
        due_date: new Date(form.due_date).toISOString(),
        status: 'unpaid',
      })
      onSave()
    } catch (e: any) { setErr(e.message) }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h3 className="font-semibold text-slate-800">New Invoice</h3>
          <button onClick={onClose}><X size={18} className="text-slate-400"/></button>
        </div>
        <div className="p-5 space-y-3">
          {err && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{err}</div>}
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Subscriber</label>
            <select className="input" value={form.customer_id} onChange={f('customer_id')}>
              {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Amount ($)</label>
            <input className="input" type="number" step="0.01" min="0" value={form.amount}
              onChange={f('amount')} placeholder="30.00"/>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Due Date</label>
            <input className="input" type="date" value={form.due_date} onChange={f('due_date')}/>
          </div>
        </div>
        <div className="flex gap-2 px-5 pb-5">
          <button onClick={onClose} className="btn-ghost flex-1 justify-center">Cancel</button>
          <button onClick={save} disabled={saving || !form.amount || !form.due_date}
            className="btn-primary flex-1 justify-center">
            {saving ? <Loader size={14} className="animate-spin"/> : <Check size={14}/>} Create
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Invoices() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [filter, setFilter]     = useState('all')
  const [showNew, setShowNew]   = useState(false)

  const load = () => {
    setLoading(true); setError('')
    crm.invoices()
      .then(d => setInvoices(Array.isArray(d) ? d : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const markPaid = async (id: number) => {
    try {
      await crm.updateInvoice(id, { status: 'paid' })
      setInvoices(inv => inv.map(i => i.id === id ? { ...i, status: 'paid' } : i))
    } catch (e: any) { alert(e.message) }
  }

  const filtered = filter === 'all' ? invoices : invoices.filter(i => i.status === filter)
  const totalUnpaid  = invoices.filter(i => i.status !== 'paid').reduce((s, i) => s + (i.amount || 0), 0)
  const totalOverdue = invoices.filter(i => i.status === 'overdue').reduce((s, i) => s + (i.amount || 0), 0)
  const totalPaid    = invoices.filter(i => i.status === 'paid').reduce((s, i) => s + (i.amount || 0), 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Invoices</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {invoices.length} total · ${totalUnpaid.toFixed(2)} outstanding
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="btn-ghost text-xs"><RefreshCw size={13}/></button>
          <button onClick={() => setShowNew(true)} className="btn-primary text-sm gap-1.5">
            <Plus size={14}/> New Invoice
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card text-center py-3">
          <div className="text-xl font-bold text-amber-600">${totalUnpaid.toFixed(2)}</div>
          <div className="text-xs text-slate-400 mt-0.5">Outstanding</div>
        </div>
        <div className="card text-center py-3">
          <div className="text-xl font-bold text-red-600">${totalOverdue.toFixed(2)}</div>
          <div className="text-xs text-slate-400 mt-0.5">Overdue</div>
        </div>
        <div className="card text-center py-3">
          <div className="text-xl font-bold text-emerald-600">${totalPaid.toFixed(2)}</div>
          <div className="text-xs text-slate-400 mt-0.5">Collected</div>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-surface-1 rounded-lg p-1 border border-surface-3 w-fit">
        {[['all','All'], ['unpaid','Unpaid'], ['overdue','Overdue'], ['paid','Paid']].map(([v, l]) => (
          <button key={v} onClick={() => setFilter(v)}
            className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors
              ${filter === v ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}>
            {l}
          </button>
        ))}
      </div>

      {error && (
        <div className="card bg-red-50 border-red-200 text-red-700 text-sm flex items-center gap-2">
          <AlertCircle size={14} className="shrink-0"/> {error}
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              {['#', 'Subscriber', 'Amount', 'Due Date', 'Status', ''].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={6} className="text-center py-10 text-slate-400">Loading invoices...</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={6} className="text-center py-10 text-slate-400">No invoices in this view</td></tr>
            )}
            {filtered.map(inv => (
              <tr key={inv.id} className="table-row">
                <td className="px-4 py-3 font-mono text-xs text-slate-500">#{inv.id}</td>
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-800">
                    {inv.customer?.name ?? `Subscriber #${inv.customer_id}`}
                  </div>
                  {inv.customer?.email && (
                    <div className="text-xs text-slate-400">{inv.customer.email}</div>
                  )}
                </td>
                <td className="px-4 py-3 font-semibold text-slate-800">
                  ${(inv.amount ?? 0).toFixed(2)}
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">
                  {inv.due_date ? new Date(inv.due_date).toLocaleDateString() : '—'}
                  {inv.due_date && new Date(inv.due_date) < new Date() && inv.status !== 'paid' && (
                    <div className="text-red-500">overdue</div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge s={inv.status}/>
                </td>
                <td className="px-4 py-3">
                  {inv.status !== 'paid' && (
                    <button onClick={() => markPaid(inv.id)}
                      className="text-xs text-emerald-600 hover:underline font-medium whitespace-nowrap">
                      Mark paid
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && filtered.length > 0 && (
          <div className="px-4 py-2 border-t border-surface-3 bg-surface-1 text-xs text-slate-400">
            Showing {filtered.length} of {invoices.length} invoices
          </div>
        )}
      </div>

      {showNew && (
        <NewInvoiceModal
          onSave={() => { load(); setShowNew(false) }}
          onClose={() => setShowNew(false)}
        />
      )}
    </div>
  )
}
