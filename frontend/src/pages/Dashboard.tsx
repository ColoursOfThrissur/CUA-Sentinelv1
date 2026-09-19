import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BrainCircuit, MessageSquare, ListTodo, Monitor, ShieldCheck, Settings, Landmark, Bookmark, Mail, Bell, Code2, FolderKanban, Sun, Moon } from 'lucide-react'
import { useSentinelStore } from '../store'
import { tasksApi, hitlApi, settingsApi, chatApi } from '../api'
import TelemetryBar from '../components/telemetry/TelemetryBar'
import TaskQueue from '../components/tasks/TaskQueue'
import ChatPanel, { Message } from '../components/chat/ChatPanel'
import HITLPanel from '../components/hitl/HITLPanel'
import SystemStatus from '../components/canvas/SystemStatus'
import DigestPanel from '../components/digests/DigestPanel'
import FinancePanel from '../components/finance/FinancePanel'
import LinksPanel from '../components/links/LinksPanel'
import GmailTriagePanel from '../components/gmail/GmailTriagePanel'
import CodingPanel from '../components/coding/CodingPanel'
import { ProjectsPanel } from '../components/projects/ProjectsPanel'
import NotificationModal from '../components/notifications/NotificationModal'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import './Dashboard.css'

type Tab = 'chat' | 'queue' | 'system' | 'approvals' | 'finance' | 'links' | 'gmail' | 'coding' | 'projects'

