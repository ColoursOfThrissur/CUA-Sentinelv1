import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { ArrowLeft, Download, Send, ChevronDown, ChevronRight, Activity, MessageSquare, Bot, User } from 'lucide-react'
import { tasksApi, chatApi, modelsApi } from '../api'
import './TaskDetail.css'

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate   = useNavigate()
  const [data, setData] = useState<{ task: Record<string, unknown>; steps: Record<string, unknown>[] } | null>(null)
  const [replyInput, setReplyInput] = useState('')
  const [replying, setReplying]     = useState(false)
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({})
  const [activeModelTag, setActiveModelTag] = useState<string>('qwen3:14b-q4_K_M')

  useEffect(() => {
    modelsApi.getActive().then(r => {
      if (r.data?.ollama_tag || r.data?.model_name) {
        setActiveModelTag(r.data.ollama_tag || r.data.model_name)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!taskId) return
    const load = () => tasksApi.get(taskId).then((r) => {
      const payload = r.data
      setData({
        task: payload?.task && typeof payload.task === 'object' ? payload.task : {},
        steps: Array.isArray(payload?.steps) ? payload.steps : [],
      })
    })
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [taskId])

  if (!data) return <div className="task-detail-page" style={{ color: 'var(--text-dim)' }}>Loading Task Workbench...</div>

  const task         = data.task ?? {}
  const steps        = Array.isArray(data.steps) ? data.steps : []
  const result       = task.result_payload as Record<string, unknown> | undefined
  const inputPayload = task.input_payload as Record<string, unknown> | undefined
  const prompt       = String(inputPayload?.prompt || task.title || '').replace('Chat: ', '')
  const errorMessage = typeof task.error_message === 'string' ? task.error_message : ''
  const answer       = typeof result?.response === 'string' ? result.response : (typeof result?.answer === 'string' ? result.answer : (result ? JSON.stringify(result, null, 2) : ''))
  const digests      = Array.isArray(result?.digests) ? result.digests as Array<{ topic: string; digest: string }> : []

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => ({ ...prev, [stepId]: !prev[stepId] }))
  }

  const handleSendReply = async () => {
    const text = replyInput.trim()
    if (!text || replying) return
    setReplying(true)
    try {
      const historyPayload = [
        { role: 'user', content: prompt },
        { role: 'assistant', content: answer }
      ]
      await chatApi.send(text, undefined, Boolean(inputPayload?.use_web), historyPayload)
      setReplyInput('')
      navigate('/')
    } catch {
      setReplying(false)
    }
  }

  const handleReplyKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSendReply()
    }
  }

  return (
    <div className="task-detail-page animate-fade-in">
      <div className="task-detail-container">
        {/* Navigation Bar */}
        <div className="task-detail-topbar">
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={() => navigate('/')} className="btn btn-ghost">
              <ArrowLeft size={15} /> Back
            </button>
            <button onClick={() => navigate('/')} className="btn btn-ghost" title="Return to Command Chat">
              <MessageSquare size={15} /> Open in Chat
            </button>
          </div>
          {taskId && (
            <a
              href={`/api/tasks/${taskId}/report`}
              target="_blank"
              rel="noreferrer"
              className="btn btn-primary"
              style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
              <Download size={14} /> Download Report (.md)
            </a>
          )}
        </div>

        {/* Task Header Summary Card */}
        <div className="panel task-header-card">
          <div className="task-title-row">
            <span className={`status-dot ${String(task.status).toLowerCase()}`} />
            <h1 className="task-title">{String(task.title)}</h1>
            <span className="pill pill-cyan" style={{ flexShrink: 0 }}>{String(task.workflow_type)}</span>
          </div>
          <p className="task-meta">Task ID: {String(task.task_id)} • Created: {String(task.created_at)}</p>
          {errorMessage && <p className="error-banner" style={{ marginTop: 10 }}>{errorMessage}</p>}
        </div>

        {/* SCAFFOLDER & CODE_REFACTOR Dedicated Solution Card */}
        {['SCAFFOLDER', 'CODE_REFACTOR', 'REFACTOR'].includes(String(task.workflow_type)) && (
          <div className="panel task-header-card" style={{ marginTop: 16, borderLeft: '4px solid var(--c-cyan)' }}>
            <h3 style={{ margin: '0 0 8px 0', color: 'var(--c-cyan)', fontSize: '1rem', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Activity size={18} /> Autonomous AI Solution Synthesizer Workbench
            </h3>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-base)', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div><strong>Target Location:</strong> <code style={{ color: 'var(--c-green)' }}>{String(inputPayload?.project_path || 'Storage Drive')}</code></div>
              <div><strong>Directive Goal:</strong> {String(inputPayload?.goal_instruction || task.title)}</div>
              {Boolean(inputPayload?.blueprint_filename) && (
                <div><strong>Blueprint Spec Directive:</strong> <span style={{ color: 'var(--c-yellow)' }}>{String(inputPayload?.blueprint_filename)}</span></div>
              )}
            </div>
            <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
              <button onClick={() => navigate('/')} className="btn btn-primary" style={{ fontSize: '0.8rem', padding: '6px 12px' }}>
                Open Projects & Live Apps Hub
              </button>
            </div>
          </div>
        )}

        {/* User Prompt Message Bubble for ENDPOINT / Chat */}
        {prompt && !['SCAFFOLDER', 'CODE_REFACTOR', 'REFACTOR'].includes(String(task.workflow_type)) && (
          <div className="task-msg-card task-msg-user">
            <div className="task-msg-header">
              <div className="msg-avatar msg-avatar-user"><User size={14} /></div>
              <span className="task-msg-author">User Query</span>
            </div>
            <div className="task-msg-body">{String(prompt)}</div>
          </div>
        )}

        {/* Assistant Response Bubble */}
        {answer && !['SCAFFOLDER', 'CODE_REFACTOR', 'REFACTOR'].includes(String(task.workflow_type)) && (
          <div className="task-msg-card task-msg-assistant">
            <div className="task-msg-header">
              <div className="msg-avatar msg-avatar-bot"><Bot size={14} /></div>
              <span className="task-msg-author">Sentinel Assistant Response</span>
            </div>
            <div className="task-msg-body">
              <ReactMarkdown>{answer}</ReactMarkdown>
            </div>
          </div>
        )}

        {/* Structured Industry Radar Digests if available */}
        {digests.length > 0 && (
          <div className="task-digests">
            {digests.map((d) => (
              <div key={d.topic} className="panel digest-card">
                <h3 className="digest-topic">{d.topic}</h3>
                <ReactMarkdown>{d.digest}</ReactMarkdown>
              </div>
            ))}
          </div>
        )}

        {/* Deep Agent Execution Traces */}
        <div className="steps-section" style={{ marginTop: 20 }}>
          <h2 className="section-label" style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Activity size={14} color="var(--c-cyan)" /> Deep Agent Execution Traces ({steps.length} steps)
          </h2>

          <div className="steps-list">
            {steps.map((s, idx) => {
              const stepId = String(s.step_id || idx)
              const isExpanded = expandedSteps[stepId]
              const outputSummary = s.output_summary as Record<string, unknown> | undefined
              const inputContext = s.input_context as Record<string, unknown> | undefined
              const summaryText: string = typeof outputSummary?.summary === 'string'
                ? outputSummary.summary
                : (typeof outputSummary?.text === 'string' ? outputSummary.text : String(s.description || ''))
              const filesWritten: any[] = Array.isArray(outputSummary?.files_written)
                ? outputSummary.files_written
                : (Array.isArray(outputSummary?.files_updated) ? outputSummary.files_updated : [])
              const stepPayload = (outputSummary || inputContext || s.payload) as Record<string, unknown> | undefined

              return (
                <div key={stepId} className="panel step-row-card">
                  <div className="step-row-header" onClick={() => toggleStep(stepId)}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <button className="step-expand-btn">
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>
                      <span className={`status-dot ${String(s.status).toLowerCase()}`} />
                      <span className="step-label-title">#{idx + 1} {String(s.description || s.step_type)}</span>
                    </div>
                    <span className="step-status-pill">{String(s.status)}</span>
                  </div>

                  {isExpanded && (
                    <div className="step-details-body">
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 12 }}>
                        <div className="step-detail-item">
                          <span className="detail-label" style={{ fontSize: '0.75rem' }}>Step Order & Type:</span>
                          <div style={{ fontSize: '0.82rem', color: 'var(--c-cyan)', fontWeight: 600 }}>#{idx + 1} {String(s.step_type)}</div>
                        </div>
                        <div className="step-detail-item">
                          <span className="detail-label" style={{ fontSize: '0.75rem' }}>Execution Actor:</span>
                          <div style={{ fontSize: '0.82rem', color: 'var(--text-base)' }}>🤖 Local LLM Engine ({activeModelTag})</div>
                        </div>
                        <div className="step-detail-item">
                          <span className="detail-label" style={{ fontSize: '0.75rem' }}>Status:</span>
                          <div><span className={`pill ${String(s.status) === 'COMPLETED' ? 'pill-good' : (String(s.status) === 'RUNNING' ? 'pill-warn' : 'pill-danger')}`} style={{ fontSize: '0.72rem' }}>{String(s.status)}</span></div>
                        </div>
                      </div>

                      {/* Written / Modified Files List if present */}
                      {filesWritten.length > 0 && (
                        <div style={{ marginBottom: 12, background: 'var(--bg-subtle)', padding: '8px 12px', borderRadius: 6, border: '1px solid var(--border-cyan)' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--c-cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
                            📁 Files Synthesized & Written ({filesWritten.length}):
                          </span>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                            {filesWritten.map((f: any, i: number) => (
                              <span key={i} style={{ background: 'var(--bg-input)', color: 'var(--c-green)', padding: '2px 8px', borderRadius: 4, fontSize: '0.75rem', fontFamily: 'monospace', border: '1px solid var(--border-base)' }}>
                                {String(f)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* LLM Activity & Output Summary */}
                      {summaryText && (
                        <div style={{ marginTop: 8 }}>
                          <span className="detail-label" style={{ fontSize: '0.75rem', fontWeight: 600 }}>LLM Execution Activity & Summary:</span>
                          <div style={{ background: 'var(--bg-input)', padding: 12, borderRadius: 6, marginTop: 4, border: '1px solid var(--border-mid)', color: 'var(--text-base)', fontSize: '0.82rem', lineHeight: 1.5 }}>
                            <ReactMarkdown>{String(summaryText)}</ReactMarkdown>
                          </div>
                        </div>
                      )}

                      {/* Raw Context / Payload Block */}
                      {stepPayload && Object.keys(stepPayload).length > 0 && (
                        <div style={{ marginTop: 10 }}>
                          <span className="detail-label" style={{ color: 'var(--text-dim)', fontSize: '0.72rem' }}>Raw Step Context & Payload:</span>
                          <pre className="step-json-block" style={{ marginTop: 4, fontSize: '0.72rem', padding: 8, borderRadius: 4, overflowX: 'auto' }}>
                            {JSON.stringify(stepPayload, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Thread Continuation Reply Bar for ENDPOINT chat tasks */}
        {task.workflow_type === 'ENDPOINT' && (
          <div className="task-reply-card">
            <h3 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8 }}>
              💬 Continue Conversation Thread
            </h3>
            <div className="task-reply-input-wrap">
              <input
                type="text"
                value={replyInput}
                onChange={(e) => setReplyInput(e.target.value)}
                onKeyDown={handleReplyKey}
                placeholder="Ask a follow-up question to continue this task..."
                className="task-reply-input"
              />
              <button
                onClick={handleSendReply}
                disabled={replying || !replyInput.trim()}
                className="btn btn-primary"
                style={{ padding: '8px 16px', fontSize: '0.82rem' }}>
                <Send size={14} />
                {replying ? 'Sending...' : 'Reply'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
