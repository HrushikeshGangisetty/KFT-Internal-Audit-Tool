import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../../lib/api'
import { Banner, Card, Empty, Loading, Tag, humanize, when } from '../../components/ui.jsx'
import { useDialog, useToast } from '../../components/overlay.jsx'

const DELIVERY_TONE = { accepted: 'ok', failed: 'bad', unknown: 'warn', queued: '' }

/** WP13: preview the exact message and recipients, then send once. */
export default function Announce({ release }) {
  const [source, setSource] = useState(null)
  const [segment, setSegment] = useState('')
  const [campaigns, setCampaigns] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const loadCampaigns = useCallback(() => api('/api/campaigns/', { params: { release: release.id } })
    .then((d) => setCampaigns(listOf(d))).catch((e) => setError(e.message)), [release.id])
  useEffect(() => {
    api('/api/campaigns/segments/').then((s) => { setSource(s); setSegment(s.segments[0] ?? '') })
      .catch((e) => setError(e.message))
    loadCampaigns()
  }, [loadCampaigns])

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
          <select value={segment} onChange={(e) => setSegment(e.target.value)} style={{ maxWidth: 240 }}
                  aria-label="Recipient segment">
            {(source?.segments ?? []).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button disabled={busy || !segment} onClick={preview}>Preview</button>
        </div>
      ) : <p className="small muted">The latest revision is not approved, so it cannot be announced.</p>}
      {campaigns === null ? <Loading what="campaigns" /> : null}
      {campaigns?.length === 0 ? <Empty icon="inbox">No announcement drafted yet.</Empty> : null}
      {campaigns?.map((c) => <CampaignView key={c.id} c={c} run={run} busy={busy} />)}
    </Card>
  )
}

function CampaignView({ c, run, busy }) {
  const ask = useDialog()
  const toast = useToast()
  // One key per draft, reused on every click, so a double click sends once.
  const [key] = useState(() => crypto.randomUUID())
  const post = (action, body = {}, done) => run(async () => {
    await api(`/api/campaigns/${c.id}/${action}/`, { method: 'POST', body })
    if (done) toast(done)
  })
  const counts = c.deliveries.reduce((m, d) => ({ ...m, [d.status]: (m[d.status] ?? 0) + 1 }), {})

  const resend = async () => {
    const r = await ask({ title: 'Resend announcement',
      message: 'A new draft with a fresh recipient list is created. Nothing is sent until you press Send on it.',
      input: { label: 'Why resend?' }, confirmLabel: 'Create resend draft' })
    if (r) post('resend', { reason: r.text }, 'Resend draft created.')
  }
  const reconcile = async (d) => {
    const r = await ask({ title: `Reconcile ${d.email}`,
      message: 'The provider did not confirm this delivery. Record what you checked and the outcome.',
      input: { label: 'What did you check?' },
      choices: [{ value: 'accepted', label: 'Provider accepted it', tone: 'ok' },
        { value: 'not_sent', label: 'Confirmed not sent', tone: 'danger' }] })
    if (r) post('reconcile', { delivery: d.id, note: r.text, outcome: r.choice }, 'Delivery reconciled.')
  }

  return (
    <div className="campaign">
      <div className="row">
        <Tag tone={c.status === 'completed' ? 'ok' : c.status === 'draft' ? 'warn' : ''}>{humanize(c.status)}</Tag>
        {c.synthetic ? <Tag tone="warn">SYNTHETIC</Tag> : null}
        <span className="small muted">r{c.revision_number} · {c.segment} · {c.recipient_count} recipients ·
          list from {when(c.fetched_at)}{c.sent_at ? ` · sent ${when(c.sent_at)} by ${c.sent_by_name}` : ''}</span>
      </div>
      {c.resend_of ? <p className="small">Resend of #{c.resend_of}: {c.resend_reason}</p> : null}
      <p><strong>{c.subject}</strong></p>
      <pre className="email-body">{c.body_text}</pre>
      {c.status === 'draft' ? (
        <>
          <details><summary className="small">Recipients ({c.recipient_count})</summary>
            <ul className="small mono">{c.recipients.map((r) => <li key={r.id}>{r.email}</li>)}</ul>
          </details>
          <button disabled={busy} onClick={() => post('send', { idempotency_key: key }, 'Announcement sent.')}>
            Send to {c.recipient_count} recipients</button>
        </>
      ) : (
        <>
          <div className="row small">
            {Object.entries(counts).map(([s, n]) => <Tag key={s} tone={DELIVERY_TONE[s]}>{humanize(s)}: {n}</Tag>)}
            {counts.failed ? <button className="secondary sm" disabled={busy}
                                     onClick={() => post('retry', {}, 'Retrying failed deliveries.')}>
              Retry {counts.failed} failed</button> : null}
            <button className="secondary sm" disabled={busy} onClick={resend}>Resend…</button>
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
                    <button className="link" disabled={busy} onClick={() => reconcile(d)}>Reconcile…</button>
                  ) : null}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
