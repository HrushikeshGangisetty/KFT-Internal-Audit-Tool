import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import { Banner, Empty, Field, Loading, Tag, when } from '../components/ui.jsx'

const BLANK = {
  kind: 'GCS', version: '', git_sha: '', release_notes: '', approved_by: '',
}

export default function PushUpdate() {
  const { user } = useAuth()
  const canPush = Boolean(user?.permissions?.can_push_software_update)

  const [rows, setRows] = useState(null)
  const [approvers, setApprovers] = useState([])
  const [form, setForm] = useState(BLANK)
  const [filters, setFilters] = useState({ kind: '', search: '' })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [expanded, setExpanded] = useState(null)

  const load = useCallback(() => {
    setRows(null)
    api('/api/software-updates/', { params: { ...filters, page_size: 100 } })
      .then((d) => setRows(listOf(d)))
      .catch((e) => setError(e.message))
  }, [filters])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!canPush) return
    api('/api/software-updates/approvers/').then(setApprovers).catch(() => {})
  }, [canPush])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setMessage('')
    try {
      const created = await api('/api/software-updates/', {
        method: 'POST',
        body: { ...form, approved_by: Number(form.approved_by) },
      })
      setForm(BLANK)
      setMessage(`${created.kind_display} ${created.version} recorded.`)
      load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const complete = form.version.trim() && form.git_sha.trim()
    && form.release_notes.trim() && form.approved_by

  return (
    <>
      <h2>Push Update</h2>
      <p className="muted small" style={{ marginTop: -6 }}>
        The internal release record for our GCS and Configurator. Every entry ties
        a version people are running to the exact commit that produced it, and to
        the person who signed it off. It records a release — it does not deploy one.
      </p>

      <Banner>{error}</Banner>
      <Banner kind="ok">{message}</Banner>

      {canPush ? (
        <form className="card" onSubmit={submit}>
          <h2>Record a new release</h2>
          <div className="grid cols-3">
            <Field label="Software">
              <select value={form.kind} onChange={set('kind')}>
                <option value="GCS">GCS</option>
                <option value="CONFIGURATOR">Configurator</option>
              </select>
            </Field>
            <Field label="Version" hint="e.g. 2.6.0">
              <input value={form.version} onChange={set('version')} required />
            </Field>
            <Field label="Git commit SHA" hint="Required — this is the traceability link.">
              <input value={form.git_sha} onChange={set('git_sha')} required
                     className="mono" placeholder="9f2c1ab4d7e5" />
            </Field>
          </div>
          <Field label="Release notes"
                 hint="Required. What changed, what was fixed, anything the shop floor should know.">
            <textarea value={form.release_notes} onChange={set('release_notes')}
                      required style={{ minHeight: 130 }} />
          </Field>
          <Field label="Approved by"
                 hint="Department leads, managers and admins may sign off a release.">
            <select value={form.approved_by} onChange={set('approved_by')} required>
              <option value="">— select an approver —</option>
              {approvers.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.full_name || a.username} · {a.role_display}
                  {a.department_name ? ` · ${a.department_name}` : ''}
                </option>
              ))}
            </select>
          </Field>
          <button disabled={busy || !complete}>
            {busy ? 'Recording…' : 'Push update'}
          </button>
          {!complete ? (
            <span className="small muted" style={{ marginLeft: 10 }}>
              Version, commit SHA, notes and an approver are all required.
            </span>
          ) : null}
        </form>
      ) : (
        <div className="banner warn">
          Only the Software department can record a release. You can still read
          the history below.
        </div>
      )}

      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>Release history</h2>
          <div style={{ flex: 1 }} />
          <select value={filters.kind} style={{ maxWidth: 180 }}
                  onChange={(e) => setFilters((f) => ({ ...f, kind: e.target.value }))}>
            <option value="">All software</option>
            <option value="GCS">GCS</option>
            <option value="CONFIGURATOR">Configurator</option>
          </select>
          <input placeholder="Search version, SHA or notes…" style={{ maxWidth: 260 }}
                 value={filters.search}
                 onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
        </div>

        {rows === null ? <Loading what="release history" /> : null}
        {rows?.length === 0 ? <Empty>No releases recorded yet.</Empty> : null}
        {rows?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Software</th><th>Version</th><th>Commit</th><th>Pushed by</th>
                  <th>Approved by</th><th>When</th><th>Changes</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td><Tag tone={r.kind === 'GCS' ? 'info' : ''}>{r.kind_display}</Tag></td>
                    <td className="mono">{r.version}</td>
                    <td className="mono small" title={r.git_sha}>{r.short_sha}</td>
                    <td className="small">{r.pushed_by_name || '—'}</td>
                    <td className="small">{r.approved_by_name || '—'}
                      <div className="muted">{r.approved_by_role}</div></td>
                    <td className="small muted">{when(r.created_at)}</td>
                    <td className="small" style={{ maxWidth: 420 }}>
                      {expanded === r.id ? (
                        <div style={{ whiteSpace: 'pre-wrap' }}>{r.release_notes}</div>
                      ) : (
                        <div>{r.release_notes.slice(0, 90)}
                          {r.release_notes.length > 90 ? '…' : ''}</div>
                      )}
                      {r.release_notes.length > 90 ? (
                        <button className="link" style={{ paddingLeft: 0 }}
                                onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                          {expanded === r.id ? 'Show less' : 'Show full notes'}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </>
  )
}
