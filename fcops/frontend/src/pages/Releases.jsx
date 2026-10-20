import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import {
  Banner, Card, Empty, Field, Loading, PageHeader, Tag, humanize, when,
} from '../components/ui.jsx'

// WP11-WP13. Buttons are shown from /me capability flags; the backend
// rechecks every capability, the approval and the revision on each action.
const STATE_TONE = { approved: 'ok', rejected: 'bad', pending: 'warn', legacy: '' }
const STATE_LABEL = { legacy: 'Legacy — not approved under current process' }
const DELIVERY_TONE = { accepted: 'ok', failed: 'bad', unknown: 'warn', queued: '' }
const CONTENT = [
  ['source_ref', 'Source reference', 'Commit SHA or tag — required.'],
  ['artifact_ref', 'Artifact reference', 'Where the build lives.'],
  ['artifact_sha256', 'Artifact SHA-256', '64 hex characters, if known.'],
  ['recipient_notes', 'Recipient notes', 'The only release text that goes into the email.'],
  ['internal_notes', 'Internal notes', 'Never sent to recipients.'],
  ['compatibility', 'Compatibility', ''],
  ['known_limitations', 'Known limitations', ''],
]
const BLANK = Object.fromEntries(CONTENT.map(([k]) => [k, '']))

export const StateTag = ({ value }) => (
  <Tag tone={STATE_TONE[value] ?? ''}>{STATE_LABEL[value] ?? humanize(value)}</Tag>
)

export default function Releases() {
  const { id } = useParams()
  return id ? <ReleaseDetail id={id} /> : <ReleaseList />
}

function ReleaseList() {
  const { user } = useAuth()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api('/api/releases/', { params: { page_size: 100 } })
      .then((d) => setRows(listOf(d))).catch((e) => setError(e.message))
  }, [])
  return (
    <>
      <PageHeader title="Releases"
                  subtitle="GCS and Configurator releases. A revision is approved only when the Software head and the manager — two different people — both approve it. Editing creates a new revision that needs approval again." />
      <Banner>{error}</Banner>
      {user?.permissions?.can_draft_release ? <NewRelease /> : null}
      <Card title="Release history" flush>
        {rows === null && !error ? <Loading what="releases" /> : null}
        {rows?.length === 0 ? <Empty>No releases recorded yet.</Empty> : null}
        {rows?.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Release</th><th>Latest revision</th><th>State</th><th>Created</th></tr></thead>
              <tbody>{rows.map((r) => {
                const latest = r.revisions[0]
                return (
                  <tr key={r.id}>
                    <td><Link to={`/releases/${r.id}`}>{r.product_display} {r.version}</Link></td>
                    <td className="mono small">r{latest?.number} · {latest?.source_ref.slice(0, 12)}</td>
                    <td><StateTag value={latest?.state} /></td>
                    <td className="small muted">{when(r.created_at)}</td>
                  </tr>
                )
              })}</tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </>
  )
}

function ContentFields({ form, setForm }) {
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  return CONTENT.map(([k, label, hint]) => (
    <Field key={k} label={label} hint={hint}>
      {k.endsWith('notes') || k === 'compatibility' || k === 'known_limitations'
        ? <textarea value={form[k]} onChange={set(k)} />
        : <input value={form[k]} onChange={set(k)} className="mono" required={k === 'source_ref'} />}
    </Field>
  ))
}

function NewRelease() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ product: 'GCS', version: '', ...BLANK })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const created = await api('/api/releases/', { method: 'POST', body: form })
      navigate(`/releases/${created.id}`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <Card as="form" title="Draft a release" onSubmit={submit}>
      <Banner>{error}</Banner>
      <div className="grid cols-3">
        <Field label="Software">
          <select value={form.product} onChange={(e) => setForm((f) => ({ ...f, product: e.target.value }))}>
            <option value="GCS">GCS</option><option value="CONFIGURATOR">Configurator</option>
          </select>
        </Field>
        <Field label="Version">
          <input value={form.version} required
                 onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))} />
        </Field>
      </div>
      <ContentFields form={form} setForm={setForm} />
      <button disabled={busy || !form.version.trim() || !form.source_ref.trim()}>
        {busy ? 'Saving…' : 'Save revision 1'}</button>
    </Card>
  )
}

