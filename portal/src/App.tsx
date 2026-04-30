import React, { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, Receipt, Ticket, Network, Server,
  Settings, ChevronLeft, ChevronRight, Zap, Activity,
  Building2, MapPin, Terminal, CreditCard, LogOut
} from 'lucide-react'
import clsx from 'clsx'
import { getCrmToken, setCrmToken } from './services/api'

import LoginPage        from './pages/Login'
import Dashboard        from './pages/Dashboard'
import Subscribers      from './pages/Subscribers'
import SubscriberDetail from './pages/SubscriberDetail'
import Invoices         from './pages/Invoices'
import Tickets          from './pages/Tickets'
import Network          from './pages/Network'
import Switches         from './pages/Switches'
import JakeQuery        from './pages/JakeQuery'
import ServicePlans     from './pages/ServicePlans'
import SettingsPage     from './pages/Settings'

const NAV = [
  { section: 'Operations' },
  { to: '/',           icon: LayoutDashboard, label: 'Dashboard'     },
  { to: '/jake',       icon: Terminal,        label: 'Jake2 Query'   },
  { to: '/network',    icon: Activity,        label: 'Network Map'   },
  { to: '/switches',   icon: Server,          label: 'Switches'      },
  { section: 'Subscribers' },
  { to: '/subscribers', icon: Users,          label: 'Subscribers'   },
  { to: '/invoices',    icon: Receipt,        label: 'Invoices'      },
  { to: '/tickets',     icon: Ticket,         label: 'Tickets'       },
  { to: '/plans',       icon: CreditCard,     label: 'Service Plans' },
  { section: 'System' },
  { to: '/settings',    icon: Settings,       label: 'Settings'      },
]

function Sidebar({ collapsed, setCollapsed }: { collapsed: boolean; setCollapsed: (v: boolean) => void }) {
  return (
    <aside className={clsx(
      'h-screen sticky top-0 flex flex-col bg-white border-r border-surface-3 transition-all duration-200 shrink-0',
      collapsed ? 'w-14' : 'w-56'
    )}>
      <div className="flex items-center gap-2.5 px-3 py-4 border-b border-surface-3">
        <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shrink-0">
          <Zap size={16} className="text-white" />
        </div>
        {!collapsed && <span className="font-bold text-slate-800 text-sm leading-tight">LynxNetStack</span>}
      </div>
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {NAV.map((item, i) => {
          if ('section' in item) {
            return collapsed ? (
              <div key={i} className="h-px bg-surface-3 my-2 mx-1" />
            ) : (
              <p key={i} className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                {item.section}
              </p>
            )
          }
          const Icon = item.icon
          return (
            <NavLink key={item.to} to={item.to!} end={item.to === '/'}
              className={({ isActive }) => clsx('sidebar-link', isActive ? 'sidebar-link-active' : 'sidebar-link-default')}>
              <Icon size={16} className="shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          )
        })}
      </nav>
      <button onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-center py-3 border-t border-surface-3 text-slate-400 hover:text-slate-600 hover:bg-surface-2 transition-colors">
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
    </aside>
  )
}

function Header({ onLogout }: { onLogout: () => void }) {
  const loc = useLocation()
  const title = NAV.find(n => 'to' in n && n.to === loc.pathname)?.label ?? 'LynxNetStack'
  return (
    <header className="h-14 bg-white border-b border-surface-3 px-6 flex items-center justify-between sticky top-0 z-10">
      <h1 className="text-sm font-semibold text-slate-700">{title}</h1>
      <div className="flex items-center gap-3">
        <a href="http://localhost:3020" target="_blank" rel="noopener" className="btn-ghost text-xs gap-1.5">
          Tech App
        </a>
        <a href="http://localhost:8017" target="_blank" rel="noopener" className="btn-ghost text-xs gap-1.5">
          Jake2
        </a>
        <button onClick={onLogout} title="Sign out"
          className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center text-white text-xs font-bold hover:bg-brand-700 transition-colors">
          R
        </button>
      </div>
    </header>
  )
}

function Portal() {
  const [collapsed, setCollapsed] = useState(false)
  const handleLogout = () => { setCrmToken(null); window.location.reload() }
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header onLogout={handleLogout} />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/"              element={<Dashboard />} />
            <Route path="/jake"          element={<JakeQuery />} />
            <Route path="/network"       element={<Network />} />
            <Route path="/switches"      element={<Switches />} />
            <Route path="/subscribers"   element={<Subscribers />} />
            <Route path="/subscribers/:id" element={<SubscriberDetail />} />
            <Route path="/invoices"      element={<Invoices />} />
            <Route path="/tickets"       element={<Tickets />} />
            <Route path="/plans"         element={<ServicePlans />} />
            <Route path="/settings"      element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(!!getCrmToken())
  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />
  return <BrowserRouter><Portal /></BrowserRouter>
}
