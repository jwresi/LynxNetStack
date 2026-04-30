import React, { useEffect, useState } from 'react'
import { crm } from '../services/api'
import { Receipt, DollarSign } from 'lucide-react'

interface Invoice { id: number; invoice_number?: string; customer_name?: string; amount?: number; status?: string; due_date?: string }

export default function Invoices() {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState('')

  useEffect(() => {
    crm.invoices().then(d => setInvoices(Array.isArray(d) ? d : d.items ?? []))
      .catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  const statusBadge = (s?: string) => {
    if (!s) return <span className="badge-gray">—</span>
    if (s === 'paid') return <span className="badge-green">paid</span>
    if (s === 'overdue') return <span className="badge-red">overdue</span>
    if (s === 'open' || s === 'pending') return <span className="badge-blue">open</span>
    return <span className="badge-gray">{s}</span>
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">Invoices</h2>
      {error && <div className="card bg-red-50 border-red-200 text-red-700 text-sm">{error}</div>}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              {['#', 'Customer', 'Amount', 'Due', 'Status'].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="text-center py-8 text-slate-400">Loading...</td></tr>}
            {!loading && invoices.length === 0 && <tr><td colSpan={5} className="text-center py-8 text-slate-400">No invoices</td></tr>}
            {invoices.map(inv => (
              <tr key={inv.id} className="table-row">
                <td className="px-4 py-2.5 font-mono text-xs">{inv.invoice_number ?? inv.id}</td>
                <td className="px-4 py-2.5">{inv.customer_name ?? '—'}</td>
                <td className="px-4 py-2.5">${(inv.amount ?? 0).toFixed(2)}</td>
                <td className="px-4 py-2.5 text-slate-500 text-xs">{inv.due_date ?? '—'}</td>
                <td className="px-4 py-2.5">{statusBadge(inv.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
