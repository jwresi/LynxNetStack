import React, { useEffect, useState } from 'react'
import { CreditCard, Plus, Edit2, Trash2, Wifi, X, Check, Loader } from 'lucide-react'
import { crm } from '../services/api'

interface Plan {
  id: number; name: string; download_speed: number; upload_speed: number
  monthly_price: number; technology?: string; service_type?: string; description?: string
}

const EMPTY: Omit<Plan,'id'> = { name:'', download_speed:100, upload_speed:100, monthly_price:30, technology:'ethernet', service_type:'residential', description:'' }

function PlanModal({ plan, onSave, onClose }: { plan: Partial<Plan>|null; onSave:(p:any)=>void; onClose:()=>void }) {
  const [form, setForm] = useState<any>(plan ?? EMPTY)
  const [saving, setSaving] = useState(false)
  const f = (k: string) => (e: React.ChangeEvent<HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement>) =>
    setForm((p: any) => ({ ...p, [k]: e.target.value }))

  const save = async () => {
    setSaving(true)
    try {
      const body = { ...form, download_speed: +form.download_speed, upload_speed: +form.upload_speed, monthly_price: +form.monthly_price }
      const result = form.id ? await crm.updatePlan(form.id, body) : await crm.createPlan(body)
      onSave(result)
    } catch (e: any) { alert(e.message) }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h3 className="font-semibold text-slate-800">{form.id ? 'Edit Plan' : 'New Service Plan'}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18}/></button>
        </div>
        <div className="p-5 space-y-3">
          <div><label className="text-xs font-medium text-slate-500 mb-1 block">Plan Name</label>
            <input className="input" value={form.name} onChange={f('name')} placeholder="NYCHA 100 Mbps" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-xs font-medium text-slate-500 mb-1 block">Down (Mbps)</label>
              <input className="input" type="number" value={form.download_speed} onChange={f('download_speed')} /></div>
            <div><label className="text-xs font-medium text-slate-500 mb-1 block">Up (Mbps)</label>
              <input className="input" type="number" value={form.upload_speed} onChange={f('upload_speed')} /></div>
          </div>
          <div><label className="text-xs font-medium text-slate-500 mb-1 block">Monthly Price ($)</label>
            <input className="input" type="number" step="0.01" value={form.monthly_price} onChange={f('monthly_price')} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-xs font-medium text-slate-500 mb-1 block">Technology</label>
              <select className="input" value={form.technology||''} onChange={f('technology')}>
                {['ethernet','fiber','wireless','ghn'].map(t => <option key={t}>{t}</option>)}
              </select></div>
            <div><label className="text-xs font-medium text-slate-500 mb-1 block">Type</label>
              <select className="input" value={form.service_type||''} onChange={f('service_type')}>
                {['residential','business','government'].map(t => <option key={t}>{t}</option>)}
              </select></div>
          </div>
          <div><label className="text-xs font-medium text-slate-500 mb-1 block">Description</label>
            <textarea className="input" rows={2} value={form.description||''} onChange={f('description')} /></div>
        </div>
        <div className="flex gap-2 px-5 pb-5">
          <button onClick={onClose} className="btn-ghost flex-1 justify-center">Cancel</button>
          <button onClick={save} disabled={saving} className="btn-primary flex-1 justify-center">
            {saving ? <Loader size={14} className="animate-spin"/> : <Check size={14}/>} Save
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ServicePlans() {
  const [plans, setPlans]   = useState<Plan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState('')
  const [editing, setEditing] = useState<Partial<Plan>|null|false>(false)

  const load = () => {
    setLoading(true)
    crm.servicePlans().then(d => setPlans(Array.isArray(d) ? d : [])).catch(e => setError(e.message)).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const del = async (id: number) => {
    if (!confirm('Delete this plan?')) return
    try { await crm.deletePlan(id); setPlans(p => p.filter(x => x.id !== id)) }
    catch (e: any) { alert(e.message) }
  }

  const techColor: Record<string, string> = { fiber: 'badge-blue', ethernet: 'badge-green', wireless: 'badge-amber', ghn: 'badge-gray' }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">Service Plans</h2>
          <p className="text-xs text-slate-400 mt-0.5">{plans.length} plans configured</p>
        </div>
        <button onClick={() => setEditing({})} className="btn-primary text-sm gap-1.5"><Plus size={14}/> New Plan</button>
      </div>

      {error && <div className="card bg-red-50 border-red-200 text-red-700 text-sm">{error}</div>}

      {loading ? (
        <div className="card text-center py-12 text-slate-400">Loading plans...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {plans.map(p => (
            <div key={p.id} className="card flex flex-col gap-3">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-slate-800">{p.name}</div>
                  <div className="text-xs text-slate-400 mt-0.5">{p.service_type ?? 'residential'}</div>
                </div>
                <div className="text-xl font-bold text-brand-600">${p.monthly_price}<span className="text-xs text-slate-400 font-normal">/mo</span></div>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 text-sm text-slate-600">
                  <Wifi size={14} className="text-brand-500"/>
                  <span className="font-medium">{p.download_speed >= 1000 ? `${p.download_speed/1000}G` : `${p.download_speed}M`}</span>
                  <span className="text-slate-400">↓</span>
                  <span className="font-medium">{p.upload_speed >= 1000 ? `${p.upload_speed/1000}G` : `${p.upload_speed}M`}</span>
                  <span className="text-slate-400">↑</span>
                </div>
                {p.technology && <span className={techColor[p.technology] ?? 'badge-gray'}>{p.technology}</span>}
              </div>

              {p.description && <p className="text-xs text-slate-500 leading-relaxed">{p.description}</p>}

              <div className="flex gap-2 mt-auto pt-2 border-t border-surface-3">
                <button onClick={() => setEditing(p)} className="btn-ghost text-xs gap-1 flex-1 justify-center"><Edit2 size={12}/> Edit</button>
                <button onClick={() => del(p.id)} className="btn-ghost text-xs gap-1 flex-1 justify-center text-red-500 hover:bg-red-50"><Trash2 size={12}/> Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing !== false && (
        <PlanModal
          plan={editing ?? null}
          onSave={result => { load(); setEditing(false) }}
          onClose={() => setEditing(false)}
        />
      )}
    </div>
  )
}
