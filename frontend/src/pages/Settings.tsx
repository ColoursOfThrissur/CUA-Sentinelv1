import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Cpu, Power, ShieldAlert, Sun, Moon, Palette, Activity } from 'lucide-react'
import { settingsApi, modelsApi, type BackgroundService } from '../api'
import './Settings.css'

export default function Settings() {
  const navigate = useNavigate()
  const [models,      setModels]      = useState<Record<string, unknown>[]>([])
  const [systemState, setSystemState] = useState<Record<string, string>>({})
  const [services,    setServices]    = useState<BackgroundService[]>([])
  const [theme,       setTheme]       = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('sentinel_theme') as 'dark' | 'light') || 'dark'
  })

  useEffect(() => {
    modelsApi.list().then((r) => setModels(Array.isArray(r.data) ? r.data : []))
    settingsApi.getSystemState().then((r) => setSystemState(r.data && typeof r.data === 'object' ? r.data : {}))
    settingsApi.getBackgroundServices().then((r) => setServices(Array.isArray(r.data) ? r.data : []))
  }, [])

  const handleToggleService = async (id: string) => {
    const r = await settingsApi.toggleBackgroundService(id)
    setServices(prev => prev.map(s => s.id === id ? { ...s, enabled: r.data.enabled } : s))
  }

  const applyTheme = (newTheme: 'dark' | 'light') => {
    setTheme(newTheme)
    localStorage.setItem('sentinel_theme', newTheme)
    document.documentElement.setAttribute('data-theme', newTheme)
    document.body.className = `theme-${newTheme}`
  }

  const toggleModel = async (id: string, enabled: boolean) => {
    if (enabled) await modelsApi.disable(id)
    else         await modelsApi.enable(id)
    modelsApi.list().then((r) => setModels(Array.isArray(r.data) ? r.data : []))
  }

  const handleToggleSafeMode = async () => {
    const current = systemState.safe_mode === 'true'
    await settingsApi.setSafeMode(!current)
    settingsApi.getSystemState().then((r) => setSystemState(r.data && typeof r.data === 'object' ? r.data : {}))
  }

  const handleEmergencyStop = async () => {
    if (confirm('Trigger emergency stop? All autonomous operations will halt.')) {
      await settingsApi.emergencyStop()
      settingsApi.getSystemState().then((r) => setSystemState(r.data && typeof r.data === 'object' ? r.data : {}))
    }
  }

  const handleResetEmergencyStop = async () => {
    if (confirm('Clear emergency stop and resume normal operations?')) {
      await settingsApi.resetEmergencyStop()
      settingsApi.getSystemState().then((r) => setSystemState(r.data && typeof r.data === 'object' ? r.data : {}))
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('sentinel_api_token')
    window.location.reload()
  }

  return (
    <div className="settings-page">
      <div className="settings-container">
        <button onClick={() => navigate('/')} className="btn btn-ghost" style={{ marginBottom: 20 }}>
          <ArrowLeft size={15} /> Back
        </button>

        <div className="settings-heading">
          <p className="section-label">Settings</p>
          <h1>Control room</h1>
        </div>

        {/* Theme & Appearance Section */}
        <div className="panel settings-section">
          <div className="settings-section-header">
            <Palette size={16} style={{ color: '#38bdf8' }} />
            <h2>Theme & Appearance</h2>
          </div>
          <div className="settings-actions">
            <button
              onClick={() => applyTheme('dark')}
              className={`btn ${theme === 'dark' ? 'btn-primary' : 'btn-ghost'}`}
            >
              <Moon size={15} /> Dark Mode {theme === 'dark' && '(Active)'}
            </button>
            <button
              onClick={() => applyTheme('light')}
              className={`btn ${theme === 'light' ? 'btn-primary' : 'btn-ghost'}`}
            >
              <Sun size={15} /> Light Mode {theme === 'light' && '(Active)'}
            </button>
          </div>
        </div>

        <div className="panel settings-section">
          <div className="settings-section-header">
            <ShieldAlert size={16} style={{ color: '#fde68a' }} />
            <h2>System</h2>
          </div>
          <div className="settings-actions">
            <button
              onClick={handleToggleSafeMode}
              className={`btn ${systemState.safe_mode === 'true' ? 'btn-warning' : 'btn-secondary'}`}
            >
              Safe Mode: {systemState.safe_mode === 'true' ? 'ON (Click to Turn OFF)' : 'OFF'}
            </button>
            {systemState.emergency_stop === 'true' ? (
              <button
                onClick={handleResetEmergencyStop}
                className="btn btn-success"
                style={{ background: '#10b981', color: '#fff', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 6 }}
              >
                <Power size={15} /> Resume Normal Operations (Clear Emergency Stop)
              </button>
            ) : (
              <button onClick={handleEmergencyStop} className="btn btn-danger">
                <Power size={15} /> Emergency Stop
              </button>
            )}
            <button onClick={handleLogout} className="btn btn-ghost">Lock</button>
          </div>
          {systemState.emergency_stop === 'true' && (
            <div style={{ marginTop: 14, padding: '10px 14px', borderRadius: 6, background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.4)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <span style={{ color: '#f87171', fontSize: '0.85rem', fontWeight: 600 }}>
                🚨 Emergency Stop is currently ACTIVE — all agent operations and tool dispatches are halted.
              </span>
              <button
                onClick={handleResetEmergencyStop}
                className="btn btn-success"
                style={{ fontSize: '0.78rem', padding: '4px 12px', background: '#10b981', color: '#fff' }}
              >
                Clear & Resume Now
              </button>
            </div>
          )}
        </div>

        <div className="panel settings-section">
          <div className="settings-section-header">
            <Activity size={16} style={{ color: '#a78bfa' }} />
            <h2>Background Services</h2>
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginBottom: 12 }}>
            Changes take effect on next restart. All services are disabled by default.
          </p>
          <div className="models-list">
            {services.map((s) => (
              <div key={s.id} className="model-row">
                <div>
                  <p className="model-name">{s.label}</p>
                  <p className="model-meta">{s.description}</p>
                </div>
                <button
                  onClick={() => handleToggleService(s.id)}
                  className={`btn btn-ghost ${s.enabled ? 'model-toggle-on' : 'model-toggle-off'}`}
                >
                  {s.enabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="panel settings-section">
          <div className="settings-section-header">
            <Cpu size={16} style={{ color: 'var(--c-cyan-dim)' }} />
            <h2>Models</h2>
          </div>
          <div className="models-list">
            {models.map((m) => (
              <div key={String(m.model_id)} className="model-row">
                <div>
                  <p className="model-name">{String(m.model_name)}</p>
                  <p className="model-meta">{String(m.ollama_tag)} / {String(m.vram_mb_estimate)}MB VRAM / {String(m.current_state)}</p>
                </div>
                <button
                  onClick={() => toggleModel(String(m.model_id), Boolean(m.is_enabled))}
                  className={`btn btn-ghost ${m.is_enabled ? 'model-toggle-on' : 'model-toggle-off'}`}>
                  {m.is_enabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
