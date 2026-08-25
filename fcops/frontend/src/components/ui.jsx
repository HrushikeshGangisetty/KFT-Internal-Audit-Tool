import { Link } from 'react-router-dom'

export function Banner({ kind = 'error', children }) {
  if (!children) return null
  return <div className={`banner ${kind}`}>{children}</div>
}

export function Loading({ what = 'data' }) {
  return <p className="muted">Loading {what}…</p>
}

export function Empty({ children = 'Nothing here yet.' }) {
  return <p className="muted small">{children}</p>
}

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
  <Tag tone={STATUS_TONE[value] ?? ''}>{humanize(value)}</Tag>
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

export const FcLink = ({ id, serial }) => <Link to={`/fcs/${id}`} className="mono">{serial}</Link>
export const IssueLink = ({ id, label }) => <Link to={`/issues/${id}`} className="mono">{label}</Link>

export function Field({ label, children, hint }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint ? <div className="small muted">{hint}</div> : null}
    </div>
  )
}
