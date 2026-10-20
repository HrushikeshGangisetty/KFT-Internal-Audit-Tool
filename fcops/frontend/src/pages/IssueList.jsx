import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import {
  Banner, Card, Empty, FcLink, Icon, IssueLink, Loading, OwnerTag, PageHeader, SeverityTag, StatusTag, Tag,
  UrgencyTag, when,
} from '../components/ui.jsx'

export default function IssueList() {
  const [rows, setRows] = useState(null)
  const [meta, setMeta] = useState({ statuses: [], severities: [], categories: [] })
  const [stages, setStages] = useState([])
  const [departments, setDepartments] = useState([])
  const [filters, setFilters] = useState({
    q: '', status: '', severity: '', category: '', discovered_stage: '',
    assigned_department: '',
  })
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/issues/meta/').then(setMeta).catch(() => {})
    api('/api/lifecycle/').then((d) => setStages(d.stages)).catch(() => {})
    api('/api/departments/', { params: { page_size: 100 } })
      .then((d) => setDepartments(listOf(d))).catch(() => {})
  }, [])

  useEffect(() => {
    let alive = true
    setRows(null)
    api('/api/issues/', { params: { ...filters, page_size: 100 } })
      .then((d) => alive && setRows(listOf(d)))
      .catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [filters])

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))

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
            <input value={filters.q} onChange={set('q')}
                   placeholder="Symptom, root cause, resolution…" />
          </div>
          <div className="field">
            <label>Status</label>
            <select value={filters.status} onChange={set('status')}>
              <option value="">All</option>
              {meta.statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Severity</label>
            <select value={filters.severity} onChange={set('severity')}>
              <option value="">All</option>
              {meta.severities.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Category</label>
            <select value={filters.category} onChange={set('category')}>
              <option value="">All</option>
              {meta.categories.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Discovered at stage</label>
            <select value={filters.discovered_stage} onChange={set('discovered_stage')}>
              <option value="">All</option>
              {stages.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Assigned department</label>
            <select value={filters.assigned_department} onChange={set('assigned_department')}>
              <option value="">All</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
        </div>
      </Card>

      <Banner>{error}</Banner>
      <Card flush>
        {rows === null ? <Loading what="issues" cols={10} /> : null}
        {rows?.length === 0 ? <Empty>No issues match these filters.</Empty> : null}
        {rows?.length ? (
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
                    <td className="small">{i.stage_label}<br />
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
        ) : null}
      </Card>
    </>
  )
}
