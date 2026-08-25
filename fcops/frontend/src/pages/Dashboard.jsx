import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { Banner, Empty, FcLink, IssueLink, Loading, SeverityTag, StatusTag, humanize } from '../components/ui.jsx'

function Bar({ label, value, max, tone }) {
  const pct = max ? Math.round((value / max) * 100) : 0
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="row small" style={{ justifyContent: 'space-between' }}>
        <span>{label}</span>
        <span className="muted">{value}</span>
      </div>
      <div style={{ background: 'var(--surface-2)', borderRadius: 4, height: 8 }}>
        <div style={{
          width: `${pct}%`, height: 8, borderRadius: 4,
          background: tone === 'bad' ? 'var(--bad)' : 'var(--accent)',
          minWidth: value ? 4 : 0,
        }} />
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/dashboard/summary/').then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <Banner>{error}</Banner>
  if (!data) return <Loading what="dashboard" />

  const maxStage = Math.max(1, ...data.fc_by_stage.map((s) => s.count))
  const maxDept = Math.max(1, ...data.issues_by_department.map((d) => d.n))

  return (
    <>
      <div className="grid cols-4" style={{ marginBottom: 18 }}>
        <div className="stat"><div className="n">{data.fc_total}</div><div className="l">FCs total</div></div>
        <div className="stat"><div className="n">{data.blocked.length}</div><div className="l">FCs blocked</div></div>
        <div className="stat"><div className="n">{data.open_issue_total}</div><div className="l">Open issues</div></div>
        <div className="stat">
          <div className="n">{data.avg_resolution_hours ?? '—'}</div>
          <div className="l">Avg resolution (h)</div>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>FCs by lifecycle stage</h2>
          {data.fc_by_stage.map((s) => (
            <Bar key={s.stage} label={s.label} value={s.count} max={maxStage} />
          ))}
        </div>

        <div className="card">
          <h2>Open issues by assigned department</h2>
          {data.issues_by_department.length === 0 ? <Empty>No open issues.</Empty> : null}
          {data.issues_by_department.map((d) => (
            <Bar key={d.assigned_department__name || 'unassigned'}
                 label={d.assigned_department__name || 'Unassigned'}
                 value={d.n} max={maxDept} tone="bad" />
          ))}
          <h3 style={{ marginTop: 18 }}>By severity</h3>
          <div className="row">
            {data.issues_by_severity.map((s) => (
              <span key={s.severity}><SeverityTag value={s.severity} /> {s.n}</span>
            ))}
            {data.issues_by_severity.length === 0 ? <Empty>None.</Empty> : null}
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Blocked FCs — and why</h2>
        {data.blocked.length === 0 ? <Empty>Nothing is blocked right now.</Empty> : null}
        <div className="table-wrap">
          <table>
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
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Average time in stage (h)</h2>
          {data.avg_time_in_stage.length === 0 ? <Empty /> : null}
          <div className="table-wrap">
            <table>
              <tbody>
                {data.avg_time_in_stage.map((s) => (
                  <tr key={s.stage}><td>{s.label}</td><td>{s.avg_hours}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <h2>Where issues are discovered (last {data.window_days} days)</h2>
          {data.issues_by_discovery_stage.length === 0 ? <Empty /> : null}
          <div className="table-wrap">
            <table>
              <tbody>
                {data.issues_by_discovery_stage.map((s) => (
                  <tr key={s.discovered_stage}>
                    <td>{humanize(s.discovered_stage)}</td><td>{s.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 style={{ marginTop: 16 }}>Reworks per FC</h3>
          {data.reworks_per_fc.length === 0 ? <Empty /> : null}
          <div className="row small">
            {data.reworks_per_fc.map((r) => (
              <span key={r.fc__serial} className="tag">{r.fc__serial}: {r.n}</span>
            ))}
          </div>
        </div>
      </div>

      <p className="small muted">
        <Link to="/fcs/new">Register a new FC</Link> · <Link to="/issues/new">Report an issue</Link>
      </p>
    </>
  )
}
