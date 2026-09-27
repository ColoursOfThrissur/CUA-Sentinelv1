import { describe, it, expect } from 'vitest'
import {
  tasksApi,
  chatApi,
  modelsApi,
  telemetryApi,
  hitlApi,
  settingsApi,
  financeApi,
  linksApi,
  projectsApi,
  researchApi,
  appsApi,
  healthApi,
  improvementsApi,
} from './index'

describe('API Client Layer', () => {
  it('exports all expected API modules', () => {
    expect(tasksApi).toBeDefined()
    expect(typeof tasksApi.list).toBe('function')
    expect(typeof tasksApi.create).toBe('function')
    expect(typeof tasksApi.cancel).toBe('function')

    expect(chatApi).toBeDefined()
    expect(typeof chatApi.send).toBe('function')

    expect(modelsApi).toBeDefined()
    expect(typeof modelsApi.list).toBe('function')
    expect(typeof modelsApi.getActive).toBe('function')

    expect(telemetryApi).toBeDefined()
    expect(typeof telemetryApi.hardware).toBe('function')

    expect(hitlApi).toBeDefined()
    expect(typeof hitlApi.pending).toBe('function')
    expect(typeof hitlApi.resolve).toBe('function')

    expect(settingsApi).toBeDefined()
    expect(typeof settingsApi.getSystemState).toBe('function')
    expect(typeof settingsApi.setSafeMode).toBe('function')

    expect(financeApi).toBeDefined()
    expect(typeof financeApi.getPortfolio).toBe('function')

    expect(linksApi).toBeDefined()
    expect(typeof linksApi.list).toBe('function')

    expect(projectsApi).toBeDefined()
    expect(typeof projectsApi.list).toBe('function')

    expect(researchApi).toBeDefined()
    expect(typeof researchApi.start).toBe('function')
    expect(typeof researchApi.getReports).toBe('function')
    expect(typeof researchApi.getReport).toBe('function')
    expect(typeof researchApi.getClaims).toBe('function')

    expect(appsApi).toBeDefined()
    expect(typeof appsApi.list).toBe('function')
    expect(typeof appsApi.connect).toBe('function')
    expect(typeof appsApi.disconnect).toBe('function')

    expect(healthApi).toBeDefined()
    expect(typeof healthApi.getReady).toBe('function')

    expect(improvementsApi).toBeDefined()
    expect(typeof improvementsApi.list).toBe('function')
    expect(typeof improvementsApi.approve).toBe('function')
    expect(typeof improvementsApi.reject).toBe('function')
  })
})
