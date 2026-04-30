import React, { useEffect, useState } from 'react'
import { Ticket as TicketIcon, Plus, ChevronDown, Zap, MessageSquare, X, Check, Loader, AlertCircle, Clock, CheckCircle } from 'lucide-react'
import { crm, jake } from '../services/api'

interface Ticket { id: number; title: string; description: string; status: string; priority: string; created_at: string; customer?: { id: number; name: string } }

const STATUS_COLORS: Record<string, string> = { open:'badge-red', in_progress:'badge-amber', resolved:'badge-green', closed:'badge-gray' }
const PRI_COLORS:    Record<string, string> = { high:'text-red-600', medium:'text-amber-600', low:'text-slate-400' }

function TicketRow({ t, onSelect }: { t: Ticket; onSelect: (t: Ticket) => void }) {
  return (
    <tr className="table-row cursor-pointer" onClick={() => onSelect(t)}>
      <td className="px-4 py-3">
        <div className="font-medium text-slate-800 text-sm">{t.title}</div>
        <div className="text-xs text-slate-400 mt-0.5 truncate max-w-xs">{t.description?.slice(0,80)}{t.description?.length>80?'...':''}</div>
      </td>
      <td className="px-4 py-3 text-sm text-slate-600">{t.customer?.name ?? '—'}</td>
      <td className="px-4 py-3"><span className={STATUS_COLORS[t.status] ?? 'badge-gray'}>{t.status?.replace('_',' ')}</span></td>
      <td className={`px-4 py-3 text-xs font-semibold ${PRI_COLORS[t.priority] ?? ''}`}>{t.priority}</td>
      <td className="px-4 py-3 text-xs text-slate-400">{t.created_at ? new Date(t.created_at).toLocaleDateString() : '—'}</td>
    </tr>
  )
}

