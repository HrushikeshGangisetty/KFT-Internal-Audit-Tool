import { useState } from 'react'
import { api } from '../../lib/api'
import {
  Banner, Card, Empty, IssueLink, Loading, PageHeader, SkeletonCard, Tag, humanize, when,
} from '../../components/ui.jsx'
import { LoadMore, usePaged } from '../../components/data.jsx'
import { useDebounced } from '../../lib/hooks.js'

export default function KnownIssues() {
  const [q, setQ] = useState('')
  const page = usePaged('/api/known-issues/', { q: useDebounced(q) }, 20)

  return (
    <>
      <PageHeader
        title="Known issues"
        subtitle="Curated reference entries promoted from resolved issues. Every raw resolved issue stays searchable whether or not it was promoted."
      />
      <Card className="filter-bar">
        <div className="field">
          <label>Search</label>
          <input value={q} onChange={(e) => setQ(e.target.value)} type="search"
                 placeholder="Symptom, root cause, resolution…" />
        </div>
      </Card>
      <Banner>{page.error}</Banner>
      {page.rows === null ? <><SkeletonCard /><SkeletonCard /></> : null}
      {page.rows?.length === 0 && !page.error ? <Empty icon="book">Nothing promoted yet.</Empty> : null}
      {page.rows?.map((k) => <KnownIssue key={k.id} k={k} />)}
      <LoadMore page={page} />
    </>
  )
}

function KnownIssue({ k }) {
  const [occurrences, setOccurrences] = useState(null)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const toggle = () => {
    setOpen((o) => !o)
    if (occurrences || open) return
    api(`/api/known-issues/${k.id}/occurrences/`).then(setOccurrences).catch((e) => setError(e.message))
  }
  return (
    <Card title={k.title}
          subtitle={<span className="row" style={{ gap: 6, marginTop: 4 }}>
            <Tag tone="info">{k.occurrence_count} occurrences</Tag>
            <Tag>{humanize(k.category)}</Tag>
            {k.owning_department_name ? <Tag>{k.owning_department_name}</Tag> : null}
          </span>}
          actions={<button className="secondary sm" onClick={toggle} aria-expanded={open}>
            {open ? 'Hide occurrences' : 'Show occurrences'}
          </button>}>
      <dl className="kv">
        <dt>Symptoms</dt><dd>{k.symptoms_summary}</dd>
        <dt>Root cause</dt><dd>{k.root_cause}</dd>
        <dt>Resolution</dt><dd>{k.resolution}</dd>
        <dt>Affected</dt>
        <dd className="mono small">
          {[k.affected_revisions, k.affected_firmware, k.affected_software].filter(Boolean).join(' · ') || '—'}
        </dd>
        <dt>Promoted</dt><dd className="small muted">{k.promoted_by_name} · {when(k.created_at)}</dd>
      </dl>
      {open ? (
        <div className="reveal" style={{ marginTop: 16 }}>
          <Banner>{error}</Banner>
          {occurrences === null && !error ? <Loading what="occurrences" cols={5} rows={2} /> : null}
          {occurrences?.length === 0 ? <Empty>No occurrences you can see.</Empty> : null}
          {occurrences?.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Issue</th><th>FC</th><th>Discovered</th><th>Status</th><th>Opened</th></tr></thead>
                <tbody>
                  {occurrences.map((i) => (
                    <tr key={i.id}>
                      <td><IssueLink id={i.id} label={i.key} /></td>
                      <td className="mono small">{i.fc_serial || '—'}</td>
                      <td className="small">{i.stage_label || '—'}</td>
                      <td className="small">{humanize(i.status)}</td>
                      <td className="small muted">{when(i.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}
