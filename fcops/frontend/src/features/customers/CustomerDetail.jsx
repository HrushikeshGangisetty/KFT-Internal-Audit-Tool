import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, listOf } from '../../lib/api'
import { useAuth } from '../../lib/auth.jsx'
import { Banner, Card, FcLink, Field, Icon, PageHeader, Panel, usePanel, when } from '../../components/ui.jsx'
import { Paged, usePaged } from '../../components/data.jsx'
import { useToast } from '../../components/overlay.jsx'
import CustomerForm from './CustomerForm.jsx'

export default function CustomerDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const p = user?.permissions ?? {}
  const canEdit = p.can_view_fcs && p.is_head_or_manager // customers.services.save_record
  const customer = usePanel(`/api/customers/${id}/`)
  const deployments = usePaged('/api/deployments/', { customer: id })
  // Empty unless the viewer holds can_view_customer_contacts (enforced server-side).
  const contacts = usePaged('/api/customer-contacts/', { customer: id })
  const [editing, setEditing] = useState(false)
  const [deploying, setDeploying] = useState(null) // null | 'new' | a deployment
  // Unit ids -> serials for links and the unit picker (the FC list is FC-scoped).
  // ponytail: first 200 FCs only; switch to a serial search when the fleet grows.
  const [fcs, setFcs] = useState([])
  useEffect(() => {
    api('/api/fcs/', { params: { page_size: 200 } }).then((d) => setFcs(listOf(d))).catch(() => {})
  }, [])
  const serials = useMemo(() => Object.fromEntries(fcs.map((f) => [f.id, f.serial])), [fcs])

  const c = customer.data
  if (customer.error) return <Banner>{customer.error}</Banner>
  return (
    <>
      <PageHeader title={c?.name ?? 'Customer'} back={{ to: '/customers', label: 'All customers' }}
                  actions={c && canEdit && !editing
                    ? <button className="secondary" onClick={() => setEditing(true)}>Edit customer</button> : null} />
      {editing ? (
        <CustomerForm customer={c} onCancel={() => setEditing(false)}
                      onSaved={() => { setEditing(false); customer.reload() }} />
      ) : (
        <Panel panel={customer} title="Summary" lines={2}>
          {(d) => (
            <dl className="kv">
              <dt>Region</dt><dd>{d.region || '—'}</dd>
              <dt>Notes</dt><dd>{d.notes || '—'}</dd>
              <dt>Updated</dt><dd>{when(d.updated_at)}</dd>
            </dl>
          )}
        </Panel>
      )}
      {deploying ? (
        <DeploymentForm key={deploying.id ?? 'new'} customerId={id} fcs={fcs}
                        deployment={deploying === 'new' ? null : deploying}
                        onCancel={() => setDeploying(null)}
                        onSaved={() => { setDeploying(null); deployments.reload() }} />
      ) : null}
      <Card title="Deployments" flush
            actions={canEdit && !deploying
              ? <button className="sm" onClick={() => setDeploying('new')}><Icon name="plus" />Add deployment</button>
              : null}>
        <Paged page={deployments} what="deployments" cols={5} empty="No deployments recorded." emptyIcon="chip">
          {(rows) => (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Site</th><th>Units</th><th>GCS at handover</th><th>Deployed</th>
                  {canEdit ? <th aria-label="Actions" /> : null}</tr></thead>
                <tbody>{rows.map((d) => (
                  <tr key={d.id}>
                    <td>{d.site_name}{d.notes ? <div className="small muted">{d.notes}</div> : null}</td>
                    <td>{d.units.length ? d.units.map((u, i) => (
                      <span key={u}>{i ? ', ' : ''}<FcLink id={u} serial={serials[u] ?? `FC #${u}`} /></span>
                    )) : <span className="muted">—</span>}</td>
                    <td className="mono small">{d.gcs_version_at_handover || '—'}</td>
                    <td className="small muted">{when(d.deployed_at)}</td>
                    {canEdit ? (
                      <td><button className="secondary sm" onClick={() => setDeploying(d)}
                                  aria-label={`Edit ${d.site_name}`}>Edit</button></td>
                    ) : null}
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Paged>
      </Card>
      {contacts.rows?.length ? (
        <Card title="Contacts" subtitle="Restricted: shown only with the customer-contacts permission." flush>
          <Paged page={contacts} what="contacts" cols={4}>
            {(rows) => (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Name</th><th>Role</th><th>Phone</th><th>Email</th></tr></thead>
                  <tbody>{rows.map((x) => (
                    <tr key={x.id}><td>{x.name}</td><td>{x.role || '—'}</td>
                      <td>{x.phone || '—'}</td><td>{x.email || '—'}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </Paged>
        </Card>
      ) : null}
    </>
  )
}

// <input type="datetime-local"> wants local "YYYY-MM-DDTHH:mm"; the API returns ISO.
const toLocalInput = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function DeploymentForm({ customerId, deployment, fcs, onCancel, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState({
    site_name: deployment?.site_name ?? '',
    units: (deployment?.units ?? []).map(String),
    gcs_version_at_handover: deployment?.gcs_version_at_handover ?? '',
    deployed_at: toLocalInput(deployment?.deployed_at),
    notes: deployment?.notes ?? '',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    const body = {
      ...form, customer: Number(customerId), units: form.units.map(Number),
      deployed_at: form.deployed_at ? new Date(form.deployed_at).toISOString() : null,
    }
    try {
      await api(deployment ? `/api/deployments/${deployment.id}/` : '/api/deployments/',
        { method: deployment ? 'PATCH' : 'POST', body })
      toast(deployment ? 'Deployment updated.' : 'Deployment added.')
      onSaved()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <Card as="form" title={deployment ? 'Edit deployment' : 'Add a deployment'} onSubmit={submit}
          footer={<>
            <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
            <button disabled={busy || !form.site_name.trim()}>{busy ? 'Saving…' : 'Save deployment'}</button>
          </>}>
      <Banner>{error}</Banner>
      <div className="grid cols-3">
        <Field label="Site"><input value={form.site_name} required onChange={set('site_name')} /></Field>
        <Field label="GCS version at handover">
          <input value={form.gcs_version_at_handover} onChange={set('gcs_version_at_handover')} />
        </Field>
        <Field label="Deployed at">
          <input type="datetime-local" value={form.deployed_at} onChange={set('deployed_at')} />
        </Field>
      </div>
      <Field label="Units" hint="Ctrl/Cmd-click to pick several.">
        <select multiple size={Math.min(8, Math.max(3, fcs.length))} value={form.units}
                onChange={(e) => setForm((f) => ({
                  ...f, units: [...e.target.selectedOptions].map((o) => o.value) }))}>
          {fcs.map((fc) => <option key={fc.id} value={fc.id}>{fc.serial}</option>)}
        </select>
      </Field>
      <Field label="Notes"><textarea rows={2} value={form.notes} onChange={set('notes')} /></Field>
    </Card>
  )
}
