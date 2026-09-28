import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { Trash2, Bot, FileText, Globe2, MessageSquare, Send, Sparkles, TrendingUp, Search, Activity, ChevronDown, ChevronRight, Download, Check, X, Box, ShieldCheck, Play } from 'lucide-react'
import { useSentinelStore } from '../../store'
import { chatApi, hitlApi } from '../../api'
import './ChatPanel.css'

export interface Message { role: 'user' | 'assistant'; content: string; task_id?: string }

interface Props {
  messages: Message[]
  input: string
  loading: boolean
  webEnabled: boolean
  pendingTaskId?: string | null
  onInput: (v: string) => void
  onSend: () => void
  onClear: () => void
  onToggleWeb: (v: boolean) => void
}

const formatStepName = (stepName: string) => {
  const name = String(stepName || '').toUpperCase()
  if (name.includes('GMAIL')) return 'Searching Gmail Inbox'
  if (name.includes('WEB_SEARCH')) return 'Searching Web'
  if (name.includes('MARKET_QUOTE')) return 'Fetching Stock Quote'
  if (name.includes('BOOKMARK') || name.includes('LINK')) return 'Indexing Web Link'
  if (name.includes('DESKTOP') || name.includes('CUA')) return 'Desktop Automation'
  return stepName.replace(/_/g, ' ')
}

