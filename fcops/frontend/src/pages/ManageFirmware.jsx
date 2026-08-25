import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import { Banner, Empty, Field, Loading, Tag, when } from '../components/ui.jsx'

const BLANK = {
  name: '', firmware_type: 'APJ', version: '', git_sha: '', build_datetime: '',
  source_type: 'OPEN_SOURCE', description: '', includes_scripts: false,
  script_name: '', script_version: '', script_notes: '', is_signed: false,
  is_locked: false, bootloader_version: '', bootloader_notes: '',
  parameter_profile: '',
}

export default function ManageFirmware() {
  const { user } = useAuth()
  const canManage = Boolean(user?.permissions?.can_manage_firmware)

  const [rows, setRows] = useState(null)
  const [profiles, setProfiles] = useState([])
  const [meta, setMeta] = useState({ suggested_types: [], source_types: [] })
  const [filters, setFilters] = useState({ search: '', is_active: '' })
  const [form, setForm] = useState(BLANK)
  const [editing, setEditing] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setRows(null)
    api('/api/firmware-builds/', { params: { ...filters, page_size: 100 } })
      .then((d) => setRows(listOf(d)))
      .catch((e) => setError(e.message))
  }, [filters])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    api('/api/parameter-profiles/').then((d) => setProfiles(listOf(d))).catch(() => {})
    api('/api/firmware-builds/meta/').then(setMeta).catch(() => {})
  }, [])

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const startCreate = () => { setEditing(null); setForm(BLANK); setShowForm(true) }
  const startEdit = (build) => {
    setEditing(build)
    setForm({
      ...BLANK, ...build,
      build_datetime: build.build_datetime ? build.build_datetime.slice(0, 16) : '',
      parameter_profile: build.parameter_profile ?? '',
    })
    setShowForm(true)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setMessage('')
    const body = {
      ...form,
      parameter_profile: form.parameter_profile ? Number(form.parameter_profile) : null,
      build_datetime: form.build_datetime || null,
    }
    try {
      if (editing) {
        await api(`/api/firmware-builds/${editing.id}/`, { method: 'PATCH', body })
        setMessage(`${form.name} ${form.version} updated.`)
      } else {
        await api('/api/firmware-builds/', { method: 'POST', body })
        setMessage(`${form.name} ${form.version} added to the catalogue.`)
      }
      setShowForm(false); setEditing(null); setForm(BLANK); load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const toggleActive = async (build) => {
    const next = !build.is_active
    if (!next && build.flash_count > 0
        && !window.confirm(
          `${build.name} ${build.version} has been flashed onto ${build.flash_count} FC(s).\n\n`
          + 'Deactivating removes it from the pick-list for new flashes. Those FCs '
          + 'keep their existing firmware records unchanged.\n\nContinue?')) return
    setError('')
    try {
      await api(`/api/firmware-builds/${build.id}/set-active/`,
                { method: 'POST', body: { is_active: next } })
      load()
    } catch (err) { setError(err.message) }
  }

  const openDetail = async (build) => {
    const flashes = await api(`/api/firmware-builds/${build.id}/flashes/`)
    setDetail({ build, flashes })
  }

  return (
    <>
      <div className="row" style={{ marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>Manage Firmware</h2>
        <div style={{ flex: 1 }} />
        {canManage ? <button onClick={startCreate}>Add firmware build</button> : null}
      </div>
      <p className="muted small" style={{ marginTop: -4 }}>
        The catalogue of builds that can be flashed onto an FC. When a build is
        flashed, its details are copied onto that FC's own record — so an FC's
        history always shows exactly what went on it, even after a build is edited
        or retired.
      </p>

      <Banner>{error}</Banner>
      <Banner kind="ok">{message}</Banner>

      {!canManage ? (
        <div className="banner warn">
          Only the Firmware department can change the catalogue. You can read it below.
        </div>
      ) : null}

      {showForm && canManage ? (
        <form className="card" onSubmit={submit}>
          <h2>{editing ? `Edit ${editing.name} ${editing.version}` : 'Add a firmware build'}</h2>
          <div className="grid cols-3">
            <Field label="Firmware name">
              <input value={form.name} onChange={set('name')} required />
            </Field>
            <Field label="Type / format" hint="Free text — new formats need no code change.">
              <input value={form.firmware_type} onChange={set('firmware_type')}
                     list="firmware-types" required />
              <datalist id="firmware-types">
                {meta.suggested_types.map((t) => <option key={t} value={t} />)}
              </datalist>
            </Field>
            <Field label="Version / build id">
              <input value={form.version} onChange={set('version')} required />
            </Field>
            <Field label="Git SHA / source reference">
              <input className="mono" value={form.git_sha} onChange={set('git_sha')} />
            </Field>
            <Field label="Build date/time">
              <input type="datetime-local" value={form.build_datetime}
                     onChange={set('build_datetime')} />
            </Field>
            <Field label="Source">
              <select value={form.source_type} onChange={set('source_type')}>
                {meta.source_types.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>))}
              </select>
            </Field>
            <Field label="Bootloader version">
              <input value={form.bootloader_version} onChange={set('bootloader_version')} />
            </Field>
            <Field label="Parameter profile">
              <select value={form.parameter_profile} onChange={set('parameter_profile')}>
                <option value="">— none —</option>
                {profiles.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Description" hint="What this build contains, changes and enables.">
            <textarea value={form.description} onChange={set('description')} />
          </Field>
          <div className="row" style={{ marginBottom: 10 }}>
            {[['includes_scripts', 'Includes scripts'], ['is_signed', 'Signed'],
              ['is_locked', 'Locked']].map(([key, label]) => (
              <label key={key} className="row small" style={{ marginBottom: 0 }}>
                <input type="checkbox" checked={form[key]} onChange={set(key)}
                       style={{ width: 'auto' }} /> {label}
              </label>
            ))}
          </div>
          {form.includes_scripts ? (
            <div className="grid cols-3">
              <Field label="Script name">
                <input value={form.script_name} onChange={set('script_name')} />
              </Field>
              <Field label="Script version">
                <input value={form.script_version} onChange={set('script_version')} />
              </Field>
              <Field label="Script notes">
                <input value={form.script_notes} onChange={set('script_notes')} />
              </Field>
            </div>
          ) : null}
          <Field label="Bootloader notes">
            <input value={form.bootloader_notes} onChange={set('bootloader_notes')} />
          </Field>
          <div className="row">
            <button disabled={busy || !form.name || !form.version}>
              {busy ? 'Saving…' : editing ? 'Save changes' : 'Add build'}
            </button>
            <button type="button" className="secondary"
                    onClick={() => { setShowForm(false); setEditing(null) }}>Cancel</button>
          </div>
        </form>
      ) : null}

      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <input placeholder="Search name, version, SHA…" style={{ maxWidth: 280 }}
                 value={filters.search}
                 onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
          <select value={filters.is_active} style={{ maxWidth: 170 }}
                  onChange={(e) => setFilters((f) => ({ ...f, is_active: e.target.value }))}>
            <option value="">Active and retired</option>
            <option value="true">Active only</option>
            <option value="false">Retired only</option>
          </select>
        </div>

        {rows === null ? <Loading what="firmware catalogue" /> : null}
        {rows?.length === 0 ? <Empty>No firmware builds yet.</Empty> : null}
        {rows?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Build</th><th>Type</th><th>Source</th><th>Flags</th>
                  <th>Bootloader</th><th>Flashed on</th><th>Status</th><th /></tr>
              </thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <strong>{b.name}</strong> <span className="mono">{b.version}</span>
                      {b.git_sha ? <div className="mono small muted">{b.git_sha.slice(0, 12)}</div> : null}
                    </td>
                    <td className="small">{b.firmware_type}</td>
                    <td className="small">{b.source_type_display}</td>
                    <td className="small">
                      {b.is_signed ? <Tag tone="ok">signed</Tag> : <Tag>unsigned</Tag>}{' '}
                      {b.is_locked ? <Tag>locked</Tag> : null}{' '}
                      {b.includes_scripts ? <Tag tone="info">scripts</Tag> : null}
                    </td>
                    <td className="small mono">{b.bootloader_version || '—'}</td>
                    <td className="small">
                      {b.flash_count
                        ? <button className="link" style={{ paddingLeft: 0 }}
                                  onClick={() => openDetail(b)}>{b.flash_count} FC(s)</button>
                        : '—'}
                    </td>
                    <td>{b.is_active ? <Tag tone="ok">active</Tag> : <Tag tone="warn">retired</Tag>}</td>
                    <td className="small">
                      {canManage ? (
                        <>
                          <button className="link" onClick={() => startEdit(b)}>Edit</button>
                          <button className="link" onClick={() => toggleActive(b)}>
                            {b.is_active ? 'Retire' : 'Restore'}
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

      {detail ? (
        <div className="card">
          <div className="row">
            <h2 style={{ margin: 0 }}>
              {detail.build.name} {detail.build.version} — flashed onto
            </h2>
            <div style={{ flex: 1 }} />
            <button className="secondary" onClick={() => setDetail(null)}>Close</button>
          </div>
          <p className="small muted">
            These records were copied at flash time and are unaffected by later
            edits to the catalogue entry.
          </p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>FC</th><th>Version recorded</th><th>Signed</th>
                <th>Operator</th><th>When</th></tr></thead>
              <tbody>
                {detail.flashes.map((f) => (
                  <tr key={f.id}>
                    <td className="mono small">{f.fc}</td>
                    <td className="mono small">{f.firmware_name} {f.version}</td>
                    <td className="small">{f.is_signed ? 'Yes' : 'No'}</td>
                    <td className="small">{f.operator_name}</td>
                    <td className="small muted">{when(f.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  )
}
