import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../lib/api'
import { Banner, Empty, Field, Tag, humanize } from '../components/ui.jsx'

export default function Admin() {
  const [tab, setTab] = useState('users')
  return (
    <>
      <h2>Administration</h2>
      <div className="row" style={{ marginBottom: 14 }}>
        {['users', 'departments', 'models', 'software', 'checklists'].map((t) => (
          <button key={t} className={tab === t ? '' : 'secondary'} onClick={() => setTab(t)}>
            {humanize(t)}
          </button>
        ))}
      </div>
      {tab === 'users' ? <Users /> : null}
      {tab === 'departments' ? <Departments /> : null}
      {tab === 'models' ? <FcModels /> : null}
      {tab === 'software' ? <SoftwareVersions /> : null}
      {tab === 'checklists' ? <Checklists /> : null}
    </>
  )
}

function useList(path, params) {
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const load = useCallback(() => {
    api(path, { params: { page_size: 200, ...params } })
      .then((d) => setRows(listOf(d))).catch((e) => setError(e.message))
  }, [path, JSON.stringify(params)])
  useEffect(() => { load() }, [load])
  return { rows, error, setError, load }
}

function Users() {
  const { rows, error, setError, load } = useList('/api/users/')
  const departments = useList('/api/departments/').rows
  const [roles, setRoles] = useState([])
  const [form, setForm] = useState({ username: '', full_name: '', email: '', role: 'TECHNICIAN', department: '', password: '' })
  const [busy, setBusy] = useState(false)

  useEffect(() => { api('/api/users/roles/').then(setRoles) }, [])
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      await api('/api/users/', {
        method: 'POST',
        body: { ...form, department: form.department ? Number(form.department) : null },
      })
      setForm({ username: '', full_name: '', email: '', role: 'TECHNICIAN', department: '', password: '' })
      load()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const changeRole = async (user, role) => {
    try { await api(`/api/users/${user.id}/`, { method: 'PATCH', body: { role } }); load() }
    catch (err) { setError(err.message) }
  }

  return (
    <>
      <Banner>{error}</Banner>
      <div className="card">
        <h2>Users</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Username</th><th>Name</th><th>Department</th><th>Role</th><th>Active</th></tr></thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id}>
                  <td className="mono">{u.username}</td>
                  <td>{u.full_name}</td>
                  <td className="small">{u.department_name || '—'}</td>
                  <td>
                    <select value={u.role} onChange={(e) => changeRole(u, e.target.value)}
                            style={{ maxWidth: 190 }}>
                      {roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </td>
                  <td>{u.is_active ? <Tag tone="ok">active</Tag> : <Tag>disabled</Tag>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <form className="card" onSubmit={submit}>
        <h2>Add a user</h2>
        <div className="grid cols-3">
          <Field label="Username"><input value={form.username} onChange={set('username')} required /></Field>
          <Field label="Full name"><input value={form.full_name} onChange={set('full_name')} /></Field>
          <Field label="Email"><input type="email" value={form.email} onChange={set('email')} /></Field>
          <Field label="Role">
            <select value={form.role} onChange={set('role')}>
              {roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </Field>
          <Field label="Department">
            <select value={form.department} onChange={set('department')}>
              <option value="">—</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
          <Field label="Initial password"><input type="password" value={form.password} onChange={set('password')} /></Field>
        </div>
        <button disabled={busy || !form.username}>Create user</button>
      </form>
    </>
  )
}

function Departments() {
  const { rows, error, setError, load } = useList('/api/departments/')
  const [form, setForm] = useState({ name: '', code: '', kind: 'HARDWARE' })
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = async (e) => {
    e.preventDefault()
    try { await api('/api/departments/', { method: 'POST', body: form }); setForm({ name: '', code: '', kind: 'HARDWARE' }); load() }
    catch (err) { setError(err.message) }
  }
  return (
    <>
      <Banner>{error}</Banner>
      <div className="card">
        <h2>Departments</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Code</th><th>Kind</th><th>Members</th></tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}><td>{d.name}</td><td className="mono small">{d.code}</td>
                  <td className="small">{humanize(d.kind)}</td><td>{d.member_count}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <form className="card" onSubmit={submit}>
        <h2>Add a department</h2>
        <div className="grid cols-3">
          <Field label="Name"><input value={form.name} onChange={set('name')} required /></Field>
          <Field label="Code"><input value={form.code} onChange={set('code')} required /></Field>
          <Field label="Kind">
            <select value={form.kind} onChange={set('kind')}>
              {['HARDWARE', 'FIRMWARE', 'SOFTWARE', 'MECHANICAL', 'TESTING', 'QUALITY',
                'MANAGEMENT', 'OTHER'].map((k) => <option key={k} value={k}>{humanize(k)}</option>)}
            </select>
          </Field>
        </div>
        <button>Create department</button>
      </form>
    </>
  )
}

function FcModels() {
  const { rows, error, setError, load } = useList('/api/fc-models/')
  const [form, setForm] = useState({ name: '', code: '' })
  const submit = async (e) => {
    e.preventDefault()
    try { await api('/api/fc-models/', { method: 'POST', body: form }); setForm({ name: '', code: '' }); load() }
    catch (err) { setError(err.message) }
  }
  return (
    <>
      <Banner>{error}</Banner>
      <div className="card">
        <h2>FC models</h2>
        {rows.length === 0 ? <Empty /> : null}
        <div className="table-wrap">
          <table><thead><tr><th>Name</th><th>Code</th></tr></thead>
            <tbody>{rows.map((m) => (
              <tr key={m.id}><td>{m.name}</td><td className="mono small">{m.code}</td></tr>))}
            </tbody></table>
        </div>
      </div>
      <form className="card" onSubmit={submit}>
        <h2>Add an FC model</h2>
        <div className="grid cols-2">
          <Field label="Name"><input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required /></Field>
          <Field label="Code"><input value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} required /></Field>
        </div>
        <button>Create model</button>
      </form>
    </>
  )
}

