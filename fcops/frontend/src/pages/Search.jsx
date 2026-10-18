import { useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import {
  Banner, Card, Empty, FcLink, Field, Icon, IssueLink, Loading, PageHeader, SeverityTag, StatusTag, Tag, when,
} from '../components/ui.jsx'

export default function Search() {
  const [meta, setMeta] = useState({ statuses: [], severities: [], categories: [] })
  const [stages, setStages] = useState([])
  const [filters, setFilters] = useState({
    q: '', category: '', severity: '', status: '', stage: '',
    hardware_revision: '', firmware_version: '', gcs_version: '', configurator_version: '',
  })
  const [rows, setRows] = useState([])
  const [known, setKnown] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/api/issues/meta/').then(setMeta)
    api('/api/lifecycle/').then((d) => setStages(d.stages))
  }, [])

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))

  const run = async (e) => {
    e?.preventDefault()
    setBusy(true); setError('')
    try {
      const [issues, knownIssues] = await Promise.all([
        api('/api/issues/search/', { params: { ...filters, page_size: 50 } }),
        filters.q ? api('/api/known-issues/', { params: { q: filters.q } }) : Promise.resolve({ results: [] }),
      ])
      setRows(listOf(issues))
      setKnown(listOf(knownIssues))
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader
        title="Knowledge search"
        subtitle="Has this happened before? Search every issue ever recorded — symptoms, root causes and resolutions — plus structured filters."
      />
      <Card as="form" onSubmit={run} footer={
        <button disabled={busy}><Icon name="search" />{busy ? 'Searching…' : 'Search'}</button>
      }>
        <Field label="Symptom / keyword">
          <input value={filters.q} onChange={set('q')} autoFocus
                 placeholder="e.g. GPS not detected after flashing" />
        </Field>
        <div className="grid cols-4">
          <Field label="Stage">
            <select value={filters.stage} onChange={set('stage')}>
              <option value="">Any</option>
              {stages.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="Category">
            <select value={filters.category} onChange={set('category')}>
              <option value="">Any</option>
              {meta.categories.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="Severity">
            <select value={filters.severity} onChange={set('severity')}>
              <option value="">Any</option>
              {meta.severities.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="Status">
            <select value={filters.status} onChange={set('status')}>
              <option value="">Any</option>
              {meta.statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="Hardware revision"><input value={filters.hardware_revision} onChange={set('hardware_revision')} /></Field>
          <Field label="Firmware version"><input value={filters.firmware_version} onChange={set('firmware_version')} /></Field>
          <Field label="GCS version"><input value={filters.gcs_version} onChange={set('gcs_version')} /></Field>
          <Field label="Configurator version"><input value={filters.configurator_version} onChange={set('configurator_version')} /></Field>
        </div>
      </Card>

      <Banner>{error}</Banner>

      {known.length ? (
        <Card title="Known issues matching">
          {known.map((k) => (
            <div className="note" key={k.id}>
              <strong>{k.title}</strong> <Tag tone="info">{k.occurrence_count} occurrences</Tag>
              <div className="small">{k.symptoms_summary}</div>
              <div className="small"><strong>Fix:</strong> {k.resolution}</div>
            </div>
          ))}
        </Card>
      ) : null}

      <Card title="Matching issues" actions={<Tag>{rows.length}</Tag>} flush>
        {busy ? <Loading what="results" cols={7} /> : rows.length === 0 ? <Empty icon="search">No results yet — run a search above.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Key</th><th>FC</th><th>Title</th><th>Root cause</th>
                <th>Severity</th><th>Status</th><th>When</th></tr></thead>
              <tbody>
                {rows.map((i) => (
                  <tr key={i.id}>
                    <td><IssueLink id={i.id} label={i.key} /></td>
                    <td><FcLink id={i.fc} serial={i.fc_serial} /></td>
                    <td>{i.title}<div className="small muted">{i.symptoms?.slice(0, 120)}</div></td>
                    <td className="small">{i.assigned_department_name || '—'}</td>
                    <td><SeverityTag value={i.severity} /></td>
                    <td><StatusTag value={i.status} /></td>
                    <td className="small muted">{when(i.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  )
}
