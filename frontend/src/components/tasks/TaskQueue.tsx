import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2, Clock, Plus, ChevronDown, ChevronRight, Activity, FileCode, ExternalLink } from 'lucide-react'
import { useSentinelStore } from '../../store'
import { tasksApi, schedulerApi } from '../../api'
import './TaskQueue.css'

const STATUS_DOT: Record<string, string> = {
  RUNNING: 'dot-running', COMPLETED: 'dot-completed', FAILED: 'dot-failed',
  QUEUED: 'dot-queued', PREEMPTED: 'dot-preempted', CANCELLED: 'dot-cancelled',
}

function workflowClass(type: string) {
  const map: Record<string, string> = {
    ENDPOINT:    'pill-workflow-endpoint',
    RESEARCHER:  'pill-workflow-researcher',
    SYNTHESIZER: 'pill-workflow-synthesizer',
    REFACTOR:    'pill-workflow-synthesizer',
    SCAFFOLDER:  'pill-workflow-synthesizer',
  }
  return map[type] ?? 'pill-workflow-endpoint'
}

export interface ScheduledJob {
  job_id: string
  name: string
  schedule_type: string
  run_at: string
  workflow_type: string
  prompt: string
  status: string
  created_at: string
}

export default function TaskQueue() {
  const { tasks, setTasks } = useSentinelStore()
  const navigate  = useNavigate()
  const [scheduledJobs, setScheduledJobs] = useState<ScheduledJob[]>([])
  const [showAddReminder, setShowAddReminder] = useState(false)
  const [remName, setRemName] = useState('')
  const [remTime, setRemTime] = useState('15m')
  const [remPrompt, setRemPrompt] = useState('')
  const [expandedTaskIds, setExpandedTaskIds] = useState<Record<string, boolean>>({})
  const [taskStepsCache, setTaskStepsCache] = useState<Record<string, any[]>>({})

  const taskList = Array.isArray(tasks) ? tasks : []
  const active = taskList.filter((t) => ['RUNNING', 'QUEUED', 'PREEMPTED'].includes(t.status))
  const recent = taskList.filter((t) => ['COMPLETED', 'FAILED', 'CANCELLED'].includes(t.status)).slice(0, 8)

  const toggleTaskExpand = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const willExpand = !expandedTaskIds[taskId]
    setExpandedTaskIds((prev) => ({ ...prev, [taskId]: willExpand }))

    if (willExpand && !taskStepsCache[taskId]) {
      try {
        const resp = await tasksApi.get(taskId)
        if (Array.isArray(resp.data?.steps)) {
          setTaskStepsCache((prev) => ({ ...prev, [taskId]: resp.data.steps }))
        }
      } catch (err) {
        console.error(err)
      }
    }
  }

  const loadScheduledJobs = async () => {
    try {
      const res = await schedulerApi.listJobs()
      if (Array.isArray(res.data?.jobs)) {
        setScheduledJobs(res.data.jobs)
      }
    } catch {
      // Ignore background load failures
    }
  }

  useEffect(() => {
    loadScheduledJobs()
    const interval = setInterval(loadScheduledJobs, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleDeleteTask = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setTasks(taskList.filter((t) => t.task_id !== taskId))
    try {
      await tasksApi.deleteTask(taskId)
      const r = await tasksApi.list()
      setTasks(Array.isArray(r.data) ? r.data : [])
    } catch {
      try {
        await tasksApi.cancel(taskId)
        await tasksApi.deleteTask(taskId)
      } catch {}
      const r = await tasksApi.list()
      setTasks(Array.isArray(r.data) ? r.data : [])
    }
  }

  const cancelReminder = async (jobId: string) => {
    try {
      await schedulerApi.cancelJob(jobId)
      loadScheduledJobs()
    } catch {
      loadScheduledJobs()
    }
  }

  const handleCreateReminder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!remPrompt.trim()) return
    try {
      await schedulerApi.createJob({
        name: remName.trim() || `Reminder: ${remPrompt.slice(0, 20)}`,
        time_offset: remTime,
        prompt: remPrompt.trim()
      })
      setRemName('')
      setRemPrompt('')
      setShowAddReminder(false)
      loadScheduledJobs()
    } catch (err) {
      alert('Failed to schedule reminder. Ensure format like 15m, 1h, 2d.')
    }
  }

  const pendingReminders = scheduledJobs.filter((j) => j.status === 'PENDING')

  return (
    <div className="card task-queue">
      <div className="task-queue-header">
        <span className="section-label">Queue</span>
        {active.length > 0 && <span className="pill pill-active">{active.length} active</span>}
      </div>

      {active.length === 0 && recent.length === 0 && (
        <div className="task-empty">
          <div className="empty-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--text-faint)' }}>
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <p className="task-empty-text">No tasks yet</p>
        </div>
      )}

      {active.map((t) => {
        const isExpanded = expandedTaskIds[t.task_id]
        const steps = taskStepsCache[t.task_id] || []

        return (
          <div key={t.task_id} className={`card card-hover task-card status-${t.status} animate-fade-in`} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }} onClick={() => navigate(`/tasks/${t.task_id}`)}>
              <button
                className="btn-icon"
                style={{ padding: 2, color: '#94a3b8' }}
                onClick={(e) => toggleTaskExpand(t.task_id, e)}
                title="Expand sub-tasks & LLM details">
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              <span className={`dot ${STATUS_DOT[t.status] ?? 'dot-queued'}`} style={{ width: 10, height: 10 }} />
              <div className="task-card-body" style={{ flex: 1 }}>
                <p className="task-card-title">{t.title}</p>
                <div className="task-card-meta">
                  <span className={`pill ${workflowClass(t.workflow_type)}`} style={{ padding: '2px 8px', fontSize: '0.72rem' }}>{t.workflow_type}</span>
                  <span className="task-priority">P{t.priority}</span>
                  <span className="task-time" style={{ fontSize: '0.7rem', color: '#64748b' }}>{new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
              </div>
              <button
                className="task-delete-btn"
                title="Remove/Cancel task from queue"
                onClick={(e) => handleDeleteTask(t.task_id, e)}>
                <Trash2 size={13} />
              </button>
            </div>

            {/* Expanded Sub-Task Details Panel */}
            {isExpanded && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-base)', fontSize: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ color: 'var(--c-cyan)', fontWeight: 600, fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Activity size={12} /> LLM Sub-tasks & Execution Steps ({steps.length}):
                  </span>
                  <button
                    onClick={() => navigate(`/tasks/${t.task_id}`)}
                    className="btn btn-ghost"
                    style={{ fontSize: '0.68rem', padding: '2px 6px', gap: 4, color: 'var(--c-cyan)' }}>
                    <ExternalLink size={10} /> Full View
                  </button>
                </div>

                {steps.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {steps.map((s, idx) => {
                      const summary = s.output_summary as Record<string, any> | undefined
                      const files = Array.isArray(summary?.files_written) ? summary.files_written : (Array.isArray(summary?.files_updated) ? summary.files_updated : [])
                      const summaryStr = summary?.summary ? String(summary.summary) : ''
                      return (
                        <div key={s.step_id || idx} style={{ background: 'var(--bg-input)', padding: '8px 10px', borderRadius: 6, border: '1px solid var(--border-mid)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 600, color: 'var(--text-base)', fontSize: '0.78rem' }}>
                              #{idx + 1} {s.description || s.step_type}
                            </span>
                            <span className={`pill ${s.status === 'COMPLETED' ? 'pill-good' : (s.status === 'RUNNING' ? 'pill-warn' : 'pill-danger')}`} style={{ fontSize: '0.65rem', padding: '1px 6px' }}>
                              {s.status}
                            </span>
                          </div>
                          {summaryStr && (
                            <div style={{ margin: '6px 0 0 0', color: 'var(--text-muted)', fontSize: '0.7rem', lineHeight: 1.45, whiteSpace: 'pre-line', background: 'rgba(0,0,0,0.15)', padding: '6px 8px', borderRadius: 4, fontFamily: 'monospace' }}>
                              {summaryStr}
                            </div>
                          )}
                          {files.length > 0 && (
                            <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 4, color: '#10b981', fontSize: '0.68rem', fontWeight: 600 }}>
                              <FileCode size={11} /> Synthesized: <code>{files.join(', ')}</code>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-dim)', fontSize: '0.7rem', margin: '4px 0' }}>🤖 LLM preparing initial step execution plan...</p>
                )}
              </div>
            )}
          </div>
        )
      })}

      {/* Scheduled Reminders & Timers Section */}
      <div className="scheduled-section" style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border-base)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span className="section-label" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', color: 'var(--c-cyan)' }}>
            <Clock size={12} /> Scheduled Reminders ({pendingReminders.length})
          </span>
          <button
            onClick={() => setShowAddReminder(!showAddReminder)}
            className="btn btn-ghost"
            style={{ padding: '2px 6px', fontSize: '0.7rem', gap: 4 }}>
            <Plus size={12} /> + Reminder
          </button>
        </div>

        {showAddReminder && (
          <form onSubmit={handleCreateReminder} style={{ padding: 8, background: 'var(--bg-surface-lo)', borderRadius: 6, marginBottom: 8, border: '1px solid var(--border-mid)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <input
              type="text"
              placeholder="Reminder Prompt (e.g. Check Flipkart order)"
              value={remPrompt}
              onChange={(e) => setRemPrompt(e.target.value)}
              style={{ background: 'var(--bg-input)', border: '1px solid var(--border-mid)', borderRadius: 4, padding: '4px 8px', color: 'var(--text-base)', fontSize: '0.75rem' }}
              required
            />
            <div style={{ display: 'flex', gap: 6 }}>
              <select
                value={remTime}
                onChange={(e) => setRemTime(e.target.value)}
                style={{ background: 'var(--bg-input)', border: '1px solid var(--border-mid)', borderRadius: 4, padding: '4px 6px', color: 'var(--text-base)', fontSize: '0.72rem', flex: 1 }}>
                <option value="10s">In 10 Seconds (Test)</option>
                <option value="15m">In 15 Minutes</option>
                <option value="1h">In 1 Hour</option>
                <option value="4h">In 4 Hours</option>
                <option value="1d">In 1 Day</option>
              </select>
              <button type="submit" className="btn btn-primary" style={{ padding: '4px 10px', fontSize: '0.72rem' }}>
                Schedule
              </button>
            </div>
          </form>
        )}

        {pendingReminders.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {pendingReminders.map((job) => (
              <div key={job.job_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', background: 'var(--bg-input)', borderRadius: 6, border: '1px solid var(--border-cyan)' }}>
                <div style={{ flex: 1, overflow: 'hidden', marginRight: 6 }}>
                  <p style={{ margin: 0, fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-base)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    ⏰ {job.name}
                  </p>
                  <span style={{ fontSize: '0.68rem', color: 'var(--c-cyan)' }}>
                    Due: {new Date(job.run_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <button
                  onClick={() => cancelReminder(job.job_id)}
                  className="task-delete-btn"
                  title="Cancel scheduled reminder">
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          !showAddReminder && <p style={{ fontSize: '0.7rem', color: 'var(--text-dim)', margin: '4px 0' }}>No active background reminders</p>
        )}
      </div>

      {recent.length > 0 && (
        <div className="recent-list" style={{ marginTop: 14 }}>
          <span className="section-label recent-label">Recent Tasks & History</span>
          {recent.map((t) => (
            <div key={t.task_id} className="recent-item clickable" onClick={() => navigate(`/tasks/${t.task_id}`)} title="Click to view full execution details">
              <span className={`dot ${STATUS_DOT[t.status] ?? 'dot-queued'}`} style={{ width: 7, height: 7 }} />
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <p className="recent-title" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.title}</p>
                <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>{new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
              <span className="recent-type">{(t.workflow_type ?? '???').slice(0, 3)}</span>
              <button
                className="task-delete-btn task-delete-btn-compact"
                title="Remove task from queue history"
                onClick={(e) => handleDeleteTask(t.task_id, e)}>
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
