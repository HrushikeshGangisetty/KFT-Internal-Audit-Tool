import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth.jsx'
import {
  Empty, FcLink, Icon, IssueLink, PageHeader, Panel, StatusTag, Tabs, Tag, ago, humanize, usePanel,
} from '../../components/ui.jsx'
import { IssueRow, QueuePanel, TaskRow } from '../work/Queue.jsx'

/* Role-aware Home (WP10). Every panel reads an endpoint that is already
   scoped server-side; panels a role cannot use are not requested at all. */
export default function Home() {
  const { user } = useAuth()
  const p = user?.permissions ?? {}
  const firstName = (user?.full_name || user?.username || '').split(' ')[0]

  return (
    <>
      <PageHeader title={`Hello, ${firstName}`}
                  subtitle="What is waiting on you, and what needs attention today." />
      <QuickActions canFindFc={p.can_view_fcs} canCreateFc={p.can_register_fc} />
      <QueuePanel limit={6} />
      {p.is_head_or_manager ? <NeedsAttention /> : null}
      <div className="grid cols-2 section">
        <RecentActivity />
        {p.can_view_fcs ? <Pipeline /> : null}
      </div>
    </>
  )
}

function QuickActions({ canFindFc, canCreateFc }) {
  const navigate = useNavigate()
  const [serial, setSerial] = useState('')
  const find = (e) => {
    e.preventDefault()
    navigate(`/fcs?search=${encodeURIComponent(serial.trim())}`)
  }
  return (
    <div className="quick-actions section">
      <Link className="btn primary-action" to="/report"><Icon name="alert" />Report a problem</Link>
      {canFindFc ? (
        <form className="quick-find" onSubmit={find} role="search">
          <input value={serial} onChange={(e) => setSerial(e.target.value)}
                 placeholder="Find an FC / serial" aria-label="Find an FC by serial" />
          <button className="secondary" aria-label="Search FCs"><Icon name="search" /></button>
        </form>
      ) : null}
      {canCreateFc ? <Link className="btn secondary" to="/fcs/new"><Icon name="plus" />New FC</Link> : null}
    </div>
  )
}

/** Heads and the manager: plain lists with counts, never rankings. */
function NeedsAttention() {
  const progress = usePanel('/api/progress/')
  const summary = usePanel('/api/dashboard/summary/')
  const [tab, setTab] = useState('past_target')
  const d = progress.data
  const blockedFcs = summary.data?.blocked ?? []
  const tabs = d ? [
    { value: 'past_target', label: `Unacknowledged past target (${d.unacknowledged_past_target.length})` },
    { value: 'escalated', label: `Escalated (${d.escalated.length})` },
    { value: 'blocked_tasks', label: `Blocked tasks (${d.blocked.length})` },
    { value: 'blocked_fcs', label: `Blocked FCs (${summary.data ? blockedFcs.length : '…'})` },
    { value: 'no_update', label: `No update today (${d.no_update_today.length})` },
  ] : null

  return (
    <Panel panel={progress} title="Needs attention" subtitle="Across all teams you can see"
           actions={<Link className="btn sm secondary" to="/tasks?view=team">Team progress</Link>}
           tabs={tabs ? <Tabs inCard tabs={tabs} value={tab} onChange={setTab} /> : null}>
      {(data) => {
        if (tab === 'blocked_fcs') {
          if (summary.error) return <Empty icon="alert">Couldn't load blocked FCs: {summary.error}</Empty>
          if (!summary.data) return <Empty>Loading blocked FCs…</Empty>
          return blockedFcs.length ? (
            <ul className="qlist">{blockedFcs.map((fc) => (
              <li key={fc.id} className="qrow">
                <div className="qrow-main"><FcLink id={fc.id} serial={fc.serial} />
                  <span className="qrow-title">{fc.stage}</span></div>
                <div className="qrow-tags">{fc.issues.map((i) => (
                  <span key={i.id} className="row small"><IssueLink id={i.id} label={i.key} />
                    <StatusTag value={i.status} /></span>))}</div>
              </li>))}</ul>
          ) : <Empty icon="check">No FC is blocked.</Empty>
        }
        const lists = {
          past_target: [data.unacknowledged_past_target, (i) => (
            <IssueRow key={i.id} issue={i} />), 'Every report has been acknowledged within its target.'],
          escalated: [data.escalated, (i) => <IssueRow key={i.id} issue={i} />,
            'Nothing has been escalated.'],
          blocked_tasks: [data.blocked, (t) => <TaskRow key={t.id} task={t} />, 'No task is blocked.'],
          no_update: [data.no_update_today, (m) => (
            <li key={m.id} className="qrow"><div className="qrow-main">{m.name}</div></li>),
          'Everyone has posted an update today.'],
        }
        const [items, render, empty] = lists[tab]
        return items.length ? <ul className="qlist">{items.map(render)}</ul>
          : <Empty icon="check">{empty}</Empty>
      }}
    </Panel>
  )
}

const ACTION_LABEL = {
  CREATE: 'created', UPDATE: 'updated', TRANSITION: 'moved', REASSIGN: 'reassigned',
  STATUS_CHANGE: 'changed status of', VERIFICATION: 'verified',
}

function RecentActivity() {
  const panel = usePanel('/api/audit-log/?page_size=8')
  return (
    <Panel panel={panel} title="Recent activity" subtitle="Changes to records you can see"
           actions={<Link className="btn sm secondary" to="/audit">All activity</Link>}>
      {(data) => (data.results.length ? (
        <ul className="qlist">{data.results.map((e) => (
          <li key={e.id} className="qrow">
            <div className="qrow-main small">
              <strong>{e.actor_name || 'System'}</strong>
              <span>{ACTION_LABEL[e.action] || humanize(e.action).toLowerCase()}</span>
              <span className="qrow-title">{humanize(e.entity_type)} {e.entity_label}</span>
            </div>
            <div className="qrow-tags"><span className="small muted">{ago(e.created_at)}</span></div>
          </li>))}</ul>
      ) : <Empty>No recent activity.</Empty>)}
    </Panel>
  )
}

function Pipeline() {
  const panel = usePanel('/api/dashboard/summary/')
  return (
    <Panel panel={panel} title="FC pipeline" subtitle="Units in each lifecycle stage today"
           actions={<Link className="btn sm secondary" to="/fcs">All FCs</Link>}>
      {(data) => (
        <>
          <div className="stage-strip">
            {data.fc_by_stage.map((s) => (
              <Link key={s.stage} to={`/fcs?current_stage=${s.stage}`}
                    className={`stage-chip ${s.count ? 'in_progress' : ''}`}>
                {s.label} <strong>{s.count}</strong>
              </Link>))}
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>
            {data.fc_total} FCs in total · {data.blocked.length
              ? <Tag tone="bad">{data.blocked.length} blocked</Tag> : 'none blocked'}
          </p>
        </>
      )}
    </Panel>
  )
}
