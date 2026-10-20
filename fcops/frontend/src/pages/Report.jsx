import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import { Banner, Card, Field, PageHeader } from '../components/ui.jsx'

/* Quick report (WP4 endpoint POST /api/issues/report/): a title, what you saw
   and how urgent it is. Everything else is optional, including the FC. */
export default function Report() {
  const { user } = useAuth()
  const canPickFc = user?.permissions?.can_view_fcs
  const navigate = useNavigate()
  const [meta, setMeta] = useState({ urgencies: [], product_areas: [], impacts: [] })
  const [fcs, setFcs] = useState([])
  const [form, setForm] = useState({
    title: '', symptom: '', urgency: '', product_area: '', impact: '', fc: '',
    description: '', occurred_at_approx: '', location_context: '',
  })
  const [files, setFiles] = useState([])
  const [more, setMore] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/issues/meta/').then(setMeta).catch(() => {})
    if (canPickFc) api('/api/fcs/', { params: { page_size: 200 } }).then((d) => setFcs(listOf(d))).catch(() => {})
  }, [canPickFc])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    const body = new FormData()
    Object.entries(form).forEach(([k, v]) => { if (v) body.append(k, v) })
    files.forEach((f) => body.append('files', f))
    try {
      const issue = await api('/api/issues/report/', { method: 'POST', body, isForm: true })
      const failed = issue.failed_attachments?.length
      navigate(`/issues/${issue.id}${failed ? '?attachments=failed' : ''}`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Report a problem"
                  subtitle="No FC, stage or version needed. It is routed to a team, who acknowledge it." />
      <Card as="form" onSubmit={submit} className="report-form" footer={
        <button className="primary-action" disabled={busy || !form.title || !form.symptom || !form.urgency}>
          {busy ? 'Sending…' : 'Send report'}
        </button>
      }>
        <Banner>{error}</Banner>
        <Field label="What is the problem?">
          <input value={form.title} onChange={set('title')} required maxLength={255}
                 placeholder="e.g. Telemetry drops during hover" />
        </Field>
        <Field label="What did you see?" hint="Describe the symptom as observed. This is what searches match on.">
          <textarea value={form.symptom} onChange={set('symptom')} required />
        </Field>
        <fieldset className="field choice-group">
          <legend>How urgent is it?</legend>
          {meta.urgencies.map((u) => (
            <label key={u.value} className={`choice ${form.urgency === u.value ? 'selected' : ''}`}>
              <input type="radio" name="urgency" value={u.value} checked={form.urgency === u.value}
                     onChange={set('urgency')} required />
              {u.value === 'unknown' ? 'Not sure' : u.label}
            </label>
          ))}
        </fieldset>
        {canPickFc ? (
          <Field label="Flight controller (optional)">
            <select value={form.fc} onChange={set('fc')}>
              <option value="">— not about a specific FC —</option>
              {fcs.map((fc) => <option key={fc.id} value={fc.id}>{fc.serial} · {fc.stage_label}</option>)}
            </select>
          </Field>
        ) : null}
        <Field label="Photos, logs or files (optional)">
          <input type="file" multiple onChange={(e) => setFiles([...e.target.files])} />
        </Field>
        {more ? (
          <>
            <div className="grid cols-2">
              <Field label="Product area">
                <select value={form.product_area} onChange={set('product_area')}>
                  <option value="">— not sure —</option>
                  {meta.product_areas.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
                </select>
              </Field>
              <Field label="Impact">
                <select value={form.impact} onChange={set('impact')}>
                  <option value="">— not sure —</option>
                  {meta.impacts.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
                </select>
              </Field>
              <Field label="When did it happen?">
                <input value={form.occurred_at_approx} onChange={set('occurred_at_approx')}
                       placeholder="e.g. this morning, around 10" maxLength={120} />
              </Field>
              <Field label="Where?">
                <input value={form.location_context} onChange={set('location_context')}
                       placeholder="Site, bench, customer location…" maxLength={255} />
              </Field>
            </div>
            <Field label="Anything else">
              <textarea value={form.description} onChange={set('description')} />
            </Field>
          </>
        ) : (
          <button type="button" className="link" onClick={() => setMore(true)}>Add more detail (optional)</button>
        )}
      </Card>
    </>
  )
}
