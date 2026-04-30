import React from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Home, Wifi, Map, Search, Settings } from 'lucide-react'
import clsx from 'clsx'
import HomeScreen   from './pages/HomeScreen'
import Onboard      from './pages/Onboard'
import PortMap      from './pages/PortMap'
import SubLookup    from './pages/SubLookup'
import TechSettings from './pages/TechSettings'

const TABS = [
  { to: '/',        icon: Home,     label: 'Home'    },
  { to: '/onboard', icon: Wifi,     label: 'Onboard' },
  { to: '/portmap', icon: Map,      label: 'Port Map'},
  { to: '/lookup',  icon: Search,   label: 'Lookup'  },
  { to: '/settings',icon: Settings, label: 'Settings'},
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen pb-20">
        <Routes>
          <Route path="/"         element={<HomeScreen />} />
          <Route path="/onboard"  element={<Onboard />} />
          <Route path="/portmap"  element={<PortMap />} />
          <Route path="/lookup"   element={<SubLookup />} />
          <Route path="/settings" element={<TechSettings />} />
        </Routes>
      </div>
      <nav className="tab-bar">
        {TABS.map(t => (
          <NavLink key={t.to} to={t.to} end={t.to === '/'}
            className={({ isActive }) => clsx('tab-item', isActive ? 'tab-active' : 'tab-idle')}>
            <t.icon size={20} />
            <span className="text-[10px] font-medium">{t.label}</span>
          </NavLink>
        ))}
      </nav>
    </BrowserRouter>
  )
}
