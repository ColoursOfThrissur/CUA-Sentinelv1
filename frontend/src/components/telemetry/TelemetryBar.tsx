import { useSentinelStore } from '../../store'
import './TelemetryBar.css'

export default function TelemetryBar(_props: { mobile?: boolean }) {
  const { telemetry } = useSentinelStore()

  if (!telemetry) return (
    <div className="telemetry-bar">
      {['CPU', 'RAM', 'VRAM'].map((l) => (
        <div key={l} className="skeleton" style={{ height: 24, width: 64, borderRadius: 99 }} />
      ))}
    </div>
  )

  return (
    <div className="telemetry-bar">
      <Chip label="CPU"  value={`${telemetry.cpu_percent.toFixed(0)}%`} pct={telemetry.cpu_percent} />
      <Chip label="RAM"  value={`${telemetry.ram_percent.toFixed(0)}%`} pct={telemetry.ram_percent} />
      {telemetry.vram_used_mb !== null && telemetry.vram_total_mb !== null && (
        <Chip label="VRAM" value={`${telemetry.vram_used_mb}/${telemetry.vram_total_mb}`} pct={(telemetry.vram_used_mb / telemetry.vram_total_mb) * 100} />
      )}
      {telemetry.gpu_temp_c !== null && (
        <Chip label="GPU" value={`${telemetry.gpu_temp_c}°C`} pct={telemetry.gpu_temp_c} tempMode />
      )}
    </div>
  )
}

function Chip({ label, value, pct, tempMode }: { label: string; value: string; pct: number; tempMode?: boolean }) {
  const hot   = tempMode ? pct > 80 : pct > 85
  const warm  = pct > 65
  const state = hot ? 'hot' : warm ? 'warm' : ''
  return (
    <div className={`telemetry-chip ${state}`}>
      <span className="telemetry-label">{label}</span>
      <span className={`telemetry-value ${state}`}>{value}</span>
    </div>
  )
}