function ReleaseDetail({ id }) {
  const { user } = useAuth()
  const p = user?.permissions ?? {}
  const [release, setRelease] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const load = () => api(`/api/releases/${id}/`).then(setRelease).catch((e) => setError(e.message))
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!release) return error ? <Banner>{error}</Banner> : <Loading what="release" variant="card" />
  const [latest, ...older] = release.revisions
  return (
    <>
      <PageHeader title={`${release.product_display} ${release.version}`}
                  meta={<><StateTag value={latest.state} />
                    {release.legacy ? <Tag>Migrated legacy record</Tag> : null}
                    {release.current_approved_revision ? <Tag tone="ok">Can be announced</Tag>
                      : <Tag tone="warn">Not announceable</Tag>}</>}
                  actions={<Link to="/releases">All releases</Link>} />
      <Banner>{error}</Banner>
      <Revision revision={latest} release={release} onChange={load} latest />
      {p.can_draft_release ? (editing
        ? <Revise release={release} latest={latest} onDone={() => { setEditing(false); load() }} />
        : <button className="secondary" onClick={() => setEditing(true)}>
            Edit (creates revision {latest.number + 1})</button>) : null}
      {p.can_send_announcements ? <Announce release={release} /> : null}
      {older.length ? (
        <Card title="Earlier revisions">
          {older.map((r) => <Revision key={r.id} revision={r} release={release} />)}
        </Card>
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
          <div key={k}><dt>{label}</dt>
            <dd className={k.startsWith('artifact') || k === 'source_ref' ? 'mono' : ''}
                style={{ whiteSpace: 'pre-wrap' }}>{r[k]}</dd></div>) : null))}
      </dl>
      <h3 className="small">Approvals</h3>
      {r.approvals.length ? (
        <ul className="qlist">{r.approvals.map((a) => (
          <li key={a.id} className="qrow small">
            <Tag tone={a.decision === 'approve' ? 'ok' : 'bad'}>{humanize(a.decision)}</Tag>{' '}
            {humanize(a.role)} · {a.actor_name} · {when(a.at)}
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
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')
  const decided = new Set(revision.approvals.map((a) => a.role))
  const roles = (user?.permissions?.release_approval_roles ?? []).filter((r) => !decided.has(r))
  if (!roles.length || revision.state !== 'pending') return null
  const decide = async (role, decision) => {
    setError('')
    try {
      await api(`/api/releases/${release.id}/decide/`, {
        method: 'POST', body: { revision: revision.id, role, decision, comment } })
      setComment(''); onChange()
    } catch (err) { setError(err.message) }
  }
  return (
    <div className="stack">
      <Banner>{error}</Banner>
      <Field label="Comment" hint="Required to reject.">
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} />
      </Field>
      {roles.map((role) => (
        <div key={role} className="row">
          <button onClick={() => decide(role, 'approve')}>Approve as {humanize(role)}</button>
          <button className="danger" disabled={!comment.trim()}
                  onClick={() => decide(role, 'reject')}>Reject as {humanize(role)}</button>
        </div>
      ))}
    </div>
  )
}

function Revise({ release, latest, onDone }) {
  const [form, setForm] = useState(Object.fromEntries(CONTENT.map(([k]) => [k, latest[k] ?? ''])))
  const [error, setError] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await api(`/api/releases/${release.id}/revise/`, { method: 'POST', body: form })
      onDone()
    } catch (err) { setError(err.message) }
  }
  return (
    <Card as="form" title={`Revision ${latest.number + 1}`} onSubmit={submit}
          subtitle="Saving clears approval: both approvers must approve the new revision.">
      <Banner>{error}</Banner>
      <ContentFields form={form} setForm={setForm} />
      <button>Save new revision</button>
    </Card>
  )
}

function Announce({ release }) {
  const [source, setSource] = useState(null)
  const [segment, setSegment] = useState('')
  const [campaigns, setCampaigns] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const loadCampaigns = () => api('/api/campaigns/', { params: { release: release.id } })
    .then((d) => setCampaigns(listOf(d))).catch((e) => setError(e.message))
  useEffect(() => {
    api('/api/campaigns/segments/').then((s) => { setSource(s); setSegment(s.segments[0] ?? '') })
      .catch((e) => setError(e.message))
    loadCampaigns()
  }, [release.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (fn) => {
    setBusy(true); setError('')
    try { await fn(); await loadCampaigns() } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const preview = () => run(() => api('/api/campaigns/preview/', {
    method: 'POST', body: { release_revision: release.current_approved_revision, segment } }))

  return (
    <Card title="Announcement email"
          subtitle="Preview the exact message and recipients, then send once. Sending announces a release; it does not install it.">
      <Banner>{error}</Banner>
      {source?.synthetic ? (
        <Banner kind="warn">SYNTHETIC recipients only (example.invalid). The signup API is not
          connected, so nothing reaches a real inbox.</Banner>) : null}
      {release.current_approved_revision ? (
        <div className="row">
          <select value={segment} onChange={(e) => setSegment(e.target.value)} style={{ maxWidth: 240 }}>
            {(source?.segments ?? []).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button disabled={busy || !segment} onClick={preview}>Preview</button>
        </div>
      ) : <p className="small muted">The latest revision is not approved, so it cannot be announced.</p>}
      {campaigns === null ? <Loading what="campaigns" /> : null}
      {campaigns?.map((c) => <CampaignView key={c.id} c={c} run={run} busy={busy} />)}
    </Card>
  )
}

function CampaignView({ c, run, busy }) {
  // One key per draft, reused on every click, so a double click sends once.
  const [key] = useState(() => crypto.randomUUID())
  const post = (action, body = {}) => run(() => api(`/api/campaigns/${c.id}/${action}/`, { method: 'POST', body }))
  const counts = c.deliveries.reduce((m, d) => ({ ...m, [d.status]: (m[d.status] ?? 0) + 1 }), {})
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="card-body">
        <div className="row">
          <Tag tone={c.status === 'completed' ? 'ok' : c.status === 'draft' ? 'warn' : ''}>{humanize(c.status)}</Tag>
          {c.synthetic ? <Tag tone="warn">SYNTHETIC</Tag> : null}
          <span className="small muted">r{c.revision_number} · {c.segment} · {c.recipient_count} recipients ·
            list from {when(c.fetched_at)}{c.sent_at ? ` · sent ${when(c.sent_at)} by ${c.sent_by_name}` : ''}</span>
        </div>
        {c.resend_of ? <p className="small">Resend of #{c.resend_of}: {c.resend_reason}</p> : null}
        <p><strong>{c.subject}</strong></p>
        <pre className="small" style={{ whiteSpace: 'pre-wrap' }}>{c.body_text}</pre>
        {c.status === 'draft' ? (
          <>
            <details><summary className="small">Recipients ({c.recipient_count})</summary>
              <ul className="small mono">{c.recipients.map((r) => <li key={r.id}>{r.email}</li>)}</ul>
            </details>
            <button disabled={busy} onClick={() => post('send', { idempotency_key: key })}>
              Send to {c.recipient_count} recipients</button>
          </>
        ) : (
          <>
            <div className="row small">
              {Object.entries(counts).map(([s, n]) => <Tag key={s} tone={DELIVERY_TONE[s]}>{humanize(s)}: {n}</Tag>)}
              {counts.failed ? <button className="secondary" disabled={busy} onClick={() => post('retry')}>
                Retry {counts.failed} failed</button> : null}
              <button className="secondary" disabled={busy} onClick={() => {
                const reason = window.prompt('Why resend? A new draft with a fresh recipient list is created.')
                if (reason) post('resend', { reason })
              }}>Resend…</button>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Recipient</th><th>Status</th><th>Attempts</th><th>Last error</th><th /></tr></thead>
                <tbody>{c.deliveries.map((d) => (
                  <tr key={d.id}>
                    <td className="mono small">{d.email}</td>
                    <td><Tag tone={DELIVERY_TONE[d.status]}>{humanize(d.status)}</Tag></td>
                    <td className="small">{d.attempts}</td>
                    <td className="small muted">{d.last_error || '—'}</td>
                    <td>{d.status === 'unknown' ? (
                      <button className="link" disabled={busy} onClick={() => {
                        const note = window.prompt('What did you check? Type "sent" if the provider log shows it was accepted; anything else marks it confirmed not sent.')
                        if (note) post('reconcile', { delivery: d.id, note,
                          outcome: note.trim().toLowerCase() === 'sent' ? 'accepted' : 'not_sent' })
                      }}>Reconcile…</button>) : null}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
