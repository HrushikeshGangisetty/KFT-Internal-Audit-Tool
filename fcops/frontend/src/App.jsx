import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from './lib/auth.jsx'
import { api, listOf } from './lib/api'

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
import AuditLog from './pages/AuditLog.jsx'

function Shell({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [unread, setUnread] = useState(0)

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
          FC Knowledge System
          <small>Production · Traceability · Issues</small>
        </div>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/fcs">Flight Controllers</NavLink>
          <NavLink to="/issues">Issues</NavLink>
          <NavLink to="/search">Knowledge Search</NavLink>
          <NavLink to="/known-issues">Known Issues</NavLink>
          <NavLink to="/audit">Audit Log</NavLink>

          {user?.permissions?.can_push_software_update ? (
            <>
              <div className="nav-section">Software</div>
              <NavLink to="/software/push-update">Push Update</NavLink>
            </>
          ) : null}

          {user?.permissions?.can_manage_firmware ? (
            <>
              <div className="nav-section">Firmware</div>
              <NavLink to="/firmware/builds">Manage Firmware</NavLink>
            </>
          ) : null}

          {user?.permissions?.can_configure_tests ? (
            <>
              <div className="nav-section">Manager</div>
              <NavLink to="/manager/test-configuration">Test Configuration</NavLink>
              <NavLink to="/manager/fc-models">FC Models</NavLink>
            </>
          ) : null}

          {user?.permissions?.is_admin ? (
            <>
              <div className="nav-section">Administration</div>
              <NavLink to="/admin">Admin</NavLink>
            </>
          ) : null}
        </nav>
        <div className="spacer" />
        <div className="who">
          <strong>{user?.full_name || user?.username}</strong>
          {user?.role_display} · {user?.department_name || 'No department'}
          <div style={{ marginTop: 8 }}>
            <button className="link" onClick={() => { logout(); navigate('/login') }}>
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <div className="main">
        <Notifications unread={unread} onRead={() => setUnread(0)} />
        <div className="content">{children}</div>
      </div>
    </div>
  )
}

function Notifications({ unread, onRead }) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next) {
      const data = await api('/api/notifications/', { params: { page_size: 15 } })
      setItems(listOf(data))
      await api('/api/notifications/mark_all_read/', { method: 'POST' })
      onRead()
    }
  }

  return (
    <>
      <div className="topbar">
        <h1>Internal Production &amp; Engineering Knowledge System</h1>
        <div className="spacer" />
        <button className="secondary" onClick={toggle}>
          Notifications{unread ? ` (${unread})` : ''}
        </button>
      </div>
      {open ? (
        <div style={{ padding: '12px 22px 0' }}>
          <div className="card">
            <h2>Recent notifications</h2>
            {items.length === 0 ? <p className="muted small">Nothing yet.</p> : null}
            {items.map((n) => (
              <div key={n.id} className="note">
                <div>{n.message}</div>
                <div className="meta">{new Date(n.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </>
  )
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="login-wrap"><p className="muted">Loading…</p></div>
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
        <Route path="/software/push-update" element={<PushUpdate />} />
        <Route path="/firmware/builds" element={<ManageFirmware />} />
        <Route path="/manager/test-configuration" element={<TestConfiguration />} />
        <Route path="/manager/fc-models" element={<FcModels />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<p>Not found.</p>} />
      </Routes>
    </Shell>
  )
}
