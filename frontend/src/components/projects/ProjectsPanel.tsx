import React, { useState, useEffect, useRef } from 'react'
import {
  FolderKanban,
  Play,
  Square,
  ExternalLink,
  Terminal,
  Download,
  Trash2,
  RefreshCw,
  Plus,
  Search,
  ShieldCheck,
  Activity,
  HardDrive,
  X,
  Maximize2,
  CheckCircle,
  AlertTriangle,
  Server,
  Zap,
  Code2
} from 'lucide-react'
import { projectsApi } from '../../api'
import CodeWorkspace from '../coding/CodeWorkspace'
import './ProjectsPanel.css'

export interface Project {
  project_id: string
  project_name: string
  target_path: string
  tech_stack: string
  ui_style: string
  blueprint_filename?: string
  created_at: string
  health_score: number
  security_score: number
  status: 'REGISTERED' | 'RUNNING' | 'STOPPED' | 'ERROR'
  active_port?: number
  active_pid?: number
  path_exists: boolean
  file_count: number
  disk_size_mb: number
}

export const ProjectsPanel: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState<string>('')
  
  // Modals and drawers state
  const [previewProject, setPreviewProject] = useState<Project | null>(null)
  const [workspaceProject, setWorkspaceProject] = useState<Project | null>(null)
  const [logProject, setLogProject] = useState<Project | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [isLogLoading, setIsLogLoading] = useState<boolean>(false)
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null)
  const [purgeFiles, setPurgeFiles] = useState<boolean>(false)
  const [showRegisterModal, setShowRegisterModal] = useState<boolean>(false)

  // Registration Form State
  const [regName, setRegName] = useState('')
  const [regPath, setRegPath] = useState('')
  const [regTech, setRegTech] = useState('FastAPI + React')
  const [regStyle, setRegStyle] = useState('Glassmorphism')

  // Log auto-scroll
  const logEndRef = useRef<HTMLDivElement>(null)

  const fetchProjects = async () => {
    try {
      setLoading(true)
      const res = await projectsApi.list()
      setProjects(res.data.projects || [])
      setError(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load projects.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProjects()
    const interval = setInterval(fetchProjects, 10000)
    return () => clearInterval(interval)
  }, [])

  // Poll logs if log drawer open
  useEffect(() => {
    if (!logProject) return
    const fetchLogs = async () => {
      try {
        setIsLogLoading(true)
        const res = await projectsApi.getLogs(logProject.project_id)
        setLogs(res.data.logs || [])
      } catch (err) {
        console.error('Failed to fetch logs', err)
      } finally {
        setIsLogLoading(false)
      }
    }
    fetchLogs()
    const logInterval = setInterval(fetchLogs, 3000)
    return () => clearInterval(logInterval)
  }, [logProject])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const handleStartServer = async (project: Project) => {
    try {
      const res = await projectsApi.startServer(project.project_id)
      if (res.data.success) {
        await fetchProjects()
        if (res.data.preview_url) {
          setPreviewProject({ ...project, active_port: res.data.port, status: 'RUNNING' })
        }
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to start server.')
    }
  }

  const handleStopServer = async (project: Project) => {
    try {
      await projectsApi.stopServer(project.project_id)
      await fetchProjects()
      if (previewProject?.project_id === project.project_id) {
        setPreviewProject(null)
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to stop server.')
    }
  }

  const handleFulfillSpec = async (project: Project) => {
    try {
      const res = await projectsApi.fulfillSpec(project.project_id)
      if (res.data.success) {
        alert(`🤖 Autonomous Local LLM Agent Task enqueued!\nTask ID: ${res.data.task_id}\nSentinel is reading ARCHITECTURE_SPEC.md to synthesize & fulfill full solution architecture. Watch live progress in the Task Queue!`)
        await fetchProjects()
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to trigger AI spec fulfillment.')
    }
  }

  const handleExportZip = async (project: Project) => {
    try {
      const res = await projectsApi.exportZip(project.project_id)
      if (res.data.success) {
        alert(`Project successfully exported to ZIP!\nPath: ${res.data.zip_path}\nSize: ${res.data.size_mb} MB`)
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to export ZIP archive.')
    }
  }

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return
    try {
      const res = await projectsApi.deleteProject(deleteTarget.project_id, purgeFiles)
      if (res.data.success) {
        setDeleteTarget(null)
        setPurgeFiles(false)
        await fetchProjects()
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to unregister/delete project.')
    }
  }

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!regName || !regPath) return
    try {
      const res = await projectsApi.register({
        project_name: regName,
        target_path: regPath,
        tech_stack: regTech,
        ui_style: regStyle
      })
      if (res.data.success) {
        setShowRegisterModal(false)
        setRegName('')
        setRegPath('')
        await fetchProjects()
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to register project.')
    }
  }

  const filteredProjects = projects.filter(
    (p) =>
      p.project_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.target_path.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.tech_stack.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="projects-hub-container">
      {/* Top Header Bar */}
      <div className="projects-header">
        <div className="projects-title-area">
          <h2>
            <FolderKanban className="icon-main" /> Solutions Registry & Live App Hub
          </h2>
          <p className="projects-subtitle">
            Persistent registry, 1-click dev server launcher, live iframe previews, log streaming, and zip packaging.
          </p>
        </div>

        <div className="projects-header-actions">
          <button className="btn-secondary" onClick={() => fetchProjects()} disabled={loading}>
            <RefreshCw className={loading ? 'spin' : ''} size={16} /> Refresh
          </button>
          <button className="btn-primary" onClick={() => setShowRegisterModal(true)}>
            <Plus size={16} /> Register Solution
          </button>
        </div>
      </div>

      {/* Search & Filter Bar */}
      <div className="projects-filter-bar">
        <div className="search-input-wrapper">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            placeholder="Search by project name, drive path, or tech stack..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="stats-badge-group">
          <span className="stat-pill">Total Solutions: {projects.length}</span>
          <span className="stat-pill running">
            Running: {projects.filter((p) => p.status === 'RUNNING').length}
          </span>
        </div>
      </div>

      {/* Main Content Grid */}
      {loading && projects.length === 0 ? (
        <div className="projects-loading-state">
          <RefreshCw className="spin" size={32} />
          <p>Loading registered solutions...</p>
        </div>
      ) : error ? (
        <div className="projects-error-banner">
          <AlertTriangle size={20} /> {error}
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="projects-empty-state">
          <Server size={48} />
          <h3>No Solutions Registered Yet</h3>
          <p>Scaffold a solution from scratch in the Code Refactor tab, or register an existing codebase path.</p>
          <button className="btn-primary" onClick={() => setShowRegisterModal(true)}>
            <Plus size={16} /> Register Solution Path
          </button>
        </div>
      ) : (
        <div className="projects-cards-grid">
          {filteredProjects.map((project) => {
            const isRunning = project.status === 'RUNNING'
            return (
              <div key={project.project_id} className={`project-card ${isRunning ? 'is-running' : ''}`}>
                {/* Card Top Header */}
                <div className="card-top-row">
                  <div className="card-title-block">
                    <h3>{project.project_name}</h3>
                    <span className="project-id">{project.project_id}</span>
                  </div>
                  <span className={`status-tag ${project.status.toLowerCase()}`}>
                    {isRunning ? (
                      <>
                        <span className="pulse-dot"></span> RUNNING ({project.active_port})
                      </>
                    ) : (
                      'STOPPED'
                    )}
                  </span>
                </div>

                {/* Path & Meta details */}
                <div className="card-path-box" title={project.target_path}>
                  <HardDrive size={14} />
                  <span className="path-text">{project.target_path}</span>
                </div>

                <div className="card-meta-chips">
                  <span className="tech-badge">{project.tech_stack}</span>
                  <span className="style-badge">{project.ui_style}</span>
                  {project.blueprint_filename && (
                    <span className="blueprint-badge" title={project.blueprint_filename}>
                      Blueprint Attached
                    </span>
                  )}
                </div>

                {/* Metrics Row */}
                <div className="card-metrics-grid">
                  <div className="metric-box">
                    <span className="metric-label">Health</span>
                    <span className={`metric-val ${project.health_score >= 85 ? 'good' : 'warn'}`}>
                      <Activity size={12} /> {project.health_score}/100
                    </span>
                  </div>
                  <div className="metric-box">
                    <span className="metric-label">Security</span>
                    <span className={`metric-val ${project.security_score >= 90 ? 'good' : 'warn'}`}>
                      <ShieldCheck size={12} /> {project.security_score}/100
                    </span>
                  </div>
                  <div className="metric-box">
                    <span className="metric-label">Files</span>
                    <span className="metric-val">{project.file_count}</span>
                  </div>
                  <div className="metric-box">
                    <span className="metric-label">Disk Size</span>
                    <span className="metric-val">{project.disk_size_mb} MB</span>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="card-actions-row">
                  {isRunning ? (
                    <button className="btn-stop" onClick={() => handleStopServer(project)}>
                      <Square size={14} /> Stop Server
                    </button>
                  ) : (
                    <button className="btn-start" onClick={() => handleStartServer(project)}>
                      <Play size={14} /> Run Server
                    </button>
                  )}

                  {isRunning && project.active_port && (
                    <button className="btn-preview" onClick={() => setPreviewProject(project)}>
                      <ExternalLink size={14} /> Live Preview
                    </button>
                  )}

                  <button className="btn-icon-action spark" title="Open Interactive AI Workbench" onClick={() => setWorkspaceProject(project)}>
                    <Code2 size={14} />
                  </button>

                  <button className="btn-icon-action spark" title="Fulfill Spec Blueprint with Local LLM Agent" onClick={() => handleFulfillSpec(project)}>
                    <Zap size={14} />
                  </button>

                  <button className="btn-icon-action" title="View Terminal Logs" onClick={() => setLogProject(project)}>
                    <Terminal size={14} />
                  </button>

                  <button className="btn-icon-action" title="Export ZIP Archive" onClick={() => handleExportZip(project)}>
                    <Download size={14} />
                  </button>

                  <button className="btn-icon-action danger" title="Unregister or Delete" onClick={() => setDeleteTarget(project)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Live App Preview Drawer / Modal */}
      {previewProject && previewProject.active_port && (
        <div className="preview-modal-overlay">
          <div className="preview-modal-content">
            <div className="preview-header-bar">
              <div className="preview-address-bar">
                <span className="address-protocol">http://</span>
                <span className="address-host">localhost:{previewProject.active_port}</span>
                <span className="preview-tag">LIVE APP PREVIEW</span>
              </div>
              <div className="preview-header-actions">
                <a
                  href={`http://localhost:${previewProject.active_port}`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-header-link"
                >
                  <Maximize2 size={14} /> Open in Tab
                </a>
                <button className="btn-close-preview" onClick={() => setPreviewProject(null)}>
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="preview-iframe-wrapper">
              <iframe
                src={`http://localhost:${previewProject.active_port}`}
                title={`Live Preview - ${previewProject.project_name}`}
                className="live-iframe"
              />
            </div>
          </div>
        </div>
      )}

      {/* Terminal Log Drawer */}
      {logProject && (
        <div className="log-drawer-overlay">
          <div className="log-drawer-content">
            <div className="log-drawer-header">
              <div className="log-drawer-title">
                <Terminal size={18} />
                <span>Terminal Output: <strong>{logProject.project_name}</strong></span>
              </div>
              <div className="log-header-right">
                {isLogLoading && <RefreshCw size={14} className="spin" />}
                <button className="btn-close-log" onClick={() => setLogProject(null)}>
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="log-terminal-body">
              {logs.length === 0 ? (
                <p className="no-logs">No terminal output logs captured yet.</p>
              ) : (
                logs.map((line, idx) => (
                  <div key={idx} className={`log-line ${line.includes('STDERR') ? 'stderr' : 'stdout'}`}>
                    {line}
                  </div>
                ))
              )}
              <div ref={logEndRef} />
            </div>
          </div>
        </div>
      )}

      {/* Register Solution Modal */}
      {showRegisterModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3><Plus size={18} /> Register Existing Solution</h3>
              <button className="btn-close-modal" onClick={() => setShowRegisterModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleRegisterSubmit} className="register-form">
              <div className="form-group">
                <label>Solution Name</label>
                <input
                  type="text"
                  placeholder="e.g. Sentinel Task Monitor"
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label>Target Drive Directory Path</label>
                <input
                  type="text"
                  placeholder="e.g. G:\Projects\SentinelTaskMonitor or D:\Apps\MyApp"
                  value={regPath}
                  onChange={(e) => setRegPath(e.target.value)}
                  required
                />
                <small className="form-help">Allowed storage drives: D:\, G:\, E:\, F:\ (OS C:\ drive protected)</small>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Tech Stack</label>
                  <select value={regTech} onChange={(e) => setRegTech(e.target.value)}>
                    <option value="FastAPI + React">FastAPI + React</option>
                    <option value="Python / Uvicorn">Python / Uvicorn</option>
                    <option value="Node.js / React">Node.js / React</option>
                    <option value="Flask / HTML">Flask / HTML</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>UI/UX Style</label>
                  <select value={regStyle} onChange={(e) => setRegStyle(e.target.value)}>
                    <option value="Glassmorphism">Glassmorphism</option>
                    <option value="Neumorphism">Neumorphism</option>
                    <option value="Flat Minimalist">Flat Minimalist</option>
                    <option value="Cyberpunk Dark">Cyberpunk Dark</option>
                  </select>
                </div>
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowRegisterModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  <CheckCircle size={16} /> Save & Register
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete / Unregister Modal */}
      {deleteTarget && (
        <div className="modal-backdrop">
          <div className="modal-card warning-card">
            <div className="modal-header">
              <h3><AlertTriangle size={18} className="warn-icon" /> Remove Solution</h3>
              <button className="btn-close-modal" onClick={() => setDeleteTarget(null)}>
                <X size={18} />
              </button>
            </div>
            <div className="delete-modal-body">
              <p>
                Are you sure you want to remove <strong>{deleteTarget.project_name}</strong>?
              </p>
              <div className="path-warning-box">
                <HardDrive size={14} /> <span>{deleteTarget.target_path}</span>
              </div>

              <div className="purge-option-group">
                <label className="purge-option">
                  <input
                    type="radio"
                    name="purge"
                    checked={!purgeFiles}
                    onChange={() => setPurgeFiles(false)}
                  />
                  <div>
                    <strong>Unregister Only (Recommended)</strong>
                    <p>Removes from Sentinel Hub database. Files on disk remain untouched.</p>
                  </div>
                </label>

                <label className="purge-option danger">
                  <input
                    type="radio"
                    name="purge"
                    checked={purgeFiles}
                    onChange={() => setPurgeFiles(true)}
                  />
                  <div>
                    <strong>Permanently Purge Files from Disk</strong>
                    <p>Deletes project files from storage drive (D:\, G:\). OS drive C:\ is protected.</p>
                  </div>
                </label>
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setDeleteTarget(null)}>
                Cancel
              </button>
              <button className={`btn-danger-confirm ${purgeFiles ? 'purge-all' : ''}`} onClick={handleDeleteConfirm}>
                <Trash2 size={16} /> {purgeFiles ? 'Permanently Purge Files' : 'Unregister Solution'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Render Interactive AI Workbench Overlay */}
      {workspaceProject && (
        <CodeWorkspace
          projectId={workspaceProject.project_id}
          projectName={workspaceProject.project_name}
          targetPath={workspaceProject.target_path}
          activePort={workspaceProject.active_port}
          onClose={() => setWorkspaceProject(null)}
        />
      )}
    </div>
  )
}

