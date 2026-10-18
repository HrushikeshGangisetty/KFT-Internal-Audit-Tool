import { Empty, IssueLink, Loading, StatusTag, Tag, humanize } from '../components/ui.jsx'

export default function SimilarPanel({ result, loading }) {
  if (loading) return <Loading what="similar issues" variant="text" rows={5} />
  if (!result) {
    return <Empty icon="search">Start typing a symptom — matching past issues will appear here.</Empty>
  }
  const { similar_issues: issues = [], known_issues: known = [] } = result
  if (!issues.length && !known.length) {
    return <Empty icon="check">No similar historical issues found.</Empty>
  }
  return (
    <>
      {known.length ? (
        <>
          <h3 style={{ marginTop: 0 }}>Known issues</h3>
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
