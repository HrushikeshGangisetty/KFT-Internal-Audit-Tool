import { useState } from 'react'
import { api } from '../../lib/api'
import { Banner, Card, Field } from '../../components/ui.jsx'

// Customer create/edit. Writes are head/manager-only (customers.services);
// callers show this only when /me says so, and the server checks again.
export default function CustomerForm({ customer, onCancel, onSaved }) {
  const [form, setForm] = useState({
    name: customer?.name ?? '', region: customer?.region ?? '', notes: customer?.notes ?? '',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      onSaved(await api(customer ? `/api/customers/${customer.id}/` : '/api/customers/',
        { method: customer ? 'PATCH' : 'POST', body: form }))
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <Card as="form" title={customer ? 'Edit customer' : 'Add a customer'} onSubmit={submit}
          footer={<>
            <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
            <button disabled={busy || !form.name.trim()}>{busy ? 'Saving…' : 'Save customer'}</button>
          </>}>
      <Banner>{error}</Banner>
      <div className="grid cols-2">
        <Field label="Name"><input value={form.name} required onChange={set('name')} /></Field>
        <Field label="Region"><input value={form.region} onChange={set('region')} /></Field>
      </div>
      <Field label="Engineering notes" hint="No contact details here; contacts are kept separately.">
        <textarea rows={3} value={form.notes} onChange={set('notes')} />
      </Field>
    </Card>
  )
}
