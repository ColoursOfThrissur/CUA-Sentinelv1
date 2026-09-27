import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sentinel_api_token')
  if (token) config.headers['x-sentinel-token'] = token
  return config
})

export const tasksApi = {
  list: (status?: string) => api.get('/tasks/', { params: { status } }),
  get: (id: string) => api.get(`/tasks/${id}`),
  create: (data: object) => api.post('/tasks/', data),
  cancel: (id: string) => api.post(`/tasks/${id}/cancel`),
  deleteTask: (id: string) => api.delete(`/tasks/${id}`),
  clearChatHistory: () => api.delete('/tasks/chat-history'),
  deleteChatHistoryTask: (id: string) => api.delete(`/tasks/chat-history/${id}`),
  getReport: (id: string) => api.get<string>(`/tasks/${id}/report`, { responseType: 'text' }),
}

export const chatApi = {
  send: (prompt: string, systemPrompt?: string, useWeb = false, history?: Array<{ role: string; content: string }>, targetApp?: string) =>
    api.post('/chat/', { prompt, system_prompt: systemPrompt, use_web: useWeb, history, target_app: targetApp }),
  approveSpec: (buildId: string) =>
    api.post('/chat/approve-spec', { build_id: buildId }),
}

export const modelsApi = {
  list: () => api.get('/models/'),
  getActive: () => api.get('/models/active'),
  enable: (id: string) => api.post(`/models/${id}/enable`),
  disable: (id: string) => api.post(`/models/${id}/disable`),
}

export const telemetryApi = {
  hardware: () => api.get('/telemetry/hardware'),
  history: (hours?: number) => api.get('/telemetry/history', { params: { hours } }),
}

export interface HealthReadyResponse {
  status: 'ready' | 'not_ready'
  config: 'ok' | 'error'
  databases: {
    operational: string
    audit: string
    knowledge: string
  }
  model_runtime: 'reachable' | 'unreachable' | 'unknown'
  version: string
}

export const healthApi = {
  getReady: () => api.get<HealthReadyResponse>('/health/ready'),
}

export const hitlApi = {
  pending: () => api.get('/hitl/pending'),
  resolve: (id: string, approved: boolean) =>
    api.post(`/hitl/${id}/resolve`, { approved, resolved_by: 'user' }),
  resolveAll: (approved: boolean, approvalIds?: string[]) =>
    api.post<{ resolved_count: number; approved: boolean; remaining: number }>('/hitl/resolve-all', {
      approved,
      approval_ids: approvalIds || [],
    }),
}

export const settingsApi = {
  getPreferences: () => api.get('/settings/preferences'),
  updatePreference: (key: string, value: unknown) =>
    api.put(`/settings/preferences/${key}`, { value }),
  getSchedules: () => api.get('/settings/schedules'),
  toggleSchedule: (id: string) => api.post(`/settings/schedules/${id}/toggle`),
  getSystemState: () => api.get('/settings/system'),
  setSafeMode: (enable: boolean) => api.post('/settings/system/safe-mode', { enable }),
  emergencyStop: () => api.post('/settings/system/emergency-stop'),
  resetEmergencyStop: () => api.post('/settings/system/emergency-stop/reset'),
}

export interface ImprovementProposal {
  proposal_id: string
  project_id: string
  project_name?: string
  title: string
  rationale: string
  suggested_changes?: string
  affected_files?: string[]
  risk_level?: 'LOW' | 'MEDIUM' | 'HIGH'
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'APPLIED'
  created_at: string
  reviewed_at?: string
}

export const improvementsApi = {
  list: (status?: string) => api.get<ImprovementProposal[]>('/improvements', { params: status ? { status } : {} }),
  approve: (proposalId: string) => api.post<{ status: string; proposal_id: string; enqueued_task_id?: string }>(`/improvements/${proposalId}/approve`),
  reject: (proposalId: string) => api.post<{ status: string; proposal_id: string }>(`/improvements/${proposalId}/reject`),
}

export const financeApi = {
  getPortfolio: () => api.get('/finance/portfolio'),
  upsertAsset: (data: object) => api.post('/finance/portfolio', data),
  deleteAsset: (symbol: string) => api.delete(`/finance/portfolio/${symbol}`),
  clearPortfolio: () => api.delete('/finance/portfolio/clear-all'),
  getQuote: (symbol: string) => api.get(`/finance/quote/${symbol}`),
  evaluateAlerts: () => api.post('/finance/evaluate-alerts'),
  importCsv: (csvText: string) => api.post('/finance/portfolio/import-csv', { csv_text: csvText }),
  importFile: (formData: FormData) => api.post('/finance/portfolio/import-file', formData),
}

