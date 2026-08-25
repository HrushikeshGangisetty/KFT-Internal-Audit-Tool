import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import { Banner, Empty, Field, Loading, Tag, humanize } from '../components/ui.jsx'

const BLANK = { key: '', label: '', description: '', is_mandatory: true }

export default function TestConfiguration() {
  const { user } = useAuth()
  const canConfigure = Boolean(user?.permissions?.can_configure_tests)

  const [templates, setTemplates] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [template, setTemplate] = useState(null)
  const [form, setForm] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const loadTemplates = useCallback(() => {
    api('/api/checklist-templates/', { params: { page_size: 100 } })
      .then((d) => {
        const list = listOf(d)
        setTemplates(list)
        setSelectedId((current) => current ?? list[0]?.id ?? null)
      })
      .catch((e) => setError(e.message))
  }, [])

  const loadTemplate = useCallback(() => {
    if (!selectedId) return
    api(`/api/checklist-templates/${selectedId}/`).then(setTemplate).catch(() => {})
  }, [selectedId])

  useEffect(() => { loadTemplates() }, [loadTemplates])
  useEffect(() => { loadTemplate() }, [loadTemplate])

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const refresh = () => { loadTemplate(); loadTemplates() }

  const run = async (fn, success) => {
    setBusy(true); setError(''); setMessage('')
    try { await fn(); refresh(); if (success) setMessage(success) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const submit = (e) => {
    e.preventDefault()
    if (editing) {
      run(() => api(`/api/checklist-items/${editing.id}/`, {
        method: 'PATCH',
        body: { label: form.label, description: form.description,
                is_mandatory: form.is_mandatory },
      }), 'Test updated.').then(() => { setEditing(null); setForm(BLANK) })
    } else {
      run(() => api('/api/checklist-items/', {
        method: 'POST', body: { template: selectedId, ...form },
      }), 'Test added.').then(() => setForm(BLANK))
    }
  }

  const move = (item, direction) => {
    const items = [...(template?.checklist_items || [])].sort((a, b) => a.order - b.order)
    const index = items.findIndex((i) => i.id === item.id)
    const target = index + direction
    if (target < 0 || target >= items.length) return
    const reordered = [...items]
    ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
    run(() => api(`/api/checklist-templates/${selectedId}/reorder/`, {
      method: 'POST', body: { ordered_ids: reordered.map((i) => i.id) },
    }))
  }

  const items = [...(template?.checklist_items || [])].sort((a, b) => a.order - b.order)

  return (
    <>
      <h2>Test Configuration</h2>
      <p className="muted small" style={{ marginTop: -6 }}>
        The checklists testers see when they run a stage. Changes apply to future
        tests only — every completed test keeps a copy of the items that were
        actually answered, and the checklist version they belonged to.
      </p>

      <Banner>{error}</Banner>
      <Banner kind="ok">{message}</Banner>
      {!canConfigure ? (
        <div className="banner warn">
          Only a manager can change test configuration. You can read it below.
        </div>
      ) : null}

      <div className="card">
        <div className="row">
          <Field label="Checklist">
            <select value={selectedId ?? ''} style={{ minWidth: 340 }}
                    onChange={(e) => setSelectedId(Number(e.target.value))}>
              {(templates || []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} · {t.stage_label} ({t.active_item_count} active)
                </option>
              ))}
            </select>
          </Field>
          {template ? (
            <div style={{ paddingTop: 14 }}>
              <Tag tone="info">version {template.version}</Tag>{' '}
              <Tag>{humanize(template.stage)}</Tag>
            </div>
          ) : null}
        </div>
      </div>

      {templates === null ? <Loading what="checklists" /> : null}
      {templates?.length === 0 ? (
        <div className="card"><Empty>No checklists configured.</Empty></div>
      ) : null}

      {template ? (
        <div className="card">
          <h2>Tests in “{template.name}”</h2>
          {items.length === 0 ? <Empty>No tests defined yet.</Empty> : null}
          {items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th style={{ width: 90 }}>Order</th><th>Test</th><th>Key</th>
                    <th>Required</th><th>Status</th><th /></tr>
                </thead>
                <tbody>
                  {items.map((item, index) => (
                    <tr key={item.id} style={{ opacity: item.is_active ? 1 : 0.55 }}>
                      <td className="small">
                        {canConfigure ? (
                          <>
                            <button className="link" disabled={index === 0 || busy}
                                    onClick={() => move(item, -1)}>↑</button>
                            <button className="link" disabled={index === items.length - 1 || busy}
                                    onClick={() => move(item, 1)}>↓</button>
                          </>
                        ) : index + 1}
                      </td>
                      <td>
                        <strong>{item.label}</strong>
                        {item.description
                          ? <div className="small muted">{item.description}</div> : null}
                      </td>
                      <td className="mono small">{item.key}
                        {item.is_in_use ? <div><Tag tone="info">in use</Tag></div> : null}</td>
                      <td className="small">{item.is_mandatory ? 'Mandatory' : 'Optional'}</td>
                      <td>{item.is_active
                        ? <Tag tone="ok">enabled</Tag> : <Tag tone="warn">disabled</Tag>}</td>
                      <td className="small">
                        {canConfigure ? (
                          <>
                            <button className="link" onClick={() => {
                              setEditing(item)
                              setForm({ key: item.key, label: item.label,
                                        description: item.description,
                                        is_mandatory: item.is_mandatory })
                            }}>Edit</button>
                            <button className="link" disabled={busy} onClick={() =>
                              run(() => api(`/api/checklist-items/${item.id}/set-active/`, {
                                method: 'POST', body: { is_active: !item.is_active },
                              }))}>{item.is_active ? 'Disable' : 'Enable'}</button>
                            {!item.is_in_use ? (
                              <button className="link" disabled={busy} onClick={() => {
                                if (window.confirm(`Remove “${item.label}” from this checklist?`)) {
                                  run(() => api(`/api/checklist-items/${item.id}/`,
                                                { method: 'DELETE' }), 'Test removed.')
                                }
                              }}>Remove</button>
                            ) : null}
                          </>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {canConfigure ? (
            <form onSubmit={submit} style={{ marginTop: 18, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
              <h3>{editing ? `Edit “${editing.label}”` : 'Add a test'}</h3>
              <div className="grid cols-2">
                <Field label="Test name / label">
                  <input value={form.label} onChange={set('label')} required
                         placeholder="e.g. GPS position hold within 1 m" />
                </Field>
                <Field label="Key"
                       hint={editing
                         ? 'The key is how past results are stored and cannot change.'
                         : 'Optional — derived from the label if left blank.'}>
                  <input className="mono" value={form.key} onChange={set('key')}
                         disabled={Boolean(editing)} />
                </Field>
              </div>
              <Field label="Instructions for the tester">
                <textarea value={form.description} onChange={set('description')} />
              </Field>
              <label className="row small" style={{ marginBottom: 10 }}>
                <input type="checkbox" checked={form.is_mandatory}
                       onChange={set('is_mandatory')} style={{ width: 'auto' }} />
                Mandatory — this check must pass for the test to pass
              </label>
              <div className="row">
                <button disabled={busy || !form.label}>
                  {editing ? 'Save changes' : 'Add test'}
                </button>
                {editing ? (
                  <button type="button" className="secondary"
                          onClick={() => { setEditing(null); setForm(BLANK) }}>Cancel</button>
                ) : null}
              </div>
            </form>
          ) : null}
        </div>
      ) : null}
    </>
  )
}
