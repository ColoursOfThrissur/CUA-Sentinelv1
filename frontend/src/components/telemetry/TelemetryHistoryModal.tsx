import React, { useEffect, useState } from 'react'
import { Activity, Thermometer, Database, Cpu, X, RefreshCw, Sparkles, TrendingUp } from 'lucide-react'
import { telemetryApi } from '../../api'
import './TelemetryHistoryModal.css'

interface TelemetryPoint {
  bucket_hour: string
  gpu_temp_avg: number
  gpu_temp_max: number
  vram_avg_mb: number
  vram_max_mb: number
  ram_avg_mb: number
  ram_max_mb: number
  tokens_in_total: number
  tokens_out_total: number
  inference_count: number
}

interface Props {
  onClose: () => void
}

export const TelemetryHistoryModal: React.FC<Props> = ({ onClose }) => {
  const [data, setData] = useState<TelemetryPoint[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [activeTab, setActiveTab] = useState<'gpu' | 'vram' | 'ram' | 'tokens'>('gpu')

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await telemetryApi.history(24)
      if (Array.isArray(res.data)) {
        setData(res.data)
      }
    } catch (e) {
      console.error('Failed to fetch telemetry history:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Render SVG Sparkline Area Chart
  const renderSparkline = (
    values: number[],
    color: string,
    unit: string,
    minFloor = 0
  ) => {
    if (!values || values.length === 0) return null

    const width = 500
    const height = 120
    const padding = 15

    const min = Math.min(...values, minFloor)
    const max = Math.max(...values, min + 1)
    const range = max - min || 1

    const points = values.map((val, idx) => {
      const x = padding + (idx / (values.length - 1 || 1)) * (width - 2 * padding)
      const y = height - padding - ((val - min) / range) * (height - 2 * padding)
      return { x, y, val }
    })

    const pathD = points.reduce(
      (acc, pt, idx) => `${acc} ${idx === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`,
      ''
    )

    const areaD = `${pathD} L ${points[points.length - 1].x.toFixed(1)} ${height} L ${points[0].x.toFixed(1)} ${height} Z`

    const lastVal = values[values.length - 1]
    const avgVal = (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1)
    const maxVal = Math.max(...values).toFixed(1)

    return (
      <div className="sparkline-wrapper">
        <div className="sparkline-stats">
          <div>
            <span className="stat-label">CURRENT</span>
            <span className="stat-val" style={{ color }}>{lastVal} {unit}</span>
          </div>
          <div>
            <span className="stat-label">24H AVERAGE</span>
            <span className="stat-val">{avgVal} {unit}</span>
          </div>
          <div>
            <span className="stat-label">24H PEAK</span>
            <span className="stat-val">{maxVal} {unit}</span>
          </div>
        </div>

        <svg viewBox={`0 0 ${width} ${height}`} className="sparkline-svg">
          <defs>
            <linearGradient id={`grad-${color.replace(/[^a-zA-Z0-9]/g, '')}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.35" />
              <stop offset="100%" stopColor={color} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid reference lines */}
          <line x1={padding} y1={padding} x2={width - padding} y2={padding} stroke="var(--border-subtle, #334155)" strokeDasharray="3 3" opacity="0.4" />
          <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} stroke="var(--border-subtle, #334155)" strokeDasharray="3 3" opacity="0.4" />
          <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border-subtle, #334155)" strokeDasharray="3 3" opacity="0.4" />

          {/* Area Fill */}
          <path d={areaD} fill={`url(#grad-${color.replace(/[^a-zA-Z0-9]/g, '')})`} />

          {/* Line Stroke */}
          <path d={pathD} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

          {/* Data Points */}
          {points.map((pt, idx) => (
            <circle
              key={idx}
              cx={pt.x}
              cy={pt.y}
              r={idx === points.length - 1 ? 4 : 2}
              fill={idx === points.length - 1 ? '#ffffff' : color}
              stroke={color}
              strokeWidth={idx === points.length - 1 ? 2 : 1}
            />
          ))}
        </svg>

        <div className="sparkline-timeline">
          <span>24h ago</span>
          <span>12h ago</span>
          <span>Now</span>
        </div>
      </div>
    )
  }

  return (
    <div className="telemetry-modal-backdrop" onClick={onClose}>
      <div className="telemetry-modal card card-glow" onClick={(e) => e.stopPropagation()}>
        <div className="telemetry-modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Activity size={20} color="#38bdf8" />
            <h3 style={{ margin: 0, fontSize: '1.05rem', color: 'var(--text-primary)' }}>
              24-Hour Telemetry & Hardware Trends
            </h3>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button onClick={fetchData} className="btn btn-ghost" title="Refresh data">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
            <button onClick={onClose} className="btn btn-ghost" title="Close">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="telemetry-tabs">
          <button
            onClick={() => setActiveTab('gpu')}
            className={`telemetry-tab-btn ${activeTab === 'gpu' ? 'active' : ''}`}
          >
            <Thermometer size={14} /> GPU Temp
          </button>
          <button
            onClick={() => setActiveTab('vram')}
            className={`telemetry-tab-btn ${activeTab === 'vram' ? 'active' : ''}`}
          >
            <Database size={14} /> VRAM Load
          </button>
          <button
            onClick={() => setActiveTab('ram')}
            className={`telemetry-tab-btn ${activeTab === 'ram' ? 'active' : ''}`}
          >
            <Cpu size={14} /> System RAM
          </button>
          <button
            onClick={() => setActiveTab('tokens')}
            className={`telemetry-tab-btn ${activeTab === 'tokens' ? 'active' : ''}`}
          >
            <Sparkles size={14} /> Tokens Processed
          </button>
        </div>

        <div className="telemetry-chart-container">
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)' }}>
              Loading telemetry history...
            </div>
          ) : (
            <>
              {activeTab === 'gpu' &&
                renderSparkline(
                  data.map((d) => d.gpu_temp_avg || 45),
                  '#10b981',
                  '°C',
                  30
                )}
              {activeTab === 'vram' &&
                renderSparkline(
                  data.map((d) => Math.round(d.vram_avg_mb || 0)),
                  '#38bdf8',
                  'MB',
                  0
                )}
              {activeTab === 'ram' &&
                renderSparkline(
                  data.map((d) => Math.round(d.ram_avg_mb || 0)),
                  '#a855f7',
                  'MB',
                  0
                )}
              {activeTab === 'tokens' &&
                renderSparkline(
                  data.map((d) => (d.tokens_in_total || 0) + (d.tokens_out_total || 0)),
                  '#f59e0b',
                  'tokens',
                  0
                )}
            </>
          )}
        </div>

        <div className="telemetry-modal-footer">
          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <TrendingUp size={12} /> Auto-aggregated by CUA-Sentinel Hardware Watchdog
          </span>
          <button onClick={onClose} className="btn btn-ghost" style={{ fontSize: '0.8rem' }}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
