import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth.jsx'
import { Card, FcLink, Icon, PageHeader, StatusTag, humanize, when } from '../../components/ui.jsx'
import { Paged, usePaged } from '../../components/data.jsx'
import { useDebounced } from '../../lib/hooks.js'

const STATUSES = ['IN_PRODUCTION', 'IN_TESTING', 'BLOCKED', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED']

export default function FcList() {
  const { user } = useAuth()
  const [meta, setMeta] = useState({ stages: [] })
  const [params] = useSearchParams()
  const [filters, setFilters] = useState({
    search: params.get('search') || '', status: '', current_stage: params.get('current_stage') || '',
  })
  const search = useDebounced(filters.search)
  const page = usePaged('/api/fcs/', { ...filters, search })

  useEffect(() => { api('/api/lifecycle/').then(setMeta).catch(() => {}) }, [])

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))

  return (
    <>
      <PageHeader
        title="Flight controllers"
        subtitle="Every registered unit, its lifecycle stage and current status."
        actions={user?.permissions?.can_register_fc
          ? <Link className="btn" to="/fcs/new"><Icon name="plus" />Register FC</Link> : null}
      />

      <Card className="filter-bar">
        <div className="grid cols-3">
          <div className="field">
            <label>Search</label>
            <input value={filters.search} onChange={set('search')} type="search"
                   placeholder="Serial, revision, batch…" />
          </div>
          <div className="field">
            <label>Status</label>
            <select value={filters.status} onChange={set('status')}>
              <option value="">All</option>
              {STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
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

      <Card flush>
        <Paged page={page} what="FCs" cols={7} empty="No FCs match these filters." emptyIcon="chip">
          {(rows) => (
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
          )}
        </Paged>
      </Card>
    </>
  )
}
