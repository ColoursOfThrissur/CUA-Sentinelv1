import React, { useState, useEffect } from 'react'
import { AppInfo, appsApi } from '../../api'
import {
  Plug,
  Plus,
  RefreshCw,
  Power,
  Settings,
  Trash2,
  Wrench,
  Box,
  FolderOpen,
  Github,
  Search,
  Database,
  MessageSquare,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Layers,
} from 'lucide-react'
import { AppSetupModal } from './AppSetupModal'
import { AppToolBrowser } from './AppToolBrowser'
import './AppsPanel.css'

export const AppsPanel: React.FC = () => {
  const [apps, setApps] = useState<AppInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modals and tool drawer state
  const [selectedAppForEdit, setSelectedAppForEdit] = useState<AppInfo | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [expandedToolAppId, setExpandedToolAppId] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})

  const fetchApps = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await appsApi.list()
      setApps(res.data.apps || [])
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load apps')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchApps()
  }, [])

  const handleToggleConnect = async (app: AppInfo) => {
    setActionLoading((prev) => ({ ...prev, [app.app_id]: true }))
    try {
      if (app.status === 'connected') {
        await appsApi.disconnect(app.app_id)
      } else {
        await appsApi.connect(app.app_id)
      }
      await fetchApps()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Operation failed')
    } finally {
      setActionLoading((prev) => ({ ...prev, [app.app_id]: false }))
    }
  }

  const handleDelete = async (appId: string) => {
    if (!window.confirm(`Are you sure you want to remove ${appId}?`)) return
    setActionLoading((prev) => ({ ...prev, [appId]: true }))
    try {
      await appsApi.remove(appId)
      await fetchApps()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Delete failed')
    } finally {
      setActionLoading((prev) => ({ ...prev, [appId]: false }))
    }
  }

  const renderAppIcon = (iconName?: string) => {
    const size = 18
    switch (iconName) {
      case 'box':
        return <Box size={size} />
      case 'folder-open':
        return <FolderOpen size={size} />
      case 'github':
        return <Github size={size} />
      case 'search':
        return <Search size={size} />
      case 'database':
        return <Database size={size} />
      case 'message-square':
        return <MessageSquare size={size} />
      default:
        return <Plug size={size} />
    }
  }

  const connectedCount = apps.filter((a) => a.status === 'connected').length

  return (
    <div className="apps-container">
      <div className="apps-header-row">
        <div className="apps-title-block">
          <h2>Connected Applications & MCP</h2>
          <p>
            Control desktop software, APIs, and tools via Model Context Protocol (MCP 2.x).
            {connectedCount > 0 && (
              <span style={{ color: 'var(--c-green)', marginLeft: 8, fontWeight: 600 }}>
                • {connectedCount} active connection{connectedCount > 1 ? 's' : ''}
              </span>
            )}
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button
            className="btn btn-ghost"
            onClick={fetchApps}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              setSelectedAppForEdit(null)
              setIsModalOpen(true)
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Plus size={15} />
            <span>Add MCP App</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="callout callout-error" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {loading && apps.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          <Loader2 size={24} className="spin" style={{ margin: '0 auto 12px auto' }} />
          <p>Discovering application servers...</p>
        </div>
      ) : apps.length === 0 ? (
        <div
          className="card"
          style={{
            padding: 40,
            textAlign: 'center',
            background: 'var(--bg-card-solid)',
            borderRadius: 12,
          }}
        >
          <Layers size={32} style={{ color: 'var(--text-dim)', margin: '0 auto 12px auto' }} />
          <h4 style={{ margin: '0 0 6px 0', color: 'var(--text-base)' }}>No Applications Configured</h4>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', maxWidth: 460, margin: '0 auto 16px auto' }}>
            Connect Blender, File System, GitHub, or any custom MCP server to give Sentinel direct control through chat.
          </p>
          <button
            className="btn btn-primary"
            onClick={() => {
              setSelectedAppForEdit(null)
              setIsModalOpen(true)
            }}
          >
            Add First Application
          </button>
        </div>
      ) : (
        <div className="apps-grid">
          {apps.map((app) => {
            const isConnected = app.status === 'connected'
            const isBusy = Boolean(actionLoading[app.app_id])
            const isToolsExpanded = expandedToolAppId === app.app_id

            return (
              <div key={app.app_id} className="app-card">
                <div className="app-card-head">
                  <div className="app-icon-wrapper">{renderAppIcon(app.icon)}</div>
                  <div className="app-info-block">
                    <h4 className="app-display-name">{app.display_name}</h4>
                    <span className="app-slug">mcp:{app.app_id}</span>
                  </div>
                  <span className={`app-status-badge status-${app.status}`}>
                    {isConnected && <CheckCircle2 size={11} />}
                    {app.status}
                  </span>
                </div>

                {app.description && <p className="app-desc">{app.description}</p>}

                {app.error_message && (
                  <div style={{ fontSize: '0.72rem', color: 'var(--c-red)', display: 'flex', gap: 4 }}>
                    <AlertCircle size={12} style={{ flexShrink: 0, marginTop: 1 }} />
                    <span>{app.error_message}</span>
                  </div>
                )}

                {/* Footer Bar */}
                <div className="app-footer-bar">
                  <button
                    className="btn btn-ghost"
                    onClick={() => setExpandedToolAppId(isToolsExpanded ? null : app.app_id)}
                    style={{
                      padding: '4px 8px',
                      minHeight: 'auto',
                      fontSize: '0.72rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <Wrench size={12} />
                    <span>{app.tools_count || 0} tools</span>
                  </button>

                  <div className="app-actions">
                    <button
                      className="btn btn-ghost"
                      title="Edit Configuration"
                      onClick={() => {
                        setSelectedAppForEdit(app)
                        setIsModalOpen(true)
                      }}
                      style={{ padding: '4px 8px', minHeight: 'auto' }}
                    >
                      <Settings size={13} />
                    </button>
                    <button
                      className="btn btn-ghost"
                      title="Remove App"
                      onClick={() => handleDelete(app.app_id)}
                      disabled={isBusy}
                      style={{ padding: '4px 8px', minHeight: 'auto', color: 'var(--c-red)' }}
                    >
                      <Trash2 size={13} />
                    </button>
                    <button
                      className={`btn ${isConnected ? 'btn-ghost' : 'btn-primary'}`}
                      onClick={() => handleToggleConnect(app)}
                      disabled={isBusy}
                      style={{
                        padding: '4px 10px',
                        minHeight: 'auto',
                        fontSize: '0.74rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 5,
                      }}
                    >
                      {isBusy ? (
                        <Loader2 size={12} className="spin" />
                      ) : (
                        <Power size={12} />
                      )}
                      <span>{isConnected ? 'Disconnect' : 'Connect'}</span>
                    </button>
                  </div>
                </div>

                {/* Expandable tool list */}
                {isToolsExpanded && <AppToolBrowser app={app} />}
              </div>
            )
          })}
        </div>
      )}

      {isModalOpen && (
        <AppSetupModal
          app={selectedAppForEdit}
          isOpen={isModalOpen}
          onClose={() => {
            setIsModalOpen(false)
            setSelectedAppForEdit(null)
          }}
          onSaved={fetchApps}
        />
      )}
    </div>
  )
}
