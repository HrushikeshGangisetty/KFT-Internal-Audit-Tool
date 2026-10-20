import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import { Banner, Card, Empty, FcLink, Icon, Loading, PageHeader, StatusTag, when } from '../components/ui.jsx'

export default function FcList() {
  const [rows, setRows] = useState(null)
  const [meta, setMeta] = useState({ stages: [] })
  const [params] = useSearchParams()
  const [filters, setFilters] = useState({
    search: params.get('search') || '', status: '', current_stage: params.get('current_stage') || '',
  })
  const [error, setError] = useState('')

  useEffect(() => { api('/api/lifecycle/').then(setMeta).catch(() => {}) }, [])

  useEffect(() => {
    let alive = true
    setRows(null)
    api('/api/fcs/', { params: { ...filters, page_size: 100 } })
      .then((d) => alive && setRows(listOf(d)))
      .catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [filters])

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))

  return (
    <>
      <PageHeader
        title="Flight Controllers"
        subtitle="Every registered unit, its lifecycle stage and current status."
        actions={<Link className="btn" to="/fcs/new"><Icon name="plus" />Register FC</Link>}
      />

      <Card className="filter-bar">
        <div className="grid cols-3">
          <div className="field">
            <label>Search</label>
            <input value={filters.search} onChange={set('search')}
                   placeholder="Serial, revision, batch…" />
          </div>
          <div className="field">
            <label>Status</label>
            <select value={filters.status} onChange={set('status')}>
              <option value="">All</option>
              {['IN_PRODUCTION', 'IN_TESTING', 'BLOCKED', 'PENDING_APPROVAL',
                'APPROVED', 'REJECTED'].map((s) => (
                <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Stage</label>
            <select value={filters.current_stage} onChange={set('current_stage')}>
              <option value="">All</option>
              {meta.stages.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
        </div>
      </Card>

      <Banner>{error}</Banner>
      <Card flush>
        {rows === null ? <Loading what="FCs" cols={7} /> : null}
        {rows?.length === 0 ? <Empty>No FCs match these filters.</Empty> : null}
        {rows?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Serial</th><th>Model</th><th>Revision</th><th>Stage</th>
                  <th>Status</th><th>Open issues</th><th>Registered</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((fc) => (
                  <tr key={fc.id}>
                    <td><FcLink id={fc.id} serial={fc.serial} /></td>
                    <td>{fc.fc_model_name}</td>
                    <td className="small">{fc.hardware_revision || '—'}</td>
                    <td className="small">{fc.stage_label}</td>
                    <td><StatusTag value={fc.status} /></td>
                    <td>{fc.open_issue_count || '—'}</td>
                    <td className="small muted">{when(fc.created_at)}</td>
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
