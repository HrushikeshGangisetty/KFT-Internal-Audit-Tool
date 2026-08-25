import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import { Banner, Empty, Field, Loading, Tag } from '../components/ui.jsx'

const BLANK = { name: '', code: '', description: '' }

const slug = (value) =>
  value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')

export default function FcModels() {
  const { user } = useAuth()
  const canManage = Boolean(user?.permissions?.can_manage_fc_models)

  const [rows, setRows] = useState(null)
  const [form, setForm] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setRows(null)
    api('/api/fc-models/', { params: { page_size: 100 } })
      .then((d) => setRows(listOf(d)))
      .catch((e) => setError(e.message))
  }, [])
  useEffect(() => { load() }, [load])

  const set = (k) => (e) => setForm((f) => {
    const next = { ...f, [k]: e.target.value }
    if (k === 'name' && !editing) next.code = slug(e.target.value)
    return next
  })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setMessage('')
    try {
      if (editing) {
        await api(`/api/fc-models/${editing.id}/`, { method: 'PATCH', body: form })
        setMessage(`${form.name} updated.`)
      } else {
        await api('/api/fc-models/', { method: 'POST', body: form })
        setMessage(`${form.name} added.`)
      }
      setForm(BLANK); setEditing(null); load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const toggleActive = async (model) => {
    const next = !model.is_active
    if (!next && !window.confirm(
      `Archive “${model.name}”?\n\nIt will no longer be offered when registering a `
      + 'new FC. Every FC already built as this model keeps it and stays valid.')) return
    setError('')
    try {
      await api(`/api/fc-models/${model.id}/set-active/`,
                { method: 'POST', body: { is_active: next } })
      load()
    } catch (err) { setError(err.message) }
  }

  return (
    <>
      <h2>FC Models</h2>
      <p className="muted small" style={{ marginTop: -6 }}>
        The models offered when registering a new flight controller. Models in use
        are archived rather than deleted, so existing FCs keep a valid reference.
      </p>

      <Banner>{error}</Banner>
      <Banner kind="ok">{message}</Banner>
      {!canManage ? (
        <div className="banner warn">
          Only a manager can change FC models. You can read them below.
        </div>
      ) : null}

      <div className="card">
        {rows === null ? <Loading what="FC models" /> : null}
        {rows?.length === 0 ? <Empty>No FC models defined.</Empty> : null}
        {rows?.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Code</th><th>Description</th>
                <th>Status</th><th /></tr></thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={m.id} style={{ opacity: m.is_active ? 1 : 0.55 }}>
                    <td><strong>{m.name}</strong></td>
                    <td className="mono small">{m.code}</td>
                    <td className="small">{m.description || '—'}</td>
                    <td>{m.is_active
                      ? <Tag tone="ok">active</Tag> : <Tag tone="warn">archived</Tag>}</td>
                    <td className="small">
                      {canManage ? (
                        <>
                          <button className="link" onClick={() => {
                            setEditing(m)
                            setForm({ name: m.name, code: m.code,
                                      description: m.description || '' })
                          }}>Edit</button>
                          <button className="link" onClick={() => toggleActive(m)}>
                            {m.is_active ? 'Archive' : 'Restore'}
                          </button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {canManage ? (
        <form className="card" onSubmit={submit}>
          <h2>{editing ? `Edit ${editing.name}` : 'Add an FC model'}</h2>
          <div className="grid cols-2">
            <Field label="Model name">
              <input value={form.name} onChange={set('name')} required
                     placeholder="e.g. KFT-FC-PRO" />
            </Field>
            <Field label="Code" hint="Short identifier, generated from the name.">
              <input className="mono" value={form.code} onChange={set('code')} required
                     disabled={Boolean(editing)} />
            </Field>
          </div>
          <Field label="Description">
            <textarea value={form.description} onChange={set('description')} />
          </Field>
          <div className="row">
            <button disabled={busy || !form.name || !form.code}>
              {editing ? 'Save changes' : 'Add model'}
            </button>
            {editing ? (
              <button type="button" className="secondary"
                      onClick={() => { setEditing(null); setForm(BLANK) }}>Cancel</button>
            ) : null}
          </div>
        </form>
      ) : null}
    </>
  )
}