function SoftwareVersions() {
  const { rows, error, setError, load } = useList('/api/software-versions/')
  const [form, setForm] = useState({ kind: 'GCS', version: '' })
  const submit = async (e) => {
    e.preventDefault()
    try { await api('/api/software-versions/', { method: 'POST', body: form }); setForm({ kind: 'GCS', version: '' }); load() }
    catch (err) { setError(err.message) }
  }
  return (
    <>
      <Banner>{error}</Banner>
      <div className="card">
        <h2>GCS / Configurator versions</h2>
        <p className="muted small">Maintained by the Software department; selected on test records and issues.</p>
        <div className="table-wrap">
          <table><thead><tr><th>Kind</th><th>Version</th><th>Active</th></tr></thead>
            <tbody>{rows.map((v) => (
              <tr key={v.id}><td>{v.kind}</td><td className="mono">{v.version}</td>
                <td>{v.is_active ? 'Yes' : 'No'}</td></tr>))}</tbody></table>
        </div>
      </div>
      <form className="card" onSubmit={submit}>
        <h2>Add a version</h2>
        <div className="grid cols-2">
          <Field label="Kind">
            <select value={form.kind} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}>
              <option value="GCS">GCS</option><option value="CONFIGURATOR">Configurator</option>
            </select>
          </Field>
          <Field label="Version"><input value={form.version} onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))} required /></Field>
        </div>
        <button>Add version</button>
      </form>
    </>
  )
}

function Checklists() {
  const { rows, error } = useList('/api/checklist-templates/')
  return (
    <>
      <Banner>{error}</Banner>
      <div className="card">
        <h2>Test checklist templates</h2>
        {rows.length === 0 ? <Empty /> : null}
        {rows.map((t) => (
          <div className="note" key={t.id}>
            <strong>{t.name}</strong> <Tag>{humanize(t.stage)}</Tag>
            <ul className="small" style={{ marginTop: 6 }}>
              {(t.items || []).map((i) => <li key={i.key}>{i.label}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </>
  )
}
