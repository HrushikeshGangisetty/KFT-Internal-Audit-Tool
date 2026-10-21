import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import {
  Banner, DueTag, Empty, IssueLink, OwnerTag, PageHeader, Panel, StatusTag, Tabs, Tag,
  UrgencyTag, ago, usePanel,
} from '../../components/ui.jsx'
import { useDialog, useToast } from '../../components/overlay.jsx'

/** One issue row: what it is, how urgent, who owns it, how old, when due. */
export function IssueRow({ issue, action }) {
  return (
    <li className="qrow">
      <div className="qrow-main">
        <IssueLink id={issue.id} label={issue.key} />
        <span className="qrow-title">{issue.title}</span>
      </div>
      <div className="qrow-tags">
        <UrgencyTag value={issue.urgency} />
        <StatusTag value={issue.status} />
        <OwnerTag name={issue.accountable_user_name} />
        {issue.ack_due_at ? <DueTag at={issue.ack_due_at} label="Ack" /> : null}
        <span className="small muted">opened {ago(issue.submitted_at || issue.created_at)}</span>
      </div>
      {action ? <div className="qrow-action">{action}</div> : null}
    </li>
  )
}

export function TaskRow({ task }) {
  return (
    <li className="qrow">
      <div className="qrow-main">
        <Link to="/tasks">{task.title}</Link>
      </div>
      <div className="qrow-tags">
        <StatusTag value={task.status} />
        {task.priority === 'high' ? <Tag tone="warn">High priority</Tag> : null}
        <OwnerTag name={task.accountable_user_name} />
        {task.due_date ? <DueTag date={task.due_date} overdue={task.is_overdue} /> : <Tag>No due date</Tag>}
      </div>
    </li>
  )
}

export function Acknowledge({ issue, onDone }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const go = async () => {
    setBusy(true); setError('')
    try {
      await api(`/api/issues/${issue.id}/acknowledge/`, { method: 'POST' })
      toast(`${issue.key} acknowledged.`)
      onDone()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <>{error ? <span className="small error-text">{error}</span> : null}
    <button className="sm" disabled={busy} onClick={go}>{busy ? 'Acknowledging…' : 'Acknowledge'}</button></>
}

function RespondHandoff({ handoff, onDone }) {
  const ask = useDialog()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const respond = async (accept) => {
    let reason = ''
    if (!accept) {
      const r = await ask({ title: `Reject handoff of ${handoff.issue_key}`, tone: 'danger', confirmLabel: 'Reject',
        message: 'The issue stays with its current owner.', input: { label: 'Why are you rejecting this handoff?' } })
      if (!r) return
      reason = r.text
    }
    setBusy(true); setError('')
    try {
      await api(`/api/handoffs/${handoff.id}/respond/`, { method: 'POST', body: { accept, reason } })
      toast(accept ? `Handoff of ${handoff.issue_key} accepted.` : 'Handoff rejected.')
      onDone()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <>{error ? <span className="small error-text">{error}</span> : null}
    <button className="sm ok" disabled={busy} onClick={() => respond(true)}>Accept</button>
    <button className="sm secondary" disabled={busy} onClick={() => respond(false)}>Reject…</button></>
}

const EMPTY = {
  accountable: 'Nothing waiting on you. Issues you own will appear here.',
  awaiting: 'Nothing waiting for your acknowledgement.',
  handoffs: 'No handoffs waiting for your answer.',
  tasks: 'No open tasks. Tasks you own or help with will appear here.',
}

/** The caller's queue from GET /api/me/queue/ (already scoped server-side). */
/** `limit` shows a preview (Home) with a link to the full queue. */
export function QueuePanel({ title = 'My queue', limit }) {
  const panel = usePanel('/api/me/queue/')
  const [tab, setTab] = useState('accountable')
  const d = panel.data
  const tabs = d ? [
    { value: 'accountable', label: `I own (${d.accountable.length})` },
    { value: 'awaiting', label: `To acknowledge (${d.awaiting_acknowledgement.length})` },
    { value: 'handoffs', label: `Handoffs (${d.handoffs_awaiting_response.length})` },
    { value: 'tasks', label: `Tasks (${d.tasks.length})` },
  ] : null
  const update = d ? (d.updated_today
    ? <Tag tone="ok">Today's update posted</Tag>
    : <Link className="btn sm secondary" to="/tasks">No update today · Post one</Link>) : null

  return (
    <Panel panel={panel} title={title} actions={update}
           tabs={tabs ? <Tabs inCard tabs={tabs} value={tab} onChange={setTab} /> : null}>
      {(data) => {
        const rows = {
          accountable: data.accountable.map((i) => <IssueRow key={i.id} issue={i} />),
          awaiting: data.awaiting_acknowledgement.map((i) => (
            <IssueRow key={i.id} issue={i} action={<Acknowledge issue={i} onDone={panel.reload} />} />)),
          handoffs: data.handoffs_awaiting_response.map((h) => (
            <li key={h.id} className="qrow">
              <div className="qrow-main">
                <IssueLink id={h.issue} label={h.issue_key} />
                <span className="qrow-title">to {h.to_department_name}: {h.reason}</span>
              </div>
              <div className="qrow-tags"><span className="small muted">proposed {ago(h.proposed_at)}</span></div>
              <div className="qrow-action"><RespondHandoff handoff={h} onDone={panel.reload} /></div>
            </li>)),
          tasks: data.tasks.map((t) => <TaskRow key={t.id} task={t} />),
        }[tab]
        const more = limit && rows.length > limit ? rows.length - limit : 0
        if (rows.length) {
          return (
            <>
              <ul className="qlist">{more ? rows.slice(0, limit) : rows}</ul>
              {more ? <p className="small" style={{ margin: '10px 0 0' }}>
                <Link to="/queue">{more} more in My queue →</Link></p> : null}
            </>
          )
        }
        return <Empty icon="check" title="All clear">{EMPTY[tab]}</Empty>
      }}
    </Panel>
  )
}

export default function MyQueue() {
  return (
    <>
      <PageHeader title="My queue"
                  subtitle="Issues you own, reports waiting for your acknowledgement, handoffs waiting for your answer, and your tasks." />
      <Banner kind="info">Overdue acknowledgements are shown in red. Acknowledging only confirms you have seen a report; ownership and progress are tracked separately.</Banner>
      <QueuePanel title="Waiting on you" />
    </>
  )
}
