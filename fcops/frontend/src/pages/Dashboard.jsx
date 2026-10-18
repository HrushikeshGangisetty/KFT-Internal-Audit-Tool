import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import {
  Banner, Card, Empty, FcLink, IssueLink, Icon, Meter, PageHeader, PageSkeleton, SeverityTag,
  StatCard, StatusTag, humanize,
} from '../components/ui.jsx'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/dashboard/summary/').then(setData).catch((e) => setError(e.message))
  }, [])

  const header = (
    <PageHeader
      title="Dashboard"
      subtitle="Production health, blocked units and open engineering issues at a glance."
      actions={<>
        <Link className="btn secondary" to="/issues/new"><Icon name="alert" />Report issue</Link>
        <Link className="btn" to="/fcs/new"><Icon name="plus" />Register FC</Link>
      </>}
    />
  )
  if (error) return <>{header}<Banner>{error}</Banner></>
  if (!data) return <PageSkeleton stats={4} />

  const maxStage = Math.max(1, ...data.fc_by_stage.map((s) => s.count))
  const maxDept = Math.max(1, ...data.issues_by_department.map((d) => d.n))

  return (
    <>
      {header}
      <div className="grid cols-4 section">
        <StatCard icon="chip" label="FCs total" value={data.fc_total} />
        <StatCard icon="alert" label="FCs blocked" value={data.blocked.length}
                  tone={data.blocked.length ? 'bad' : ''} />
        <StatCard icon="inbox" label="Open issues" value={data.open_issue_total}
                  tone={data.open_issue_total ? 'warn' : ''} />
        <StatCard icon="history" label="Avg resolution" value={data.avg_resolution_hours ?? '—'}
                  hint="hours, open → resolved" />
      </div>

      <div className="grid cols-2 section">
        <Card title="FCs by lifecycle stage">
          {data.fc_by_stage.map((s) => (
            <Meter key={s.stage} label={s.label} value={s.count} max={maxStage} />
          ))}
        </Card>

        <Card title="Open issues by assigned department">
          {data.issues_by_department.length === 0 ? <Empty>No open issues.</Empty> : null}
          {data.issues_by_department.map((d) => (
            <Meter key={d.assigned_department__name || 'unassigned'}
                 label={d.assigned_department__name || 'Unassigned'}
                 value={d.n} max={maxDept} tone="bad" />
          ))}
          <h3 style={{ marginTop: 20 }}>By severity</h3>
          <div className="row">
            {data.issues_by_severity.map((s) => (
              <span key={s.severity}><SeverityTag value={s.severity} /> {s.n}</span>
            ))}
            {data.issues_by_severity.length === 0 ? <Empty>None.</Empty> : null}
          </div>
        </Card>
      </div>

      <Card title="Blocked FCs — and why" subtitle="Units held at a stage by open blocking issues" flush>
        {data.blocked.length === 0 ? <Empty icon="check">Nothing is blocked right now.</Empty> : null}
        {data.blocked.length ? <div className="table-wrap">
          <table>
            <thead><tr><th>FC</th><th>Stage</th><th>Blocking issues</th></tr></thead>
            <tbody>
              {data.blocked.map((fc) => (
                <tr key={fc.id}>
                  <td style={{ width: 140 }}><FcLink id={fc.id} serial={fc.serial} /></td>
                  <td style={{ width: 200 }} className="small muted">{fc.stage}</td>
                  <td>
                    {fc.issues.map((i) => (
                      <div key={i.id} className="row small" style={{ marginBottom: 4 }}>
                        <IssueLink id={i.id} label={i.key} />
                        <SeverityTag value={i.severity} />
                        <StatusTag value={i.status} />
                        <span>{i.title}</span>
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div> : null}
      </Card>

      <div className="grid cols-2 section">
        <Card title="Average time in stage" subtitle="Hours spent per lifecycle stage" flush>
          {data.avg_time_in_stage.length === 0 ? <div className="card-body"><Empty /></div> : null}
          <div className="table-wrap">
            <table>
              <tbody>
                {data.avg_time_in_stage.map((s) => (
                  <tr key={s.stage}><td>{s.label}</td><td style={{ textAlign: 'right' }}>{s.avg_hours} h</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Where issues are discovered" subtitle={`Last ${data.window_days} days`} flush>
          {data.issues_by_discovery_stage.length === 0 ? <div className="card-body"><Empty /></div> : null}
          <div className="table-wrap">
            <table>
              <tbody>
                {data.issues_by_discovery_stage.map((s) => (
                  <tr key={s.discovered_stage}>
                    <td>{humanize(s.discovered_stage)}</td><td style={{ textAlign: 'right' }}>{s.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card-body" style={{ borderTop: '1px solid var(--border)' }}>
          <h3 style={{ marginTop: 0 }}>Reworks per FC</h3>
          {data.reworks_per_fc.length === 0 ? <Empty>No reworks recorded.</Empty> : null}
          <div className="row small">
            {data.reworks_per_fc.map((r) => (
              <span key={r.fc__serial} className="tag mono">{r.fc__serial} · {r.n}</span>
            ))}
          </div>
          </div>
        </Card>
      </div>

    </>
  )
}
