import React, { useState } from 'react'
import { Zap, AlertCircle, Loader } from 'lucide-react'
import { crm, setCrmToken } from '../services/api'

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [user, setUser] = useState('admin')
  const [pass, setPass] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const data = await crm.login(user, pass)
      if (data.access_token) {
        setCrmToken(data.access_token)
        onLogin()
      } else {
        setError(data.detail || 'Login failed')
      }
    } catch (err: any) {
      setError(err.message || 'Could not reach LynxMSP backend')
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-surface-1 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-brand-600 flex items-center justify-center">
            <Zap size={20} className="text-white" />
          </div>
          <div>
            <div className="font-bold text-slate-800 text-lg leading-tight">LynxNetStack</div>
            <div className="text-xs text-slate-400">Operator Portal</div>
          </div>
        </div>

        <form onSubmit={submit} className="card space-y-4">
          <h2 className="text-sm font-semibold text-slate-700">Sign in</h2>

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              <AlertCircle size={14} className="shrink-0" /> {error}
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Username</label>
            <input className="input" value={user} onChange={e => setUser(e.target.value)} required />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">Password</label>
            <input className="input" type="password" value={pass} onChange={e => setPass(e.target.value)}
              placeholder="admin" required />
          </div>

          <button type="submit" disabled={loading}
            className="btn-primary w-full justify-center disabled:opacity-50">
            {loading ? <><Loader size={14} className="animate-spin" /> Signing in...</> : 'Sign in'}
          </button>

          <p className="text-xs text-slate-400 text-center">Default: admin / admin</p>
        </form>
      </div>
    </div>
  )
}
