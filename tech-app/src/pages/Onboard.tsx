import React, { useState } from 'react'
import { Wifi, Search, CheckCircle, AlertCircle, Loader, ChevronDown } from 'lucide-react'

type Step = 'scan' | 'found' | 'assign' | 'done' | 'error'

interface Device { mac: string; ip: string; model: string; identity: string }

export default function Onboard() {
  const [step, setStep] = useState<Step>('scan')
  const [device, setDevice] = useState<Device | null>(null)
  const [building, setBuilding] = useState('')
  const [unit, setUnit] = useState('')
  const [scanning, setScanning] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const scanNetwork = async () => {
    setScanning(true)
    setErrorMsg('')
    try {
      const r = await fetch('/api/prov/api/devices')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      const devices: Device[] = Array.isArray(data) ? data : data.devices ?? []
      if (devices.length > 0) {
        setDevice(devices[0])
        setStep('found')
      } else {
        setErrorMsg('No devices detected on the provisioning VLAN. Check the switch port and CPE power.')
        setStep('error')
      }
    } catch (e: any) {
      setErrorMsg(`Scan failed: ${e.message}. Is Provisioner running on :5001?`)
      setStep('error')
    }
    setScanning(false)
  }

  const assignDevice = async () => {
    if (!building.trim() || !unit.trim()) {
      setErrorMsg('Building ID and unit are required')
      return
    }
    // In production this would: create Tenant in NetBox, link Circuit, push config via tikfig+ssh_mcp
    setStep('done')
  }

  return (
    <div className="px-4 pt-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Onboard CPE</h1>
        <p className="text-sm text-slate-500 mt-0.5">Scan and register a new device</p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {(['scan','found','assign','done'] as Step[]).map((s, i, arr) => (
          <React.Fragment key={s}>
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
              step === s ? 'bg-brand-600 text-white' :
              arr.indexOf(step) > i ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-400'
            }`}>{arr.indexOf(step) > i ? '✓' : i + 1}</div>
            {i < arr.length - 1 && <div className={`flex-1 h-0.5 rounded ${arr.indexOf(step) > i ? 'bg-emerald-400' : 'bg-slate-200'}`} />}
          </React.Fragment>
        ))}
      </div>

      {/* Step: Scan */}
      {step === 'scan' && (
        <div className="space-y-4">
          <div className="card text-center py-8 space-y-4">
            <div className="w-16 h-16 rounded-full bg-brand-50 flex items-center justify-center mx-auto">
              <Wifi size={28} className="text-brand-600" />
            </div>
            <div>
              <p className="font-semibold text-slate-800">Ready to scan</p>
              <p className="text-sm text-slate-400 mt-1">Connect the CPE to the provisioning port, then tap Scan</p>
            </div>
          </div>
          <button className="btn-primary" onClick={scanNetwork} disabled={scanning}>
            {scanning ? <><Loader size={16} className="animate-spin" /> Scanning...</> : <><Search size={16} /> Scan Network</>}
          </button>
        </div>
      )}

      {/* Step: Found */}
      {step === 'found' && device && (
        <div className="space-y-4">
          <div className="card space-y-3">
            <div className="flex items-center gap-2 text-emerald-600">
              <CheckCircle size={16} /> <span className="font-semibold text-sm">Device detected</span>
            </div>
            {[['MAC', device.mac], ['IP', device.ip], ['Model', device.model], ['Identity', device.identity]].map(([k,v]) => (
              <div key={k} className="flex justify-between text-sm border-t border-surface-3 pt-2 first:border-0 first:pt-0">
                <span className="text-slate-400">{k}</span>
                <span className="font-mono text-slate-700 text-xs">{v || '—'}</span>
              </div>
            ))}
          </div>
          <button className="btn-primary" onClick={() => setStep('assign')}>
            Assign to Unit →
          </button>
          <button className="btn-outline" onClick={() => setStep('scan')}>Rescan</button>
        </div>
      )}

      {/* Step: Assign */}
      {step === 'assign' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">Assign this device to a subscriber unit in NetBox.</p>
          {errorMsg && <div className="card bg-red-50 border-red-200 text-red-700 text-xs">{errorMsg}</div>}
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1.5 block">Building ID</label>
              <input className="input" placeholder="e.g. 000007.001" value={building} onChange={e => setBuilding(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1.5 block">Unit</label>
              <input className="input" placeholder="e.g. 1B" value={unit} onChange={e => setUnit(e.target.value)} />
            </div>
          </div>
          <button className="btn-primary" onClick={assignDevice}>Provision Unit →</button>
          <button className="btn-outline" onClick={() => setStep('found')}>← Back</button>
        </div>
      )}

      {/* Step: Done */}
      {step === 'done' && (
        <div className="card text-center py-8 space-y-4">
          <div className="w-16 h-16 rounded-full bg-emerald-50 flex items-center justify-center mx-auto">
            <CheckCircle size={28} className="text-emerald-500" />
          </div>
          <div>
            <p className="font-semibold text-slate-800">Unit provisioned!</p>
            <p className="text-sm text-slate-400 mt-1">{building} / {unit} — subscriber record created in NetBox</p>
          </div>
          <button className="btn-outline" onClick={() => { setStep('scan'); setDevice(null); setBuilding(''); setUnit('') }}>
            Onboard another
          </button>
        </div>
      )}

      {/* Error */}
      {step === 'error' && (
        <div className="space-y-4">
          <div className="card bg-red-50 border-red-200 space-y-2">
            <div className="flex items-center gap-2 text-red-600"><AlertCircle size={15} /><span className="font-semibold text-sm">Scan failed</span></div>
            <p className="text-xs text-red-600">{errorMsg}</p>
          </div>
          <button className="btn-primary" onClick={() => setStep('scan')}>Try again</button>
        </div>
      )}
    </div>
  )
}