export default function Dashboard() {
  const { setTasks, setHitlPending, setSystemState, hitlPending } = useSentinelStore()
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const [showNotifModal, setShowNotifModal] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('sentinel_theme') as 'dark' | 'light') || 'dark'
  })
  const navigate = useNavigate()

  useEffect(() => {
    const savedTheme = (localStorage.getItem('sentinel_theme') as 'dark' | 'light') || 'dark'
    document.documentElement.setAttribute('data-theme', savedTheme)
    document.body.className = `theme-${savedTheme}`
  }, [])

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark'
    setTheme(nextTheme)
    localStorage.setItem('sentinel_theme', nextTheme)
    document.documentElement.setAttribute('data-theme', nextTheme)
    document.body.className = `theme-${nextTheme}`
  }

  // Chat state — owned here so only one ChatPanel instance ever exists
  const [messages,      setMessages]      = useState<Message[]>([])
  const [chatInput,     setChatInput]     = useState('')
  const [chatLoading,   setChatLoading]   = useState(false)
  const [useWeb,        setUseWeb]        = useState(false)
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null)
  const sendInFlightRef = useRef(false)
  const pollInFlightRef = useRef(false)
  const handledTaskIdsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    tasksApi.list().then((r) => {
      const list = Array.isArray(r.data) ? r.data : []
      setTasks(list)

      // Auto-populate chat history from completed ENDPOINT tasks
      const completedChats = list.filter((t: any) => t.workflow_type === 'ENDPOINT' && t.status === 'COMPLETED').reverse()
      if (completedChats.length > 0) {
        const historyMsgs: Message[] = []
        for (const ct of completedChats) {
          const prompt = ct.input_payload?.prompt || ct.title?.replace('Chat: ', '')
          const resPayload = ct.result_payload as Record<string, unknown> | undefined
          const resp = resPayload?.response || resPayload?.answer
          if (prompt && resp) {
            historyMsgs.push({ role: 'user', content: String(prompt) })
            historyMsgs.push({ role: 'assistant', content: String(resp), task_id: ct.task_id })
          }
        }
        if (historyMsgs.length > 0) {
          setMessages(historyMsgs)
        }
      }
    })
    hitlApi.pending().then((r) => setHitlPending(Array.isArray(r.data) ? r.data : []))
    settingsApi.getSystemState().then((r) => setSystemState(r.data))
    const interval = setInterval(() => {
      tasksApi.list().then((r) => setTasks(Array.isArray(r.data) ? r.data : []))
      hitlApi.pending().then((r) => setHitlPending(Array.isArray(r.data) ? r.data : []))
    }, 10000)
    return () => clearInterval(interval)
  }, [setHitlPending, setSystemState, setTasks])

  // Single polling loop for pending chat task with timeout safeguard
  useEffect(() => {
    if (!pendingTaskId) return
    handledTaskIdsRef.current.delete(pendingTaskId)

    const finishPendingTask = (taskId: string) => {
      handledTaskIdsRef.current.add(taskId)
      pollInFlightRef.current = false
      sendInFlightRef.current = false
      setPendingTaskId(null)
      setChatLoading(false)
    }

    const pollInterval = setInterval(async () => {
      if (pollInFlightRef.current) return
      pollInFlightRef.current = true
      try {
        const resp = await tasksApi.get(pendingTaskId)
        const task = resp.data.task
        if (task.status === 'COMPLETED') {
          clearInterval(pollInterval)
          const resultText = task.result_payload?.response || task.result_payload?.answer || 'Task completed.'
          setMessages((prev) => [...prev, { role: 'assistant', content: String(resultText), task_id: pendingTaskId }])
          finishPendingTask(pendingTaskId)
        } else if (task.status === 'FAILED' || task.status === 'CANCELLED') {
          clearInterval(pollInterval)
          setMessages((prev) => [...prev, { role: 'assistant', content: `Task failed: ${task.error_message || 'Unknown error'}`, task_id: pendingTaskId }])
          finishPendingTask(pendingTaskId)
        }
      } catch (err) {
        console.error('Error polling chat task:', err)
      } finally {
        pollInFlightRef.current = false
      }
    }, 1500)

    const timeoutTimer = setTimeout(() => {
      clearInterval(pollInterval)
      if (!handledTaskIdsRef.current.has(pendingTaskId)) {
        setMessages((prev) => [...prev, { role: 'assistant', content: 'Chat request timed out. Please try again.', task_id: pendingTaskId }])
        finishPendingTask(pendingTaskId)
      }
    }, 45000)

    return () => {
      clearInterval(pollInterval)
      clearTimeout(timeoutTimer)
    }
  }, [pendingTaskId])

  const handleSendMessage = async () => {
    if (!chatInput.trim() || chatLoading || sendInFlightRef.current) return
    const userText = chatInput.trim()
    setChatInput('')
    sendInFlightRef.current = true
    setChatLoading(true)

    setMessages((prev) => [...prev, { role: 'user', content: userText }])
    try {
      const resp = await chatApi.send(userText, undefined, useWeb, messages.slice(-8))
      if (resp.data && resp.data.task_id) {
        setPendingTaskId(resp.data.task_id)
      } else {
        setChatLoading(false)
        sendInFlightRef.current = false
      }
    } catch (err: any) {
      console.error('Error sending chat message:', err)
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ **Connection Error**\n\nFailed to reach the backend. Please check that the server is running at http://localhost:8000.\n\n_Error: ${err.message || 'Network error'}_` }])
      setChatLoading(false)
      sendInFlightRef.current = false
    }
  }
  const clearChat = async () => {
    sendInFlightRef.current = false
    pollInFlightRef.current = false
    handledTaskIdsRef.current.clear()
    setMessages([])
    setChatInput('')
    setChatLoading(false)
    setPendingTaskId(null)
    try {
      await tasksApi.clearChatHistory()
      const r = await tasksApi.list()
      setTasks(Array.isArray(r.data) ? r.data : [])
    } catch {
      // visible chat cleared
    }
  }

  const chatProps = {
    messages,
    input: chatInput,
    loading: chatLoading,
    webEnabled: useWeb,
    pendingTaskId,
    onInput: setChatInput,
    onSend: handleSendMessage,
    onClear: clearChat,
    onToggleWeb: setUseWeb,
  }

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-brand" onClick={() => setActiveTab('chat')} style={{ cursor: 'pointer' }}>
          <div className="logo-mark">
            <BrainCircuit size={18} color="#ffffff" />
          </div>
          <div>
            <div className="header-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              CUA-SENTINEL <span style={{ fontSize: '0.65rem', background: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', padding: '1px 6px', borderRadius: 4, fontWeight: 700 }}>2.0</span>
            </div>
            <div className="header-sub">Autonomous AI Developer & Operating Engine</div>
          </div>
        </div>

        <div className="header-nav-tabs">
          <button onClick={() => setActiveTab('chat')} className={`desktop-nav-btn ${activeTab === 'chat' ? 'active' : ''}`}>
            <MessageSquare size={14} /> Command Chat
          </button>
          <button onClick={() => setActiveTab('coding')} className={`desktop-nav-btn ${activeTab === 'coding' ? 'active' : ''}`}>
            <Code2 size={14} /> Code Refactor & AI Dev
          </button>
          <button onClick={() => setActiveTab('projects')} className={`desktop-nav-btn ${activeTab === 'projects' ? 'active' : ''}`}>
            <FolderKanban size={14} /> Projects & Live Apps
          </button>
          <button onClick={() => setActiveTab('finance')} className={`desktop-nav-btn ${activeTab === 'finance' ? 'active' : ''}`}>
            <Landmark size={14} /> Finance & Portfolio
          </button>
          <button onClick={() => setActiveTab('links')} className={`desktop-nav-btn ${activeTab === 'links' ? 'active' : ''}`}>
            <Bookmark size={14} /> Links & Research
          </button>
          <button onClick={() => setActiveTab('gmail')} className={`desktop-nav-btn ${activeTab === 'gmail' ? 'active' : ''}`}>
            <Mail size={14} /> Gmail Triage
          </button>
        </div>

        <div className="header-right">
          <div className="telemetry-desktop"><TelemetryBar /></div>
          <button onClick={toggleTheme} className="btn btn-ghost" style={{ padding: '8px 10px', fontSize: '0.82rem' }} title="Toggle Light/Dark Theme">
            {theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
          </button>
          <button onClick={() => setShowNotifModal(true)} className="btn btn-ghost" style={{ padding: '8px 10px', fontSize: '0.82rem' }} title="Notification Settings">
            <Bell size={14} />
          </button>
          <button onClick={() => navigate('/settings')} className="btn btn-ghost" style={{ padding: '8px 10px', fontSize: '0.82rem' }} title="Settings">
            <Settings size={14} />
          </button>
        </div>
      </header>

      {/* Main Full-Width & Grid Views */}
      {activeTab === 'coding' ? (
        <main style={{ padding: '8px 16px', width: '100%', flex: 1, minHeight: 0, overflow: 'auto' }}>
          <ErrorBoundary fallbackTitle="Code Refactor"><CodingPanel /></ErrorBoundary>
        </main>
      ) : activeTab === 'projects' ? (
        <main style={{ padding: '8px 16px', width: '100%', flex: 1, minHeight: 0, overflow: 'auto' }}>
          <ErrorBoundary fallbackTitle="Projects"><ProjectsPanel /></ErrorBoundary>
        </main>
      ) : activeTab === 'finance' ? (
        <main style={{ padding: 16, maxWidth: 1200, margin: '0 auto', width: '100%' }}>
          <ErrorBoundary fallbackTitle="Finance"><FinancePanel /></ErrorBoundary>
        </main>
      ) : activeTab === 'links' ? (
        <main style={{ padding: 16, maxWidth: 1200, margin: '0 auto', width: '100%' }}>
          <ErrorBoundary fallbackTitle="Links"><LinksPanel /></ErrorBoundary>
        </main>
      ) : activeTab === 'gmail' ? (
        <main style={{ padding: 16, maxWidth: 1200, margin: '0 auto', width: '100%' }}>
          <ErrorBoundary fallbackTitle="Gmail Triage"><GmailTriagePanel /></ErrorBoundary>
        </main>
      ) : (
        <main className="main-grid">
          <aside className="side-column">
            <ErrorBoundary fallbackTitle="System Status"><SystemStatus /></ErrorBoundary>
            <ErrorBoundary fallbackTitle="Task Queue"><TaskQueue /></ErrorBoundary>
          </aside>
          <section className="center-column">
            <ErrorBoundary fallbackTitle="Chat"><ChatPanel {...chatProps} /></ErrorBoundary>
          </section>
          <aside className="right-column">
            <ErrorBoundary fallbackTitle="Approvals"><HITLPanel /></ErrorBoundary>
            <ErrorBoundary fallbackTitle="Digests"><DigestPanel /></ErrorBoundary>
          </aside>
        </main>
      )}

      {/* Mobile: single ChatPanel instance, shown/hidden via CSS — never remounted */}
      <div className="mobile-stack">
        <div className="mobile-content">
          <div className={activeTab === 'chat' ? '' : 'mobile-hidden'}>
            <ChatPanel {...chatProps} />
          </div>
          {activeTab === 'queue'     && <div style={{ display:'flex', flexDirection:'column', gap:12 }}><SystemStatus /><TaskQueue /></div>}
          {activeTab === 'system'    && <div style={{ display:'flex', flexDirection:'column', gap:12 }}><TelemetryBar mobile /><SystemStatus /></div>}
          {activeTab === 'approvals' && <div style={{ display:'flex', flexDirection:'column', gap:12 }}><HITLPanel /><DigestPanel /></div>}
          {activeTab === 'coding'    && <CodingPanel />}
          {activeTab === 'projects'  && <ProjectsPanel />}
          {activeTab === 'finance'   && <FinancePanel />}
          {activeTab === 'links'     && <LinksPanel />}
          {activeTab === 'gmail'     && <GmailTriagePanel />}
        </div>
      </div>

      <nav className="bottom-nav" aria-label="Main navigation">
        <NavItem icon={<MessageSquare size={20} />} label="Chat"      tab="chat"      active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<Code2 size={20} />}          label="Coding"    tab="coding"    active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<FolderKanban size={20} />}   label="Projects"  tab="projects"  active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<Landmark size={20} />}      label="Finance"   tab="finance"   active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<Bookmark size={20} />}      label="Links"     tab="links"     active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<Mail size={20} />}          label="Gmail"     tab="gmail"     active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<ListTodo size={20} />}      label="Queue"     tab="queue"     active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<Monitor size={20} />}       label="System"    tab="system"    active={activeTab} onClick={setActiveTab} />
        <NavItem icon={<ShieldCheck size={20} />}   label="Approvals" tab="approvals" active={activeTab} onClick={setActiveTab} badge={hitlPending.length} />
      </nav>

      {showNotifModal && <NotificationModal onClose={() => setShowNotifModal(false)} />}
    </div>
  )
}

function NavItem({ icon, label, tab, active, onClick, badge }: {
  icon: React.ReactNode; label: string; tab: Tab; active: Tab
  onClick: (t: Tab) => void; badge?: number
}) {
  return (
    <button className={`bottom-nav-item ${active === tab ? 'active' : ''}`} onClick={() => onClick(tab)} aria-label={label} aria-current={active === tab ? 'page' : undefined}>
      <div style={{ position: 'relative' }}>
        {icon}
        {badge ? <span className="nav-badge">{badge > 9 ? '9+' : badge}</span> : null}
      </div>
      {label}
    </button>
  )
}
