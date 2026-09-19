import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { Trash2, Bot, FileText, Globe2, MessageSquare, Send, Sparkles, TrendingUp, Search, Activity, ChevronDown, ChevronRight, Download } from 'lucide-react'
import { useSentinelStore } from '../../store'
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
  const { agentTraces, hitlPending, telemetry } = useSentinelStore()
  const safeMessages = Array.isArray(messages) ? messages : []

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
                  ? <ReactMarkdown>{m.content}</ReactMarkdown>
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

                  // Check known tickers first
                  for (const [keyword, [name, symbol]] of Object.entries(KNOWN_TICKERS)) {
                    if (contentLower.includes(keyword)) {
                      tickerName = name
                      tickerSymbol = symbol
                      break
                    }
                  }

                  // Fallback: detect $SYMBOL patterns (e.g. $AAPL, $TSLA)
                  if (!tickerSymbol) {
                    const dollarMatch = m.content.match(/\$([A-Z]{2,5}(?:\.[A-Z]{2})?)/);
                    if (dollarMatch) {
                      tickerSymbol = dollarMatch[1]
                      tickerName = tickerSymbol
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

                {/* Contextual Smart Next-Action Chips */}
                {m.role === 'assistant' && i === safeMessages.length - 1 && !loading && (
                  <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    <span style={{ fontSize: '0.7rem', color: '#64748b', width: '100%', marginBottom: 2 }}>Suggested next actions:</span>
                    <button onClick={() => applyPromptChip("Check current portfolio alert statuses")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <TrendingUp size={12} color="#10b981" /> Check Portfolio Alerts
                    </button>
                    <button onClick={() => applyPromptChip("Deep research latest developments in this sector")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <Search size={12} color="#38bdf8" /> Deep Research Sector
                    </button>
                    <button onClick={() => applyPromptChip("Summarize key takeaways in bullet points")} className="chat-chip" style={{ fontSize: '0.72rem', padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <FileText size={12} color="#c084fc" /> Bullet Summary
                    </button>
                  </div>
                )}

                {/* Clean Agent Execution Trace Accordion at Bottom */}
                {m.role === 'assistant' && taskTraces.length > 0 && (
                  <div className="trace-accordion-box" style={{ marginTop: 10 }}>
                    <button
                      onClick={() => m.task_id && toggleTrace(m.task_id)}
                      className="trace-accordion-toggle">
                      {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      <Activity size={12} /> ⚡ Execution Details ({taskTraces.length} step{taskTraces.length > 1 ? 's' : ''})
                    </button>

                    {isExpanded && (
                      <div className="trace-accordion-body">
                        {taskTraces.map((tr, idx) => (
                          <div key={idx} className="trace-step-item">
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
                )}

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
                        ? `⚡ ${formatStepName(latestTrace.step_name)}`
                        : 'Sentinel is analyzing request...'}
                  </span>
                </div>

                {pendingApproval && (
                  <div style={{ marginTop: 6, fontSize: '0.75rem', color: '#f87171', background: 'rgba(248,113,113,0.1)', padding: '6px 10px', borderRadius: 6, border: '1px solid rgba(248,113,113,0.2)' }}>
                    Action: <strong>{pendingApproval.action_description}</strong> requires approval in the <strong>Approvals</strong> tab.
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
