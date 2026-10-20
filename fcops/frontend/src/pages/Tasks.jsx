import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, listOf } from '../lib/api'
import { useAuth } from '../lib/auth.jsx'
import {
  Banner, Card, DueTag, Empty, Field, OwnerTag, PageHeader, Panel, StatusTag, Tabs, Tag, ago,
  usePanel,
} from '../components/ui.jsx'
import { IssueRow } from './Queue.jsx'

const STATUSES = [['planned', 'Planned'], ['in_progress', 'In progress'], ['blocked', 'Blocked'],
  ['done', 'Done'], ['cancelled', 'Cancelled']]

export default function Tasks() {
  const { user } = useAuth()
  const head = user?.permissions?.is_head_or_manager
  const [params, setParams] = useSearchParams()
  const view = params.get('view') || 'mine'
  const tabs = [{ value: 'mine', label: 'My tasks' }, ...(head ? [
    { value: 'all', label: 'All tasks' }, { value: 'team', label: 'Team progress' }] : [])]
  return (
    <>
      <PageHeader title="Tasks" subtitle="Planned work and a short daily progress note. Earlier days are kept as written." />
      <Tabs tabs={tabs} value={view} onChange={(v) => setParams(v === 'mine' ? {} : { view: v })} />
      {view === 'team' && head ? <TeamProgress /> : <TaskWork all={view === 'all' && head} />}
    </>
  )
}

function TaskWork({ all }) {
  const { user } = useAuth()
  const [tick, setTick] = useState(0)
  const reload = () => setTick((t) => t + 1)
  const tasks = usePanel(`/api/tasks/?page_size=100&open=1${all ? '' : '&mine=1'}&_=${tick}`)
  const updates = usePanel(`/api/daily-updates/?mine=1&current=1&page_size=10&_=${tick}`)
  const mine = listOf(tasks.data).filter((t) => t.accountable_user === user.id
    || t.collaborators.some((c) => c.id === user.id))
  return (
    <div className="split">
      <div>
        <Panel panel={tasks} title={all ? 'All open tasks' : 'My open tasks'} flush>
          {(data) => (listOf(data).length ? (
            <ul className="qlist">{listOf(data).map((t) => (
              <TaskItem key={t.id} task={t} onChange={reload}
                        canManage={user.permissions.is_head_or_manager || t.accountable_user === user.id} />
            ))}</ul>
          ) : <Empty icon="check">No open tasks.</Empty>)}
        </Panel>
        <NewTask onCreated={reload} />
      </div>
      <div>
        <PostUpdate tasks={mine} onPosted={reload} />
        <Panel panel={updates} title="My recent updates">
          {(data) => (listOf(data).length ? (
            <ul className="qlist">{listOf(data).map((u) => (
              <li key={u.id} className="qrow">
                <div className="qrow-main small"><strong>{u.date}</strong>
                  <span className="qrow-title">{u.task_title || 'General'}</span></div>
                <div className="small">{u.progress}</div>
                {u.next_step ? <div className="small muted">Next: {u.next_step}</div> : null}
                {u.blockers ? <div className="qrow-tags"><Tag tone="bad">Blocker: {u.blockers}</Tag></div> : null}
              </li>))}</ul>
          ) : <Empty>No updates yet.</Empty>)}
        </Panel>
      </div>
    </div>
  )
}