export const linksApi = {
  list: (search?: string) => api.get('/links/', { params: { search } }),
  add: (url: string, title?: string) => api.post('/links/', { url, title }),
  crawl: (linkId: string) => api.post(`/links/${linkId}/crawl`),
}

export const notificationsApi = {
  getSettings: () => api.get('/notifications/settings'),
  updateSettings: (data: object) => api.post('/notifications/settings', data),
  sendTest: (data: object) => api.post('/notifications/test', data),
  testDiscordBot: () => api.post('/notifications/test-discord-bot'),
  testGmailSync: () => api.post('/notifications/test-gmail-sync'),
  testEmail: () => api.post('/notifications/test-email'),
  getVapidPublicKey: () => api.get<{ public_key: string }>('/notifications/vapid-public-key'),
  pushSubscribe: (subscription: object) => api.post('/notifications/push-subscribe', subscription),
  pushTest: (data?: object) => api.post('/notifications/push-test', data || {}),
}

export const schedulerApi = {
  listJobs: () => api.get('/scheduler/jobs'),
  createJob: (data: { name: string; time_offset: string; prompt: string; workflow_type?: string }) => api.post('/scheduler/jobs', data),
  cancelJob: (jobId: string) => api.delete(`/scheduler/jobs/${jobId}`),
}

export const digestsApi = {
  getLatest: () => api.get('/digests/latest'),
  generate: () => api.post('/digests/generate'),
  listHistory: (limit?: number) => api.get('/digests/history', { params: { limit } }),
}

export const gmailTriageApi = {
  getFeed: (category?: string) => api.get('/gmail-triage/feed', { params: { category } }),
  scanInbox: () => api.post('/gmail-triage/scan'),
}

export const codeRefactorApi = {
  scan: (projectPath: string) => api.post('/code-refactor/scan', { project_path: projectPath }),
  solutionContext: (projectPath: string) => api.post('/code-refactor/solution-context', { project_path: projectPath }),
  dualDiagnostics: (projectPath: string) => api.post('/code-refactor/dual-diagnostics', { project_path: projectPath }),
  autoHealTrigger: (projectPath: string, errorContext: string, source?: string) =>
    api.post('/code-refactor/auto-heal-trigger', { project_path: projectPath, error_context: errorContext, source }),
  start: (projectPath: string, goalInstruction?: string, approvedFeatures?: string[], blueprintContent?: string, blueprintFilename?: string) =>
    api.post('/code-refactor/start', { project_path: projectPath, goal_instruction: goalInstruction, approved_features: approvedFeatures, blueprint_content: blueprintContent, blueprint_filename: blueprintFilename }),
  createScratch: (data: { project_name: string; target_path: string; tech_stack: string; ui_style?: string; features?: string[]; description?: string; blueprint_content?: string; blueprint_filename?: string }) =>
    api.post('/code-refactor/create-scratch', data),
  launchPreview: (projectPath: string) => api.post('/code-refactor/launch-preview', { project_path: projectPath }),
  rollback: (projectPath: string, taskId: string) => api.post('/code-refactor/rollback', { project_path: projectPath, task_id: taskId }),
  installDeps: (projectPath: string) => api.post('/code-refactor/install-dependencies', { project_path: projectPath }),
  diagnoseFile: (projectPath: string, filePath: string) => api.post('/code-refactor/diagnose-file', { project_path: projectPath, file_path: filePath }),
  validateAlignment: (projectPath: string, goalInstruction?: string, autoRemediate?: boolean) =>
    api.post('/code-refactor/validate-alignment', { project_path: projectPath, goal_instruction: goalInstruction, auto_remediate: autoRemediate }),
  remediateAlignment: (projectPath: string, goalInstruction?: string) =>
    api.post('/code-refactor/auto-remediate-alignment', { project_path: projectPath, goal_instruction: goalInstruction }),
  runHealthDaemonNow: (projectPath: string) => api.post('/code-refactor/health-daemon/run-now', { project_path: projectPath }),
  getHealthDaemonLogs: (projectPath?: string) => api.get('/code-refactor/health-daemon/logs', { params: projectPath ? { project_path: projectPath } : {} }),
  clearHealthDaemonCooloff: (projectPath: string) => api.post('/code-refactor/health-daemon/clear-cooloff', { project_path: projectPath }),
}

