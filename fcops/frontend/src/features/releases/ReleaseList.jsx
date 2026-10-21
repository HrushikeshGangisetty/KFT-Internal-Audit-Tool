import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth.jsx'
import { Banner, Card, Field, Icon, PageHeader, when } from '../../components/ui.jsx'
import { Paged, usePaged } from '../../components/data.jsx'
import { BLANK, ContentFields, StateTag } from './shared.jsx'

export default function ReleaseList() {
  const { user } = useAuth()
  const [drafting, setDrafting] = useState(false)
  const page = usePaged('/api/releases/')
  const canDraft = user?.permissions?.can_draft_release
  return (
    <>
      <PageHeader title="Releases"
                  subtitle="GCS and Configurator releases. A revision is approved only when the Software head and the manager — two different people — both approve it. Editing creates a new revision that needs approval again."
                  actions={canDraft && !drafting
                    ? <button onClick={() => setDrafting(true)}><Icon name="plus" />Draft a release</button> : null} />
      {canDraft && drafting ? <NewRelease onCancel={() => setDrafting(false)} /> : null}
      <Card title="Release history" flush>
        <Paged page={page} what="releases" cols={4} empty="No releases recorded yet." emptyIcon="upload">
          {(rows) => (
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
          )}
        </Paged>
      </Card>
    </>
  )
}

function NewRelease({ onCancel }) {
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
    <Card as="form" title="Draft a release" onSubmit={submit}
          subtitle="Saved as revision 1, pending both approvals."
          footer={<>
            <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
            <button disabled={busy || !form.version.trim() || !form.source_ref.trim()}>
              {busy ? 'Saving…' : 'Save revision 1'}</button>
          </>}>
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
    </Card>
  )
}