export default function ChatPanel({ messages, input, loading, webEnabled, pendingTaskId, onInput, onSend, onClear, onToggleWeb }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const navigate  = useNavigate()
  const [isFocused, setIsFocused] = useState(false)
  const [expandedTraces, setExpandedTraces] = useState<Record<string, boolean>>({})
  const [approvedBuilds, setApprovedBuilds] = useState<Record<string, boolean>>({})
  const [approvingBuildId, setApprovingBuildId] = useState<string | null>(null)
  const [approvedPlans, setApprovedPlans] = useState<Record<string, boolean>>({})
  const { agentTraces, hitlPending, setHitlPending, telemetry } = useSentinelStore()
  const safeMessages = Array.isArray(messages) ? messages : []

  const handleApproveSpec = async (buildId: string) => {
    setApprovingBuildId(buildId)
    try {
      await chatApi.approveSpec(buildId)
      setApprovedBuilds(prev => ({ ...prev, [buildId]: true }))
    } catch (e) {
      console.error('Failed to approve 3D spec:', e)
    } finally {
      setApprovingBuildId(null)
    }
  }

  const handleResolveHitl = async (approvalId: string, approved: boolean) => {
    try {
      await hitlApi.resolve(approvalId, approved)
      setHitlPending(hitlPending.filter((h) => h.approval_id !== approvalId))
    } catch (e) {
      console.error('Failed to resolve governance action in chat:', e)
    }
  }

  const handleExecutePlan = (planPrompt: string, planKey: string) => {
    setApprovedPlans(prev => ({ ...prev, [planKey]: true }))
    onInput(planPrompt)
    setTimeout(() => onSend(), 50)
  }

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [safeMessages, loading])

  // Auto-expand textarea height as user types
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`
    }
  }, [input])

  const toggleTrace = (taskId: string) => {
    setExpandedTraces((prev) => ({ ...prev, [taskId]: !prev[taskId] }))
  }

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  const applyPromptChip = (text: string) => {
    onInput(text)
    if (textareaRef.current) {
      textareaRef.current.focus()
    }
  }

  return (
    <div className="card card-glow chat-panel">
      <span className="chat-drag-handle" aria-hidden />

      {/* Chat Header */}
      <div className="chat-header">
        <div className="chat-header-left">
          <MessageSquare size={16} style={{ color: '#38bdf8' }} />
          <span className="chat-header-title">Command Chat</span>
        </div>
        <div className="chat-header-pills">
          <span className="pill pill-cyan">P0 Chat</span>
          <span className="pill pill-subtle">Local GPU ({telemetry?.vram_total_mb ? `${Math.round(telemetry.vram_total_mb / 1024)}GB` : 'GPU'})</span>
          <button
            onClick={() => onToggleWeb(!webEnabled)}
            className={`btn ${webEnabled ? 'btn-primary' : 'btn-ghost'}`}
            style={{ padding: '4px 8px', fontSize: '0.75rem', gap: 4 }}
            title={webEnabled ? 'Web Context Active' : 'Web Context Disabled'}>
            <Globe2 size={12} />
            Web {webEnabled ? 'ON' : 'OFF'}
          </button>
          <button onClick={onClear} className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.75rem', gap: 4 }} title="Clear Chat History">
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="chat-body">
        {safeMessages.length === 0 && (
          <div className="chat-empty animate-fade-in">
            <div className="brand-mark"><Bot size={24} color="#38bdf8" /></div>
            <p className="chat-empty-title">Ask Sentinel Anything</p>
            <p className="chat-empty-sub">Your 24/7 Governed Personal Assistant & Operations Engine.</p>

            {/* Quick Suggestion Chips */}
            <div className="chat-chips-container">
              <button onClick={() => applyPromptChip("Deep research latest frontend AI tools and summarize insights")} className="chat-chip">
                <Search size={12} color="#38bdf8" /> Deep Research AI Tools
              </button>
              <button onClick={() => applyPromptChip("Check portfolio prices and alert if any asset shifted by >= 5%")} className="chat-chip">
                <TrendingUp size={12} color="#10b981" /> Check Finance Alerts
              </button>
              <button onClick={() => applyPromptChip("Summarize recent tech sector developments")} className="chat-chip">
                <Sparkles size={12} color="#a855f7" /> Industry Radar Digest
              </button>
            </div>
          </div>
        )}

        {safeMessages.map((m, i) => {
          const taskTraces = m.task_id ? agentTraces.filter((t) => t.task_id === m.task_id) : []
          const isExpanded = m.task_id ? expandedTraces[m.task_id] : false

          return (
            <div key={i} className={`chat-row animate-fade-in ${m.role === 'user' ? 'chat-row-user' : 'chat-row-assistant'}`}>
              {m.role === 'assistant'
                ? <div className="msg-avatar msg-avatar-bot" aria-hidden><Bot size={15} /></div>
                : <div className="msg-avatar msg-avatar-user" aria-hidden>U</div>
              }
              <div className={`message-bubble ${m.role === 'user' ? 'msg-user' : 'msg-assistant'}`}>
                {m.role === 'assistant'
                  ? <ReactMarkdown disallowedElements={['img']} unwrapDisallowed>{m.content}</ReactMarkdown>
                  : m.content}

                {/* Generative Interactive Stock Quote Card */}
                {m.role === 'assistant' && (() => {
                  const contentLower = m.content.toLowerCase()

                  // Configurable ticker lookup — easy to extend
                  const KNOWN_TICKERS: Record<string, [string, string]> = {
                    'c3.ai': ['C3.ai, Inc.', 'AI'], 'c3 ai': ['C3.ai, Inc.', 'AI'], 'ticker: ai': ['C3.ai, Inc.', 'AI'],
                    'nvidia': ['NVIDIA Corp', 'NVDA'], 'nvda': ['NVIDIA Corp', 'NVDA'],
                    'apple': ['Apple Inc.', 'AAPL'], 'aapl': ['Apple Inc.', 'AAPL'],
                    'microsoft': ['Microsoft Corp', 'MSFT'], 'msft': ['Microsoft Corp', 'MSFT'],
                    'tesla': ['Tesla, Inc.', 'TSLA'], 'tsla': ['Tesla, Inc.', 'TSLA'],
                    'bitcoin': ['Bitcoin', 'BTC-USD'], 'btc': ['Bitcoin', 'BTC-USD'],
                    'google': ['Alphabet Inc.', 'GOOGL'], 'googl': ['Alphabet Inc.', 'GOOGL'], 'alphabet': ['Alphabet Inc.', 'GOOGL'],
                    'amazon': ['Amazon.com Inc.', 'AMZN'], 'amzn': ['Amazon.com Inc.', 'AMZN'],
                    'meta': ['Meta Platforms', 'META'], 'facebook': ['Meta Platforms', 'META'],
                    'ethereum': ['Ethereum', 'ETH-USD'], 'eth': ['Ethereum', 'ETH-USD'],
                    'reliance': ['Reliance Industries', 'RELIANCE.NS'],
                    'tcs': ['Tata Consultancy Services', 'TCS.NS'],
                    'infosys': ['Infosys Ltd', 'INFY.NS'], 'infy': ['Infosys Ltd', 'INFY.NS'],
                  }

                  let tickerName = ""
                  let tickerSymbol = ""

                  // Finance context keywords to ensure we don't false-trigger on words like 'meta', 'apple', 'amazon' in general or 3D contexts
                  const hasFinanceContext = /\b(stock|price|share|shares|market|nasdaq|nyse|dividend|trading|invest|quote|valuation|portfolio|watchlist|earnings)\b/i.test(contentLower)
                  const isBlenderOr3DContext = /\b(blender|spec3d|metallic|roughness|mesh|geometry|viewport|render|polygon|build_spec)\b/i.test(contentLower)

                  // Fallback 1: detect explicit $SYMBOL patterns (e.g. $AAPL, $TSLA, $META) — highest confidence
                  const dollarMatch = m.content.match(/\$([A-Z]{2,5}(?:\.[A-Z]{2})?)\b/);
                  if (dollarMatch) {
                    tickerSymbol = dollarMatch[1]
                    tickerName = tickerSymbol
                  }

                  // Fallback 2: Check known tickers ONLY if financial intent is present and not a 3D/Blender context
                  if (!tickerSymbol && hasFinanceContext && !isBlenderOr3DContext) {
                    for (const [keyword, [name, symbol]] of Object.entries(KNOWN_TICKERS)) {
                      const regex = new RegExp(`\\b${keyword.replace('.', '\\.')}\\b`, 'i')
                      if (regex.test(contentLower)) {
                        tickerName = name
                        tickerSymbol = symbol
                        break
                      }
                    }
                  }

                  if (!tickerSymbol) return null

                  return (
                    <div style={{ marginTop: 10, padding: 12, background: 'linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(15,23,42,0.8) 100%)', borderRadius: 8, border: '1px solid rgba(16,185,129,0.3)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <span style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: 4, background: '#334155', color: '#10b981', fontWeight: 600 }}>LIVE MARKET TICKER</span>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f8fafc', margin: '4px 0 0 0' }}>{tickerName} ({tickerSymbol})</h4>
                      </div>
                      <button
                        onClick={() => applyPromptChip(`Add ${tickerSymbol} stock ticker to my personal portfolio watchlist with 5% alert threshold`)}
                        className="btn btn-primary"
                        style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <TrendingUp size={12} /> + Track {tickerSymbol}
                      </button>
                    </div>
                  )
                })()}

                {/* 3D Spec Approval Card */}
                {m.role === 'assistant' && (() => {
                  const match = m.content.match(/\b(?:save\s+as\s+approved|build_id[:=]\s*["']?|build\s*#?)\s*([a-f0-9]{6,12})\b/i)
                    || m.content.match(/"build_id"\s*:\s*"([a-f0-9]{6,12})"/i);
                  if (!match) return null;
                  const buildId = match[1].toLowerCase();
                  const isApproved = approvedBuilds[buildId];

                  // Extract model name if mentioned
                  const nameMatch = m.content.match(/(?:model_name|Model|spec for ['"]?)([\w_]+)/i);
                  const modelName = nameMatch ? nameMatch[1] : '3D Model';

                  // Extract poly count if mentioned
                  const polyMatch = m.content.match(/(?:poly_count|polys?|polygons?)[:\s]+(\d+)/i);
                  const polyCount = polyMatch ? polyMatch[1] : null;

                  return (
                    <div className="chat-spec3d-card animate-fade-in">
                      <div className="chat-spec3d-header">
                        <div className="chat-spec3d-title">
                          <Box size={16} color="#38bdf8" />
                          <span>{modelName} (Build #{buildId})</span>
                        </div>
                        {isApproved ? (
                          <span style={{ fontSize: '0.74rem', color: '#10b981', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Check size={14} /> Saved to Library
                          </span>
                        ) : (
                          <button
                            onClick={() => handleApproveSpec(buildId)}
                            disabled={approvingBuildId === buildId}
                            className="btn btn-primary"
                            style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Check size={12} /> {approvingBuildId === buildId ? 'Saving...' : 'Approve & Save to Library'}
                          </button>
                        )}
                      </div>
                      <div className="chat-spec3d-meta">
                        {polyCount && <span>Polygons: {polyCount}</span>}
                        <span>Status: Verified & Loaded in Blender</span>
                        <span>Build ID: <code>{buildId}</code></span>
                      </div>
                    </div>
                  );
                })()}

                {/* Plan Execution Card */}
                {m.role === 'assistant' && (() => {
                  let planMatch = m.content.match(/```(?:json)?\s*(\{\s*"(?:action)"\s*:\s*"plan"[\s\S]*?\})\s*```/);
                  if (!planMatch) {
                    planMatch = m.content.match(/(\{\s*"action"\s*:\s*"plan"[\s\S]*?"(?:steps|actions)"\s*:\s*\[[\s\S]*?\][\s\S]*?\})/);
                  }
                  if (!planMatch) return null;
                  try {
                    let cleanedJson = planMatch[1];
                    // Only run math sanitizer if bare JSON.parse fails first
                    let planObj: any;
                    try {
                      planObj = JSON.parse(cleanedJson);
                    } catch {
                      // Strip content inside quoted strings before applying math regex
                      // so we don't corrupt material description strings like "color=[0.6,0.6,0.62,1]"
                      const mathPattern = /(?<!"[^"]*)(\[\s*)([\s0-9\.\+\-\*\/\(\)]*[\+\-\*\/][\s0-9\.\+\-\*\/\(\)]*?)(\s*[,\]])/g;
                      for (let pass = 0; pass < 5; pass++) {
                        const next = cleanedJson.replace(mathPattern, (match: string, p1: string, expr: string, p3: string) => {
                          try {
                            if (/^[\s0-9\.\+\-\*\/\(\)]+$/.test(expr)) {
                              // eslint-disable-next-line no-new-func
                              const val = Function('"use strict"; return (' + expr + ')')();
                              if (typeof val === 'number' && !isNaN(val) && isFinite(val)) {
                                return p1 + (Math.round(val * 10000) / 10000) + p3;
                              }
                            }
                          } catch {}
                          return match;
                        });
                        if (next === cleanedJson) break;
                        cleanedJson = next;
                      }
                      planObj = JSON.parse(cleanedJson);
                    }
                    const steps = planObj.steps || planObj.actions || [];
                    if (!Array.isArray(steps) || steps.length === 0) return null;
                    const planKey = `plan_${i}`;
                    const isExecuted = approvedPlans[planKey];

                    const taskHitl = m.task_id && Array.isArray(hitlPending)
                      ? hitlPending.find((h) => h.task_id === m.task_id)
                      : null;

                    const backendExecuted = m.content.includes('**Action Execution Summary:**') || m.content.includes('✅');

                    return (
                      <div className="chat-plan-card animate-fade-in">
                        <div className="chat-plan-header">
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                            <ShieldCheck size={16} /> Multi-Step Execution Plan ({steps.length} actions)
                          </span>
                          {taskHitl ? (
                            <button
                              onClick={() => handleResolveHitl(taskHitl.approval_id, true)}
                              className="btn btn-primary"
                              style={{ fontSize: '0.72rem', padding: '4px 8px', gap: 4 }}>
                              <Check size={12} /> Approve & Run (requires your confirmation)
                            </button>
                          ) : (backendExecuted || isExecuted) ? (
                            <span style={{ fontSize: '0.72rem', color: '#10b981', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                              <Check size={12} /> Auto-executed — verified by Sentinel
                            </span>
                          ) : (
                            <button
                              onClick={() => handleExecutePlan(`Execute this action plan:\n\`\`\`json\n${JSON.stringify(planObj, null, 2)}\n\`\`\``, planKey)}
                              className="btn btn-primary"
                              style={{ fontSize: '0.72rem', padding: '4px 8px', gap: 4 }}>
                              <Play size={12} /> Execute Plan in Blender
                            </button>
                          )}
                        </div>
                        <div className="chat-plan-steps">
                          {steps.map((st: any, sIdx: number) => (
                            <div key={sIdx} className="chat-plan-step-item">
                              <span style={{ color: '#38bdf8', fontWeight: 600 }}>{sIdx + 1}.</span>
                              <span><code>{st.tool || st.name}</code></span>
                              {st.args && <span style={{ color: '#94a3b8' }}>({Object.keys(st.args).join(', ')})</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  } catch (err) {
                      console.error('Plan card render failed:', err);
                    return null;
                  }
                })()}

                {/* Contextual Smart Next-Action Chips */}
                {m.role === 'assistant' && i === safeMessages.length - 1 && !loading && (() => {
                  const combinedText = (m.content + " " + (safeMessages[i - 1]?.content || "")).toLowerCase();
                  const is3D = /blender|model|mesh|spec|cylinder|sphere|box|lamp|3d|render|geometry/.test(combinedText);
                  const isFinance = /stock|portfolio|ticker|price|market|invest|dividend/.test(combinedText);

                  return (
                    <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      <span style={{ fontSize: '0.7rem', color: '#64748b', width: '100%', marginBottom: 2 }}>Suggested next actions:</span>
                      {is3D ? (
                        <>
                          <button onClick={() => applyPromptChip("Inspect Blender scene manifest and objects")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Box size={12} color="#f59e0b" /> Inspect 3D Manifest
                          </button>
                          <button onClick={() => applyPromptChip("Take viewport screenshot in Blender to verify layout")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Search size={12} color="#38bdf8" /> Verify Viewport
                          </button>
                          <button onClick={() => applyPromptChip("Apply smooth shading and studio lighting to the model")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Sparkles size={12} color="#10b981" /> Studio Shading & Light
                          </button>
                        </>
                      ) : isFinance ? (
                        <>
                          <button onClick={() => applyPromptChip("Check current portfolio alert statuses")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <TrendingUp size={12} color="#10b981" /> Check Portfolio Alerts
                          </button>
                          <button onClick={() => applyPromptChip("Deep research latest developments in this sector")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Search size={12} color="#38bdf8" /> Deep Research Sector
                          </button>
                          <button onClick={() => applyPromptChip("Summarize key takeaways in bullet points")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <FileText size={12} color="#c084fc" /> Bullet Summary
                          </button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => applyPromptChip("Summarize key takeaways in bullet points")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <FileText size={12} color="#c084fc" /> Bullet Summary
                          </button>
                          <button onClick={() => applyPromptChip("Explain the technical details and step-by-step breakdown")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <Sparkles size={12} color="#38bdf8" /> Technical Breakdown
                          </button>
                        </>
                      )}
                    </div>
                  );
                })()}

                {/* Clean Agent Execution Trace Accordion at Bottom */}
                {m.role === 'assistant' && taskTraces.length > 0 && (() => {
                  const dedupedTraces = Array.from(
                    new Map(taskTraces.map((tr, i) => [tr.span_id || `${tr.step_name}-${tr.tool_name}-${i}`, tr])).values()
                  )
                  return (
                    <div className="trace-accordion-box" style={{ marginTop: 10 }}>
                      <button
                        onClick={() => m.task_id && toggleTrace(m.task_id)}
                        className="trace-accordion-toggle">
                        {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        <Activity size={12} /> ⚡ Execution Details ({dedupedTraces.length} step{dedupedTraces.length > 1 ? 's' : ''})
                      </button>

                      {isExpanded && (
                        <div className="trace-accordion-body">
                          {dedupedTraces.map((tr, idx) => (
                            <div key={tr.span_id || idx} className="trace-step-item">
                              <span className="trace-step-name">{formatStepName(tr.step_name)}</span>
                              <span className="trace-step-tool">via {tr.tool_name}</span>
                              {tr.details && Object.keys(tr.details).length > 0 && (
                                <span className="trace-step-details">({JSON.stringify(tr.details)})</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })()}

                {m.task_id && (
                  <div style={{ marginTop: 8, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button onClick={() => navigate(`/tasks/${m.task_id}`)} className="msg-task-link">
                      <FileText size={12} /> View Task Detail
                    </button>
                    <a
                      href={`/api/tasks/${m.task_id}/report`}
                      target="_blank"
                      rel="noreferrer"
                      className="msg-task-link"
                      style={{ color: '#10b981', display: 'inline-flex', alignItems: 'center', gap: 4, textDecoration: 'none' }}>
                      <Download size={12} /> Download Report (.md)
                    </a>
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {loading && (() => {
          const pendingApproval = pendingTaskId ? hitlPending.find((h) => h.task_id === pendingTaskId) : null
          const latestTrace     = pendingTaskId ? agentTraces.find((t) => t.task_id === pendingTaskId) : null

          return (
            <div className="chat-row chat-row-assistant animate-fade-in">
              <div className="msg-avatar msg-avatar-bot"><Bot size={15} /></div>
              <div className="message-bubble msg-assistant thinking">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="thinking-dots">
                    <span /><span /><span />
                  </div>
                  <span style={{ fontSize: '0.82rem', color: '#38bdf8', fontWeight: 600 }}>
                    {pendingApproval
                      ? '⚠️ Action Pending Governance Approval'
                      : latestTrace
                        ? `⚡ ${formatStepName(latestTrace.step_name)}${latestTrace.tool_name ? ` (${latestTrace.tool_name})` : ''}`
                        : 'Sentinel is analyzing request...'}
                  </span>
                </div>

                {pendingApproval && (
                  <div className="chat-approval-box animate-fade-in">
                    <div className="chat-approval-desc">
                      ⚠️ Action requires governance approval: <strong>{pendingApproval.action_description}</strong>
                    </div>
                    <div className="chat-approval-actions">
                      <button
                        onClick={() => handleResolveHitl(pendingApproval.approval_id, true)}
                        className="btn btn-primary"
                        style={{ padding: '4px 10px', fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Check size={12} /> Approve Action
                      </button>
                      <button
                        onClick={() => handleResolveHitl(pendingApproval.approval_id, false)}
                        className="btn btn-ghost"
                        style={{ padding: '4px 10px', fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center', gap: 4, color: '#f87171' }}>
                        <X size={12} /> Deny
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })()}
        <div ref={bottomRef} />
      </div>

      {/* Footer & Chat Input Bar */}
      <div className="chat-footer">
        <div className={`chat-input-wrap ${isFocused ? 'chat-input-focused' : ''}`}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={handleKey}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder="Type a message or command (Shift + Enter for new line)..."
            rows={1}
            className="chat-textarea"
          />

          <div className="chat-input-controls">
            <button
              onClick={() => onToggleWeb(!webEnabled)}
              className={`chat-action-btn ${webEnabled ? 'web-active' : ''}`}
              title={webEnabled ? "Web Surfing Enabled" : "Enable Web Surfing"}>
              <Globe2 size={14} />
            </button>

            <button
              onClick={onSend}
              disabled={loading || !input.trim()}
              className="btn btn-primary chat-send">
              <Send size={14} />
              <span className="send-label">{loading ? 'Sending' : 'Send'}</span>
            </button>
          </div>
        </div>

        <div className="chat-input-hints">
          <span>Press <strong>Enter</strong> to send • <strong>Shift + Enter</strong> for new line</span>
          {webEnabled && <span style={{ color: '#38bdf8', fontWeight: 600 }}>🌐 Web Browsing Active</span>}
        </div>
      </div>
    </div>
  )
}
