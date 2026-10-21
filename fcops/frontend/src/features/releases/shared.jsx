import { Field, Tag, humanize } from '../../components/ui.jsx'

// WP11-WP13. Buttons are shown from /me capability flags; the backend
// rechecks every capability, the approval and the revision on each action.
const STATE_TONE = { approved: 'ok', rejected: 'bad', pending: 'warn', legacy: '' }
const STATE_LABEL = { legacy: 'Legacy — not approved under current process' }

export const CONTENT = [
  ['source_ref', 'Source reference', 'Commit SHA or tag — required.'],
  ['artifact_ref', 'Artifact reference', 'Where the build lives.'],
  ['artifact_sha256', 'Artifact SHA-256', '64 hex characters, if known.'],
  ['recipient_notes', 'Recipient notes', 'The only release text that goes into the email.'],
  ['internal_notes', 'Internal notes', 'Never sent to recipients.'],
  ['compatibility', 'Compatibility', ''],
  ['known_limitations', 'Known limitations', ''],
]
export const BLANK = Object.fromEntries(CONTENT.map(([k]) => [k, '']))
const LONG = new Set(['recipient_notes', 'internal_notes', 'compatibility', 'known_limitations'])
export const isRef = (k) => k.startsWith('artifact') || k === 'source_ref'

export const StateTag = ({ value }) => (
  <Tag tone={STATE_TONE[value] ?? ''}>{STATE_LABEL[value] ?? humanize(value)}</Tag>
)

export function ContentFields({ form, setForm }) {
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  return CONTENT.map(([k, label, hint]) => (
    <Field key={k} label={label} hint={hint}>
      {LONG.has(k)
        ? <textarea value={form[k]} onChange={set(k)} />
        : <input value={form[k]} onChange={set(k)} className="mono" required={k === 'source_ref'} />}
    </Field>
  ))
}
