import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, listOf } from '../../lib/api'
import {
  Card, FcLink, Icon, IssueLink, OwnerTag, PageHeader, SeverityTag, StatusTag, Tag,
  UrgencyTag, when,
} from '../../components/ui.jsx'
import { Paged, usePaged } from '../../components/data.jsx'
import { useDebounced } from '../../lib/hooks.js'

export default function IssueList() {
  const [meta, setMeta] = useState({ statuses: [], severities: [], categories: [] })
  const [stages, setStages] = useState([])
  const [departments, setDepartments] = useState([])
  const [filters, setFilters] = useState({
    q: '', status: '', severity: '', category: '', discovered_stage: '',
    assigned_department: '',
  })
  const q = useDebounced(filters.q)
  const page = usePaged('/api/issues/', { ...filters, q })

  useEffect(() => {
    api('/api/issues/meta/').then(setMeta).catch(() => {})
    api('/api/lifecycle/').then((d) => setStages(d.stages)).catch(() => {})
    api('/api/departments/', { params: { page_size: 100 } })
      .then((d) => setDepartments(listOf(d))).catch(() => {})
  }, [])

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))
  const select = (k, label, options) => (
    <div className="field">
      <label>{label}</label>
      <select value={filters[k]} onChange={set(k)}>
        <option value="">All</option>
        {options.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
      </select>
    </div>
  )

  return (
    <>
      <PageHeader
        title="Issues"
        subtitle="Problems raised across production, testing and the field."
        actions={<Link className="btn" to="/report"><Icon name="plus" />Report a problem</Link>}
      />

      <Card className="filter-bar">
        <div className="grid cols-3">
          <div className="field">
            <label>Full-text search</label>
            <input value={filters.q} onChange={set('q')} type="search"
                   placeholder="Symptom, root cause, resolution…" />
          </div>
          {select('status', 'Status', meta.statuses)}
          {select('severity', 'Severity', meta.severities)}
          {select('category', 'Category', meta.categories)}
          {select('discovered_stage', 'Discovered at stage', stages)}
          {select('assigned_department', 'Assigned department',
                  departments.map((d) => ({ value: d.id, label: d.name })))}
        </div>
      </Card>

      <Card flush>
        <Paged page={page} what="issues" cols={10} empty="No issues match these filters.">
          {(rows) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Key</th><th>FC</th><th>Title</th><th>Discovered</th>
                    <th>Assigned</th><th>Urgency</th><th>Owner</th><th>Severity</th><th>Status</th><th>Opened</th></tr>
                </thead>
                <tbody>
                  {rows.map((i) => (
                    <tr key={i.id}>
                      <td><IssueLink id={i.id} label={i.key} /></td>
                      <td><FcLink id={i.fc} serial={i.fc_serial} /></td>
                      <td>{i.title}
                        {i.is_recurring ? <> <Tag tone="warn">recurring</Tag></> : null}
                        {i.is_waiting ? <> <Tag>waiting</Tag></> : null}
                      </td>
                      <td className="small">{i.stage_label || '—'}<br />
                        <span className="muted">{i.discovering_department_name}</span></td>
                      <td className="small">{i.assigned_department_name || '—'}<br />
                        <span className="muted">{i.assigned_person_name}</span></td>
                      <td><UrgencyTag value={i.urgency} /></td>
                      <td><OwnerTag name={i.accountable_user_name} /></td>
                      <td><SeverityTag value={i.severity} /></td>
                      <td><StatusTag value={i.status} /></td>
                      <td className="small muted">{when(i.created_at)}</td>
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
