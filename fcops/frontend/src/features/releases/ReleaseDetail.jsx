import { Fragment, useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth.jsx'
import { Banner, Card, Field, Loading, PageHeader, Tag, humanize, when } from '../../components/ui.jsx'
import { useToast } from '../../components/overlay.jsx'
import { CONTENT, ContentFields, StateTag, isRef } from './shared.jsx'
import Announce from './Announce.jsx'

export default function ReleaseDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const p = user?.permissions ?? {}
  const [release, setRelease] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const load = useCallback(() => api(`/api/releases/${id}/`).then(setRelease)
    .catch((e) => setError(e.message)), [id])
  useEffect(() => { load() }, [load])

  if (!release) return error ? <Banner>{error}</Banner> : <Loading what="release" variant="page" />
  const [latest, ...older] = release.revisions
  return (
    <>
      <PageHeader title={`${release.product_display} ${release.version}`}
                  back={{ to: '/releases', label: 'All releases' }}
                  meta={<><StateTag value={latest.state} />
                    {release.legacy ? <Tag>Migrated legacy record</Tag> : null}
                    {release.current_approved_revision ? <Tag tone="ok">Can be announced</Tag>
                      : <Tag tone="warn">Not announceable</Tag>}</>}
                  actions={p.can_draft_release && !editing
                    ? <button className="secondary" onClick={() => setEditing(true)}>
                        Edit (creates revision {latest.number + 1})</button> : null} />
      <Banner>{error}</Banner>
      {editing ? (
        <Revise release={release} latest={latest}
                onCancel={() => setEditing(false)} onDone={() => { setEditing(false); load() }} />
      ) : null}
      <Revision revision={latest} release={release} onChange={load} latest />
      {p.can_send_announcements ? <Announce release={release} /> : null}
      {older.length ? (
        <details className="card disclosure">
          <summary className="card-header"><h2>Earlier revisions ({older.length})</h2></summary>
          <div className="card-body">
            {older.map((r) => <Revision key={r.id} revision={r} release={release} />)}
          </div>
        </details>
      ) : null}
    </>
  )
}

function Revision({ revision: r, release, onChange, latest }) {
  return (
    <Card title={`Revision ${r.number}`} subtitle={`${r.created_by_name || 'Unknown'} · ${when(r.created_at)}`}
          actions={<StateTag value={r.state} />}>
      <dl className="kv">
        {CONTENT.map(([k, label]) => (r[k] ? (
          <Fragment key={k}>
            <dt>{label}</dt>
            <dd className={isRef(k) ? 'mono' : ''} style={{ whiteSpace: 'pre-wrap' }}>{r[k]}</dd>
          </Fragment>) : null))}
      </dl>
      <h3>Approvals</h3>
      {r.approvals.length ? (
        <ul className="qlist">{r.approvals.map((a) => (
          <li key={a.id} className="qrow small">
            <Tag tone={a.decision === 'approve' ? 'ok' : 'bad'}>{humanize(a.decision)}</Tag>
            <span>{humanize(a.role)} · {a.actor_name} · {when(a.at)}</span>
            {a.comment ? <div className="muted">{a.comment}</div> : null}
          </li>))}</ul>
      ) : <p className="small muted">No decisions recorded.</p>}
      {latest && !release.legacy ? <Decide release={release} revision={r} onChange={onChange} /> : null}
      {latest && release.legacy && r.number === 1 ? (
        <p className="small muted">Legacy records are not approved retroactively. Edit to create a
          new revision for approval.</p>) : null}
    </Card>
  )
}

function Decide({ release, revision, onChange }) {
  const { user } = useAuth()
  const toast = useToast()
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const decided = new Set(revision.approvals.map((a) => a.role))
  const roles = (user?.permissions?.release_approval_roles ?? []).filter((r) => !decided.has(r))
  if (!roles.length || revision.state !== 'pending') return null
  const decide = async (role, decision) => {
    setBusy(true); setError('')
    try {
      await api(`/api/releases/${release.id}/decide/`, {
        method: 'POST', body: { revision: revision.id, role, decision, comment } })
      setComment('')
      toast(`Recorded: ${decision === 'approve' ? 'approved' : 'rejected'} as ${humanize(role)}.`)
      onChange()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <div className="decide">
      <h3>Your decision</h3>
      <Banner>{error}</Banner>
      <Field label="Comment" hint="Required to reject.">
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} />
      </Field>
      {roles.map((role) => (
        <div key={role} className="row">
          <button className="ok" disabled={busy} onClick={() => decide(role, 'approve')}>
            Approve as {humanize(role)}</button>
          <button className="danger" disabled={busy || !comment.trim()}
                  onClick={() => decide(role, 'reject')}>Reject as {humanize(role)}</button>
        </div>
      ))}
    </div>
  )
}

function Revise({ release, latest, onCancel, onDone }) {
  const toast = useToast()
  const [form, setForm] = useState(Object.fromEntries(CONTENT.map(([k]) => [k, latest[k] ?? ''])))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      await api(`/api/releases/${release.id}/revise/`, { method: 'POST', body: form })
      toast(`Revision ${latest.number + 1} saved. Both approvals are needed again.`)
      onDone()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <Card as="form" title={`Revision ${latest.number + 1}`} onSubmit={submit}
          subtitle="Saving clears approval: both approvers must approve the new revision."
          footer={<>
            <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
            <button disabled={busy}>{busy ? 'Saving…' : 'Save new revision'}</button>
          </>}>
      <Banner>{error}</Banner>
      <ContentFields form={form} setForm={setForm} />
    </Card>
  )
}