function TaskItem({ task, canManage, onChange }) {
  const [error, setError] = useState('')
  const setStatus = async (e) => {
    setError('')
    try {
      await api(`/api/tasks/${task.id}/`, { method: 'PATCH', body: { status: e.target.value } })
      onChange()
    } catch (err) { setError(err.message) }
  }
  return (
    <li className="qrow">
      <div className="qrow-main"><span className="qrow-title">{task.title}</span></div>
      <div className="qrow-tags">
        <StatusTag value={task.status} />
        {task.priority === 'high' ? <Tag tone="warn">High priority</Tag> : null}
        <OwnerTag name={task.accountable_user_name} />
        {task.due_date ? <DueTag date={task.due_date} overdue={task.is_overdue} /> : null}
        {task.department_name ? <Tag>{task.department_name}</Tag> : null}
      </div>
      {canManage ? (
        <div className="qrow-action">
          <select value={task.status} onChange={setStatus} aria-label={`Status of ${task.title}`}>
            {STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {error ? <span className="small" style={{ color: 'var(--bad)' }}>{error}</span> : null}
        </div>
      ) : null}
    </li>
  )
}

function NewTask({ onCreated }) {
  const [form, setForm] = useState({ title: '', due_date: '', priority: 'normal' })
  const [error, setError] = useState('')
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = async (e) => {
    e.preventDefault(); setError('')
    try {
      await api('/api/tasks/', { method: 'POST', body: { ...form, due_date: form.due_date || null } })
      setForm({ title: '', due_date: '', priority: 'normal' })
      onCreated()
    } catch (err) { setError(err.message) }
  }
  return (
    <Card as="form" title="New task for me" onSubmit={submit}
          footer={<button disabled={!form.title}>Add task</button>}>
      <Banner>{error}</Banner>
      <Field label="Title"><input value={form.title} onChange={set('title')} required /></Field>
      <div className="grid cols-2">
        <Field label="Due date"><input type="date" value={form.due_date} onChange={set('due_date')} /></Field>
        <Field label="Priority">
          <select value={form.priority} onChange={set('priority')}>
            <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
          </select>
        </Field>
      </div>
    </Card>
  )
}

function PostUpdate({ tasks, onPosted }) {
  const [form, setForm] = useState({ task: '', progress: '', next_step: '', blockers: '' })
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const submit = async (e) => {
    e.preventDefault(); setError(''); setOk('')
    try {
      await api('/api/daily-updates/', { method: 'POST',
        body: { ...form, task: form.task ? Number(form.task) : null } })
      setForm({ task: '', progress: '', next_step: '', blockers: '' })
      setOk('Update posted for today.')
      onPosted()
    } catch (err) { setError(err.message) }
  }
  return (
    <Card as="form" title="Today's update" onSubmit={submit}
          footer={<button disabled={!form.progress}>Post update</button>}>
      <Banner>{error}</Banner>
      <Banner kind="ok">{ok}</Banner>
      <Field label="Task">
        <select value={form.task} onChange={set('task')}>
          <option value="">General (no task)</option>
          {tasks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
        </select>
      </Field>
      <Field label="Progress"><textarea value={form.progress} onChange={set('progress')} required /></Field>
      <Field label="Next step"><input value={form.next_step} onChange={set('next_step')} /></Field>
      <Field label="Blockers" hint="Leave empty if nothing is in your way.">
        <input value={form.blockers} onChange={set('blockers')} />
      </Field>
    </Card>
  )
}

/** Head view from GET /api/progress/: lists only, no counts per person or rankings. */
function TeamProgress() {
  const [departments, setDepartments] = useState([])
  const [department, setDepartment] = useState('')
  const progress = usePanel(`/api/progress/${department ? `?department=${department}` : ''}`)
  useEffect(() => {
    api('/api/departments/', { params: { page_size: 100 } }).then((d) => setDepartments(listOf(d))).catch(() => {})
  }, [])
  return (
    <>
      <Card className="filter-bar">
        <Field label="Department">
          <select value={department} onChange={(e) => setDepartment(e.target.value)}>
            <option value="">All departments</option>
            {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
      </Card>
      <Panel panel={progress} title="Team progress" subtitle="Assigned work, missing updates, overdue and blocked tasks, next steps">
        {(d) => (
          <div className="grid cols-2">
            <Section title="No update today" items={d.no_update_today} empty="Everyone has posted an update today."
                     render={(m) => <li key={m.id} className="qrow">{m.name}</li>} />
            <Section title="Blockers and next steps" items={d.updates_today} empty="No updates yet today."
                     render={(u) => (
                       <li key={u.id} className="qrow">
                         <div className="qrow-main small"><strong>{u.author_name}</strong>
                           <span className="qrow-title">{u.task_title || 'General'}</span></div>
                         <div className="small">{u.progress}</div>
                         {u.next_step ? <div className="small muted">Next: {u.next_step}</div> : null}
                         {u.blockers ? <div className="qrow-tags"><Tag tone="bad">Blocker: {u.blockers}</Tag></div> : null}
                       </li>)} />
            <Section title="Overdue tasks" items={d.overdue} empty="Nothing is overdue." render={taskLine} />
            <Section title="Blocked tasks" items={d.blocked} empty="No task is blocked." render={taskLine} />
            <Section title="Unacknowledged past target" items={d.unacknowledged_past_target}
                     empty="Nothing is past its acknowledgement target."
                     render={(i) => <IssueRow key={i.id} issue={i} />} />
            <Section title="Assigned work" items={d.assigned_work.filter((m) => m.tasks.length)}
                     empty="No open tasks assigned."
                     render={(m) => (
                       <li key={m.id} className="qrow">
                         <div className="qrow-main small"><strong>{m.name}</strong></div>
                         {m.tasks.map((t) => (
                           <div key={t.id} className="qrow-tags small">{t.title} <StatusTag value={t.status} />
                             {t.due_date ? <DueTag date={t.due_date} overdue={t.is_overdue} /> : null}</div>))}
                       </li>)} />
          </div>
        )}
      </Panel>
    </>
  )
}

const taskLine = (t) => (
  <li key={t.id} className="qrow">
    <div className="qrow-main"><span className="qrow-title">{t.title}</span></div>
    <div className="qrow-tags"><StatusTag value={t.status} /><OwnerTag name={t.accountable_user_name} />
      {t.due_date ? <DueTag date={t.due_date} overdue={t.is_overdue} /> : null}
      <span className="small muted">updated {ago(t.updated_at)}</span></div>
  </li>)

function Section({ title, items, render, empty }) {
  return (
    <div>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      {items.length ? <ul className="qlist">{items.map(render)}</ul> : <Empty icon="check">{empty}</Empty>}
    </div>
  )
}
