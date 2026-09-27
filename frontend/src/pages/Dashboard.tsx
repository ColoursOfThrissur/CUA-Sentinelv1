import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  MessageSquare,
  Code2,
  FolderKanban,
  Microscope,
  Landmark,
  Mail,
  ShieldCheck,
  ListTodo,
  Monitor,
  Sparkles,
  Plug,
} from 'lucide-react'
import { useSentinelStore } from '../store'
import { tasksApi, hitlApi, settingsApi, chatApi } from '../api'
import SidebarNav, { NavTab } from '../components/navigation/SidebarNav'
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
import { AppsPanel } from '../components/apps/AppsPanel'
import NotificationModal from '../components/notifications/NotificationModal'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import './Dashboard.css'

const TAB_CONFIG: Record<
  NavTab,
  { section: string; title: string; icon: React.ReactNode }
> = {
  chat: {
    section: 'Core Workspace',
    title: 'Command Chat & Control Center',
    icon: <MessageSquare size={15} />,
  },
  coding: {
    section: 'Core Workspace',
    title: 'Code Refactor & AI Studio',
    icon: <Code2 size={15} />,
  },
  projects: {
    section: 'Core Workspace',
    title: 'Projects & Live Apps',
    icon: <FolderKanban size={15} />,
  },
  links: {
    section: 'Intelligence & Research',
    title: 'Research & Knowledge Hub',
    icon: <Microscope size={15} />,
  },
  finance: {
    section: 'Intelligence & Research',
    title: 'Personal Finance & Portfolio',
    icon: <Landmark size={15} />,
  },
  gmail: {
    section: 'Intelligence & Research',
    title: 'Gmail Inbox Triage',
    icon: <Mail size={15} />,
  },
  approvals: {
    section: 'Operations & Control',
    title: 'Human-in-the-Loop Approvals',
    icon: <ShieldCheck size={15} />,
  },
  queue: {
    section: 'Operations & Control',
    title: 'Autonomous Task Queue',
    icon: <ListTodo size={15} />,
  },
  system: {
    section: 'Operations & Control',
    title: 'System Diagnostics & Telemetry',
    icon: <Monitor size={15} />,
  },
  digests: {
    section: 'Operations & Control',
    title: 'Daily Industry Digests',
    icon: <Sparkles size={15} />,
  },
  apps: {
    section: 'Operations & Control',
    title: 'App Connections & MCP',
    icon: <Plug size={15} />,
  },
}

