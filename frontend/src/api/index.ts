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
}

export const chatApi = {
  send: (prompt: string, systemPrompt?: string, useWeb = false, history?: Array<{ role: string; content: string }>) =>
    api.post('/chat/', { prompt, system_prompt: systemPrompt, use_web: useWeb, history }),
}

export const modelsApi = {
  list: () => api.get('/models/'),
  enable: (id: string) => api.post(`/models/${id}/enable`),
  disable: (id: string) => api.post(`/models/${id}/disable`),
}

export const telemetryApi = {
  hardware: () => api.get('/telemetry/hardware'),
  history: (hours?: number) => api.get('/telemetry/history', { params: { hours } }),
}

export const hitlApi = {
  pending: () => api.get('/hitl/pending'),
  resolve: (id: string, approved: boolean) =>
    api.post(`/hitl/${id}/resolve`, { approved, resolved_by: 'user' }),
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
  start: (projectPath: string, goalInstruction?: string, approvedFeatures?: string[], blueprintContent?: string, blueprintFilename?: string) =>
    api.post('/code-refactor/start', { project_path: projectPath, goal_instruction: goalInstruction, approved_features: approvedFeatures, blueprint_content: blueprintContent, blueprint_filename: blueprintFilename }),
  createScratch: (data: { project_name: string; target_path: string; tech_stack: string; ui_style?: string; features?: string[]; description?: string; blueprint_content?: string; blueprint_filename?: string }) =>
    api.post('/code-refactor/create-scratch', data),
  launchPreview: (projectPath: string) => api.post('/code-refactor/launch-preview', { project_path: projectPath }),
  rollback: (projectPath: string, taskId: string) => api.post('/code-refactor/rollback', { project_path: projectPath, task_id: taskId }),
  installDeps: (projectPath: string) => api.post('/code-refactor/install-dependencies', { project_path: projectPath }),
}

export const projectsApi = {
  list: () => api.get('/projects/list'),
  register: (data: { project_name: string; target_path: string; tech_stack: string; ui_style?: string; blueprint_filename?: string }) =>
    api.post('/projects/register', data),
  get: (projectId: string) => api.get(`/projects/${projectId}`),
  startServer: (projectId: string) => api.post(`/projects/${projectId}/start-server`),
  stopServer: (projectId: string) => api.post(`/projects/${projectId}/stop-server`),
  getLogs: (projectId: string, tail = 100) => api.get(`/projects/${projectId}/logs`, { params: { tail } }),
  exportZip: (projectId: string, exportDir?: string) => api.post(`/projects/${projectId}/export-zip`, { export_dir: exportDir }),
  fulfillSpec: (projectId: string) => api.post(`/projects/${projectId}/fulfill-spec`),
  deleteProject: (projectId: string, purgeFiles = false) => api.delete(`/projects/${projectId}`, { params: { purge_files: purgeFiles } }),
  getTree: (projectId: string) => api.get(`/projects/${projectId}/tree`),
  readFile: (projectId: string, relativePath: string) => api.get(`/projects/${projectId}/file`, { params: { relative_path: relativePath } }),
  writeFile: (projectId: string, relativePath: string, content: string) => api.post(`/projects/${projectId}/file`, { relative_path: relativePath, content }),
  sendPrompt: (projectId: string, prompt: string, targetFile?: string) => api.post(`/projects/${projectId}/prompt`, { prompt, target_file: targetFile }),
}

