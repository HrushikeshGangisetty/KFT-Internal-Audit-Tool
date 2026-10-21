import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth.jsx'
import { api, listOf } from '../lib/api'
import { APP_NAME, Empty, Icon, SkeletonText, initials, when } from '../components/ui.jsx'
import { visibleNav } from './nav.js'

export function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark">K</div>
      <div className="brand-name">{APP_NAME}<small>Issues · Work · Releases · Hardware</small></div>
    </div>
  )
}

export default function Shell({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const name = user?.full_name || user?.username
  const signOut = async () => { await logout(); navigate('/login') }

  // The drawer (phones/tablets) closes whenever the route changes.
  useEffect(() => { setMenuOpen(false) }, [pathname])

  return (
    <div className={`app ${menuOpen ? 'menu-open' : ''}`}>
      <aside className="sidebar" id="sidebar" aria-label="Main navigation">
        <Brand />
        <nav>
          {visibleNav(user?.permissions).map((group) => (
            <div key={group.section} className="nav-group" role="group" aria-label={group.section}>
              <div className="nav-section">{group.section}</div>
              {group.items.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end}>
                  <Icon name={n.icon} />{n.label}
                </NavLink>
              ))}
            </div>
          ))}
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
      <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />
      <div className="main">
        <header className="topbar">
          <button className="icon-btn mobile-only" aria-label="Menu" aria-controls="sidebar"
                  aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
            <Icon name={menuOpen ? 'x' : 'menu'} size={18} />
          </button>
          <QuickSearch />
          <div className="spacer" />
          <Notifications />
          <button className="icon-btn mobile-only" title="Sign out" aria-label="Sign out" onClick={signOut}>
            <Icon name="logout" />
          </button>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}

/** Knowledge search from anywhere: hands the text to /search?q=… */
function QuickSearch() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const submit = (e) => {
    e.preventDefault()
    if (!q.trim()) return
    navigate(`/search?q=${encodeURIComponent(q.trim())}`)
    setQ('')
  }
  return (
    <form className="topbar-search" role="search" onSubmit={submit}>
      <Icon name="search" />
      <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search past issues"
             placeholder="Search issues, symptoms, fixes…" />
    </form>
  )
}

function Notifications() {
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    let alive = true
    const poll = () => api('/api/notifications/unread_count/')
      .then((d) => alive && setUnread(d.count)).catch(() => {})
    poll()
    const t = setInterval(poll, 30000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  useEffect(() => {
    if (!open) return undefined
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
    if (!next) return
    setItems(null)
    try {
      setItems(listOf(await api('/api/notifications/', { params: { page_size: 15 } })))
      await api('/api/notifications/mark_all_read/', { method: 'POST' })
      setUnread(0)
    } catch { setItems([]) }
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
