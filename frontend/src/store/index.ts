import { create } from 'zustand'

interface TelemetrySnapshot {
  ram_used_mb: number
  ram_total_mb: number
  ram_percent: number
  cpu_percent: number
  gpu_temp_c: number | null
  vram_used_mb: number | null
  vram_total_mb: number | null
  timestamp: string
}

interface Task {
  task_id: string
  workflow_type: string
  title: string
  status: string
  priority: number
  created_at: string
  updated_at: string
  result_payload?: Record<string, unknown>
  error_message?: string
}

interface HITLPending {
  approval_id: string
  task_id: string
  risk_level: number
  action_description: string
  action_payload: string
  expires_at: string
}

interface SystemState {
  safe_mode: string
  emergency_stop: string
}

export interface AgentTrace {
  task_id: string
  step_name: string
  tool_name: string
  status: string
  details: Record<string, unknown>
  timestamp: string
  span_id?: string
}

interface SentinelStore {
  telemetry: TelemetrySnapshot | null
  tasks: Task[]
  hitlPending: HITLPending[]
  systemState: SystemState | null
  wsConnected: boolean
  agentTraces: AgentTrace[]
  setTelemetry: (t: TelemetrySnapshot) => void
  setTasks: (tasks: Task[]) => void
  upsertTask: (task: Task) => void
  setHitlPending: (items: HITLPending[]) => void
  setSystemState: (s: SystemState) => void
  setWsConnected: (v: boolean) => void
  addAgentTrace: (trace: AgentTrace) => void
}

export const useSentinelStore = create<SentinelStore>((set) => ({
  telemetry: null,
  tasks: [],
  hitlPending: [],
  systemState: null,
  wsConnected: false,
  agentTraces: [],
  setTelemetry: (t) => set({ telemetry: t }),
  setTasks: (tasks) => set({ tasks: Array.isArray(tasks) ? tasks : [] }),
  upsertTask: (task) =>
    set((state) => {
      const idx = state.tasks.findIndex((t) => t.task_id === task.task_id)
      if (idx >= 0) {
        const updated = [...state.tasks]
        updated[idx] = task
        return { tasks: updated }
      }
      return { tasks: [task, ...state.tasks] }
    }),
  setHitlPending: (items) => set({ hitlPending: Array.isArray(items) ? items : [] }),
  setSystemState: (s) => set({ systemState: s }),
  setWsConnected: (v) => set({ wsConnected: v }),
  addAgentTrace: (trace) =>
    set((state) => {
      // Deduplicate by step_name + timestamp (within 1 second)
      const isDupe = state.agentTraces.some(
        (t) =>
          t.step_name === trace.step_name &&
          t.task_id === trace.task_id &&
          Math.abs(new Date(t.timestamp).getTime() - new Date(trace.timestamp).getTime()) < 1000
      )
      if (isDupe) return state
      return { agentTraces: [trace, ...state.agentTraces].slice(0, 50) }
    }),
}))
