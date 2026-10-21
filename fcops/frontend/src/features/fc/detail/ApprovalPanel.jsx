import { useState } from 'react'
import { Field } from '../../../components/ui.jsx'
import { useDialog } from '../../../components/overlay.jsx'

export default function ApprovalPanel({ fc, canApprove, busy, act }) {
  const [justification, setJustification] = useState('')
  const ask = useDialog()
  const reject = async () => {
    const ok = await ask({ title: `Reject ${fc.serial}?`, tone: 'danger', confirmLabel: 'Reject / scrap',
      message: 'This is the final decision for this unit; it leaves the lifecycle as rejected.' })
    if (ok) act('approve', { approve: false, note: justification })
  }
  if (!canApprove) {
    return <p className="muted small">Only a manager or admin can record the final release decision.</p>
  }
  return (
    <>
      {fc.approval_blockers.warnings.length ? (
        <>
          <div className="banner warn">
            Unverified non-blocking issues remain. A justification is mandatory.
          </div>
          <Field label="Deviation justification">
            <textarea value={justification} onChange={(e) => setJustification(e.target.value)} />
          </Field>
        </>
      ) : null}
      <div className="row">
        <button className="ok" disabled={busy}
                onClick={() => act('approve', { approve: true, deviation_justification: justification })}>
          Approve for release
        </button>
        <button className="danger" disabled={busy}
                onClick={reject}>
          Reject / scrap
        </button>
      </div>
    </>
  )
}

