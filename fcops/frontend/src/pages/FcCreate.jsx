import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import { Banner, Field } from '../components/ui.jsx'

export default function FcCreate() {
  const navigate = useNavigate()
  const [models, setModels] = useState([])
  const [form, setForm] = useState({ fc_model: '', hardware_revision: '', pcb_batch: '', notes: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/api/fc-models/').then((d) => {
      const list = listOf(d)
      setModels(list)
      if (list[0]) setForm((f) => ({ ...f, fc_model: list[0].id }))
    })
  }, [])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const fc = await api('/api/fcs/', { method: 'POST', body: { ...form, fc_model: Number(form.fc_model) } })
      navigate(`/fcs/${fc.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" style={{ maxWidth: 620 }} onSubmit={submit}>
      <h2>Register a new flight controller</h2>
      <p className="muted small">
        A serial number is assigned automatically in the form FC-YYYY-NNNNN. The FC
        starts at Fabrication.
      </p>
      <Banner>{error}</Banner>
      <Field label="FC model">
        <select value={form.fc_model} onChange={set('fc_model')}>
          {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </Field>
      <Field label="Hardware revision" hint="e.g. rev-C">
        <input value={form.hardware_revision} onChange={set('hardware_revision')} />
      </Field>
      <Field label="PCB batch / panel reference">
        <input value={form.pcb_batch} onChange={set('pcb_batch')} />
      </Field>
      <Field label="Notes">
        <textarea value={form.notes} onChange={set('notes')} />
      </Field>
      <button disabled={busy || !form.fc_model}>{busy ? 'Registering…' : 'Register FC'}</button>
    </form>
  )
}
