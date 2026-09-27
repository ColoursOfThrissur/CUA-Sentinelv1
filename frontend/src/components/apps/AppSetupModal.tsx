import React, { useState } from 'react'
import { AppInfo, appsApi } from '../../api'
import { X, Plug, Play, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'

interface AppSetupModalProps {
  app?: AppInfo | null
  isOpen: boolean
  onClose: () => void
  onSaved: () => void
}

export const AppSetupModal: React.FC<AppSetupModalProps> = ({
  app,
  isOpen,
  onClose,
  onSaved,
}) => {
  const isEditing = Boolean(app)

  const [appId, setAppId] = useState(app?.app_id || '')
  const [displayName, setDisplayName] = useState(app?.display_name || '')
  const [transport, setTransport] = useState<'stdio' | 'http'>(app?.transport || 'stdio')
  const [command, setCommand] = useState(app?.command || '')
  const [argsStr, setArgsStr] = useState((app?.args || []).join(' '))
  const [url, setUrl] = useState(app?.url || '')
  const [description, setDescription] = useState(app?.description || '')
  const [riskLevel, setRiskLevel] = useState<'L0' | 'L1' | 'L2' | 'L3'>(
    app?.security?.default_risk_level || 'L2'
  )
  const [sideEffect, setSideEffect] = useState<'read' | 'write' | 'act'>(
    app?.security?.default_side_effect || 'act'
  )
  const [autoApprove, setAutoApprove] = useState<boolean>(
    Boolean((app?.security as any)?.auto_approve)
  )

  // Testing state
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<{
    ok: boolean
    latency_ms?: number
    tools_count?: number
    error?: string
  } | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen) return null

  const handleTest = async () => {
    if (!app?.app_id) return
    setIsTesting(true)
    setTestResult(null)
    try {
      const res = await appsApi.test(app.app_id)
      setTestResult(res.data)
    } catch (err: any) {
      setTestResult({
        ok: false,
        error: err.response?.data?.detail || err.message || 'Test failed',
      })
    } finally {
      setIsTesting(false)
    }
  }

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)
    try {
      const parsedArgs = argsStr.trim() ? argsStr.trim().split(/\s+/) : []
      const payload: any = {
        display_name: displayName,
        transport,
        command: transport === 'stdio' ? command : undefined,
        args: transport === 'stdio' ? parsedArgs : undefined,
        url: transport === 'http' ? url : undefined,
        description,
        security: {
          default_risk_level: autoApprove ? 'L0' : riskLevel,
          default_side_effect: sideEffect,
          returns_untrusted: false,
          auto_approve: autoApprove,
          taint_safe: autoApprove,
        },
      }

      if (isEditing && app) {
        await appsApi.update(app.app_id, payload)
      } else {
        if (!appId.trim()) {
          setError('Application Identifier is required')
          setIsSaving(false)
          return
        }
        await appsApi.add({
          ...payload,
          app_id: appId.trim().toLowerCase().replace(/\s+/g, '_'),
        })
      }
      onSaved()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to save configuration')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="modal-overlay-centered">
      <div
        className="card card-glow"
        style={{
          width: '100%',
          maxWidth: 580,
          padding: 24,
          background: 'var(--bg-card-solid)',
          border: '1px solid var(--glass-border)',
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          borderRadius: 14,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Plug size={18} style={{ color: 'var(--c-cyan)' }} />
            <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>
              {isEditing ? `Configure ${app?.display_name}` : 'Add Application Connection'}
            </h3>
          </div>
          <button
            className="btn btn-ghost"
            onClick={onClose}
            style={{ padding: '4px 8px', minHeight: 'auto' }}
          >
            <X size={16} />
          </button>
        </div>

        {error && (
          <div className="callout callout-error" style={{ fontSize: '0.8rem', padding: '8px 12px' }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {!isEditing && (
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Application ID <span style={{ color: 'var(--text-dim)' }}>(slug, e.g. blender, vscode)</span>
              </label>
              <input
                className="input"
                placeholder="e.g. blender"
                value={appId}
                onChange={(e) => setAppId(e.target.value)}
              />
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Display Name
              </label>
              <input
                className="input"
                placeholder="e.g. Blender 3D"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Transport Protocol
              </label>
              <select
                className="input"
                value={transport}
                onChange={(e) => setTransport(e.target.value as 'stdio' | 'http')}
              >
                <option value="stdio">stdio (Local CLI Process)</option>
                <option value="http">http (Remote Stateless)</option>
              </select>
            </div>
          </div>

          {transport === 'stdio' ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Command
                </label>
                <input
                  className="input"
                  placeholder="uvx / npx / python"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Arguments
                </label>
                <input
                  className="input"
                  placeholder="e.g. blender-mcp"
                  value={argsStr}
                  onChange={(e) => setArgsStr(e.target.value)}
                />
              </div>
            </div>
          ) : (
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Server Endpoint URL
              </label>
              <input
                className="input"
                placeholder="http://localhost:8000/mcp"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
          )}

          <div>
            <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
              Description
            </label>
            <input
              className="input"
              placeholder="What this app does..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Security Tier (Risk Level)
              </label>
              <select
                className="input"
                value={riskLevel}
                onChange={(e) => setRiskLevel(e.target.value as any)}
              >
                <option value="L0">L0 - Informational (Auto-execute)</option>
                <option value="L1">L1 - Minor Write (Auto-execute, logged)</option>
                <option value="L2">L2 - Audited (Recommended for apps)</option>
                <option value="L3">L3 - Critical (Always require HITL)</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Default Side Effect
              </label>
              <select
                className="input"
                value={sideEffect}
                onChange={(e) => setSideEffect(e.target.value as any)}
              >
                <option value="read">Read-only</option>
                <option value="write">Write (State mutating)</option>
                <option value="act">Act (External application action)</option>
              </select>
            </div>
            <div style={{ gridColumn: 'span 2', marginTop: 6, padding: '10px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 6, border: '1px solid var(--border-color)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: '0.82rem', color: 'var(--text-main)' }}>
                <input
                  type="checkbox"
                  checked={autoApprove}
                  onChange={(e) => {
                    setAutoApprove(e.target.checked)
                    if (e.target.checked) {
                      setRiskLevel('L0')
                    }
                  }}
                  style={{ accentColor: 'var(--c-green)', width: 16, height: 16 }}
                />
                <span style={{ fontWeight: 600 }}>Auto-Approve All Actions (Trust App)</span>
              </label>
              <p style={{ margin: '4px 0 0 26px', fontSize: '0.73rem', color: 'var(--text-muted)' }}>
                Bypasses human-in-the-loop (HITL) approval gates for all tools exposed by this application.
              </p>
            </div>
          </div>
        </div>

        {testResult && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: 8,
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: testResult.ok ? 'rgba(34, 197, 94, 0.12)' : 'rgba(239, 68, 68, 0.12)',
              border: `1px solid ${testResult.ok ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              color: testResult.ok ? 'var(--c-green)' : 'var(--c-red)',
            }}
          >
            {testResult.ok ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>
              {testResult.ok
                ? `Connection successful! Latency: ${testResult.latency_ms}ms (${testResult.tools_count} tools discovered)`
                : `Connection failed: ${testResult.error}`}
            </span>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
          {isEditing ? (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleTest}
              disabled={isTesting}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              {isTesting ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
              <span>Test Connection</span>
            </button>
          ) : (
            <div />
          )}

          <div style={{ display: 'flex', gap: 10 }}>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSave}
              disabled={isSaving}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            >
              {isSaving && <Loader2 size={14} className="spin" />}
              <span>Save & Connect</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
