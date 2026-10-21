import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, listOf } from '../../lib/api'
import { useAuth } from '../../lib/auth.jsx'
import {
  Banner, Card, DueTag, Empty, FcLink, Field, Icon, OwnerTag, PageHeader, PageSkeleton, SeverityTag,
  StatusTag, Tag, UrgencyTag, humanize, when,
} from '../../components/ui.jsx'
import { useDialog, useToast } from '../../components/overlay.jsx'
import { Acknowledge } from '../work/Queue.jsx'
import SimilarPanel from './SimilarPanel.jsx'

export default function IssueDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const ask = useDialog()
  const toast = useToast()
  const [issue, setIssue] = useState(null)
  const [departments, setDepartments] = useState([])
  const [users, setUsers] = useState([])
  const [participantForm, setParticipantForm] = useState({ user: '', role: 'verifier' })
  const [similar, setSimilar] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [resolveForm, setResolveForm] = useState({ root_cause: '', resolution: '', root_cause_department: '' })
  const [reassignForm, setReassignForm] = useState({ to_department: '', reason: '' })
  const [handoffTo, setHandoffTo] = useState('')
  const [awaitingAck, setAwaitingAck] = useState(false)

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
    api('/api/departments/', { params: { page_size: 100 } }).then((d) => setDepartments(listOf(d))).catch(() => {})
    api('/api/users/', { params: { page_size: 200, is_active: true } }).then((d) => setUsers(listOf(d))).catch(() => {})
    api(`/api/issues/${id}/similar/`).then(setSimilar).catch(() => {})
    // Same rule as services.acknowledge: accountable person or queue head/backup.
    api('/api/me/queue/').then((q) => setAwaitingAck(q.awaiting_acknowledgement.some((i) => i.id === Number(id))))
      .catch(() => {})
  }, [id, reload])

  const run = async (fn, done = 'Saved.') => {
    setBusy(true); setError('')
    try { await fn(); await reload(); toast(done) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  if (error && !issue) return <Banner>{error}</Banner>
  if (!issue) return <PageSkeleton split />

  const can = user?.permissions || {}
  const allowed = issue.allowed_transitions || []
  const pendingHandoff = issue.handoffs.find((h) => h.status === 'pending')
  // Mirrors services.propose_handoff, except queue head/backup who are not heads.
  const canHandoff = issue.status !== 'CLOSED' && !pendingHandoff
    && (issue.accountable_user === user?.id || can.is_head_or_manager)

  return (
    <>
      <PageHeader
        title={issue.title}
        back={{ to: '/issues', label: 'Issues' }}
        meta={<>
          <span className="mono small muted">{issue.key}</span>
          <UrgencyTag value={issue.urgency} />
          <StatusTag value={issue.status} />
          <OwnerTag name={issue.accountable_user_name} />
          {issue.ack_due_at ? <DueTag at={issue.ack_due_at} label="Ack" /> : null}
          <SeverityTag value={issue.severity} />
          <Tag>{humanize(issue.category)}</Tag>
          {issue.is_recurring ? <Tag tone="warn">recurring</Tag> : null}
          {issue.is_waiting ? <Tag>waiting: {issue.waiting_reason}</Tag> : null}
        </>}
        actions={issue.fc ? <Link className="btn secondary" to={`/fcs/${issue.fc}`}>
          <Icon name="chip" />{issue.fc_serial}
        </Link> : null}
      />

      <Banner>{error}</Banner>

      <div className="split">
        <div>
          <Card title="Symptoms">
            <p style={{ whiteSpace: 'pre-wrap', marginTop: 0 }}>{issue.symptoms}</p>
            {issue.description ? (
              <>
                <h3>Description</h3>
                <p style={{ whiteSpace: 'pre-wrap' }}>{issue.description}</p>
              </>
            ) : null}
          </Card>

          <Card title="Investigation log">
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
                  }, 'Note added.')}>Add note</button>
              </>
            ) : <p className="muted small">Closed issues are read-only.</p>}
          </Card>

          <Card title="Root cause & resolution">
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
                  }), 'Marked resolved.')}>Mark resolved</button>
              </>
            ) : null}
          </Card>

          <Card title="Reassignment history">
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
                        }, 'Reassigned.')}>Reassign</button>
              </>
            ) : null}
          </Card>
        </div>

        <div>
          <Card title="Discovery vs. ownership">
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
          </Card>

          <Card title="Participants"
                subtitle="Verifiers and collaborators can open this issue even outside its department.">
            {issue.participants.length === 0 ? <Empty>None yet.</Empty> : null}
            {issue.participants.length ? (
              <ul className="qlist">{issue.participants.map((p) => (
                <li key={p.id} className="qrow small">{p.user_name} · {humanize(p.role)}</li>
              ))}</ul>
            ) : null}
            {issue.status !== 'CLOSED' ? (
              <div className="row" style={{ marginTop: 8 }}>
                <select aria-label="Participant" value={participantForm.user}
                        onChange={(e) => setParticipantForm((f) => ({ ...f, user: e.target.value }))}>
                  <option value="">— person —</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.username}</option>)}
                </select>
                <select aria-label="Participant role" value={participantForm.role}
                        onChange={(e) => setParticipantForm((f) => ({ ...f, role: e.target.value }))}>
                  <option value="verifier">Verifier</option>
                  <option value="collaborator">Collaborator</option>
                </select>
                <button className="secondary" disabled={busy || !participantForm.user}
                        onClick={() => run(async () => {
                          await api(`/api/issues/${id}/participants/`, {
                            method: 'POST',
                            body: { user: Number(participantForm.user), role: participantForm.role },
                          })
                          setParticipantForm({ user: '', role: 'verifier' })
                        }, 'Participant added.')}>Add</button>
              </div>
            ) : null}
          </Card>

          <Card title="Versions at discovery">
            <dl className="kv">
              <dt>Hardware</dt><dd className="mono">{issue.hardware_revision || '—'}</dd>
              <dt>Firmware</dt><dd className="mono">{issue.firmware_version || '—'}</dd>
              <dt>Parameters</dt><dd className="mono">{issue.parameter_profile || '—'}</dd>
              <dt>GCS</dt><dd className="mono">{issue.gcs_version || '—'}</dd>
              <dt>Configurator</dt><dd className="mono">{issue.configurator_version || '—'}</dd>
            </dl>
          </Card>

          <Card title="Actions">
            <div className="row">
              {awaitingAck && !issue.acknowledged_at && issue.status !== 'CLOSED'
                ? <Acknowledge issue={issue} onDone={reload} /> : null}
              {allowed.includes('INVESTIGATING') ? (
                <button className="secondary" disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/status/`, { method: 'POST', body: { status: 'INVESTIGATING' } }),
                'Investigation started.')}>
                  Start investigating
                </button>
              ) : null}
              {allowed.includes('VERIFIED') && can.can_verify ? (
                <button className="ok" disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/status/`, { method: 'POST', body: { status: 'VERIFIED' } }),
                'Fix verified.')}>
                  Verify fix
                </button>
              ) : null}
              {allowed.includes('CLOSED') ? (
                <button disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/status/`, { method: 'POST', body: { status: 'CLOSED' } }),
                'Issue closed.')}>
                  Close issue
                </button>
              ) : null}
              {issue.status === 'CLOSED' && can.is_manager ? (
                <button className="secondary" disabled={busy} onClick={async () => {
                  const r = await ask({ title: `Reopen ${issue.key}`, input: { label: 'Reason for reopening' },
                    confirmLabel: 'Reopen' })
                  if (r) run(() => api(`/api/issues/${id}/reopen/`, { method: 'POST', body: { reason: r.text } }),
                    'Issue reopened.')
                }}>Reopen…</button>
              ) : null}
              {issue.status !== 'CLOSED' ? (
                <button className="secondary" disabled={busy} onClick={async () => {
                  let reason = ''
                  if (!issue.is_waiting) {
                    const r = await ask({ title: 'Flag as waiting', confirmLabel: 'Flag as waiting',
                      input: { label: 'Waiting on what?', placeholder: 'e.g. replacement part, customer log' } })
                    if (!r) return
                    reason = r.text
                  }
                  run(() => api(`/api/issues/${id}/waiting/`, {
                    method: 'POST', body: { waiting: !issue.is_waiting, reason },
                  }), issue.is_waiting ? 'Waiting flag cleared.' : 'Flagged as waiting.')
                }}>{issue.is_waiting ? 'Clear waiting flag' : 'Flag as waiting…'}</button>
              ) : null}
            </div>
            {pendingHandoff ? (
              <p className="small">Handoff to <strong>{pendingHandoff.to_department_name}</strong> is waiting
                for that team to accept. Ownership does not change until then.</p>
            ) : null}
            {canHandoff ? (
              <div className="row" style={{ marginTop: 10 }}>
                <select aria-label="Hand off to" value={handoffTo} onChange={(e) => setHandoffTo(e.target.value)}>
                  <option value="">— hand off to team —</option>
                  {departments.filter((d) => d.id !== issue.assigned_department)
                    .map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <button className="secondary" disabled={busy || !handoffTo} onClick={async () => {
                  const dept = departments.find((d) => d.id === Number(handoffTo))
                  const r = await ask({ title: `Hand off ${issue.key} to ${dept?.name}`, confirmLabel: 'Propose handoff',
                    message: 'You stay accountable until the receiving team accepts.',
                    input: { label: 'Why should this team take it?' } })
                  if (r) run(async () => {
                    await api(`/api/issues/${id}/handoffs/`, {
                      method: 'POST', body: { to_department: Number(handoffTo), reason: r.text },
                    })
                    setHandoffTo('')
                  }, 'Handoff proposed.')
                }}>Propose handoff…</button>
              </div>
            ) : null}
            {can.can_promote_known_issue && !issue.known_issue
              && ['RESOLVED', 'VERIFIED', 'CLOSED'].includes(issue.status) ? (
              <div style={{ marginTop: 10 }}>
                <button className="secondary" disabled={busy} onClick={() => run(() =>
                  api(`/api/issues/${id}/promote/`, { method: 'POST', body: {} }), 'Promoted to known issue.')}>
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
          </Card>

          <Card title="Attachments">
            <Attachments issue={issue} onDone={reload} />
          </Card>

          <Card title="Similar past issues">
            <SimilarPanel result={similar} loading={!similar} />
          </Card>
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
          <a href={a.url}>{a.original_name || 'file'}</a>
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
