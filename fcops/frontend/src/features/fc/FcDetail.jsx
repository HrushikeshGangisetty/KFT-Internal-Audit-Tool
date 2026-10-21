import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth.jsx'
import {
  Banner, Card, Field, Icon, Loading, PageHeader, PageSkeleton, StatusTag, Tabs, Tag, humanize, when,
} from '../../components/ui.jsx'
import { useToast } from '../../components/overlay.jsx'
import ApprovalPanel from './detail/ApprovalPanel.jsx'
import StageRecords from './detail/StageRecords.jsx'
import FirmwareTab from './detail/FirmwareTab.jsx'
import TestTab from './detail/TestTab.jsx'
import { AuditTable, IssuesTable, Timeline } from './detail/tables.jsx'

const TABS = ['timeline', 'stages', 'issues', 'firmware', 'test', 'audit']
const STAGE_MARK = { PASSED: '✓', FAILED: '✕', IN_PROGRESS: '◐' }

const DONE = {
  start_stage: 'Stage started.', pass_stage: 'Stage passed.', fail_stage: 'Stage marked failed.',
  approve: 'Decision recorded.',
}

export default function FcDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const toast = useToast()
  const [fc, setFc] = useState(null)
  const [tab, setTab] = useState('timeline')
  const [timeline, setTimeline] = useState([])
  const [records, setRecords] = useState([])
  const [issues, setIssues] = useState([])
  const [auditRows, setAuditRows] = useState(null)
  const [error, setError] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)

  const reload = useCallback(async () => {
    const [detail, tl, recs, iss] = await Promise.all([
      api(`/api/fcs/${id}/`),
      api(`/api/fcs/${id}/timeline/`),
      api(`/api/fcs/${id}/stage_records/`),
      api(`/api/fcs/${id}/issues/`),
    ])
    setFc(detail); setTimeline(tl); setRecords(recs); setIssues(iss)
  }, [id])

  useEffect(() => {
    reload().catch((e) => setError(e.message))
  }, [reload])

  useEffect(() => {
    if (tab === 'audit' && auditRows === null) {
      api(`/api/fcs/${id}/audit_log/`).then(setAuditRows).catch(() => setAuditRows([]))
    }
  }, [tab, id, auditRows])

  const act = async (path, body = {}) => {
    setBusy(true); setError('')
    try {
      await api(`/api/fcs/${id}/${path}/`, { method: 'POST', body: { notes, ...body } })
      setNotes('')
      await reload()
      setAuditRows(null)
      toast(DONE[path] ?? 'Saved.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !fc) return <Banner>{error}</Banner>
  if (!fc) return <PageSkeleton split />

  const current = records.filter((r) => r.stage === fc.current_stage)
    .sort((a, b) => b.attempt - a.attempt)[0]
  const canApprove = user?.permissions?.can_approve
  const terminal = fc.status === 'APPROVED' || fc.status === 'REJECTED'

  return (
    <>
      <PageHeader
        mono
        title={fc.serial}
        back={{ to: '/fcs', label: 'Flight controllers' }}
        meta={<>
          <StatusTag value={fc.status} />
          <Tag>{fc.fc_model_name}</Tag>
          {fc.hardware_revision ? <Tag>{fc.hardware_revision}</Tag> : null}
          <span className="small muted">at {fc.stage_label || humanize(fc.current_stage)}</span>
        </>}
        actions={
          <Link className="btn" to={`/issues/new?fc=${fc.id}&stage=${fc.current_stage}`}>
            <Icon name="alert" />Report an issue
          </Link>
        }
      />

      <Banner>{error}</Banner>

      <Card title="Lifecycle progress">
        <div className="stage-strip">
          {fc.stage_progress.map((s) => (
            <div key={s.stage}
                 className={`stage-chip ${s.status.toLowerCase()} ${s.stage === fc.current_stage ? 'current' : ''}`}>
              <span aria-hidden="true">{STAGE_MARK[s.status] ?? '○'}</span>
              <span>{s.label}</span>
              {s.attempts > 1 ? <span className="muted">×{s.attempts}</span> : null}
            </div>
          ))}
        </div>
      </Card>

      <div className="split">
        <div>
          <Card tabs={
            <Tabs inCard value={tab} onChange={setTab}
                  tabs={TABS} />
          }>
            {tab === 'timeline' ? <Timeline events={timeline} /> : null}
            {tab === 'stages' ? <StageRecords records={records} fc={fc} onDone={reload} /> : null}
            {tab === 'issues' ? <IssuesTable issues={issues} /> : null}
            {tab === 'firmware' ? <FirmwareTab fc={fc} current={current} onDone={reload} /> : null}
            {tab === 'test' ? <TestTab fc={fc} current={current} onDone={reload} /> : null}
            {tab === 'audit' ? (auditRows === null ? <Loading what="audit" cols={5} />
              : <AuditTable rows={auditRows} />) : null}
          </Card>
        </div>

        <div>
          <Card title="Current stage">
            <p className="row" style={{ marginTop: 0, gap: 8 }}>
              <strong>{humanize(fc.current_stage)}</strong>
              {current ? <StatusTag value={current.status} /> : null}
              {current?.attempt > 1 ? <span className="muted small"> attempt {current.attempt}</span> : null}
            </p>
            {terminal ? (
              <p className="muted small">This FC is {humanize(fc.status).toLowerCase()}; no further stage actions.</p>
            ) : (
              <>
                <Field label="Notes for this action">
                  <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                            placeholder="Optional — what was observed, who signed off…" />
                </Field>
                {fc.stage_blockers?.length ? (
                  <div className="banner warn">
                    <strong>This stage cannot pass yet.</strong>
                    <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                      {fc.stage_blockers.map((reason, i) => <li key={i}>{reason}</li>)}
                    </ul>
                  </div>
                ) : null}
                {fc.current_stage === 'MANAGER_APPROVAL' ? (
                  <ApprovalPanel fc={fc} canApprove={canApprove} busy={busy} act={act} />
                ) : (
                  <div className="row">
                    <button className="secondary" disabled={busy}
                            onClick={() => act('start_stage')}>Start stage</button>
                    <button className="ok" disabled={busy || fc.stage_blockers?.length > 0}
                            title={fc.stage_blockers?.length
                              ? 'Resolve and verify the open issues first'
                              : ''}
                            onClick={() => act('pass_stage')}>Mark passed</button>
                    <button className="danger" disabled={busy}
                            onClick={() => act('fail_stage')}>Mark failed</button>
                  </div>
                )}
              </>
            )}
            {fc.approval_blockers.blockers.length ? (
              <div style={{ marginTop: 12 }}>
                <h3>Blocking release</h3>
                <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                  {fc.approval_blockers.blockers.slice(0, 6).map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </div>
            ) : null}
          </Card>

          <Card title="Record">
            <dl className="kv">
              <dt>Model</dt><dd>{fc.fc_model_name}</dd>
              <dt>Revision</dt><dd>{fc.hardware_revision || '—'}</dd>
              <dt>PCB batch</dt><dd>{fc.pcb_batch || '—'}</dd>
              <dt>Firmware</dt>
              <dd>{fc.current_firmware
                ? `${fc.current_firmware.firmware_name} ${fc.current_firmware.version}`
                : '—'}</dd>
              <dt>Registered</dt><dd>{when(fc.created_at)} by {fc.registered_by_name || '—'}</dd>
              {fc.approved_at ? (<><dt>Decision</dt>
                <dd>{when(fc.approved_at)} by {fc.approved_by_name}</dd></>) : null}
            </dl>
            {fc.notes ? <p className="small muted" style={{ marginBottom: 0 }}>{fc.notes}</p> : null}
          </Card>
        </div>
      </div>
    </>
  )
}