export default function Dashboard() {
  const { setTasks, setHitlPending, setSystemState, hitlPending } = useSentinelStore()
  const [activeTab, setActiveTab] = useState<NavTab>('chat')
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
  const [selectedTargetApp, setSelectedTargetApp] = useState<string | null>(null)
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
    }, 180000)

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
      const resp = await chatApi.send(userText, undefined, useWeb, messages.slice(-8), selectedTargetApp || undefined)
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

  const currentTabMeta = TAB_CONFIG[activeTab] || TAB_CONFIG.chat

  return (
    <div className="dashboard-root">
      {/* Claude Code Console Sidebar with Overlay Expansion */}
      <SidebarNav
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        hitlPendingCount={hitlPending.length}
        theme={theme}
        toggleTheme={toggleTheme}
        onOpenNotifications={() => setShowNotifModal(true)}
        onOpenSettings={() => navigate('/settings')}
        selectedTargetApp={selectedTargetApp}
        onSelectTargetApp={setSelectedTargetApp}
      />

      {/* Main Workspace Area (starts at 68px rail, never pushes or jiggles on sidebar expansion) */}
      <div className="main-workspace-area">
        {/* Workspace Top Header with Breadcrumbs & Live Telemetry */}
        <header className="workspace-top-header">
          <div className="workspace-breadcrumb">
            <span className="workspace-breadcrumb-section">{currentTabMeta.section}</span>
            <span className="workspace-breadcrumb-separator">/</span>
            <span className="workspace-breadcrumb-active">
              {currentTabMeta.icon}
              {currentTabMeta.title}
            </span>
          </div>

          <div className="workspace-header-actions">
            <div className="telemetry-desktop">
              <TelemetryBar />
            </div>
          </div>
        </header>

        {/* Dynamic Workspace Viewport */}
        <div className="workspace-viewport">
          {activeTab === 'coding' ? (
            <div className="full-workspace-fluid">
              <ErrorBoundary fallbackTitle="Code Studio">
                <CodingPanel />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'projects' ? (
            <div className="full-workspace-fluid">
              <ErrorBoundary fallbackTitle="Projects">
                <ProjectsPanel />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'links' ? (
            <div className="full-workspace-container">
              <ErrorBoundary fallbackTitle="Research & Knowledge Hub">
                <LinksPanel />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'finance' ? (
            <div className="full-workspace-container">
              <ErrorBoundary fallbackTitle="Finance">
                <FinancePanel />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'gmail' ? (
            <div className="full-workspace-container">
              <ErrorBoundary fallbackTitle="Gmail Triage">
                <GmailTriagePanel />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'approvals' ? (
            <div className="full-workspace-container" style={{ maxWidth: 960 }}>
              <ErrorBoundary fallbackTitle="Approvals">
                <HITLPanel />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'queue' ? (
            <div className="full-workspace-container" style={{ maxWidth: 960 }}>
              <ErrorBoundary fallbackTitle="Task Queue">
                <TaskQueue />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'system' ? (
            <div className="full-workspace-container" style={{ maxWidth: 960 }}>
              <ErrorBoundary fallbackTitle="System Diagnostics">
                <SystemStatus />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'digests' ? (
            <div className="full-workspace-container" style={{ maxWidth: 1000 }}>
              <ErrorBoundary fallbackTitle="Daily Digests">
                <DigestPanel />
              </ErrorBoundary>
            </div>
          ) : activeTab === 'apps' ? (
            <div className="full-workspace-container" style={{ maxWidth: 1200 }}>
              <ErrorBoundary fallbackTitle="App Connections & MCP">
                <AppsPanel />
              </ErrorBoundary>
            </div>
          ) : (
            /* Default: Command Center Chat & Operations Grid */
            <main className="main-grid">
              <aside className="side-column">
                <ErrorBoundary fallbackTitle="System Status">
                  <SystemStatus />
                </ErrorBoundary>
                <ErrorBoundary fallbackTitle="Task Queue">
                  <TaskQueue />
                </ErrorBoundary>
              </aside>
              <section className="center-column">
                <ErrorBoundary fallbackTitle="Chat">
                  <ChatPanel {...chatProps} />
                </ErrorBoundary>
              </section>
              <aside className="right-column">
                <ErrorBoundary fallbackTitle="Approvals">
                  <HITLPanel />
                </ErrorBoundary>
                <ErrorBoundary fallbackTitle="Digests">
                  <DigestPanel />
                </ErrorBoundary>
              </aside>
            </main>
          )}
        </div>
      </div>

      {/* Mobile Bottom Navigation (<768px viewport) */}
      <nav className="mobile-bottom-nav" aria-label="Mobile Navigation">
        <MobileNavItem
          icon={<MessageSquare size={17} />}
          label="Chat"
          tab="chat"
          active={activeTab}
          onClick={setActiveTab}
        />
        <MobileNavItem
          icon={<Code2 size={17} />}
          label="Code"
          tab="coding"
          active={activeTab}
          onClick={setActiveTab}
        />
        <MobileNavItem
          icon={<FolderKanban size={17} />}
          label="Projects"
          tab="projects"
          active={activeTab}
          onClick={setActiveTab}
        />
        <MobileNavItem
          icon={<Microscope size={17} />}
          label="Research"
          tab="links"
          active={activeTab}
          onClick={setActiveTab}
        />
        <MobileNavItem
          icon={<Landmark size={17} />}
          label="Finance"
          tab="finance"
          active={activeTab}
          onClick={setActiveTab}
        />
        <MobileNavItem
          icon={<Mail size={17} />}
          label="Gmail"
          tab="gmail"
          active={activeTab}
          onClick={setActiveTab}
        />
        <MobileNavItem
          icon={<ShieldCheck size={17} />}
          label="Approvals"
          tab="approvals"
          active={activeTab}
          onClick={setActiveTab}
          badge={hitlPending.length}
        />
        <MobileNavItem
          icon={<ListTodo size={17} />}
          label="Queue"
          tab="queue"
          active={activeTab}
          onClick={setActiveTab}
        />
        <MobileNavItem
          icon={<Monitor size={17} />}
          label="System"
          tab="system"
          active={activeTab}
          onClick={setActiveTab}
        />
      </nav>

      {/* Centered Notifications & Integrations Modal */}
      {showNotifModal && <NotificationModal onClose={() => setShowNotifModal(false)} />}
    </div>
  )
}

function MobileNavItem({
  icon,
  label,
  tab,
  active,
  onClick,
  badge,
}: {
  icon: React.ReactNode
  label: string
  tab: NavTab
  active: NavTab
  onClick: (t: NavTab) => void
  badge?: number
}) {
  return (
    <button
      type="button"
      className={`mobile-nav-item ${active === tab ? 'active' : ''}`}
      onClick={() => onClick(tab)}
      aria-label={label}
      aria-current={active === tab ? 'page' : undefined}
    >
      <div
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {icon}
        {badge && badge > 0 ? (
          <span className="mobile-nav-badge">{badge > 9 ? '9+' : badge}</span>
        ) : null}
      </div>
      <span>{label}</span>
    </button>
  )
}
