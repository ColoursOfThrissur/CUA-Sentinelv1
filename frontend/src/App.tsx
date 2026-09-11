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

function AppRoutes() {
  useWebSocket()
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
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
