import React, { useState } from 'react'
import {
  BrainCircuit,
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
  ChevronLeft,
  ChevronRight,
  Sun,
  Moon,
  Bell,
  Settings,
  Plug,
} from 'lucide-react'
import { appsApi, AppInfo } from '../../api'
import './SidebarNav.css'

export type NavTab =
  | 'chat'
  | 'coding'
  | 'projects'
  | 'links'
  | 'finance'
  | 'gmail'
  | 'approvals'
  | 'queue'
  | 'system'
  | 'digests'
  | 'apps'

interface SidebarNavProps {
  activeTab: NavTab
  setActiveTab: (tab: NavTab) => void
  hitlPendingCount?: number
  theme: 'dark' | 'light'
  toggleTheme: () => void
  onOpenNotifications: () => void
  onOpenSettings: () => void
  selectedTargetApp?: string | null
  onSelectTargetApp?: (appId: string | null) => void
}

interface NavSectionItem {
  id: NavTab
  label: string
  icon: React.ReactNode
  badge?: number
}

interface NavSection {
  title: string
  items: NavSectionItem[]
}

export default function SidebarNav({
  activeTab,
  setActiveTab,
  hitlPendingCount = 0,
  theme,
  toggleTheme,
  onOpenNotifications,
  onOpenSettings,
  selectedTargetApp,
  onSelectTargetApp,
}: SidebarNavProps) {
  const [isExpanded, setIsExpanded] = useState<boolean>(() => {
    return localStorage.getItem('sentinel_sidebar_expanded') === 'true'
  })
  const [connectedApps, setConnectedApps] = useState<AppInfo[]>([])

  React.useEffect(() => {
    appsApi.list().then((r) => setConnectedApps(r.data.apps || [])).catch(() => {})
  }, [activeTab])

  const handleToggleExpand = () => {
    const next = !isExpanded
    setIsExpanded(next)
    localStorage.setItem('sentinel_sidebar_expanded', String(next))
  }

  const sections: NavSection[] = [
    {
      title: 'Core Workspace',
      items: [
        { id: 'chat', label: 'Command Chat', icon: <MessageSquare size={17} /> },
        { id: 'coding', label: 'Code Refactor & AI Dev', icon: <Code2 size={17} /> },
        { id: 'projects', label: 'Projects & Live Apps', icon: <FolderKanban size={17} /> },
      ],
    },
    {
      title: 'Intelligence & Research',
      items: [
        { id: 'links', label: 'Research & Knowledge Hub', icon: <Microscope size={17} /> },
        { id: 'finance', label: 'Finance & Portfolio', icon: <Landmark size={17} /> },
        { id: 'gmail', label: 'Gmail Triage', icon: <Mail size={17} /> },
      ],
    },
    {
      title: 'Operations & Control',
      items: [
        { id: 'apps', label: 'App Connections & MCP', icon: <Plug size={17} /> },
        {
          id: 'approvals',
          label: 'HITL Approvals',
          icon: <ShieldCheck size={17} />,
          badge: hitlPendingCount,
        },
        { id: 'queue', label: 'Task Queue', icon: <ListTodo size={17} /> },
        { id: 'system', label: 'System & Telemetry', icon: <Monitor size={17} /> },
        { id: 'digests', label: 'Daily Industry Digests', icon: <Sparkles size={17} /> },
      ],
    },
  ]

  return (
    <>
      {/* Persistent 68px anchor in page flow so main screen never shifts */}
      <div className="sidebar-rail-anchor" />

      {/* Scrim click-away backdrop when overlay is expanded */}
      {isExpanded && (
        <div
          className="sidebar-overlay-scrim"
          onClick={() => setIsExpanded(false)}
          title="Click to collapse sidebar"
        />
      )}

      {/* Floating Overlay Navigation Container */}
      <aside className={`sidebar-nav-container ${isExpanded ? 'expanded' : ''}`}>
        {/* Header / Brand */}
        <div className="sidebar-header">
          <div className="sidebar-brand-wrapper" onClick={() => setActiveTab('chat')}>
            <div className="sidebar-logo" title="CUA-Sentinel">
              <BrainCircuit size={20} color="#FFFFFF" />
            </div>
            <div className="sidebar-brand-text">
              <div className="sidebar-brand-title">
                SENTINEL <span className="sidebar-version-pill">2.0</span>
              </div>
              <div className="sidebar-brand-subtitle">Autonomous AI Engine</div>
            </div>
          </div>

          <button
            type="button"
            className="sidebar-toggle-btn"
            onClick={handleToggleExpand}
            title={isExpanded ? 'Collapse to Rail' : 'Expand Sidebar'}
            aria-label="Toggle Sidebar"
          >
            {isExpanded ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
          </button>
        </div>

        {/* Active Connected Software Target Dropdown */}
        {isExpanded ? (
          <div className="sidebar-app-target-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontSize: '0.68rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                Active Software
              </label>
              {selectedTargetApp && (
                <span
                  style={{ fontSize: '0.68rem', color: 'var(--c-cyan)', cursor: 'pointer' }}
                  onClick={() => onSelectTargetApp?.(null)}
                >
                  Reset
                </span>
              )}
            </div>
            <select
              value={selectedTargetApp || ''}
              onChange={(e) => onSelectTargetApp?.(e.target.value ? e.target.value : null)}
              className="sidebar-app-select"
            >
              <option value="">Auto (All Tools)</option>
              {connectedApps.map((a) => (
                <option key={a.app_id} value={a.app_id}>
                  {a.status === 'connected' ? '🟢' : '⚪'} {a.display_name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          selectedTargetApp && (
            <div className="sidebar-app-badge-rail" title={`Targeting: ${selectedTargetApp}`}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--c-green)', display: 'inline-block' }} />
            </div>
          )
        )}

        {/* Navigation Sections */}
        <div className="sidebar-body">
          {sections.map((section, sIdx) => (
            <div key={sIdx} className="sidebar-section">
              <div className="sidebar-section-title">{section.title}</div>
              {section.items.map((item) => {
                const isActive = activeTab === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                    onClick={() => setActiveTab(item.id)}
                    title={!isExpanded ? item.label : undefined}
                  >
                    <div className="sidebar-item-icon">{item.icon}</div>
                    <span className="sidebar-item-label">{item.label}</span>
                    {item.badge && item.badge > 0 ? (
                      <>
                        <span className="sidebar-badge">{item.badge}</span>
                        <span className="sidebar-mini-dot" />
                      </>
                    ) : null}
                  </button>
                )
              })}
            </div>
          ))}
        </div>

        {/* Footer Utility Belt */}
        <div className="sidebar-footer">
          <div className="sidebar-system-pill" title="Local System Online">
            <span className="sidebar-online-dot" />
            <span className="sidebar-system-status-text">Ollama Engine Online</span>
          </div>

          <div className="sidebar-actions-row">
            <button
              type="button"
              className="sidebar-action-btn"
              onClick={toggleTheme}
              title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Theme`}
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>

            <button
              type="button"
              className="sidebar-action-btn"
              onClick={onOpenNotifications}
              title="Push Notification Settings"
            >
              <Bell size={15} />
            </button>

            <button
              type="button"
              className="sidebar-action-btn"
              onClick={onOpenSettings}
              title="System Configuration & Preferences"
            >
              <Settings size={15} />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
