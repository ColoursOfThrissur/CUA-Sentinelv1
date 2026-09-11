import { useNavigate } from 'react-router-dom'
import { useSentinelStore } from '../../store'
import { settingsApi } from '../../api'
import './SystemStatus.css'

export default function SystemStatus() {
  const { systemState, wsConnected, telemetry } = useSentinelStore()
  const navigate = useNavigate()

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
        <div className="status-row" style={{ cursor: 'pointer' }} onClick={handleToggleSafeMode} title="Click to toggle Safe Mode">
          <span className="status-row-label">Safe Mode</span>
          <span className={`pill ${safeMode ? 'pill-warn' : 'pill-good'}`}>
            {safeMode ? 'Active (Click to Off)' : 'Off'}
          </span>
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
          <HardwareBar label="CPU" pct={telemetry.cpu_percent} color="var(--c-indigo)" />
          <HardwareBar label="RAM" pct={telemetry.ram_percent} color="var(--c-purple)" />
          {vramPct !== null && (
            <HardwareBar
              label="VRAM"
              pct={vramPct}
              color={vramPct > 85 ? 'var(--c-red)' : 'var(--c-cyan)'}
              detail={`${telemetry.vram_used_mb}/${telemetry.vram_total_mb} MB`}
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
