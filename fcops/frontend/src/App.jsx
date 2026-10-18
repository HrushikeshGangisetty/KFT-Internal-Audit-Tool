import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from './lib/auth.jsx'
import { api, listOf } from './lib/api'
import { Empty, Icon, PageSkeleton, SkeletonText, initials, when } from './components/ui.jsx'

import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import FcList from './pages/FcList.jsx'
import FcCreate from './pages/FcCreate.jsx'
import FcDetail from './pages/FcDetail.jsx'
import IssueList from './pages/IssueList.jsx'
import IssueCreate from './pages/IssueCreate.jsx'
import IssueDetail from './pages/IssueDetail.jsx'
import KnownIssues from './pages/KnownIssues.jsx'
import Search from './pages/Search.jsx'
import Admin from './pages/Admin.jsx'
import PushUpdate from './pages/PushUpdate.jsx'
import ManageFirmware from './pages/ManageFirmware.jsx'
import TestConfiguration from './pages/TestConfiguration.jsx'
import FcModels from './pages/FcModels.jsx'
import ParamCompare from './pages/ParamCompare.jsx'
import AuditLog from './pages/AuditLog.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/fcs', label: 'Flight Controllers', icon: 'chip' },
  { to: '/issues', label: 'Issues', icon: 'alert' },
  { to: '/search', label: 'Knowledge Search', icon: 'search' },
  { to: '/known-issues', label: 'Known Issues', icon: 'book' },
  { to: '/audit', label: 'Audit Log', icon: 'history' },
  { to: '/param-compare', label: 'Parameter Compare', icon: 'compare' },
  { section: 'Software', perm: 'can_push_software_update' },
  { to: '/software/push-update', label: 'Push Update', icon: 'upload', perm: 'can_push_software_update' },
  { section: 'Firmware', perm: 'can_manage_firmware' },
  { to: '/firmware/builds', label: 'Manage Firmware', icon: 'cpu', perm: 'can_manage_firmware' },
  { section: 'Manager', perm: 'can_configure_tests' },
  { to: '/manager/test-configuration', label: 'Test Configuration', icon: 'sliders', perm: 'can_configure_tests' },
  { to: '/manager/fc-models', label: 'FC Models', icon: 'layers', perm: 'can_configure_tests' },
  { section: 'Administration', perm: 'is_admin' },
  { to: '/admin', label: 'Admin', icon: 'shield', perm: 'is_admin' },
]

function Shell({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)
  const name = user?.full_name || user?.username
  const signOut = async () => { await logout(); navigate('/login') }

  useEffect(() => {
    let alive = true
    const poll = () =>
      api('/api/notifications/unread_count/')
        .then((d) => alive && setUnread(d.count))
        .catch(() => {})
    poll()
    const t = setInterval(poll, 30000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">FC</div>
          <div className="brand-name">FC Knowledge<small>Production · Traceability</small></div>
        </div>
        <nav>
          {NAV.filter((n) => !n.perm || user?.permissions?.[n.perm]).map((n) =>
            n.section ? (
              <div key={n.section} className="nav-section">{n.section}</div>
            ) : (
              <NavLink key={n.to} to={n.to} end={n.end}>
                <Icon name={n.icon} />{n.label}
              </NavLink>
            ),
          )}
        </nav>
        <div className="spacer" />
        <div className="who">
          <div className="avatar">{initials(name)}</div>
          <div className="who-text">
            <strong>{name}</strong>
            <span>{user?.role_display} · {user?.department_name || 'No department'}</span>
          </div>
          <button className="icon-btn" title="Sign out" aria-label="Sign out" onClick={signOut}>
            <Icon name="logout" />
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <span className="topbar-title">Internal Production &amp; Engineering Knowledge System</span>
          <div className="spacer" />
          <Notifications unread={unread} onRead={() => setUnread(0)} />
          <button className="icon-btn mobile-only" title="Sign out" aria-label="Sign out" onClick={signOut}>
            <Icon name="logout" />
          </button>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}

function Notifications({ unread, onRead }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next) {
      setItems(null)
      const data = await api('/api/notifications/', { params: { page_size: 15 } })
      setItems(listOf(data))
      await api('/api/notifications/mark_all_read/', { method: 'POST' })
      onRead()
    }
  }

  return (
    <div className="popover-anchor" ref={ref}>
      <button className="icon-btn" onClick={toggle} aria-expanded={open}
              aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`}>
        <Icon name="bell" size={18} />
        {unread ? <span className="badge-dot">{unread > 99 ? '99+' : unread}</span> : null}
      </button>
      {open ? (
        <div className="popover">
          <div className="popover-head">Notifications</div>
          <div className="popover-body">
            {items === null ? (
              <div style={{ padding: 16 }}><SkeletonText lines={4} /></div>
            ) : items.length === 0 ? (
              <div style={{ padding: 16 }}><Empty icon="bell">You're all caught up.</Empty></div>
            ) : items.map((n) => (
              <div key={n.id} className="notif">
                <div>{n.message}</div>
                <div className="meta">{when(n.created_at)}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="content"><PageSkeleton stats={4} /></div>
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/fcs" element={<FcList />} />
        <Route path="/fcs/new" element={<FcCreate />} />
        <Route path="/fcs/:id" element={<FcDetail />} />
        <Route path="/issues" element={<IssueList />} />
        <Route path="/issues/new" element={<IssueCreate />} />
        <Route path="/issues/:id" element={<IssueDetail />} />
        <Route path="/known-issues" element={<KnownIssues />} />
        <Route path="/search" element={<Search />} />
        <Route path="/audit" element={<AuditLog />} />
        <Route path="/param-compare" element={<ParamCompare />} />
        <Route path="/software/push-update" element={<PushUpdate />} />
        <Route path="/firmware/builds" element={<ManageFirmware />} />
        <Route path="/manager/test-configuration" element={<TestConfiguration />} />
        <Route path="/manager/fc-models" element={<FcModels />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Empty title="Page not found">That page doesn't exist.</Empty>} />
      </Routes>
    </Shell>
  )
}
