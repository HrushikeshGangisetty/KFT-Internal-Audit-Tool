import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../../../lib/api'
import { Banner, Empty, Field, StatusTag, humanize, when } from '../../../components/ui.jsx'

const TEST_STAGES = ['SENSOR_VALIDATION', 'BENCH_TESTING', 'GROUND_TESTING', 'FINAL_VALIDATION']

export default function TestTab({ fc, current, onDone }) {
  const [templates, setTemplates] = useState([])
  const [versions, setVersions] = useState([])
  const [rows, setRows] = useState([])
  const [items, setItems] = useState([])
  const [gcs, setGcs] = useState('')
  const [cfg, setCfg] = useState('')
  const [notes, setNotes] = useState('')
  const [version, setVersion] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const stage = fc.current_stage

  const load = useCallback(() => {
    api('/api/test-results/', { params: { fc: fc.id } }).then((d) => setRows(listOf(d)))
  }, [fc.id])

  useEffect(() => {
    load()
    api('/api/software-versions/', { params: { page_size: 100 } }).then((d) => setVersions(listOf(d)))
    // Pull the checklist through /current/ so the tester always sees exactly the
    // configuration a manager has published, together with its version.
    api('/api/checklist-templates/', { params: { stage, is_active: true } })
      .then((d) => {
        const list = listOf(d)
        setTemplates(list)
        if (!list[0]) { setItems([]); return }
        return api(`/api/checklist-templates/${list[0].id}/current/`).then((cfg) => {
          setVersion(cfg.version)
          setItems((cfg.items || []).map((i) => ({ ...i, passed: true, note: '' })))
        })
      })
      .catch(() => {})
  }, [stage, load])

  if (!TEST_STAGES.includes(stage)) {
    return (
      <>
        <h3>Test results</h3>
        <p className="muted small">
          The FC is at {humanize(stage)}, which is not a testing stage. Existing results:
        </p>
        <ResultsTable rows={rows} />
      </>
    )
  }

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      await api('/api/test-results/', {
        method: 'POST',
        body: {
          fc: fc.id, stage_record: current?.id, test_type: stage,
          template: templates[0]?.id ?? null, checklist_results: items,
          gcs_version: gcs ? Number(gcs) : null,
          configurator_version: cfg ? Number(cfg) : null, notes,
        },
      })
      setNotes(''); load(); onDone()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <>
      <h3>Test results</h3>
      <ResultsTable rows={rows} />
      <form onSubmit={submit} style={{ marginTop: 18, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <h3>
          Record {humanize(stage)} checklist
          {version ? <span className="tag info" style={{ marginLeft: 8 }}>
            checklist v{version}</span> : null}
        </h3>
        <Banner>{error}</Banner>
        {items.length === 0 ? <Empty>No checklist template configured for this stage.</Empty> : null}
        {items.map((item, idx) => (
          <div key={item.key} className="row" style={{ marginBottom: 6 }}>
            <input type="checkbox" checked={item.passed} style={{ width: 'auto' }}
                   onChange={(e) => setItems((all) =>
                     all.map((x, i) => (i === idx ? { ...x, passed: e.target.checked } : x)))} />
            <span style={{ minWidth: 260 }}>
              {item.label}
              {item.mandatory === false
                ? <span className="muted small"> (optional)</span> : null}
              {item.description
                ? <div className="small muted">{item.description}</div> : null}
            </span>
            <input placeholder="Note (optional)" value={item.note} style={{ maxWidth: 320 }}
                   onChange={(e) => setItems((all) =>
                     all.map((x, i) => (i === idx ? { ...x, note: e.target.value } : x)))} />
          </div>
        ))}
        <div className="grid cols-2" style={{ marginTop: 12 }}>
          <Field label="GCS version used">
            <select value={gcs} onChange={(e) => setGcs(e.target.value)}>
              <option value="">— not recorded —</option>
              {versions.filter((v) => v.kind === 'GCS').map((v) => (
                <option key={v.id} value={v.id}>{v.version}</option>))}
            </select>
          </Field>
          <Field label="Configurator version used">
            <select value={cfg} onChange={(e) => setCfg(e.target.value)}>
              <option value="">— not recorded —</option>
              {versions.filter((v) => v.kind === 'CONFIGURATOR').map((v) => (
                <option key={v.id} value={v.id}>{v.version}</option>))}
            </select>
          </Field>
        </div>
        <Field label="Notes"><textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <button disabled={busy || items.length === 0}>Save test result</button>
      </form>
    </>
  )
}

function ResultsTable({ rows }) {
  if (!rows.length) return <Empty>No test results recorded.</Empty>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Test</th><th>Result</th><th>Failed items</th><th>GCS</th>
          <th>Configurator</th><th>Tester</th><th>When</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{humanize(r.test_type)}</td>
              <td><StatusTag value={r.overall_passed ? 'PASSED' : 'FAILED'} /></td>
              <td className="small">
                {(r.checklist_results || []).filter((i) => !i.passed)
                  .map((i) => i.label).join(', ') || '—'}
              </td>
              <td className="small mono">{r.gcs_version_label || '—'}</td>
              <td className="small mono">{r.configurator_version_label || '—'}</td>
              <td className="small">{r.tester_name}</td>
              <td className="small muted">{when(r.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

