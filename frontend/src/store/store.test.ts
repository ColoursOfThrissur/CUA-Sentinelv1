import { describe, it, expect, beforeEach } from 'vitest'
import { useSentinelStore } from './index'

describe('useSentinelStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useSentinelStore.setState({
      telemetry: null,
      tasks: [],
      hitlPending: [],
      systemState: null,
      wsConnected: false,
      agentTraces: [],
    })
  })

  it('updates telemetry snapshot', () => {
    const sampleTelemetry = {
      ram_used_mb: 4096,
      ram_total_mb: 16384,
      ram_percent: 25.0,
      cpu_percent: 12.5,
      gpu_temp_c: 48.0,
      vram_used_mb: 4200,
      vram_total_mb: 12288,
      timestamp: new Date().toISOString(),
    }

    useSentinelStore.getState().setTelemetry(sampleTelemetry)
    expect(useSentinelStore.getState().telemetry).toEqual(sampleTelemetry)
  })

  it('upserts tasks correctly: inserts new task', () => {
    const task = {
      task_id: 'task-101',
      workflow_type: 'ENDPOINT',
      title: 'Direct Chat',
      status: 'QUEUED',
      priority: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    useSentinelStore.getState().upsertTask(task)
    const tasks = useSentinelStore.getState().tasks
    expect(tasks).toHaveLength(1)
    expect(tasks[0].task_id).toBe('task-101')
  })

  it('upserts tasks correctly: updates existing task by task_id', () => {
    const taskInitial = {
      task_id: 'task-101',
      workflow_type: 'ENDPOINT',
      title: 'Direct Chat',
      status: 'QUEUED',
      priority: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    useSentinelStore.getState().upsertTask(taskInitial)

    const taskUpdated = {
      ...taskInitial,
      status: 'COMPLETED',
      result_payload: { answer: 'Hello world' },
    }

    useSentinelStore.getState().upsertTask(taskUpdated)
    const tasks = useSentinelStore.getState().tasks
    expect(tasks).toHaveLength(1)
    expect(tasks[0].status).toBe('COMPLETED')
  })

  it('caps real-time agent traces ring buffer at 50 items', () => {
    for (let i = 0; i < 60; i++) {
      useSentinelStore.getState().addAgentTrace({
        task_id: `task-${i}`,
        step_name: `Step ${i}`,
        tool_name: 'test_tool',
        status: 'SUCCESS',
        details: { index: i },
        timestamp: new Date().toISOString(),
      })
    }

    const traces = useSentinelStore.getState().agentTraces
    expect(traces).toHaveLength(50)
    // Most recent item should be at the front
    expect(traces[0].step_name).toBe('Step 59')
  })

  it('updates HITL pending approvals array', () => {
    const hitlItems = [
      {
        approval_id: 'appr-1',
        task_id: 'task-1',
        risk_level: 3,
        action_description: 'Deploy to remote',
        action_payload: '{}',
        expires_at: new Date().toISOString(),
      },
    ]

    useSentinelStore.getState().setHitlPending(hitlItems)
    expect(useSentinelStore.getState().hitlPending).toEqual(hitlItems)
  })
})
