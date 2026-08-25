import { useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import { Banner, Empty, IssueLink, Loading, Tag, humanize, when } from '../components/ui.jsx'

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
      <h2>Known issues</h2>
      <p className="muted small" style={{ marginTop: -6 }}>
        Curated reference entries promoted from resolved issues. Every raw resolved
        issue stays searchable whether or not it was promoted.
      </p>
      <div className="card">
        <div className="field">
          <label>Search</label>
          <input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Symptom, root cause, resolution…" />
        </div>
      </div>
      <Banner>{error}</Banner>
      {rows === null ? <Loading what="known issues" /> : null}
      {rows?.length === 0 ? <div className="card"><Empty>Nothing promoted yet.</Empty></div> : null}
      {rows?.map((k) => (
        <div className="card" key={k.id}>
          <div className="row">
            <h2 style={{ margin: 0 }}>{k.title}</h2>
            <Tag tone="info">{k.occurrence_count} occurrences</Tag>
            <Tag>{humanize(k.category)}</Tag>
            {k.owning_department_name ? <Tag>{k.owning_department_name}</Tag> : null}
            <div style={{ flex: 1 }} />
            <button className="link" onClick={() => expand(k)}>
              {open === k.id ? 'Hide occurrences' : 'Show occurrences'}
            </button>
          </div>
          <dl className="kv" style={{ marginTop: 10 }}>
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
            <div className="table-wrap" style={{ marginTop: 10 }}>
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
        </div>
      ))}
    </>
  )
}
