import React, { useState, useRef, useEffect } from 'react'
import { Send, Zap, Activity, ChevronRight } from 'lucide-react'
import { jake } from '../services/api'

interface Msg { role: 'user' | 'jake'; text: string; raw?: any; ts: number }

const SUGGESTIONS = [
  'how many customers are online right now',
  'which switches have high error rates',
  'which sites have the most offline customers',
  'which mcp should i use for bridge vlan issues',
  'are there any switches on old firmware',
  'show me the status of all sites',
  'what is online at chenoweth',
  'how is nycha doing',
]

export default function JakeQuery() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])

  const send = async (q?: string) => {
    const query = (q ?? input).trim()
    if (!query || loading) return
    setInput('')
    setMsgs(m => [...m, { role: 'user', text: query, ts: Date.now() }])
    setLoading(true)
    try {
      const r = await jake.query(query)
      const text = r.operator_summary ?? r.assistant_answer ?? JSON.stringify(r.result ?? r, null, 2)
      setMsgs(m => [...m, { role: 'jake', text, raw: r, ts: Date.now() }])
    } catch (e: any) {
      setMsgs(m => [...m, { role: 'jake', text: `Error: ${e.message}`, ts: Date.now() }])
    }
    setLoading(false)
  }

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto gap-4">
      {/* Header */}
      <div className="card flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center">
          <Zap size={16} className="text-white" />
        </div>
        <div>
          <div className="font-semibold text-slate-800 text-sm">Jake2 Network Intelligence</div>
          <div className="text-xs text-slate-400">Ask anything about the network in plain English</div>
        </div>
      </div>

      {/* Suggestions */}
      {msgs.length === 0 && (
        <div className="card">
          <p className="text-xs text-slate-500 mb-3 font-medium">Try asking:</p>
          <div className="flex flex-col gap-1.5">
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => send(s)}
                className="flex items-center gap-2 text-left text-sm text-slate-600 hover:text-brand-700 hover:bg-surface-1 px-3 py-1.5 rounded-lg transition-colors group">
                <ChevronRight size={12} className="text-slate-300 group-hover:text-brand-500 shrink-0" />
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 flex flex-col gap-3 overflow-y-auto">
        {msgs.map((m, i) => (
          <div key={i} className={`flex flex-col gap-1 ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
            <div className={`text-[10px] font-medium uppercase tracking-wide ${m.role === 'user' ? 'text-brand-500' : 'text-slate-400'}`}>
              {m.role === 'user' ? 'You' : 'Jake2'}
            </div>
            <div className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === 'user' ? 'bg-brand-600 text-white' : 'bg-white border border-surface-3 text-slate-700'
            }`}>
              <pre className="whitespace-pre-wrap font-sans">{m.text}</pre>
            </div>
            {m.raw && (
              <details className="max-w-[85%]">
                <summary className="text-[10px] text-slate-400 cursor-pointer hover:text-slate-600">raw data</summary>
                <pre className="text-[10px] bg-surface-1 rounded-lg p-2 mt-1 overflow-auto max-h-48 text-slate-600">
                  {JSON.stringify(m.raw, null, 2)}
                </pre>
              </details>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Activity size={12} className="animate-spin" /> Jake2 is thinking...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="card flex gap-3 items-center p-3">
        <input
          className="input flex-1 border-0 focus:ring-0 px-1 text-sm bg-transparent"
          placeholder="Ask Jake2 anything about the network..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          disabled={loading}
        />
        <button onClick={() => send()} disabled={loading || !input.trim()}
          className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center text-white disabled:opacity-40 hover:bg-brand-700 transition-colors">
          <Send size={14} />
        </button>
      </div>
    </div>
  )
}
