import { IssueLink, StatusTag, Tag, humanize } from '../components/ui.jsx'

export default function SimilarPanel({ result, loading }) {
  if (loading) return <p className="muted small">Searching history…</p>
  if (!result) {
    return <p className="muted small">
      Start typing a symptom — matching past issues will appear here.
    </p>
  }
  const { similar_issues: issues = [], known_issues: known = [] } = result
  if (!issues.length && !known.length) {
    return <p className="muted small">No similar historical issues found.</p>
  }
  return (
    <>
      {known.length ? (
        <>
          <h3>Known issues</h3>
          {known.map((k) => (
            <div key={k.id} className="note">
              <div><strong>{k.title}</strong> <Tag tone="info">{k.occurrence_count ?? 0} occurrences</Tag></div>
              <div className="small">{k.symptoms_summary}</div>
              <div className="small"><strong>Fix:</strong> {k.resolution}</div>
            </div>
          ))}
        </>
      ) : null}
      {issues.length ? (
        <>
          <h3>Similar past issues</h3>
          {issues.map((i) => (
            <div key={i.id} className="note">
              <div className="row" style={{ gap: 6 }}>
                <IssueLink id={i.id} label={i.key} />
                <StatusTag value={i.status} />
                <span className="muted small">score {i.score}</span>
              </div>
              <div>{i.title}</div>
              <div className="small muted">
                {i.fc_serial} · {i.stage_label}
                {i.matched_on?.length ? ` · matched on ${i.matched_on.map(humanize).join(', ')}` : ''}
              </div>
            </div>
          ))}
        </>
      ) : null}
    </>
  )
}
