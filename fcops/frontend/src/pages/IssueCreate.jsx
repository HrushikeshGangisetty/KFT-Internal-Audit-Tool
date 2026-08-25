import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import { Banner, Field } from '../components/ui.jsx'
import SimilarPanel from './SimilarPanel.jsx'

export default function IssueCreate() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [fcs, setFcs] = useState([])
  const [departments, setDepartments] = useState([])
  const [meta, setMeta] = useState({ severities: [], categories: [] })
  const [stages, setStages] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [similar, setSimilar] = useState(null)
  const [searching, setSearching] = useState(false)

  const [form, setForm] = useState({
    fc: params.get('fc') || '',
    discovered_stage: params.get('stage') || '',
    title: '', symptoms: '', description: '',
    severity: 'MAJOR', category: 'UNKNOWN',
    assigned_department: '', firmware_version: '', hardware_revision: '',
    gcs_version: '', configurator_version: '',
  })

  useEffect(() => {
    api('/api/fcs/', { params: { page_size: 200 } }).then((d) => setFcs(listOf(d)))
    api('/api/departments/', { params: { page_size: 100 } }).then((d) => setDepartments(listOf(d)))
    api('/api/issues/meta/').then(setMeta)
    api('/api/lifecycle/').then((d) => setStages(d.stages))
  }, [])

  // When an FC is chosen, default the stage and prefill the recorded versions.
  useEffect(() => {
    if (!form.fc) return
    api(`/api/fcs/${form.fc}/`).then((fc) => {
      setForm((f) => ({
        ...f,
        discovered_stage: f.discovered_stage || fc.current_stage,
        hardware_revision: f.hardware_revision || fc.hardware_revision || '',
        firmware_version: f.firmware_version || fc.current_firmware?.version || '',
      }))
    }).catch(() => {})
  }, [form.fc])

  const probe = useMemo(
    () => `${form.title} ${form.symptoms}`.trim(),
    [form.title, form.symptoms],
  )

  useEffect(() => {
    if (probe.length < 4) { setSimilar(null); return }
    const t = setTimeout(() => {
      setSearching(true)
      api('/api/issues/similar-search/', {
        method: 'POST',
        body: {
          text: probe, stage: form.discovered_stage, category: form.category,
          hardware_revision: form.hardware_revision,
          firmware_version: form.firmware_version,
          gcs_version: form.gcs_version,
          configurator_version: form.configurator_version, limit: 8,
        },
      }).then(setSimilar).catch(() => {}).finally(() => setSearching(false))
    }, 450)
    return () => clearTimeout(t)
  }, [probe, form.discovered_stage, form.category, form.hardware_revision,
      form.firmware_version, form.gcs_version, form.configurator_version])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const issue = await api('/api/issues/', {
        method: 'POST',
        body: {
          ...form,
          fc: Number(form.fc),
          assigned_department: form.assigned_department ? Number(form.assigned_department) : null,
        },
      })
      navigate(`/issues/${issue.id}`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <div className="split">
      <form className="card" onSubmit={submit}>
        <h2>Report an issue</h2>
        <Banner>{error}</Banner>
        <div className="grid cols-2">
          <Field label="Flight controller">
            <select value={form.fc} onChange={set('fc')} required>
              <option value="">— select an FC —</option>
              {fcs.map((fc) => (
                <option key={fc.id} value={fc.id}>{fc.serial} · {fc.stage_label}</option>
              ))}
            </select>
          </Field>
          <Field label="Discovered at stage" hint="Where the symptom was observed — not necessarily where it originated.">
            <select value={form.discovered_stage} onChange={set('discovered_stage')}>
              <option value="">— current stage —</option>
              {stages.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Title">
          <input value={form.title} onChange={set('title')} required
                 placeholder="e.g. GPS not detected after firmware flashing" />
        </Field>
        <Field label="Symptoms" hint="What was actually observed. This is what future searches will match on.">
          <textarea value={form.symptoms} onChange={set('symptoms')} required />
        </Field>
        <Field label="Further description">
          <textarea value={form.description} onChange={set('description')} />
        </Field>
        <div className="grid cols-3">
          <Field label="Severity">
            <select value={form.severity} onChange={set('severity')}>
              {meta.severities.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="Category">
            <select value={form.category} onChange={set('category')}>
              {meta.categories.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="Assign to department" hint="Best guess at the owner; it can be reassigned with a reason.">
            <select value={form.assigned_department} onChange={set('assigned_department')}>
              <option value="">— unassigned —</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
        </div>
        <h3>Versions at time of discovery</h3>
        <div className="grid cols-4">
          <Field label="Hardware revision"><input value={form.hardware_revision} onChange={set('hardware_revision')} /></Field>
          <Field label="Firmware version"><input value={form.firmware_version} onChange={set('firmware_version')} /></Field>
          <Field label="GCS version"><input value={form.gcs_version} onChange={set('gcs_version')} /></Field>
          <Field label="Configurator version"><input value={form.configurator_version} onChange={set('configurator_version')} /></Field>
        </div>
        <button disabled={busy || !form.fc || !form.title || !form.symptoms}>
          {busy ? 'Creating…' : 'Create issue'}
        </button>
      </form>

      <div className="card">
        <h2>Has this happened before?</h2>
        <SimilarPanel result={similar} loading={searching} />
      </div>
    </div>
  )
}
