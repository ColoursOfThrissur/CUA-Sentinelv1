import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSentinelStore } from '../../store'
import { settingsApi, healthApi, HealthReadyResponse } from '../../api'
import { Activity, Database, Cpu } from 'lucide-react'
import { TelemetryHistoryModal } from '../telemetry/TelemetryHistoryModal'
import './SystemStatus.css'

export default function SystemStatus() {
  const { systemState, wsConnected, telemetry } = useSentinelStore()
  const navigate = useNavigate()
  const [autoHeal, setAutoHeal] = useState(true)
  const [showHistory, setShowHistory] = useState(false)
  const [healthReady, setHealthReady] = useState<HealthReadyResponse | null>(null)

  useEffect(() => {
    settingsApi.getPreferences().then(r => {
      if (r.data?.auto_heal !== undefined) setAutoHeal(r.data.auto_heal)
    })

    const pollHealth = () => {
      healthApi.getReady().then(r => setHealthReady(r.data)).catch(() => {
        setHealthReady(prev => prev ? { ...prev, status: 'not_ready' } : null)
      })
    }
    pollHealth()
    const timer = setInterval(pollHealth, 15000)
    return () => clearInterval(timer)
  }, [])

  const safeMode      = systemState?.safe_mode === 'true'
  const emergencyStop = systemState?.emergency_stop === 'true'
  const vramPct = telemetry?.vram_used_mb && telemetry?.vram_total_mb
    ? (telemetry.vram_used_mb / telemetry.vram_total_mb) * 100 : null

  const handleToggleSafeMode = async () => {
    try {
      await settingsApi.setSafeMode(!safeMode)
    } catch (err) {
      console.error('Failed to toggle safe mode:', err)
    }
  }

  const handleResetEmergencyStop = async () => {
    try {
      await settingsApi.resetEmergencyStop()
      useSentinelStore.getState().setSystemState({
        safe_mode: systemState?.safe_mode || 'false',
        emergency_stop: 'false',
      })
    } catch (err) {
      console.error('Failed to reset emergency stop:', err)
    }
  }

  return (
    <div className="card card-glow system-status">
      <div className="system-header">
        <span className="section-label">System</span>
        <button className="system-settings-link" onClick={() => navigate('/settings')}>
          Settings
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
      </div>

      <div className="status-rows">
        <div className="status-row">
          <span className="status-row-label">Connection</span>
          <span className={`pill ${wsConnected ? 'pill-good' : 'pill-danger'}`}>{wsConnected ? 'Live' : 'Reconnecting'}</span>
        </div>
        <div className="status-row clickable" onClick={handleToggleSafeMode} title="Click to toggle Safe Mode">
          <span className="status-row-label">Safe Mode</span>
          <div className={`switch-toggle ${safeMode ? 'active' : ''}`}>
            <span className="switch-knob" />
            <span className="switch-text">{safeMode ? 'ON' : 'OFF'}</span>
          </div>
        </div>
        <div className="status-row clickable" onClick={() => { settingsApi.updatePreference('auto_heal', !autoHeal); setAutoHeal(!autoHeal) }} title="Click to toggle Zero-Touch Auto-Healing">
          <span className="status-row-label" style={{ color: 'var(--c-cyan)' }}>Auto-Heal</span>
          <div className={`switch-toggle ${autoHeal ? 'active' : ''}`}>
            <span className="switch-knob" />
            <span className="switch-text">{autoHeal ? 'ON' : 'OFF'}</span>
          </div>
        </div>
        {emergencyStop && (
          <div className="status-row" style={{ background: 'rgba(239, 68, 68, 0.15)', padding: '6px 8px', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="status-row-label" style={{ color: '#ef4444', fontWeight: 600 }}>Emergency Stop</span>
            <button
              onClick={handleResetEmergencyStop}
              className="btn btn-success"
              style={{ fontSize: '0.68rem', padding: '2px 8px', height: 'auto', background: '#10b981', color: '#fff', border: 'none', cursor: 'pointer', borderRadius: 4, fontWeight: 700 }}
              title="Click to clear emergency stop and resume normal operations"
            >
              Resume Normal
            </button>
          </div>
        )}
        {healthReady && (
          <>
            <div
              className="status-row"
              title={`SQLite Databases: operational=${healthReady.databases.operational}, audit=${healthReady.databases.audit}, knowledge=${healthReady.databases.knowledge}`}
            >
              <span className="status-row-label" style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <Database size={11} color="var(--text-faint)" /> Databases
              </span>
              <span className={`pill ${healthReady.status === 'ready' ? 'pill-good' : 'pill-danger'}`} style={{ fontSize: '0.68rem', padding: '2px 7px' }}>
                {healthReady.status === 'ready' ? '3/3 WAL' : 'Degraded'}
              </span>
            </div>
            <div className="status-row">
              <span className="status-row-label" style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <Cpu size={11} color="var(--text-faint)" /> Local LLM
              </span>
              <span
                className={`pill ${healthReady.model_runtime === 'reachable' ? 'pill-good' : 'pill-warn'}`}
                style={{ fontSize: '0.68rem', padding: '2px 7px' }}
              >
                {healthReady.model_runtime === 'reachable' ? 'Ollama Live' : 'Ollama Offline'}
              </span>
            </div>
          </>
        )}
      </div>

      {telemetry ? (
        <div className="hw-bars">
          <HardwareBar label="CPU" pct={telemetry.cpu_percent} color="linear-gradient(90deg, #0284c7, #38bdf8)" />
          <HardwareBar label="RAM" pct={telemetry.ram_percent} color="linear-gradient(90deg, #6366f1, #818cf8)" />
          {vramPct !== null && telemetry.vram_used_mb !== null && telemetry.vram_total_mb !== null && (
            <HardwareBar
              label="VRAM"
              pct={vramPct}
              color={vramPct > 85 ? 'linear-gradient(90deg, #ef4444, #f87171)' : 'linear-gradient(90deg, #0d9488, #2dd4bf)'}
              detail={telemetry.vram_total_mb >= 1024 ? `${(telemetry.vram_used_mb / 1024).toFixed(1)} / ${(telemetry.vram_total_mb / 1024).toFixed(0)} GB` : `${telemetry.vram_used_mb}/${telemetry.vram_total_mb} MB`}
            />
          )}
          {telemetry.gpu_temp_c !== null && (
            <div className="hw-bar-header">
              <span className="hw-bar-label">GPU Temp</span>
              <span className="hw-bar-value" style={{ color: telemetry.gpu_temp_c > 80 ? 'var(--c-red)' : 'var(--text-muted)' }}>
                {telemetry.gpu_temp_c}°C
              </span>
            </div>
          )}
        </div>
      ) : (
        <div className="hw-bars">
          {['CPU', 'RAM', 'VRAM'].map((l) => (
            <div key={l} className="hw-skeleton-row">
              <span className="hw-skeleton-label">{l}</span>
              <div className="skeleton hw-skeleton-bar" />
            </div>
          ))}
        </div>
      )}

      <button
        onClick={() => setShowHistory(true)}
        className="btn btn-ghost"
        style={{ width: '100%', marginTop: 8, fontSize: '0.72rem', gap: 6, justifyContent: 'center', padding: '5px 8px' }}
        title="View 24-hour hardware trends and metrics"
      >
        <Activity size={12} color="#38bdf8" /> 24h Hardware Trends
      </button>

      {showHistory && <TelemetryHistoryModal onClose={() => setShowHistory(false)} />}
    </div>
  )
}

function HardwareBar({ label, pct, color, detail }: { label: string; pct: number; color: string; detail?: string }) {
  return (
    <div className="hw-bar">
      <div className="hw-bar-header">
        <span className="hw-bar-label">{label}</span>
        <span className="hw-bar-value">{detail ?? `${pct.toFixed(0)}%`}</span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${Math.min(pct, 100)}%`, background: color, boxShadow: `0 0 6px ${color}` }} />
      </div>
    </div>
  )
}
