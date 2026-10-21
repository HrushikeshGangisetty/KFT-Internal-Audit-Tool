import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, listOf } from '../../lib/api'
import {
  Card, Empty, FcLink, Field, Icon, IssueLink, PageHeader, SeverityTag, StatusTag, Tag, when,
} from '../../components/ui.jsx'
import { Paged, usePaged } from '../../components/data.jsx'

const BLANK = {
  q: '', category: '', severity: '', status: '', stage: '',
  hardware_revision: '', firmware_version: '', gcs_version: '', configurator_version: '',
}

export default function Search() {
  const [params, setParams] = useSearchParams()
  const [meta, setMeta] = useState({ statuses: [], severities: [], categories: [] })
  const [stages, setStages] = useState([])
  const [filters, setFilters] = useState({ ...BLANK, q: params.get('q') || '' })
  // Searches run on submit; `?q=` from the top bar submits straight away.
  const [submitted, setSubmitted] = useState(params.get('q') ? { ...BLANK, q: params.get('q') } : null)
  const page = usePaged(submitted ? '/api/issues/search/' : null, submitted ?? {})
  const [known, setKnown] = useState([])

  useEffect(() => {
    api('/api/issues/meta/').then(setMeta).catch(() => {})
    api('/api/lifecycle/').then((d) => setStages(d.stages)).catch(() => {})
  }, [])

  // A new top-bar search while already on this page.
  const urlQ = params.get('q') || ''
  useEffect(() => {
    if (!urlQ) return
    setFilters((f) => ({ ...f, q: urlQ }))
    setSubmitted((s) => ({ ...(s ?? BLANK), q: urlQ }))
  }, [urlQ])

  useEffect(() => {
    if (!submitted?.q) { setKnown([]); return }
    api('/api/known-issues/', { params: { q: submitted.q, page_size: 5 } })
      .then((d) => setKnown(listOf(d))).catch(() => setKnown([]))
  }, [submitted])

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }))
  const run = (e) => {
    e.preventDefault()
    if (JSON.stringify(filters) === JSON.stringify(submitted)) page.reload()
    else setSubmitted({ ...filters })
    setParams(filters.q ? { q: filters.q } : {}, { replace: true })
  }
  const select = (k, label, options) => (
    <Field label={label}>
      <select value={filters[k]} onChange={set(k)}>
        <option value="">Any</option>
        {options.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
      </select>
    </Field>
  )

  return (
    <>
      <PageHeader
        title="Knowledge search"
        subtitle="Has this happened before? Search every issue you can see — symptoms, root causes and resolutions — plus structured filters."
      />
      <Card as="form" onSubmit={run} footer={
        <button disabled={submitted && page.rows === null}><Icon name="search" />Search</button>
      }>
        <Field label="Symptom / keyword">
          <input value={filters.q} onChange={set('q')} autoFocus type="search"
                 placeholder="e.g. GPS not detected after flashing" />
        </Field>
        <div className="grid cols-4">
          {select('stage', 'Stage', stages)}
          {select('category', 'Category', meta.categories)}
          {select('severity', 'Severity', meta.severities)}
          {select('status', 'Status', meta.statuses)}
          <Field label="Hardware revision"><input value={filters.hardware_revision} onChange={set('hardware_revision')} /></Field>
          <Field label="Firmware version"><input value={filters.firmware_version} onChange={set('firmware_version')} /></Field>
          <Field label="GCS version"><input value={filters.gcs_version} onChange={set('gcs_version')} /></Field>
          <Field label="Configurator version"><input value={filters.configurator_version} onChange={set('configurator_version')} /></Field>
        </div>
      </Card>

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

      <Card title="Matching issues" flush
            actions={submitted && page.rows ? <Tag>{page.count}</Tag> : null}>
        {!submitted ? <Empty icon="search">Run a search above.</Empty> : (
          <Paged page={page} what="results" cols={7} empty="No issues match this search." emptyIcon="search">
            {(rows) => (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Key</th><th>FC</th><th>Title</th><th>Assigned</th>
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
          </Paged>
        )}
      </Card>
    </>
  )
}
