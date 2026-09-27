import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { BrainCircuit, Lock } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import TaskDetail from './pages/TaskDetail'
import Settings from './pages/Settings'
import { useWebSocket } from './hooks/useWebSocket'
import './App.css'

const TOKEN_KEY = 'sentinel_api_token'

async function checkAuth(token: string): Promise<boolean> {
  try {
    const res = await fetch('/api/settings/system', { headers: { 'x-sentinel-token': token } })
    return res.status !== 401
  } catch {
    return true
  }
}

function TokenGate({ onUnlock }: { onUnlock: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState(false)
  const [busy,  setBusy]  = useState(false)

  const submit = async () => {
    const t = value.trim()
    if (!t) return
    setBusy(true); setError(false)
    const ok = await checkAuth(t)
    if (ok) { localStorage.setItem(TOKEN_KEY, t); onUnlock() }
    else    { setError(true); setBusy(false) }
  }

  return (
    <div className="token-gate">
      <div className="card card-glow token-gate-card">
        <div className="token-gate-logo"><BrainCircuit size={24} color="#fff" /></div>
        <div>
          <p className="token-gate-title">CUA-Sentinel</p>
          <p className="token-gate-sub">Enter your access token to continue</p>
        </div>
        <div className="token-gate-form">
          <div className="token-input-wrap">
            <Lock size={14} className="token-input-icon" />
            <input
              type="password"
              className="input token-input"
              placeholder="Access token"
              value={value}
              onChange={(e) => { setValue(e.target.value); setError(false) }}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
              autoFocus
              autoComplete="current-password"
            />
          </div>
          {error && <p className="token-error">Invalid token — try again</p>}
          <button onClick={submit} disabled={busy || !value.trim()} className="btn btn-primary token-submit">
            {busy ? 'Checking...' : 'Unlock'}
          </button>
        </div>
      </div>
    </div>
  )
}

import { useSentinelStore } from './store'
import { settingsApi } from './api'

function GlobalEmergencyStopBanner() {
  const { systemState } = useSentinelStore()
  const isEmergencyStop = systemState?.emergency_stop === 'true'

  if (!isEmergencyStop) return null

  const handleResume = async () => {
    try {
      await settingsApi.resetEmergencyStop()
      useSentinelStore.getState().setSystemState({ ...systemState, emergency_stop: 'false' })
    } catch (err) {
      console.error('Failed to reset emergency stop:', err)
    }
  }

  return (
    <div style={{
      background: 'linear-gradient(90deg, #991b1b, #dc2626)',
      color: '#fff',
      padding: '8px 16px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      fontSize: '0.85rem',
      fontWeight: 600,
      zIndex: 9999,
      boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: '1.1rem' }}>🚨</span>
        <span>EMERGENCY STOP IS ACTIVE — All autonomous agent tool calls and executions are blocked.</span>
      </div>
      <button
        onClick={handleResume}
        style={{
          background: '#10b981',
          color: '#fff',
          border: 'none',
          borderRadius: 4,
          padding: '5px 14px',
          fontWeight: 700,
          fontSize: '0.8rem',
          cursor: 'pointer',
        }}
      >
        Resume Normal Operations
      </button>
    </div>
  )
}

function AppRoutes() {
  useWebSocket()
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <GlobalEmergencyStopBanner />
      <Routes>
        <Route path="/"              element={<Dashboard />} />
        <Route path="/tasks/:taskId" element={<TaskDetail />} />
        <Route path="/settings"      element={<Settings />} />
      </Routes>
    </BrowserRouter>
  )
}

export default function App() {
  const [unlocked, setUnlocked] = useState<boolean | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY) ?? ''
    checkAuth(stored).then((ok) => setUnlocked(ok ? true : false))
  }, [])

  if (unlocked === null) return (
    <div className="app-loading">
      <span className="loading-dot" /><span className="loading-dot" /><span className="loading-dot" />
    </div>
  )

  if (!unlocked) return <TokenGate onUnlock={() => setUnlocked(true)} />
  return <AppRoutes />
}
