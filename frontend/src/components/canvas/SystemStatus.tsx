import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSentinelStore } from '../../store'
import { settingsApi } from '../../api'
import './SystemStatus.css'

export default function SystemStatus() {
  const { systemState, wsConnected, telemetry } = useSentinelStore()
  const navigate = useNavigate()
  const [autoHeal, setAutoHeal] = useState(true)

  useEffect(() => {
    settingsApi.getPreferences().then(r => {
      if (r.data?.auto_heal !== undefined) setAutoHeal(r.data.auto_heal)
    })
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
          <div className="status-row">
            <span className="status-row-label">Emergency Stop</span>
            <span className="pill pill-danger">ACTIVE</span>
          </div>
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
