import { useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import { Banner, Empty, Loading, humanize, when } from '../components/ui.jsx'

export default function AuditLog() {
  const [rows, setRows] = useState(null)
  const [filters, setFilters] = useState({ entity_type: '', action: '' })
  const [error, setError] = useState('')

  useEffect(() => {
    setRows(null)
    api('/api/audit-log/', { params: { ...filters, page_size: 100 } })
      .then((d) => setRows(listOf(d)))
      .catch((e) => setError(e.message))
  }, [filters])

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))

  return (
    <>
      <h2>Audit log</h2>
      <p className="muted small" style={{ marginTop: -6 }}>
        Append-only. Entries cannot be edited or deleted by anyone, including admins —
        the database refuses the write.
      </p>
      <div className="card">
        <div className="grid cols-2">
          <div className="field">
            <label>Entity type</label>
            <select value={filters.entity_type} onChange={set('entity_type')}>
              <option value="">All</option>
              {['FlightController', 'StageRecord', 'Issue', 'ReworkRecord',
                'KnownIssue', 'FirmwareRecord', 'TestResult', 'User', 'Department']
                .map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Action</label>
            <select value={filters.action} onChange={set('action')}>
              <option value="">All</option>
              {['CREATE', 'UPDATE', 'TRANSITION', 'REASSIGN', 'STATUS_CHANGE',
                'PROMOTE_KNOWN_ISSUE', 'MANAGER_APPROVAL', 'MANAGER_REJECTION',
                'VERIFICATION', 'PERMISSION_CHANGE', 'LOGIN']
                .map((a) => <option key={a} value={a}>{humanize(a)}</option>)}
            </select>
          </div>
        </div>
      </div>
      <Banner>{error}</Banner>
      <div className="card">
        {rows === null ? <Loading what="audit entries" /> : null}
        {rows?.length === 0 ? <Empty /> : null}
        {rows?.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>FC</th>
                <th>Actor</th><th>Before → After</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="small muted" style={{ whiteSpace: 'nowrap' }}>{when(r.created_at)}</td>
                    <td className="small">{humanize(r.action)}</td>
                    <td className="small">{r.entity_type}<div className="muted">{r.entity_label}</div></td>
                    <td className="small mono">{r.fc_serial || '—'}</td>
                    <td className="small">{r.actor_name}</td>
                    <td className="small mono" style={{ maxWidth: 420, wordBreak: 'break-word' }}>
                      {r.note ? <div>{r.note}</div> : null}
                      {r.before ? <div className="muted">− {JSON.stringify(r.before).slice(0, 160)}</div> : null}
                      {r.after ? <div>+ {JSON.stringify(r.after).slice(0, 160)}</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </>
  )
}
