import { useEffect, useState } from 'react'
import { api } from '../../../lib/api'
import { Banner, Empty, Field, StatusTag, when } from '../../../components/ui.jsx'

export default function StageRecords({ records, fc, onDone }) {
  const [reworkFor, setReworkFor] = useState(null)
  if (!records.length) return <Empty />
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Stage</th><th>Attempt</th><th>Status</th><th>Operator</th>
              <th>Completed</th><th>Notes</th><th /></tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id}>
                <td>{r.stage_label}</td>
                <td>{r.attempt}</td>
                <td><StatusTag value={r.status} /></td>
                <td className="small">{r.operator_name || '—'}</td>
                <td className="small muted">{when(r.completed_at)}</td>
                <td className="small">{r.notes || '—'}</td>
                <td>
                  {r.status === 'FAILED' && r.allowed_rework_targets.length ? (
                    <button className="link" onClick={() => setReworkFor(r)}>Add rework</button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {reworkFor ? (
        <ReworkForm record={reworkFor} fc={fc} onClose={() => setReworkFor(null)}
                    onDone={() => { setReworkFor(null); onDone() }} />
      ) : null}
    </>
  )
}

function ReworkForm({ record, fc, onClose, onDone }) {
  const [description, setDescription] = useState('')
  const [target, setTarget] = useState(record.allowed_rework_targets[0]?.value || '')
  const [issue, setIssue] = useState('')
  const [issues, setIssues] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`/api/fcs/${fc.id}/issues/`).then(setIssues).catch(() => {})
  }, [fc.id])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const rework = await api('/api/rework-records/', {
        method: 'POST',
        body: {
          stage_record: record.id, description, return_to_stage: target,
          originating_issue: issue ? Number(issue) : null,
        },
      })
      await api(`/api/rework-records/${rework.id}/complete/`, {
        method: 'POST', body: { outcome: 'COMPLETED', outcome_notes: description },
      })
      onDone()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
      <h3>Rework on {record.stage_label} (attempt {record.attempt})</h3>
      <Banner>{error}</Banner>
      <Field label="What was reworked">
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} required />
      </Field>
      <Field label="Return the FC to" hint="Only routes allowed for this failure are listed.">
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          {record.allowed_rework_targets.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </Field>
      <Field label="Originating issue">
        <select value={issue} onChange={(e) => setIssue(e.target.value)}>
          <option value="">— none —</option>
          {issues.map((i) => <option key={i.id} value={i.id}>{i.key} · {i.title}</option>)}
        </select>
      </Field>
      <div className="row">
        <button disabled={busy || !description}>Record rework &amp; return FC</button>
        <button type="button" className="secondary" onClick={onClose}>Cancel</button>
      </div>
    </form>
  )
}