export const dependencyPlansApi = {
  list: (status?: string) => api.get<any[]>('/dependency-plans', { params: status ? { status } : {} }),
  get: (planId: string) => api.get<any>(`/dependency-plans/${planId}`),
  approve: (planId: string, planHash: string, allowUnpinned: boolean = false) =>
    api.post(`/dependency-plans/${planId}/approve`, { plan_hash: planHash, allow_unpinned: allowUnpinned }),
  execute: (planId: string, planHash: string) =>
    api.post(`/dependency-plans/${planId}/execute`, { plan_hash: planHash }),
  reject: (planId: string, reason: string = '') =>
    api.post(`/dependency-plans/${planId}/reject`, { reason }),
  rollback: (planId: string) =>
    api.post(`/dependency-plans/${planId}/rollback`),
}

export const projectsApi = {
  list: () => api.get('/projects/list'),
  register: (data: { project_name: string; target_path: string; tech_stack: string; ui_style?: string; blueprint_filename?: string }) =>
    api.post('/projects/register', data),
  get: (projectId: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.get(`/projects/${projectId}`)
  },
  repairEnv: (projectId: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.post(`/projects/${projectId}/repair-env`)
  },
  startServer: (projectId: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.post(`/projects/${projectId}/start-server`)
  },
  stopServer: (projectId: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.post(`/projects/${projectId}/stop-server`)
  },
  getLogs: (projectId: string, tail = 100) => {
    if (!projectId || !projectId.trim()) return Promise.resolve({ data: { logs: [] } })
    return api.get(`/projects/${projectId}/logs`, { params: { tail } })
  },
  exportZip: (projectId: string, exportDir?: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.post(`/projects/${projectId}/export-zip`, { export_dir: exportDir })
  },
  fulfillSpec: (projectId: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.post(`/projects/${projectId}/fulfill-spec`)
  },
  deleteProject: (projectId: string, purgeFiles = false) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.delete(`/projects/${projectId}`, { params: { purge_files: purgeFiles } })
  },
  getTree: (projectId: string) => {
    if (!projectId || !projectId.trim()) return Promise.resolve({ data: { tree: [] } })
    return api.get(`/projects/${projectId}/tree`)
  },
  readFile: (projectId: string, relativePath: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.get(`/projects/${projectId}/file`, { params: { relative_path: relativePath } })
  },
  writeFile: (projectId: string, relativePath: string, content: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.post(`/projects/${projectId}/file`, { relative_path: relativePath, content })
  },
  sendPrompt: (projectId: string, prompt: string, targetFile?: string) => {
    if (!projectId || !projectId.trim()) return Promise.reject(new Error('Invalid project ID'))
    return api.post(`/projects/${projectId}/prompt`, { prompt, target_file: targetFile })
  },
}

export const researchApi = {
  start: (question: string, depth: 'quick' | 'deep' = 'deep') =>
    api.post('/research/start', { question, depth }),
  getReports: (limit = 20) =>
    api.get('/research/reports', { params: { limit } }),
  getReport: (taskId: string) =>
    api.get(`/research/reports/${taskId}`),
  getClaims: (domain?: string, search?: string, limit = 50) =>
    api.get('/research/claims', { params: { domain, search, limit } }),
}

export interface AppTool {
  name: string
  description: string
  input_schema?: Record<string, any>
}

export interface AppSecurity {
  default_side_effect?: 'read' | 'write' | 'act'
  default_risk_level?: 'L0' | 'L1' | 'L2' | 'L3'
  returns_untrusted?: boolean
}

export interface AppInfo {
  app_id: string
  display_name: string
  icon?: string
  transport: 'stdio' | 'http'
  command?: string
  args?: string[]
  url?: string
  env?: Record<string, string>
  enabled: boolean
  status: 'connected' | 'disconnected' | 'connecting' | 'error'
  description?: string
  error_message?: string
  tools_count: number
  tools: AppTool[]
  security?: AppSecurity
}

export const appsApi = {
  list: () => api.get<{ apps: AppInfo[] }>('/apps/'),
  get: (appId: string) => api.get<AppInfo>(`/apps/${appId}`),
  connect: (appId: string) => api.post(`/apps/${appId}/connect`),
  disconnect: (appId: string) => api.post(`/apps/${appId}/disconnect`),
  test: (appId: string) => api.post<{ ok: boolean; latency_ms: number; tools_count: number; tool_names: string[]; error?: string }>(`/apps/${appId}/test`),
  update: (appId: string, updates: Partial<AppInfo>) => api.put(`/apps/${appId}`, updates),
  add: (newApp: Partial<AppInfo> & { app_id: string; display_name: string; transport: string }) => api.post('/apps/', newApp),
  remove: (appId: string) => api.delete(`/apps/${appId}`),
}


