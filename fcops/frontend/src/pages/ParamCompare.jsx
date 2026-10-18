import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getTokens, listOf } from '../lib/api'
import { Banner, Card, Empty, Field, PageHeader, StatCard, Tag, when } from '../components/ui.jsx'

const TOLERANCES = [
  { value: 0, label: 'Show every difference' },
  { value: 1e-9, label: 'Ignore below 1e-9 (float noise)' },
  { value: 1e-6, label: 'Ignore below 0.0001%' },
  { value: 1e-4, label: 'Ignore below 0.01%' },
]

function Side({ side, stored, pick, onPick, file, onFile }) {
  const input = useRef(null)
  return (
    <div>
      <Field label={`${side} file`}>
        <select value={pick} onChange={(e) => { onPick(e.target.value); onFile(null) }}>
          <option value="">— upload a file —</option>
          {stored.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label || f.name} · {f.parameter_count} params
              {f.fc_serial ? ` · ${f.fc_serial}` : ''}
            </option>
          ))}
        </select>
      </Field>
      {!pick ? (
        <div className="row" style={{ marginTop: -4 }}>
          <input ref={input} type="file" accept=".param,.parm,.txt"
                 onChange={(e) => onFile(e.target.files?.[0] || null)} />
          {file ? <Tag tone="info">{file.name}</Tag> : null}
        </div>
      ) : null}
    </div>
  )
}

