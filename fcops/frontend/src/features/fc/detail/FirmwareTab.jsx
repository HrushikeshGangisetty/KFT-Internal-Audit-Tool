import { useCallback, useEffect, useState } from 'react'
import { api, listOf } from '../../../lib/api'
import { Banner, Empty, Field, StatusTag, Tag, humanize, when } from '../../../components/ui.jsx'

export default function FirmwareTab({ fc, current, onDone }) {
  const [rows, setRows] = useState([])
  const [profiles, setProfiles] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    firmware_name: '', version: '', source_type: 'OPEN_SOURCE', is_signed: false,
    is_locked: false, bootloader_version: '', build_ref: '', parameter_profile: '',
    script_name: '', script_version: '', flashing_result: 'SUCCESS',
    config_result: 'SUCCESS', notes: '',
  })

  const [builds, setBuilds] = useState([])
  const [selectedBuild, setSelectedBuild] = useState('')
  const [flashNotes, setFlashNotes] = useState('')
  const [flashResult, setFlashResult] = useState('SUCCESS')
  const [manual, setManual] = useState(false)

  const load = useCallback(() => {
    api('/api/firmware-records/', { params: { fc: fc.id } }).then((d) => setRows(listOf(d)))
    api('/api/parameter-profiles/').then((d) => setProfiles(listOf(d)))
    api('/api/firmware-builds/', { params: { is_active: true, page_size: 100 } })
      .then((d) => setBuilds(listOf(d)))
      .catch(() => {})
  }, [fc.id])
  useEffect(() => { load() }, [load])

  const flashBuild = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      await api('/api/firmware-builds/flash/', {
        method: 'POST',
        body: {
          fc: fc.id, build: Number(selectedBuild),
          stage_record: current?.id ?? null,
          flashing_result: flashResult, config_result: flashResult,
          notes: flashNotes,
        },
      })
      setSelectedBuild(''); setFlashNotes(''); load(); onDone()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const set = (k) => (e) =>
    setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      await api('/api/firmware-records/', {
        method: 'POST',
        body: {
          ...form, fc: fc.id, stage_record: current?.id ?? null,
          parameter_profile: form.parameter_profile ? Number(form.parameter_profile) : null,
        },
      })
      setForm((f) => ({ ...f, notes: '' }))
      load(); onDone()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <>
      <h3>Firmware history</h3>
      {rows.length === 0 ? <Empty>No firmware recorded yet.</Empty> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Firmware</th><th>Source</th><th>Signed</th><th>Bootloader</th>
              <th>Params</th><th>Flash</th><th>Operator</th><th>When</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.firmware_name} <span className="mono">{r.version}</span>
                    {r.is_current ? <> <Tag tone="info">current</Tag></> : null}</td>
                  <td className="small">{humanize(r.source_type)}</td>
                  <td className="small">{r.is_signed ? 'Signed' : 'Unsigned'}{r.is_locked ? ' · locked' : ''}</td>
                  <td className="small mono">{r.bootloader_version || '—'}</td>
                  <td className="small">{r.parameter_profile_label || '—'}</td>
                  <td><StatusTag value={r.flashing_result === 'SUCCESS' ? 'PASSED' : 'FAILED'} /></td>
                  <td className="small">{r.operator_name}</td>
                  <td className="small muted">{when(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 18, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <h3>Flash a build from the catalogue</h3>
        <Banner>{error}</Banner>
        <p className="small muted" style={{ marginTop: 0 }}>
          The build's details are copied onto this FC's record, so its history
          stays accurate even if the catalogue entry changes later.
        </p>
        <form onSubmit={flashBuild}>
          <div className="grid cols-3">
            <Field label="Firmware build">
              <select value={selectedBuild} onChange={(e) => setSelectedBuild(e.target.value)}>
                <option value="">— select a build —</option>
                {builds.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} {b.version} · {b.firmware_type}
                    {b.is_signed ? ' · signed' : ''}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Flashing result">
              <select value={flashResult} onChange={(e) => setFlashResult(e.target.value)}>
                <option value="SUCCESS">Success</option>
                <option value="PARTIAL">Partial</option>
                <option value="FAILED">Failed</option>
              </select>
            </Field>
            <Field label="Notes">
              <input value={flashNotes} onChange={(e) => setFlashNotes(e.target.value)} />
            </Field>
          </div>
          <div className="row">
            <button disabled={busy || !selectedBuild}>Record flash</button>
            <button type="button" className="secondary" onClick={() => setManual((m) => !m)}>
              {manual ? 'Hide manual entry' : 'Enter manually instead'}
            </button>
          </div>
          {builds.length === 0 ? (
            <p className="small muted">
              No active firmware builds in the catalogue yet — the Firmware
              department adds them under Manage Firmware.
            </p>
          ) : null}
        </form>
      </div>

      <form onSubmit={submit} hidden={!manual}
            style={{ marginTop: 18, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
        <h3>Record a firmware operation manually</h3>
        <div className="grid cols-3">
          <Field label="Firmware name"><input value={form.firmware_name} onChange={set('firmware_name')} required /></Field>
          <Field label="Version"><input value={form.version} onChange={set('version')} required /></Field>
          <Field label="Source">
            <select value={form.source_type} onChange={set('source_type')}>
              <option value="OPEN_SOURCE">Open source</option>
              <option value="CLOSED_SOURCE">Closed source</option>
            </select>
          </Field>
          <Field label="Bootloader version"><input value={form.bootloader_version} onChange={set('bootloader_version')} /></Field>
          <Field label="Build / git ref"><input value={form.build_ref} onChange={set('build_ref')} /></Field>
          <Field label="Parameter profile">
            <select value={form.parameter_profile} onChange={set('parameter_profile')}>
              <option value="">— none —</option>
              {profiles.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </Field>
          <Field label="Script name"><input value={form.script_name} onChange={set('script_name')} /></Field>
          <Field label="Script version"><input value={form.script_version} onChange={set('script_version')} /></Field>
          <Field label="Flashing result">
            <select value={form.flashing_result} onChange={set('flashing_result')}>
              <option value="SUCCESS">Success</option><option value="PARTIAL">Partial</option>
              <option value="FAILED">Failed</option>
            </select>
          </Field>
          <Field label="Configuration result">
            <select value={form.config_result} onChange={set('config_result')}>
              <option value="SUCCESS">Success</option><option value="PARTIAL">Partial</option>
              <option value="FAILED">Failed</option>
            </select>
          </Field>
        </div>
        <div className="row" style={{ marginBottom: 10 }}>
          <label className="row small" style={{ marginBottom: 0 }}>
            <input type="checkbox" checked={form.is_signed} onChange={set('is_signed')}
                   style={{ width: 'auto' }} /> Signed
          </label>
          <label className="row small" style={{ marginBottom: 0 }}>
            <input type="checkbox" checked={form.is_locked} onChange={set('is_locked')}
                   style={{ width: 'auto' }} /> Locked
          </label>
        </div>
        <Field label="Notes"><textarea value={form.notes} onChange={set('notes')} /></Field>
        <button disabled={busy}>Save firmware record</button>
      </form>
    </>
  )
}

