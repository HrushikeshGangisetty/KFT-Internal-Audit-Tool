import { Link } from 'react-router-dom'

/* ---------------------------------------------------------------------------
   Icons — a small inline set (24×24, stroke). Add paths here, not new deps.
   ------------------------------------------------------------------------- */
const ICONS = {
  dashboard: 'M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z',
  chip: 'M9 3v2M15 3v2M9 19v2M15 19v2M3 9h2M3 15h2M19 9h2M19 15h2M7 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM9 9h6v6H9z',
  alert: 'M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3',
  book: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5',
  history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 3',
  compare: 'M16 3h5v5M8 21H3v-5M21 3l-7 7M3 21l7-7',
  upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12',
  cpu: 'M4 4h16v16H4zM9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3',
  sliders: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6',
  layers: 'M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  plus: 'M12 5v14M5 12h14',
  inbox: 'M22 12h-6l-2 3h-4l-2-3H2M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
  check: 'M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4 12 14l-3-3',
}

export function Icon({ name, size = 16, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      <path d={ICONS[name]} />
    </svg>
  )
}

/* ---------------------------------------------------------------------------
   Layout primitives
   ------------------------------------------------------------------------- */

/** Top-of-page title block. `meta` renders a row of tags under the title. */
export function PageHeader({ title, subtitle, meta, actions, mono }) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        <h1 className={mono ? 'mono' : undefined}>{title}</h1>
        {subtitle ? <p className="subtitle">{subtitle}</p> : null}
        {meta ? <div className="meta-row">{meta}</div> : null}
      </div>
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </header>
  )
}

/**
 * Surface container. Pass `title` for a header row, `actions` for header
 * buttons, `footer` for a bottom action bar, `flush` to drop body padding
 * (tables), `tabs` for a <Tabs inCard> strip under the header, and
 * `as="form"` (+ form props) to make the card itself a form.
 */
export function Card({
  title, subtitle, actions, tabs, footer, flush, className = '', as: As = 'section', children, ...rest
}) {
  return (
    <As className={`card ${className}`} {...rest}>
      {title || actions ? (
        <div className="card-header">
          <div className="card-header-text">
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p className="card-subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="card-actions">{actions}</div> : null}
        </div>
      ) : null}
      {tabs || null}
      <div className={`card-body ${flush ? 'flush' : ''}`}>{children}</div>
      {footer ? <div className="card-footer">{footer}</div> : null}
    </As>
  )
}

export function StatCard({ label, value, hint, tone = '', icon }) {
  return (
    <div className={`stat ${tone}`}>
      <div className="l">{icon ? <Icon name={icon} size={14} /> : null}{label}</div>
      <div className="n">{value}</div>
      {hint ? <div className="hint">{hint}</div> : null}
    </div>
  )
}

/** Underline tabs. `tabs` is a list of values or {value, label}. */
export function Tabs({ tabs, value, onChange, inCard }) {
  return (
    <div className={`tabs ${inCard ? 'in-card' : ''}`} role="tablist">
      {tabs.map((t) => {
        const v = t.value ?? t
        return (
          <button key={v} type="button" role="tab" aria-selected={value === v}
                  onClick={() => onChange(v)}>
            {t.label ?? humanize(v)}
          </button>
        )
      })}
    </div>
  )
}

