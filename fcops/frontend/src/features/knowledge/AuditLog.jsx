import { useState } from 'react'
import { Card, PageHeader, Tag, humanize, when } from '../../components/ui.jsx'
import { Paged, usePaged } from '../../components/data.jsx'

// Entity types are model class names (core.audit.record). An unused type
// simply returns no rows.
const ENTITY_TYPES = [
  'Issue', 'Handoff', 'KnownIssue', 'Task', 'DailyUpdate', 'Release', 'ReleaseRevision', 'Campaign',
  'FlightController', 'StageRecord', 'ReworkRecord', 'FirmwareRecord', 'FirmwareBuild', 'TestResult',
  'ParameterFile', 'ConfigEvidence', 'ChecklistTemplate', 'FCModelType',
  'Customer', 'CustomerContact', 'Deployment', 'User', 'Department',
]
const ACTIONS = [
  'CREATE', 'UPDATE', 'TRANSITION', 'REASSIGN', 'STATUS_CHANGE', 'PROMOTE_KNOWN_ISSUE',
  'MANAGER_APPROVAL', 'MANAGER_REJECTION', 'VERIFICATION', 'PERMISSION_CHANGE', 'CONFIG_CHANGE',
  'SOFTWARE_UPDATE_PUSHED', 'LOGIN',
]

export default function AuditLog() {
  const [filters, setFilters] = useState({ entity_type: '', action: '' })
  const page = usePaged('/api/audit-log/', filters, 50)
  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))

  return (
    <>
      <PageHeader
        title="Activity log"
        subtitle="Append-only record of changes to things you can see. The application and database refuse edits and deletes."
      />
      <Card className="filter-bar">
        <div className="grid cols-2">
          <div className="field">
            <label>Entity type</label>
            <select value={filters.entity_type} onChange={set('entity_type')}>
              <option value="">All</option>
              {ENTITY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Action</label>
            <select value={filters.action} onChange={set('action')}>
              <option value="">All</option>
              {ACTIONS.map((a) => <option key={a} value={a}>{humanize(a)}</option>)}
            </select>
          </div>
        </div>
      </Card>
      <Card flush>
        <Paged page={page} what="activity" cols={6} empty="No activity matches these filters." emptyIcon="history">
          {(rows) => (
            <div className="table-wrap">
              <table>
                <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>FC</th>
                  <th>Actor</th><th>Before → After</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td className="small muted nowrap">{when(r.created_at)}</td>
                      <td><Tag>{humanize(r.action)}</Tag></td>
                      <td className="small">{r.entity_type}<div className="muted">{r.entity_label}</div></td>
                      <td className="small mono">{r.fc_serial || '—'}</td>
                      <td className="small">{r.actor_name || 'System'}</td>
                      <td className="small mono diff-cell">
                        {r.note ? <div>{r.note}</div> : null}
                        {r.before ? <div className="muted">− {JSON.stringify(r.before).slice(0, 160)}</div> : null}
                        {r.after ? <div>+ {JSON.stringify(r.after).slice(0, 160)}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Paged>
      </Card>
    </>
  )
}
