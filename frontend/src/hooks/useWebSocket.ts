import { useEffect, useRef } from 'react'
import { useSentinelStore } from '../store'

const WS_BASE_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`
const RECONNECT_DELAY = 3000

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null)
  const { setTelemetry, upsertTask, setHitlPending, setWsConnected, addAgentTrace } = useSentinelStore()

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      const token = localStorage.getItem('sentinel_api_token')
      const url = token ? `${WS_BASE_URL}?token=${encodeURIComponent(token)}` : WS_BASE_URL
      ws.current = new WebSocket(url)

      ws.current.onopen = () => {
        setWsConnected(true)
        const ping = setInterval(() => {
          if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send('ping')
          } else {
            clearInterval(ping)
          }
        }, 20000)
      }

      ws.current.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'telemetry') setTelemetry(msg)
          if (msg.type === 'task_update') upsertTask(msg)
          if (msg.type === 'hitl_update') setHitlPending(Array.isArray(msg.pending) ? msg.pending : [])
          if (msg.type === 'AGENT_TRACE') addAgentTrace(msg)
        } catch {
          // ignore malformed messages
        }
      }

      ws.current.onclose = () => {
        setWsConnected(false)
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY)
      }

      ws.current.onerror = () => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
          ws.current.close()
        }
      }
    }

    connect()
    return () => {
      clearTimeout(reconnectTimer)
      ws.current?.close()
    }
  }, [])
}