export function Meter({ label, value, max, tone }) {
  const pct = max ? Math.round((value / max) * 100) : 0
  return (
    <div className="meter">
      <div className="meter-label"><span>{label}</span><span>{value}</span></div>
      <div className="meter-track">
        <div className={`meter-fill ${tone || ''}`}
             style={{ width: `${pct}%`, minWidth: value ? 4 : 0 }} />
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
   Feedback: banners, empty states, skeletons
   ------------------------------------------------------------------------- */
const BANNER_ICON = { error: 'alert', warn: 'alert', ok: 'check', info: 'info' }

export function Banner({ kind = 'error', children }) {
  if (!children) return null
  return (
    <div className={`banner has-icon ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <Icon name={BANNER_ICON[kind]} />
      <div>{children}</div>
    </div>
  )
}

export function Empty({ title, children = 'Nothing here yet.', icon = 'inbox', action }) {
  return (
    <div className="empty">
      <Icon name={icon} size={20} />
      {title ? <div className="empty-title">{title}</div> : null}
      <div>{children}</div>
      {action || null}
    </div>
  )
}

export function Skeleton({ w = '100%', h = 12, r, style }) {
  return <span className="skeleton" style={{ width: w, height: h, borderRadius: r, ...style }} />
}

export function SkeletonText({ lines = 3 }) {
  return (
    <div className="skeleton-text">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} w={i === lines - 1 ? '60%' : '100%'} />
      ))}
    </div>
  )
}

export function SkeletonTable({ rows = 6, cols = 5 }) {
  return (
    <div className="skeleton-table">
      {Array.from({ length: rows + 1 }, (_, r) => (
        <div className="sk-row" key={r}>
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton key={c} h={r === 0 ? 10 : 12} w={r === 0 ? '50%' : `${60 + ((r * 7 + c * 13) % 40)}%`} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonCard({ lines = 4, title = true }) {
  return (
    <div className="card" aria-hidden="true">
      {title ? <div className="card-header"><Skeleton w={160} h={14} /></div> : null}
      <div className="card-body"><SkeletonText lines={lines} /></div>
    </div>
  )
}

/** Full-page placeholder: header, optional stat row, then cards. */
export function PageSkeleton({ stats = 0, split = false }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      <div className="page-header">
        <div className="page-header-text">
          <Skeleton w={220} h={24} />
          <div style={{ marginTop: 10 }}><Skeleton w={340} h={12} /></div>
        </div>
      </div>
      {stats ? (
        <div className="grid cols-4 section">
          {Array.from({ length: stats }, (_, i) => (
            <div className="stat" key={i}><Skeleton w={90} h={11} /><Skeleton w={60} h={26} /></div>
          ))}
        </div>
      ) : null}
      {split ? (
        <div className="split">
          <div><SkeletonCard lines={6} /><SkeletonCard lines={4} /></div>
          <div><SkeletonCard lines={5} /><SkeletonCard lines={3} /></div>
        </div>
      ) : (
        <div className="grid cols-2"><SkeletonCard lines={5} /><SkeletonCard lines={5} /></div>
      )}
    </div>
  )
}

/** Inline loading placeholder; table-shaped by default since most lists are tables. */
export function Loading({ what = 'data', variant = 'table', rows, cols }) {
  return (
    <div aria-busy="true" aria-label={`Loading ${what}`}>
      {variant === 'text' ? <SkeletonText lines={rows ?? 3} /> : <SkeletonTable rows={rows} cols={cols} />}
    </div>
  )
}

/* ---------------------------------------------------------------------------
   Domain tags & formatters
   ------------------------------------------------------------------------- */
const SEVERITY_TONE = { BLOCKER: 'bad', MAJOR: 'warn', MINOR: '', COSMETIC: '' }
const STATUS_TONE = {
  OPEN: 'bad',
  INVESTIGATING: 'warn',
  RESOLVED: 'info',
  VERIFIED: 'ok',
  CLOSED: '',
  BLOCKED: 'bad',
  APPROVED: 'ok',
  REJECTED: 'bad',
  IN_TESTING: 'info',
  PENDING_APPROVAL: 'warn',
  IN_PRODUCTION: '',
  PASSED: 'ok',
  FAILED: 'bad',
  IN_PROGRESS: 'info',
  PENDING: '',
}

export const Tag = ({ children, tone = '' }) => (
  <span className={`tag ${tone}`}>{children}</span>
)

export const StatusTag = ({ value }) => (
  <span className={`tag dot ${STATUS_TONE[value] ?? ''}`}>{humanize(value)}</span>
)

export const SeverityTag = ({ value }) => (
  <Tag tone={SEVERITY_TONE[value] ?? ''}>{humanize(value)}</Tag>
)

export function humanize(value) {
  if (!value) return '—'
  return String(value)
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

export function when(value) {
  if (!value) return '—'
  const d = new Date(value)
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export function initials(name = '') {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?'
}

export const FcLink = ({ id, serial }) => (id
  ? <Link to={`/fcs/${id}`} className="mono">{serial}</Link>
  : <span className="muted">—</span>)
export const IssueLink = ({ id, label }) => <Link to={`/issues/${id}`} className="mono">{label}</Link>

export function Field({ label, children, hint }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint ? <div className="small muted hint">{hint}</div> : null}
    </div>
  )
}