function TicketDetail({ t, onClose, onUpdated }: { t: Ticket; onClose: ()=>void; onUpdated: (t:Ticket)=>void }) {
  const [status, setStatus] = useState(t.status)
  const [aiAnswer, setAiAnswer] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)

  const diagnose = async () => {
    setAiLoading(true); setAiAnswer('')
    try {
      const r = await jake.query(`troubleshoot: ${t.title}. Details: ${t.description}`)
      setAiAnswer(r.answer)
    } catch (e: any) { setAiAnswer(`Error: ${e.message}`) }
    setAiLoading(false)
  }

  const saveStatus = async () => {
    setSaving(true)
    try { const updated = await crm.updateTicket(t.id, { status }); onUpdated(updated) }
    catch (e: any) { alert(e.message) }
    setSaving(false)
  }

  const addComment = async () => {
    if (!comment.trim()) return
    setSaving(true)
    try { await crm.addComment(t.id, { content: comment, author: 'operator' }); setComment('') }
    catch (e: any) { alert(e.message) }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h3 className="font-semibold text-slate-800 text-sm">Ticket #{t.id}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18}/></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <div className="font-semibold text-slate-800">{t.title}</div>
            <div className="text-xs text-slate-500 mt-0.5">{t.customer?.name} · {t.created_at ? new Date(t.created_at).toLocaleString() : ''}</div>
          </div>
          <p className="text-sm text-slate-600 leading-relaxed">{t.description}</p>

          {/* Status update */}
          <div className="flex gap-2 items-center">
            <select className="input flex-1" value={status} onChange={e => setStatus(e.target.value)}>
              {['open','in_progress','resolved','closed'].map(s => <option key={s} value={s}>{s.replace('_',' ')}</option>)}
            </select>
            <button onClick={saveStatus} disabled={saving || status === t.status} className="btn-primary px-3 py-2 text-sm">
              {saving ? <Loader size={14} className="animate-spin"/> : <Check size={14}/>}
            </button>
          </div>

          {/* Jake2 diagnostic */}
          <div className="border border-surface-3 rounded-xl p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-medium text-brand-700">
                <Zap size={12}/> Jake2 AI Diagnostic
              </div>
              <button onClick={diagnose} disabled={aiLoading} className="text-xs text-brand-600 hover:underline">
                {aiLoading ? 'Diagnosing...' : 'Run diagnostic'}
              </button>
            </div>
            {aiLoading && <div className="flex items-center gap-1.5 text-xs text-slate-400"><Loader size={10} className="animate-spin"/> Querying network intelligence...</div>}
            {aiAnswer && <pre className="text-xs text-slate-700 whitespace-pre-wrap bg-surface-1 rounded-lg p-2 max-h-32 overflow-auto">{aiAnswer}</pre>}
          </div>

          {/* Add comment */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-slate-500">Add Note</label>
            <textarea className="input" rows={2} value={comment} onChange={e => setComment(e.target.value)} placeholder="Tech notes, next steps..."/>
            <button onClick={addComment} disabled={saving || !comment.trim()} className="btn-primary text-sm px-3 py-1.5">
              <MessageSquare size={13}/> Add Note
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function NewTicketModal({ onSave, onClose }: { onSave: ()=>void; onClose: ()=>void }) {
  const [form, setForm] = useState({ title:'', description:'', priority:'medium', customer_id: 1 })
  const [customers, setCustomers] = useState<any[]>([])
  const [saving, setSaving] = useState(false)
  const f = (k: string) => (e: React.ChangeEvent<any>) => setForm(p => ({ ...p, [k]: e.target.value }))

  useEffect(() => { crm.customers().then(d => setCustomers(Array.isArray(d) ? d : [])).catch(() => {}) }, [])

  const save = async () => {
    setSaving(true)
    try { await crm.createTicket({ ...form, customer_id: +form.customer_id }); onSave() }
    catch (e: any) { alert(e.message) }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h3 className="font-semibold text-slate-800">New Ticket</h3>
          <button onClick={onClose}><X size={18} className="text-slate-400"/></button>
        </div>
        <div className="p-5 space-y-3">
          <div><label className="text-xs font-medium text-slate-500 mb-1 block">Subscriber</label>
            <select className="input" value={form.customer_id} onChange={f('customer_id')}>
              {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></div>
          <div><label className="text-xs font-medium text-slate-500 mb-1 block">Title</label>
            <input className="input" value={form.title} onChange={f('title')} placeholder="Brief issue description"/></div>
          <div><label className="text-xs font-medium text-slate-500 mb-1 block">Description</label>
            <textarea className="input" rows={3} value={form.description} onChange={f('description')} placeholder="Full details..."/></div>
          <div><label className="text-xs font-medium text-slate-500 mb-1 block">Priority</label>
            <select className="input" value={form.priority} onChange={f('priority')}>
              {['low','medium','high'].map(p => <option key={p}>{p}</option>)}
            </select></div>
        </div>
        <div className="flex gap-2 px-5 pb-5">
          <button onClick={onClose} className="btn-ghost flex-1 justify-center">Cancel</button>
          <button onClick={save} disabled={saving || !form.title} className="btn-primary flex-1 justify-center">
            {saving ? <Loader size={14} className="animate-spin"/> : <Check size={14}/>} Create Ticket
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Tickets() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState('')
  const [filter, setFilter] = useState('open')
  const [selected, setSelected] = useState<Ticket|null>(null)
  const [showNew, setShowNew] = useState(false)

  const load = () => {
    setLoading(true)
    crm.tickets().then(d => setTickets(Array.isArray(d) ? d : [])).catch(e => setError(e.message)).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const filtered = filter === 'all' ? tickets : tickets.filter(t => t.status === filter)
  const counts = { open: tickets.filter(t=>t.status==='open').length, in_progress: tickets.filter(t=>t.status==='in_progress').length, resolved: tickets.filter(t=>t.status==='resolved').length }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Tickets</h2>
          <p className="text-xs text-slate-400 mt-0.5">{counts.open} open · {counts.in_progress} in progress · {counts.resolved} resolved</p>
        </div>
        <button onClick={() => setShowNew(true)} className="btn-primary text-sm gap-1.5"><Plus size={14}/> New Ticket</button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-surface-1 rounded-lg p-1 border border-surface-3 w-fit">
        {[['all','All'],['open','Open'],['in_progress','In Progress'],['resolved','Resolved']].map(([v,l]) => (
          <button key={v} onClick={() => setFilter(v)}
            className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${filter===v ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}>
            {l}
          </button>
        ))}
      </div>

      {error && <div className="card bg-red-50 border-red-200 text-red-700 text-sm">{error}</div>}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-3 bg-surface-1">
              {['Issue','Subscriber','Status','Priority','Created'].map(h => (
                <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="text-center py-10 text-slate-400">Loading tickets...</td></tr>}
            {!loading && filtered.length === 0 && <tr><td colSpan={5} className="text-center py-10 text-slate-400">No tickets in this view</td></tr>}
            {filtered.map(t => <TicketRow key={t.id} t={t} onSelect={setSelected}/>)}
          </tbody>
        </table>
      </div>

      {selected && <TicketDetail t={selected} onClose={() => setSelected(null)} onUpdated={updated => { setTickets(ts => ts.map(t => t.id===updated.id ? {...t,...updated} : t)); setSelected(null) }}/>}
      {showNew && <NewTicketModal onSave={() => { load(); setShowNew(false) }} onClose={() => setShowNew(false)}/>}
    </div>
  )
}
