import { Empty, IssueLink, OwnerTag, SeverityTag, StatusTag, UrgencyTag, humanize, when } from '../../../components/ui.jsx'

export function Timeline({ events }) {
  if (!events.length) return <Empty>No events yet.</Empty>
  return (
    <ul className="timeline">
      {events.map((e) => (
        <li key={e.id} className={e.kind.includes('FAIL') || e.kind.includes('OPENED') ? 'bad'
          : e.kind.includes('PASS') || e.kind.includes('VERIFIED') || e.kind.includes('APPROVED') ? 'ok' : ''}>
          <div className="t">{e.title}</div>
          {e.detail ? <div className="small">{e.detail}</div> : null}
          <div className="meta">
            {when(e.created_at)} · {e.actor_name || 'system'}
            {e.stage_label ? ` · ${e.stage_label}` : ''}
            {e.issue ? <> · <IssueLink id={e.issue} label={e.issue_key} /></> : null}
          </div>
        </li>
      ))}
    </ul>
  )
}


export function IssuesTable({ issues }) {
  if (!issues.length) return <Empty>No issues raised against this FC.</Empty>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Key</th><th>Title</th><th>Discovered at</th><th>Assigned to</th>
          <th>Urgency</th><th>Owner</th><th>Severity</th><th>Status</th></tr></thead>
        <tbody>
          {issues.map((i) => (
            <tr key={i.id}>
              <td><IssueLink id={i.id} label={i.key} /></td>
              <td>{i.title}</td>
              <td className="small">{i.stage_label}<br />
                <span className="muted">{i.discovering_department_name}</span></td>
              <td className="small">{i.assigned_department_name || '—'}</td>
              <td><UrgencyTag value={i.urgency} /></td>
              <td><OwnerTag name={i.accountable_user_name} /></td>
              <td><SeverityTag value={i.severity} /></td>
              <td><StatusTag value={i.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}


export function AuditTable({ rows }) {
  if (!rows.length) return <Empty>No audit entries.</Empty>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>Actor</th><th>Change</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="small muted">{when(r.created_at)}</td>
              <td className="small">{humanize(r.action)}</td>
              <td className="small">{r.entity_type} · {r.entity_label}</td>
              <td className="small">{r.actor_name}</td>
              <td className="small mono" style={{ maxWidth: 380, wordBreak: 'break-word' }}>
                {r.note ? <div>{r.note}</div> : null}
                {r.after ? <div className="muted">{JSON.stringify(r.after).slice(0, 220)}</div> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
