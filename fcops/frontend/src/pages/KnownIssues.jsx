import { useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import {
  Banner, Card, Empty, IssueLink, PageHeader, SkeletonCard, Tag, humanize, when,
} from '../components/ui.jsx'

export default function KnownIssues() {
  const [rows, setRows] = useState(null)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)
  const [occurrences, setOccurrences] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    const t = setTimeout(() => {
      setRows(null)
      api('/api/known-issues/', { params: { q, page_size: 100 } })
        .then((d) => alive && setRows(listOf(d)))
        .catch((e) => alive && setError(e.message))
    }, 300)
    return () => { alive = false; clearTimeout(t) }
  }, [q])

  const expand = async (k) => {
    if (open === k.id) { setOpen(null); return }
    setOpen(k.id)
    setOccurrences(await api(`/api/known-issues/${k.id}/occurrences/`))
  }

  return (
    <>
      <PageHeader
        title="Known issues"
        subtitle="Curated reference entries promoted from resolved issues. Every raw resolved issue stays searchable whether or not it was promoted."
      />
      <Card className="filter-bar">
        <div className="field">
          <label>Search</label>
          <input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Symptom, root cause, resolution…" />
        </div>
      </Card>
      <Banner>{error}</Banner>
      {rows === null ? <><SkeletonCard /><SkeletonCard /></> : null}
      {rows?.length === 0 ? <Empty icon="book">Nothing promoted yet.</Empty> : null}
      {rows?.map((k) => (
        <Card key={k.id} title={k.title}
              subtitle={<span className="row" style={{ gap: 6, marginTop: 4 }}>
                <Tag tone="info">{k.occurrence_count} occurrences</Tag>
                <Tag>{humanize(k.category)}</Tag>
                {k.owning_department_name ? <Tag>{k.owning_department_name}</Tag> : null}
              </span>}
              actions={<button className="secondary sm" onClick={() => expand(k)}>
                {open === k.id ? 'Hide occurrences' : 'Show occurrences'}
              </button>}>
          <dl className="kv">
            <dt>Symptoms</dt><dd>{k.symptoms_summary}</dd>
            <dt>Root cause</dt><dd>{k.root_cause}</dd>
            <dt>Resolution</dt><dd>{k.resolution}</dd>
            <dt>Affected</dt>
            <dd className="mono small">
              {[k.affected_revisions, k.affected_firmware, k.affected_software]
                .filter(Boolean).join(' · ') || '—'}
            </dd>
            <dt>Promoted</dt><dd className="small muted">{k.promoted_by_name} · {when(k.created_at)}</dd>
          </dl>
          {open === k.id ? (
            <div className="table-wrap" style={{ marginTop: 16 }}>
              <table>
                <thead><tr><th>Issue</th><th>FC</th><th>Discovered</th><th>Status</th><th>Opened</th></tr></thead>
                <tbody>
                  {occurrences.map((i) => (
                    <tr key={i.id}>
                      <td><IssueLink id={i.id} label={i.key} /></td>
                      <td className="mono small">{i.fc_serial}</td>
                      <td className="small">{i.stage_label}</td>
                      <td className="small">{humanize(i.status)}</td>
                      <td className="small muted">{when(i.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Card>
      ))}
    </>
  )
}
