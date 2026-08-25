import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import {
  Banner, Empty, FcLink, Field, Loading, SeverityTag, StatusTag, Tag, humanize, when,
} from '../components/ui.jsx'
import SimilarPanel from './SimilarPanel.jsx'

export default function IssueDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const [issue, setIssue] = useState(null)
  const [departments, setDepartments] = useState([])
  const [similar, setSimilar] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [resolveForm, setResolveForm] = useState({ root_cause: '', resolution: '', root_cause_department: '' })
  const [reassignForm, setReassignForm] = useState({ to_department: '', reason: '' })

  const reload = useCallback(async () => {
    const data = await api(`/api/issues/${id}/`)
    setIssue(data)
    setResolveForm((f) => ({
      root_cause: f.root_cause || data.root_cause || '',
      resolution: f.resolution || data.resolution || '',
      root_cause_department: f.root_cause_department || data.root_cause_department || '',
    }))
  }, [id])

  useEffect(() => {
    reload().catch((e) => setError(e.message))
    api('/api/departments/', { params: { page_size: 100 } }).then((d) => setDepartments(listOf(d)))
    api(`/api/issues/${id}/similar/`).then(setSimilar).catch(() => {})
  }, [id, reload])

  const run = async (fn) => {
    setBusy(true); setError(''); setMessage('')
    try { await fn(); await reload(); setMessage('Done.') }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  if (error && !issue) return <Banner>{error}</Banner>
  if (!issue) return <Loading what="issue" />

  const can = user?.permissions || {}
  const allowed = issue.allowed_transitions || []

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <h2 className="mono" style={{ margin: 0, fontSize: 20 }}>{issue.key}</h2>
        <StatusTag value={issue.status} />
        <SeverityTag value={issue.severity} />
        <Tag>{humanize(issue.category)}</Tag>
        {issue.is_recurring ? <Tag tone="warn">recurring</Tag> : null}
        {issue.is_waiting ? <Tag>waiting: {issue.waiting_reason}</Tag> : null}
      </div>
      <p style={{ marginTop: 0, fontSize: 17 }}>{issue.title}</p>

      <Banner>{error}</Banner>
      <Banner kind="ok">{message}</Banner>

      <div className="split">
        <div>
          <div className="card">
            <h2>Symptoms</h2>
            <p style={{ whiteSpace: 'pre-wrap' }}>{issue.symptoms}</p>
            {issue.description ? (
              <>
                <h3>Description</h3>
                <p style={{ whiteSpace: 'pre-wrap' }}>{issue.description}</p>
              </>
            ) : null}
          </div>

          <div className="card">
            <h2>Investigation log</h2>
            {issue.investigation_notes.length === 0 ? <Empty>No notes yet.</Empty> : null}
            {issue.investigation_notes.map((n) => (
              <div key={n.id} className="note">
                <div style={{ whiteSpace: 'pre-wrap' }}>{n.note}</div>
                <div className="meta">
                  {n.author_name || '—'} · {n.author_department} · {when(n.created_at)}
                </div>
              </div>
            ))}
            {issue.status !== 'CLOSED' ? (
              <>
                <Field label="Add a note (append-only)">
                  <textarea value={note} onChange={(e) => setNote(e.target.value)} />
                </Field>
                <button disabled={busy || !note.trim()} onClick={() =>
                  run(async () => {
                    await api(`/api/issues/${id}/notes/`, { method: 'POST', body: { note } })
                    setNote('')
                  })}>Add note</button>
              </>
            ) : <p className="muted small">Closed issues are read-only.</p>}
          </div>

          <div className="card">
            <h2>Root cause &amp; resolution</h2>
            {issue.root_cause ? (
              <dl className="kv" style={{ marginBottom: 12 }}>
                <dt>Root cause</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{issue.root_cause}</dd>
                <dt>Owned by</dt><dd>{issue.root_cause_department_name || '—'}</dd>
                <dt>Resolution</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{issue.resolution}</dd>
                <dt>Resolved by</dt><dd>{issue.resolved_by_name || '—'} · {when(issue.resolved_at)}</dd>
                <dt>Verified by</dt><dd>{issue.verified_by_name || '— not yet verified —'} {issue.verified_at ? `· ${when(issue.verified_at)}` : ''}</dd>
              </dl>
            ) : <Empty>No root cause recorded yet.</Empty>}

            {allowed.includes('RESOLVED') ? (
              <>
                <h3>Record the resolution</h3>
                <Field label="Root cause">
                  <textarea value={resolveForm.root_cause}
                            onChange={(e) => setResolveForm((f) => ({ ...f, root_cause: e.target.value }))} />
                </Field>
                <Field label="Department the root cause originated in"
                       hint="This can differ from where the issue was discovered.">
                  <select value={resolveForm.root_cause_department}
                          onChange={(e) => setResolveForm((f) => ({ ...f, root_cause_department: e.target.value }))}>
                    <option value="">— not determined —</option>
                    {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </Field>
                <Field label="Resolution">
                  <textarea value={resolveForm.resolution}
                            onChange={(e) => setResolveForm((f) => ({ ...f, resolution: e.target.value }))} />
                </Field>
                <button disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/status/`, {
                    method: 'POST',
                    body: {
                      status: 'RESOLVED', ...resolveForm,
                      root_cause_department: resolveForm.root_cause_department
                        ? Number(resolveForm.root_cause_department) : null,
                    },
                  }))}>Mark resolved</button>
              </>
            ) : null}
          </div>

          <div className="card">
            <h2>Reassignment history</h2>
            {issue.reassignments.length === 0 ? <Empty /> : null}
            <ul className="timeline">
              {issue.reassignments.map((r) => (
                <li key={r.id}>
                  <div className="t">
                    {r.from_department_name || 'Unassigned'} → {r.to_department_name || 'Unassigned'}
                    {r.to_person_name ? ` (${r.to_person_name})` : ''}
                  </div>
                  <div className="small">{r.reason}</div>
                  <div className="meta">{r.actor_name} · {when(r.created_at)}</div>
                </li>
              ))}
            </ul>
            {issue.status !== 'CLOSED' ? (
              <>
                <div className="grid cols-2">
                  <Field label="Reassign to department">
                    <select value={reassignForm.to_department}
                            onChange={(e) => setReassignForm((f) => ({ ...f, to_department: e.target.value }))}>
                      <option value="">— select —</option>
                      {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                  </Field>
                  <Field label="Reason (mandatory)">
                    <input value={reassignForm.reason}
                           onChange={(e) => setReassignForm((f) => ({ ...f, reason: e.target.value }))} />
                  </Field>
                </div>
                <button disabled={busy || !reassignForm.to_department || !reassignForm.reason}
                        onClick={() => run(async () => {
                          await api(`/api/issues/${id}/reassign/`, {
                            method: 'POST',
                            body: {
                              to_department: Number(reassignForm.to_department),
                              reason: reassignForm.reason,
                            },
                          })
                          setReassignForm({ to_department: '', reason: '' })
                        })}>Reassign</button>
              </>
            ) : null}
          </div>
        </div>

        <div>
          <div className="card">
            <h2>Discovery vs. ownership</h2>
            <dl className="kv">
              <dt>FC</dt><dd><FcLink id={issue.fc} serial={issue.fc_serial} /></dd>
              <dt>Discovered at</dt><dd>{issue.stage_label}</dd>
              <dt>Discovered by</dt><dd>{issue.discovered_by_name || '—'}</dd>
              <dt>Discovering dept</dt><dd>{issue.discovering_department_name || '—'}</dd>
              <dt>Assigned dept</dt><dd>{issue.assigned_department_name || '— unassigned —'}</dd>
              <dt>Assigned person</dt><dd>{issue.assigned_person_name || '—'}</dd>
              <dt>Root cause dept</dt><dd>{issue.root_cause_department_name || '— not determined —'}</dd>
              <dt>Opened</dt><dd>{when(issue.created_at)}</dd>
            </dl>
          </div>

          <div className="card">
            <h2>Versions at discovery</h2>
            <dl className="kv">
              <dt>Hardware</dt><dd className="mono">{issue.hardware_revision || '—'}</dd>
              <dt>Firmware</dt><dd className="mono">{issue.firmware_version || '—'}</dd>
              <dt>Parameters</dt><dd className="mono">{issue.parameter_profile || '—'}</dd>
              <dt>GCS</dt><dd className="mono">{issue.gcs_version || '—'}</dd>
              <dt>Configurator</dt><dd className="mono">{issue.configurator_version || '—'}</dd>
            </dl>
          </div>

          <div className="card">
            <h2>Actions</h2>
            <div className="row">
              {allowed.includes('INVESTIGATING') ? (
                <button className="secondary" disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/status/`, { method: 'POST', body: { status: 'INVESTIGATING' } }))}>
                  Start investigating
                </button>
              ) : null}
              {allowed.includes('VERIFIED') && can.can_verify ? (
                <button className="ok" disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/status/`, { method: 'POST', body: { status: 'VERIFIED' } }))}>
                  Verify fix
                </button>
              ) : null}
              {allowed.includes('CLOSED') ? (
                <button disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/status/`, { method: 'POST', body: { status: 'CLOSED' } }))}>
                  Close issue
                </button>
              ) : null}
              {issue.status === 'CLOSED' && can.is_manager ? (
                <button className="secondary" disabled={busy} onClick={() => {
                  const reason = window.prompt('Reason for reopening?')
                  if (reason) run(() => api(`/api/issues/${id}/reopen/`, { method: 'POST', body: { reason } }))
                }}>Reopen</button>
              ) : null}
              {issue.status !== 'CLOSED' ? (
                <button className="secondary" disabled={busy} onClick={() => {
                  const reason = issue.is_waiting ? '' : window.prompt('Waiting on what?') || ''
                  run(() => api(`/api/issues/${id}/waiting/`, {
                    method: 'POST', body: { waiting: !issue.is_waiting, reason },
                  }))
                }}>{issue.is_waiting ? 'Clear waiting flag' : 'Flag as waiting'}</button>
              ) : null}
            </div>
            {can.can_promote_known_issue && !issue.known_issue
              && ['RESOLVED', 'VERIFIED', 'CLOSED'].includes(issue.status) ? (
              <div style={{ marginTop: 10 }}>
                <button className="secondary" disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/promote/`, { method: 'POST', body: {} }))}>
                  Promote to Known Issue
                </button>
              </div>
            ) : null}
            {issue.known_issue_detail ? (
              <p className="small" style={{ marginBottom: 0 }}>
                Linked known issue: <strong>{issue.known_issue_detail.title}</strong>{' '}
                ({issue.known_issue_detail.occurrence_count} occurrences)
              </p>
            ) : null}
          </div>

          <div className="card">
            <h2>Attachments</h2>
            <Attachments issue={issue} onDone={reload} />
          </div>

          <div className="card">
            <h2>Similar past issues</h2>
            <SimilarPanel result={similar} loading={!similar} />
          </div>
        </div>
      </div>
    </>
  )
}

function Attachments({ issue, onDone }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const upload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true); setError('')
    try {
      const body = new FormData()
      body.append('issue', issue.id)
      body.append('file', file)
      await api('/api/issue-attachments/', { method: 'POST', body, isForm: true })
      await onDone()
    } catch (err) { setError(err.message) } finally { setBusy(false); e.target.value = '' }
  }

  return (
    <>
      <Banner>{error}</Banner>
      {issue.attachments.length === 0 ? <Empty>No photos, logs or captures yet.</Empty> : null}
      {issue.attachments.map((a) => (
        <div key={a.id} className="note">
          <a href={a.url} target="_blank" rel="noreferrer">{a.original_name || 'file'}</a>
          <div className="meta">
            {Math.round((a.size || 0) / 1024)} kB · {a.uploaded_by_name} · {when(a.created_at)}
          </div>
        </div>
      ))}
      {issue.status !== 'CLOSED' ? (
        <div style={{ marginTop: 8 }}>
          <input type="file" onChange={upload} disabled={busy} />
        </div>
      ) : null}
    </>
  )
}