export default function ParamCompare() {
  const [stored, setStored] = useState([])
  const [leftPick, setLeftPick] = useState('')
  const [rightPick, setRightPick] = useState('')
  const [leftFile, setLeftFile] = useState(null)
  const [rightFile, setRightFile] = useState(null)
  const [tolerance, setTolerance] = useState(0)
  const [result, setResult] = useState(null)
  const [filter, setFilter] = useState('')
  const [group, setGroup] = useState('')
  const [showNegligible, setShowNegligible] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const loadStored = useCallback(() => {
    api('/api/parameter-files/', { params: { page_size: 100 } })
      .then((d) => setStored(listOf(d))).catch(() => {})
  }, [])
  useEffect(() => { loadStored() }, [loadStored])

  const ready = (leftPick || leftFile) && (rightPick || rightFile)

  const run = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setResult(null)
    try {
      const body = new FormData()
      body.append('tolerance', String(tolerance))
      if (leftPick) body.append('left', leftPick); else body.append('left_file', leftFile)
      if (rightPick) body.append('right', rightPick); else body.append('right_file', rightFile)
      setResult(await api('/api/parameter-files/compare/', {
        method: 'POST', body, isForm: true,
      }))
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const rows = result
    ? [...result.changed, ...result.only_in_left, ...result.only_in_right]
        .filter((r) => (showNegligible ? true : !r.negligible))
        .filter((r) => (group ? r.group === group : true))
        .filter((r) => (filter ? r.name.toLowerCase().includes(filter.toLowerCase()) : true))
    : []

  const kind = (r) => (r.left === null ? 'added' : r.right === null ? 'removed' : 'changed')

  return (
    <>
      <PageHeader
        title="Parameter Compare"
        subtitle={<>Diff two <span className="mono">.param</span> dumps. Upload them directly for a quick check, or pick dumps already stored against an FC. Comparing 1,100 lines by eye is how a wrong tuning value reaches a test flight.</>}
      />

      <Banner>{error}</Banner>

      <Card as="form" onSubmit={run}>
        <div className="grid cols-2">
          <Side side="Left" stored={stored} pick={leftPick} onPick={setLeftPick}
                file={leftFile} onFile={setLeftFile} />
          <Side side="Right" stored={stored} pick={rightPick} onPick={setRightPick}
                file={rightFile} onFile={setRightFile} />
        </div>
        <Field label="Precision">
          <select value={tolerance} onChange={(e) => setTolerance(Number(e.target.value))}>
            {TOLERANCES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </Field>
        <button disabled={busy || !ready}>{busy ? 'Comparing…' : 'Compare'}</button>
        {!ready ? (
          <span className="small muted" style={{ marginLeft: 10 }}>
            Choose or upload a file on each side.
          </span>
        ) : null}
      </Card>

      {result ? (
        <>
          <Card title={<>
            <span className="mono">{result.left_name}</span>
            <span className="muted"> vs </span>
            <span className="mono">{result.right_name}</span>
          </>}>
            <div className="grid cols-4">
              <StatCard label="Different values" value={result.summary.changed}
                        tone={result.summary.changed ? 'warn' : ''} />
              <StatCard label="Only on one side"
                        value={result.summary.only_in_left + result.summary.only_in_right} />
              <StatCard label="Identical" value={result.summary.identical} tone="ok" />
              <StatCard label="Groups affected" value={result.summary.groups_touched.length} />
            </div>
            {result.summary.changed === 0 && result.summary.only_in_left === 0
              && result.summary.only_in_right === 0 ? (
              <div className="banner ok" style={{ marginTop: 14 }}>
                These two files are identical — all {result.summary.identical} parameters match.
              </div>
            ) : null}
            {result.summary.negligible ? (
              <p className="small muted" style={{ marginTop: 10 }}>
                {result.summary.negligible} of the differences are within the
                precision threshold and are marked as noise.
              </p>
            ) : null}
            <div className="row small" style={{ marginTop: 12 }}>
              <span className="muted">Groups:</span>
              <button type="button" className={group ? 'secondary sm' : 'sm'}
                      
                      onClick={() => setGroup('')}>All</button>
              {result.summary.groups_touched.map((g) => (
                <button type="button" key={g}
                        className={group === g ? 'sm' : 'secondary sm'}
                        
                        onClick={() => setGroup(g === group ? '' : g)}>{g}</button>
              ))}
            </div>
          </Card>

          <Card title="Differences" flush actions={<>
              <input placeholder="Filter by parameter name…" style={{ maxWidth: 300 }}
                     value={filter} onChange={(e) => setFilter(e.target.value)} />
              <label className="row small" style={{ marginBottom: 0 }}>
                <input type="checkbox" checked={showNegligible} style={{ width: 'auto' }}
                       onChange={(e) => setShowNegligible(e.target.checked)} />
                Include negligible differences
              </label>
              <span className="small muted">{rows.length} shown</span>
            </>}>
            {rows.length === 0 ? <Empty>No differences match this filter.</Empty> : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Parameter</th><th>Group</th>
                      <th style={{ textAlign: 'right' }}>Left</th>
                      <th style={{ textAlign: 'right' }}>Right</th>
                      <th style={{ textAlign: 'right' }}>Change</th><th /></tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.name}>
                        <td className="mono">{r.name}</td>
                        <td className="small muted">{r.group}</td>
                        <td className="mono" style={{ textAlign: 'right',
                                                      fontVariantNumeric: 'tabular-nums' }}>
                          {r.left ?? <span className="muted">—</span>}
                        </td>
                        <td className="mono" style={{ textAlign: 'right',
                                                      fontVariantNumeric: 'tabular-nums' }}>
                          {r.right ?? <span className="muted">—</span>}
                        </td>
                        <td className="mono small" style={{ textAlign: 'right',
                                                            fontVariantNumeric: 'tabular-nums' }}>
                          {r.delta ?? '—'}
                        </td>
                        <td>
                          {kind(r) === 'changed'
                            ? (r.negligible ? <Tag>noise</Tag> : <Tag tone="warn">changed</Tag>)
                            : kind(r) === 'added'
                              ? <Tag tone="info">only right</Tag>
                              : <Tag tone="info">only left</Tag>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      ) : null}

      <Card title="Stored dumps" subtitle="Upload a dump against an FC to keep it in that FC's history.">
        <UploadForm onDone={loadStored} />
        {stored.length === 0 ? <Empty>Nothing stored yet.</Empty> : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead><tr><th>File</th><th>FC</th><th>Parameters</th>
                <th>Uploaded by</th><th>When</th></tr></thead>
              <tbody>
                {stored.map((f) => (
                  <tr key={f.id}>
                    <td>{f.label || f.name}
                      {f.label ? <div className="mono small muted">{f.name}</div> : null}</td>
                    <td className="mono small">{f.fc_serial || '—'}</td>
                    <td className="small">{f.parameter_count}</td>
                    <td className="small">{f.uploaded_by_name}</td>
                    <td className="small muted">{when(f.created_at)}</td>
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

function UploadForm({ onDone }) {
  const [file, setFile] = useState(null)
  const [label, setLabel] = useState('')
  const [fc, setFc] = useState('')
  const [fcs, setFcs] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/api/fcs/', { params: { page_size: 200 } })
      .then((d) => setFcs(listOf(d))).catch(() => {})
  }, [])

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const body = new FormData()
      body.append('file', file)
      if (label) body.append('label', label)
      if (fc) body.append('fc', fc)
      await api('/api/parameter-files/', { method: 'POST', body, isForm: true })
      setFile(null); setLabel(''); setFc(''); onDone()
      e.target.reset()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit}>
      <Banner>{error}</Banner>
      <div className="grid cols-3">
        <Field label="File">
          <input type="file" accept=".param,.parm,.txt"
                 onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </Field>
        <Field label="Label">
          <input value={label} onChange={(e) => setLabel(e.target.value)}
                 placeholder="e.g. after bench tune" />
        </Field>
        <Field label="Attach to FC">
          <select value={fc} onChange={(e) => setFc(e.target.value)}>
            <option value="">— not attached —</option>
            {fcs.map((f) => <option key={f.id} value={f.id}>{f.serial}</option>)}
          </select>
        </Field>
      </div>
      <button disabled={busy || !file}>{busy ? 'Uploading…' : 'Upload dump'}</button>
    </form>
  )
}
