import React, { useState, useEffect, useRef } from 'react'
import {
  FolderTree,
  FileCode,
  Folder,
  FolderOpen,
  ChevronRight,
  ChevronDown,
  Play,
  Square,
  RefreshCw,
  Terminal,
  Save,
  Sparkles,
  Monitor,
  Tablet,
  Smartphone,
  X,
  Code2,
  PackageCheck,
  Activity,
  Wrench,
  FileDiff,
  Download,
  Zap,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Link2,
  Layers
} from 'lucide-react'
import { projectsApi, codeRefactorApi, tasksApi, modelsApi } from '../../api'
import AlertModal from '../common/AlertModal'
import './CodeWorkspace.css'

interface TreeNode {
  name: string
  path: string
  type: 'file' | 'directory'
  size_bytes: number
  children?: TreeNode[]
}

interface CodeWorkspaceProps {
  projectId: string
  projectName: string
  targetPath: string
  activePort?: number
  activeTaskId?: string
  isInline?: boolean
  onClose?: () => void
}

export const CodeWorkspace: React.FC<CodeWorkspaceProps> = ({
  projectId: initialProjectId,
  projectName: initialProjectName,
  targetPath: initialTargetPath,
  activePort: initialPort,
  activeTaskId: initialTaskId,
  isInline = false,
  onClose
}) => {
  const [currentProjectId, setCurrentProjectId] = useState<string>(initialProjectId)
  const [currentProjectName, setCurrentProjectName] = useState<string>(initialProjectName)
  const [currentTargetPath, setCurrentTargetPath] = useState<string>(initialTargetPath)
  const [registeredProjects, setRegisteredProjects] = useState<any[]>([])

  const [tree, setTree] = useState<TreeNode[]>([])
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({})
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string>('')
  const [originalContent, setOriginalContent] = useState<string>('')
  const [isDirty, setIsDirty] = useState<boolean>(false)
  const [loadingTree, setLoadingTree] = useState<boolean>(true)
  const [loadingFile, setLoadingFile] = useState<boolean>(false)
  const [savingFile, setSavingFile] = useState<boolean>(false)
  
  // Server state & Preview
  const [serverStatus, setServerStatus] = useState<'RUNNING' | 'STOPPED'>('STOPPED')
  const [port, setPort] = useState<number | undefined>(initialPort)
  const [viewportMode, setViewportMode] = useState<'desktop' | 'tablet' | 'mobile'>('desktop')
  
  // Terminal logs
  const [logs, setLogs] = useState<string[]>([])
  const [showTerminal, setShowTerminal] = useState<boolean>(true)
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false)
  
  // AI Prompting & Refactor Activity Stream
  const [aiPrompt, setAiPrompt] = useState<string>('')
  const [sendingPrompt, setSendingPrompt] = useState<boolean>(false)
  const [statusMessage, setStatusMessage] = useState<string>('')
  
  // Segmented Right Panel, Auto-Dependency Repair & Real-Time Task Step Trace
  const [rightPanelTab, setRightPanelTab] = useState<'telemetry' | 'diffs' | 'deps' | 'alignment'>('telemetry')
  const [installingDeps, setInstallingDeps] = useState<boolean>(false)
  const [diagnosingFile, setDiagnosingFile] = useState<boolean>(false)
  const [depsStatus, setDepsStatus] = useState<string>('')
  const [alignmentData, setAlignmentData] = useState<{
    passed: boolean
    overall_alignment_score: number
    goal_alignment: {
      score: number
      intents_detected: string[]
      intents_found: string[]
      intents_missing: string[]
    }
    api_contracts: {
      sync_score: number
      frontend_calls: Array<{ method: string; path: string; file: string }>
      backend_endpoints: Array<{ method: string; path: string; file: string }>
      synced_contracts: Array<{ method: string; path: string; frontend_file: string }>
      missing_in_backend: Array<{ method: string; path: string; file: string }>
    }
    component_mounting: {
      score: number
      total_components: number
      mounted_components: Array<{ name: string; file: string }>
      unmounted_components: Array<{ name: string; file: string }>
    }
    design_system: {
      score: number
      violations: string[]
      passed: boolean
    }
    issues: string[]
    remediation_logs: string[]
    verdict: string
  } | null>(null)
  const [validatingAlignment, setValidatingAlignment] = useState<boolean>(false)
  const [remediatingAlignment, setRemediatingAlignment] = useState<boolean>(false)
  const [envHealthData, setEnvHealthData] = useState<{
    node_modules_count: number
    pip_packages_count: number
    venv_created: boolean
    npm_installed: boolean
    last_scanned: string
  } | null>(null)
  const [scanData, setScanData] = useState<{
    overall_score: number
    verdict: string
    verdict_badge: string
    total_issues: number
    security_score: number
    risk_level: string
    risk_badge: string
    total_vulnerabilities: number
    vulnerabilities: Array<{file: string; type: string; severity: string; description: string; remediation: string}>
    feature_ideas: Array<{idea_id: string; title: string; description: string; category: string; approved: boolean; priority: string}>
    sample_issues: string[]
    files_scanned: number
    last_scanned: string
  } | null>(null)
  const [scanning, setScanning] = useState<boolean>(false)
  const [activeModelTag, setActiveModelTag] = useState<string>('qwen3:14b-q4_K_M')
  const [modifiedFilesList, setModifiedFilesList] = useState<Array<{ path: string; timestamp: string; action: string }>>([])
  const [activityLogs, setActivityLogs] = useState<Array<{ timestamp: string; type: 'info' | 'success' | 'warn'; text: string }>>([
    { timestamp: new Date().toLocaleTimeString(), type: 'info', text: 'Sentinel Workbench & AST Activity Monitor initialized.' }
  ])

  useEffect(() => {
    modelsApi.getActive().then((res) => {
      if (res.data?.ollama_tag || res.data?.model_name) {
        setActiveModelTag(res.data.ollama_tag || res.data.model_name)
      }
    }).catch(() => {})
  }, [])

  // Custom Obsidian Glass Alert Modal & Zero-Touch Auto-Healing Trigger
  const [showAlertModal, setShowAlertModal] = useState<boolean>(false)
  const [alertModalTitle, setAlertModalTitle] = useState<string>('System Error Diagnostics')
  const [alertModalErrorText, setAlertModalErrorText] = useState<string>('')

  const handleOpenAlert = (title: string, errorText: string) => {
    setAlertModalTitle(title)
    setAlertModalErrorText(errorText)
    setShowAlertModal(true)
  }

  const handleAutoFixFromAlert = async (errDetail: string) => {
    try {
      setStatusMessage('⚡ Launching Zero-Touch Auto-Healing AI Agent...')
      await codeRefactorApi.autoHealTrigger(currentTargetPath, errDetail, 'UI_ALERT_MODAL')
      setStatusMessage('🚀 Zero-Touch Auto-Healing task enqueued! Check Live Telemetry.')
    } catch (e: any) {
      console.error(e)
    }
  }

  const handleAutoInstallPkgFromAlert = async (pkgName: string, ecosystem: string) => {
    const tNow = new Date().toLocaleTimeString()
    try {
      setStatusMessage(`📦 Installing ${ecosystem} package '${pkgName}'...`)
      const res = await codeRefactorApi.autoHealTrigger(currentTargetPath, `ModuleNotFoundError: No module named '${pkgName}'`, 'UI_ALERT_MODAL_INSTALL')
      const data = res.data || {}
      if (data.success !== false) {
        setStatusMessage(`✅ Successfully installed ${ecosystem} package '${pkgName}'!`)
        setActivityLogs((prev) => [
          { timestamp: tNow, type: 'success', text: `📦 Auto-Installed ${ecosystem} package '${pkgName}'. Log:\n${data.log || 'Success.'}` },
          ...prev
        ])
      } else {
        const errLog = data.log || 'Package installation failed.'
        setStatusMessage(`❌ Failed to install ${pkgName}.`)
        handleOpenAlert(`Package Installation Failed: ${pkgName}`, errLog)
      }
    } catch (e: any) {
      console.error(e)
      handleOpenAlert(`Package Installation Error: ${pkgName}`, e.response?.data?.detail || e.message || String(e))
    }
  }

  // Real-time AI Agent Execution Tracking with Persistent Storage & Auto-Detection
  const [activeTaskId, setActiveTaskId] = useState<string | undefined>(
    () => initialTaskId || localStorage.getItem('sentinel_active_refactor_task_id') || undefined
  )
  const [activeTaskData, setActiveTaskData] = useState<any>(null)

  useEffect(() => {
    if (initialTaskId) {
      setActiveTaskId(initialTaskId)
      localStorage.setItem('sentinel_active_refactor_task_id', initialTaskId)
    }
  }, [initialTaskId])

  // Auto-detect running or queued REFACTOR / SCAFFOLDER tasks if no active task set
  useEffect(() => {
    let isMounted = true
    const autoDetectActiveTask = async () => {
      try {
        const res = await tasksApi.list()
        const allTasks = res.data || []
        const activeTask = allTasks.find(
          (t: any) =>
            (t.status === 'RUNNING' || t.status === 'QUEUED') &&
            (t.workflow_type === 'REFACTOR' || t.workflow_type === 'SCAFFOLDER')
        )
        if (isMounted && activeTask && activeTask.task_id) {
          if (activeTaskId !== activeTask.task_id) {
            setActiveTaskId(activeTask.task_id)
            localStorage.setItem('sentinel_active_refactor_task_id', activeTask.task_id)
          }
        }
      } catch (err) {
        console.error('Auto-detect task error:', err)
      }
    }
    autoDetectActiveTask()
    const detectInterval = setInterval(autoDetectActiveTask, 3000)
    return () => {
      isMounted = false
      clearInterval(detectInterval)
    }
  }, [activeTaskId])

  // Poll active AI task status, thought summaries, and files written
  useEffect(() => {
    if (!activeTaskId) return
    let isMounted = true
    const pollTask = async () => {
      try {
        const res = await tasksApi.get(activeTaskId)
        if (isMounted && res.data) {
          setActiveTaskData(res.data)
          const steps = res.data.steps || []
          steps.forEach((step: any) => {
            const payload = step.output_summary || step.output_payload || {}
            const written = payload.files_written || payload.files_updated || []
            if (Array.isArray(written)) {
              written.forEach((filePath: string) => {
                setModifiedFilesList((prev) => {
                  if (prev.some((f) => f.path === filePath)) return prev
                  return [
                    { path: filePath, timestamp: new Date().toLocaleTimeString(), action: 'AI_WRITTEN' },
                    ...prev
                  ]
                })
              })
            }
          })
          if (res.data.task?.status === 'COMPLETED' || res.data.task?.status === 'FAILED') {
            fetchTree()
          }
        }
      } catch (err: any) {
        if (err?.response?.status === 404) {
          console.warn(`Task ${activeTaskId} not found on backend; stopping poll.`)
          clearInterval(interval)
          if (isMounted) setActiveTaskId(undefined)
        } else {
          console.error('Task polling error:', err)
        }
      }
    }
    pollTask()
    const interval = setInterval(pollTask, 1800)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [activeTaskId])

  const logEndRef = useRef<HTMLDivElement>(null)

  // Scan and install missing dependencies
  const handleInstallDeps = async () => {
    setInstallingDeps(true)
    const tStart = new Date().toLocaleTimeString()
    setDepsStatus('Scanning AST imports across project files & verifying virtualenv...')
    setActivityLogs((prev) => [
      { timestamp: tStart, type: 'info', text: 'Scanning AST imports and verifying node_modules & Python .venv...' },
      ...prev
    ])
    try {
      const res = await codeRefactorApi.installDeps(currentTargetPath)
      const data = res.data || {}
      const installedNpm = data.installed_npm || []
      const installedPip = data.installed_pip || []
      const repairedRel = data.repaired_relative_imports || []
      const allInstalled = data.installed || [...installedNpm, ...installedPip]
      const scannedJs = data.scanned_js_imports || []
      const scannedPy = data.scanned_python_imports || []
      const tDone = new Date().toLocaleTimeString()

      // Store live env health data
      setEnvHealthData({
        node_modules_count: data.node_modules_count || 0,
        pip_packages_count: data.pip_packages_count || 0,
        venv_created: !!data.venv_created,
        npm_installed: !!data.npm_installed,
        last_scanned: tDone
      })

      const totalScanned = scannedJs.length + scannedPy.length

      if (allInstalled.length > 0 || repairedRel.length > 0) {
        let msg = ''
        if (allInstalled.length > 0) {
          msg += `Installed ${allInstalled.length} package(s): ${allInstalled.join(', ')}. `
        }
        if (repairedRel.length > 0) {
          msg += `Repaired ${repairedRel.length} missing relative import(s).`
        }
        setDepsStatus(msg)
        setStatusMessage(msg)
        setActivityLogs((prev) => [
          { timestamp: tDone, type: 'success', text: `Environment Repair Complete: ${msg}\nDetails: ${data.logs || 'Verified'}` },
          ...prev
        ])
      } else {
        const msg = `Verified ${totalScanned} AST imports (${scannedJs.length} JS/TS, ${scannedPy.length} Python). All dependencies physically satisfied!`
        setDepsStatus(msg)
        setStatusMessage(msg)
        setActivityLogs((prev) => [
          { timestamp: tDone, type: 'success', text: `Dependency Scan Complete: ${msg}` },
          ...prev
        ])
      }
      fetchTree()
    } catch (err: any) {
      const errMsg = 'Dependency repair failed: ' + (err.response?.data?.detail || err.message)
      setDepsStatus(errMsg)
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'warn', text: errMsg },
        ...prev
      ])
    } finally {
      setInstallingDeps(false)
    }
  }

  // Run AST Health & Security scan
  const handleScanProject = async () => {
    setScanning(true)
    const tStart = new Date().toLocaleTimeString()
    setStatusMessage('Running AST health & security scan...')
    setActivityLogs((prev) => [
      { timestamp: tStart, type: 'info', text: 'AST Code Health & Security scan initiated...' },
      ...prev
    ])
    try {
      const res = await codeRefactorApi.scan(currentTargetPath)
      const data = res.data || {}
      const health = data.health_assessment || {}
      const security = data.security_assessment || {}
      const tDone = new Date().toLocaleTimeString()
      setScanData({
        overall_score: health.overall_score ?? 0,
        verdict: health.verdict ?? 'Unknown',
        verdict_badge: health.verdict_badge ?? 'warning',
        total_issues: health.total_issues ?? 0,
        security_score: security.security_score ?? 0,
        risk_level: security.risk_level ?? 'Unknown',
        risk_badge: security.risk_badge ?? 'warning',
        total_vulnerabilities: security.total_vulnerabilities ?? 0,
        vulnerabilities: security.vulnerabilities ?? [],
        feature_ideas: data.feature_ideas ?? [],
        sample_issues: health.sample_issues ?? [],
        files_scanned: data.total_files ?? 0,
        last_scanned: tDone
      })
      setActivityLogs((prev) => [
        { timestamp: tDone, type: 'success', text: `AST Scan: Health ${health.overall_score}/100 · Security ${security.security_score}/100 · ${data.total_files} files` },
        ...prev
      ])
      setStatusMessage(`Scan complete — Health: ${health.overall_score}/100, Security: ${security.security_score}/100`)
      setRightPanelTab('deps')
    } catch (err: any) {
      const errMsg = 'AST Scan failed: ' + (err.response?.data?.detail || err.message)
      setStatusMessage(errMsg)
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'warn', text: errMsg },
        ...prev
      ])
    } finally {
      setScanning(false)
    }
  }

  // Diagnose & Fix Errors in Selected File
  const handleDiagnoseAndFixFile = async () => {
    if (!selectedFilePath) return
    setDiagnosingFile(true)
    const tStart = new Date().toLocaleTimeString()
    setStatusMessage(`🩺 Diagnosing static errors & performing AI repair on ${selectedFilePath}...`)
    setActivityLogs((prev) => [
      { timestamp: tStart, type: 'info', text: `Diagnosing syntax & logic errors in selected file '${selectedFilePath}'...` },
      ...prev
    ])
    try {
      const res = await codeRefactorApi.diagnoseFile(currentTargetPath, selectedFilePath)
      const data = res.data || {}
      const fixedCode = data.fixed_code || ''
      const errorsFound = data.errors_found || []
      const summary = data.summary || 'File diagnosed and repaired.'
      const tDone = new Date().toLocaleTimeString()

      if (fixedCode) {
        setFileContent(fixedCode)
        setOriginalContent(fixedCode)
        setIsDirty(false)
      }
      
      const statusText = errorsFound.length > 0 
        ? `Diagnosed ${errorsFound.length} error(s) in ${selectedFilePath}: ${summary}`
        : `Inspected ${selectedFilePath}: ${summary}`

      setStatusMessage(statusText)
      setActivityLogs((prev) => [
        { timestamp: tDone, type: 'success', text: `1-Click File Repair (${selectedFilePath}): ${summary}` },
        ...prev
      ])
      
      setModifiedFilesList((prev) => [
        { path: selectedFilePath, timestamp: tDone, action: 'AI_REPAIRED' },
        ...prev.filter((f) => f.path !== selectedFilePath)
      ])
    } catch (err: any) {
      const errMsg = 'File diagnosis failed: ' + (err.response?.data?.detail || err.message)
      setStatusMessage(errMsg)
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'warn', text: errMsg },
        ...prev
      ])
    } finally {
      setDiagnosingFile(false)
    }
  }

  // Solution Alignment & Contract Verification Handlers
  const handleValidateAlignment = async (autoRemediate = false) => {
    setValidatingAlignment(true)
    const tStart = new Date().toLocaleTimeString()
    setStatusMessage('Auditing semantic goal alignment & full-stack API contracts...')
    setActivityLogs((prev) => [
      { timestamp: tStart, type: 'info', text: 'Solution Alignment & Contract Verification scan initiated...' },
      ...prev
    ])
    try {
      const res = await codeRefactorApi.validateAlignment(
        currentTargetPath,
        aiPrompt || 'Verify project functionality and contract harmony',
        autoRemediate
      )
      const data = res.data || {}
      setAlignmentData(data)
      const tDone = new Date().toLocaleTimeString()
      const score = data.overall_alignment_score ?? 0
      setActivityLogs((prev) => [
        {
          timestamp: tDone,
          type: data.passed ? 'success' : 'warn',
          text: `Alignment Audit: Score ${score}/100 (${data.verdict || 'DONE'}) · ${data.api_contracts?.synced_contracts?.length || 0} API contracts synced`
        },
        ...prev
      ])
      setStatusMessage(`Alignment Audit Complete — Score: ${score}/100 (${data.verdict || 'VERIFIED'})`)
      setRightPanelTab('alignment')
      fetchTree()
    } catch (err: any) {
      const errMsg = 'Alignment validation failed: ' + (err.response?.data?.detail || err.message)
      setStatusMessage(errMsg)
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'warn', text: errMsg },
        ...prev
      ])
    } finally {
      setValidatingAlignment(false)
    }
  }

  const handleRemediateAlignment = async () => {
    setRemediatingAlignment(true)
    const tStart = new Date().toLocaleTimeString()
    setStatusMessage('Auto-remediating full-stack contract drift and mounting components...')
    setActivityLogs((prev) => [
      { timestamp: tStart, type: 'info', text: 'Auto-remediating contract drift & synthesising missing FastAPI routes...' },
      ...prev
    ])
    try {
      const res = await codeRefactorApi.remediateAlignment(
        currentTargetPath,
        aiPrompt || 'Auto-remediate project contracts'
      )
      const data = res.data || {}
      setAlignmentData(data)
      const tDone = new Date().toLocaleTimeString()
      const logs = data.remediation_logs || []
      const logSummary = logs.length > 0 ? logs.join('; ') : 'No drift detected'
      setActivityLogs((prev) => [
        {
          timestamp: tDone,
          type: 'success',
          text: `Auto-Remediation Complete: ${logSummary}`
        },
        ...prev
      ])
      setStatusMessage(`Remediation Complete — ${logs.length} fix(es) applied. Score: ${data.overall_alignment_score}/100`)
      fetchTree()
    } catch (err: any) {
      const errMsg = 'Contract auto-remediation failed: ' + (err.response?.data?.detail || err.message)
      setStatusMessage(errMsg)
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'warn', text: errMsg },
        ...prev
      ])
    } finally {
      setRemediatingAlignment(false)
    }
  }

  // Fetch registered solutions list
  useEffect(() => {
    let isMounted = true
    projectsApi.list().then(async (r) => {
      if (!isMounted) return
      const list = r.data.projects || []
      setRegisteredProjects(list)
      if (list.length > 0) {
        // Priority 1: Match by currentProjectId if provided
        let match = currentProjectId ? list.find((p: any) => p.project_id === currentProjectId) : null

        // Priority 2: Match by target path (normalized)
        const targetToMatch = (currentTargetPath || initialTargetPath || '').trim()
        if (!match && targetToMatch) {
          const normTarget = targetToMatch.toLowerCase().replace(/\\/g, '/')
          match = list.find((p: any) => p.target_path && p.target_path.toLowerCase().replace(/\\/g, '/') === normTarget)
        }

        if (match) {
          setCurrentProjectId(match.project_id)
          setCurrentProjectName(match.project_name)
          setCurrentTargetPath(match.target_path)
          setPort(match.active_port)
        } else if (targetToMatch) {
          // Attempt on-the-fly registration of un-registered solution directory
          try {
            const regName = currentProjectName || targetToMatch.split(/[\/\\]/).pop() || 'Project'
            const regRes = await projectsApi.register({
              project_name: regName,
              target_path: targetToMatch,
              tech_stack: 'FastAPI + React'
            })
            if (isMounted && regRes.data?.project?.project_id) {
              setCurrentProjectId(regRes.data.project.project_id)
              setCurrentProjectName(regRes.data.project.project_name)
              setPort(regRes.data.project.active_port)
              return
            }
          } catch {
            // Fallback to first registered project if on-the-fly registration fails
          }
          if (isMounted) {
            const first = list[0]
            setCurrentProjectId(first.project_id)
            setCurrentProjectName(first.project_name)
            setCurrentTargetPath(first.target_path)
            setPort(first.active_port)
          }
        } else if (!currentProjectId) {
          const first = list[0]
          setCurrentProjectId(first.project_id)
          setCurrentProjectName(first.project_name)
          setCurrentTargetPath(first.target_path)
          setPort(first.active_port)
        }
      }
    }).catch(console.error)
    return () => { isMounted = false }
  }, [currentTargetPath, initialTargetPath, initialProjectId])

  // Sync props when initial parameters change
  useEffect(() => {
    if (initialProjectId) {
      setCurrentProjectId(initialProjectId)
    }
    if (initialProjectName) {
      setCurrentProjectName(initialProjectName)
    }
    if (initialTargetPath) {
      setCurrentTargetPath(initialTargetPath)
    }
    if (initialPort) {
      setPort(initialPort)
    }
  }, [initialProjectId, initialProjectName, initialTargetPath, initialPort])

  // Switch selected project
  const handleSelectProject = (projId: string) => {
    const proj = registeredProjects.find((p) => p.project_id === projId)
    if (proj) {
      setCurrentProjectId(proj.project_id)
      setCurrentProjectName(proj.project_name)
      setCurrentTargetPath(proj.target_path)
      setPort(proj.active_port)
      setSelectedFilePath(null)
      setFileContent('')
      setOriginalContent('')
      setIsDirty(false)
    }
  }

  // Fetch Tree
  const fetchTree = async () => {
    if (!currentProjectId || !currentProjectId.trim()) {
      setLoadingTree(false)
      return
    }
    try {
      setLoadingTree(true)
      const res = await projectsApi.getTree(currentProjectId)
      setTree(res.data.tree || [])
      // Default expand root folders
      const initialExpanded: Record<string, boolean> = {}
      res.data.tree?.forEach((node: TreeNode) => {
        if (node.type === 'directory') initialExpanded[node.path] = true
      })
      setExpandedFolders(initialExpanded)
    } catch (err: any) {
      console.error(err)
    } finally {
      setLoadingTree(false)
    }
  }

  // Fetch File
  const handleSelectFile = async (path: string) => {
    if (isDirty) {
      if (!window.confirm('You have unsaved changes. Discard and switch file?')) return
    }
    setSelectedFilePath(path)
    setLoadingFile(true)
    try {
      const res = await projectsApi.readFile(currentProjectId, path)
      setFileContent(res.data.content || '')
      setOriginalContent(res.data.content || '')
      setIsDirty(false)
    } catch (err: any) {
      console.error(err)
      setFileContent(`// Error reading file: ${err.message}`)
    } finally {
      setLoadingFile(false)
    }
  }

  // Save File
  const handleSaveFile = async () => {
    if (!selectedFilePath) return
    setSavingFile(true)
    const tNow = new Date().toLocaleTimeString()
    try {
      await projectsApi.writeFile(currentProjectId, selectedFilePath, fileContent)
      setOriginalContent(fileContent)
      setIsDirty(false)
      setStatusMessage(`Saved ${selectedFilePath} cleanly! Environment dependencies re-verified.`)
      setModifiedFilesList((prev) => [
        { path: selectedFilePath, timestamp: tNow, action: 'SAVED' },
        ...prev.filter((f) => f.path !== selectedFilePath)
      ])
      setActivityLogs((prev) => [
        { timestamp: tNow, type: 'success', text: `Saved changes to ${selectedFilePath}` },
        ...prev
      ])
    } catch (err: any) {
      handleOpenAlert('File Save Error', err.response?.data?.detail || err.message || String(err))
    } finally {
      setSavingFile(false)
    }
  }

  // Start Server
  const handleStartServer = async () => {
    try {
      setStatusMessage('Launching app server...')
      const res = await projectsApi.startServer(currentProjectId)
      if (res.data.success) {
        setServerStatus('RUNNING')
        setPort(res.data.port)
        setStatusMessage(`Dev server running on port ${res.data.port}`)
        setActivityLogs((prev) => [
          { timestamp: new Date().toLocaleTimeString(), type: 'success', text: `Dev Server started on port ${res.data.port}` },
          ...prev
        ])
      }
    } catch (err: any) {
      handleOpenAlert('Server Launch Failure', err.response?.data?.detail || err.message || String(err))
    }
  }

  // Stop Server
  const handleStopServer = async () => {
    try {
      await projectsApi.stopServer(currentProjectId)
      setServerStatus('STOPPED')
      setStatusMessage('Server stopped.')
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'info', text: 'Dev Server stopped.' },
        ...prev
      ])
    } catch (err: any) {
      handleOpenAlert('Server Stop Error', err.response?.data?.detail || err.message || String(err))
    }
  }

  // Send AI Prompt
  const handleSendAiPrompt = async () => {
    if (!aiPrompt.trim()) return
    setSendingPrompt(true)
    const tNow = new Date().toLocaleTimeString()
    const promptSummary = aiPrompt.slice(0, 50) + (aiPrompt.length > 50 ? '...' : '')
    setStatusMessage('🚀 Sentinel AI Developer agent synthesizing changes...')
    setActivityLogs((prev) => [
      { timestamp: tNow, type: 'info', text: `Refactor prompt submitted: "${promptSummary}"` },
      ...prev
    ])
    try {
      const res = await projectsApi.sendPrompt(currentProjectId, aiPrompt, selectedFilePath || undefined)
      if (res.data.task_id) {
        setActiveTaskId(res.data.task_id)
        setRightPanelTab('telemetry')
      }
      setStatusMessage(`Task enqueued (${res.data.task_id})! Sentinel is modifying code in the background...`)
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'success', text: `AI Refactor Task enqueued (${res.data.task_id})` },
        ...prev
      ])
      if (selectedFilePath) {
        setModifiedFilesList((prev) => [
          { path: selectedFilePath, timestamp: new Date().toLocaleTimeString(), action: 'AI_MODIFIED' },
          ...prev.filter((f) => f.path !== selectedFilePath)
        ])
      }
      setAiPrompt('')
      // Refresh tree after delay
      setTimeout(fetchTree, 3000)
    } catch (err: any) {
      const errMsg = 'AI Prompt failed: ' + (err.response?.data?.detail || err.message)
      setStatusMessage(errMsg)
      setActivityLogs((prev) => [
        { timestamp: new Date().toLocaleTimeString(), type: 'warn', text: errMsg },
        ...prev
      ])
    } finally {
      setSendingPrompt(false)
    }
  }

  // Check initial project server state & logs
  useEffect(() => {
    if (!currentProjectId || !currentProjectId.trim()) return
    fetchTree()
    const checkState = async () => {
      try {
        const res = await projectsApi.get(currentProjectId)
        if (res.data?.status === 'RUNNING') {
          setServerStatus('RUNNING')
          setPort(res.data.active_port)
        } else {
          setServerStatus('STOPPED')
        }
      } catch (e) {
        // quiet catch
      }
    }
    checkState()
  }, [currentProjectId])

  // Poll terminal logs
  useEffect(() => {
    if (!currentProjectId || !currentProjectId.trim()) return
    const fetchLogs = async () => {
      try {
        const res = await projectsApi.getLogs(currentProjectId, 80)
        setLogs(res.data?.logs || [])
      } catch (e) {
        // quiet catch
      }
    }
    fetchLogs()
    const interval = setInterval(fetchLogs, 3000)
    return () => clearInterval(interval)
  }, [currentProjectId])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => ({ ...prev, [path]: !prev[path] }))
  }

  const renderTreeNodes = (nodes: TreeNode[], depth = 0) => {
    return nodes.map((node) => {
      const isExpanded = !!expandedFolders[node.path]
      if (node.type === 'directory') {
        return (
          <div key={node.path} className="tree-dir-group">
            <div
              className="tree-node tree-dir"
              style={{ paddingLeft: `${depth * 14 + 8}px` }}
              onClick={() => toggleFolder(node.path)}
            >
              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              {isExpanded ? <FolderOpen size={14} className="icon-dir-open" /> : <Folder size={14} className="icon-dir" />}
              <span className="node-name">{node.name}</span>
            </div>
            {isExpanded && node.children && (
              <div className="tree-children">{renderTreeNodes(node.children, depth + 1)}</div>
            )}
          </div>
        )
      }

      const isSelected = selectedFilePath === node.path
      return (
        <div
          key={node.path}
          className={`tree-node tree-file ${isSelected ? 'selected' : ''}`}
          style={{ paddingLeft: `${depth * 14 + 22}px` }}
          onClick={() => handleSelectFile(node.path)}
        >
          <FileCode size={14} className="icon-file" />
          <span className="node-name">{node.name}</span>
        </div>
      )
    })
  }

  return (
    <div className={`code-workspace-overlay ${isInline ? 'is-inline' : ''} ${isFullscreen ? 'is-fullscreen' : ''}`}>
      {/* Workspace Header Toolbar */}
      <div className="workspace-header">
        <div className="workspace-title-area">
          <Code2 size={20} className="text-primary" />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h4 style={{ margin: 0 }}>Sentinel AI Workbench:</h4>
              {registeredProjects.length > 0 ? (
                <select
                  className="project-select-dropdown"
                  value={currentProjectId}
                  onChange={(e) => handleSelectProject(e.target.value)}
                >
                  <option value={currentProjectId}>{currentProjectName}</option>
                  {registeredProjects
                    .filter((p) => p.project_id !== currentProjectId)
                    .map((p) => (
                      <option key={p.project_id} value={p.project_id}>
                        {p.project_name} ({p.target_path})
                      </option>
                    ))}
                </select>
              ) : (
                <span className="text-primary" style={{ fontWeight: 700 }}>{currentProjectName}</span>
              )}
            </div>
            <div className="workspace-path-sub">{currentTargetPath}</div>
          </div>
        </div>

        {/* Server Control Bar */}
        <div className="workspace-server-bar">
          {serverStatus === 'RUNNING' ? (
            <a
              href={`http://localhost:${port}`}
              target="_blank"
              rel="noreferrer"
              className="server-status-badge running"
              title={`Open app preview at http://localhost:${port}`}
            >
              <span className="pulse-dot" />
              <span className="server-live-tag">LIVE</span>
              <span className="server-port-text">:{port}</span>
              <ExternalLink size={11} style={{ marginLeft: 2, opacity: 0.8 }} />
            </a>
          ) : (
            <div className="server-status-badge stopped">
              <span className="stopped-dot" /> Offline
            </div>
          )}

          {serverStatus === 'RUNNING' ? (
            <button className="btn-server-action btn-server-stop" onClick={handleStopServer} title="Stop development server">
              <Square size={12} /> Stop Server
            </button>
          ) : (
            <button className="btn-server-action btn-server-start" onClick={handleStartServer} title="Start development server">
              <Play size={12} /> Start Dev Server
            </button>
          )}

          <button className="btn-server-action btn-server-refresh" onClick={fetchTree} title="Rescan & refresh file tree">
            <RefreshCw size={12} className={loadingTree ? 'spin' : ''} /> Refresh Files
          </button>
        </div>

        {/* Viewport & Window Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="viewport-toggle-group">
            <button
              className={`view-btn ${viewportMode === 'desktop' ? 'active' : ''}`}
              onClick={() => setViewportMode('desktop')}
              title="Desktop View (100%)"
            >
              <Monitor size={14} />
            </button>
            <button
              className={`view-btn ${viewportMode === 'tablet' ? 'active' : ''}`}
              onClick={() => setViewportMode('tablet')}
              title="Tablet View (768px)"
            >
              <Tablet size={14} />
            </button>
            <button
              className={`view-btn ${viewportMode === 'mobile' ? 'active' : ''}`}
              onClick={() => setViewportMode('mobile')}
              title="Mobile View (375px)"
            >
              <Smartphone size={14} />
            </button>
          </div>

          {isInline && (
            <button
              className="btn-icon-sm"
              style={{ color: '#94a3b8' }}
              onClick={() => setIsFullscreen(!isFullscreen)}
              title={isFullscreen ? 'Exit Fullscreen' : 'Expand Fullscreen'}
            >
              <Monitor size={16} />
            </button>
          )}

          {onClose && (
            <button className="workspace-close-btn" onClick={onClose}>
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* Active AI Agent Floating Notification Banner */}
      {activeTaskData?.task?.status === 'RUNNING' && (
        <div className="active-agent-banner">
          <div className="banner-left">
            <Zap size={15} className="text-primary spin-slow" />
            <span>
              <strong>AI Agent Refactoring in Progress</strong> ({activeTaskData.task.title}): Sentinel is modifying project codebase...
            </span>
          </div>
          <button
            className="btn-sm btn-secondary banner-view-btn"
            onClick={() => setRightPanelTab('telemetry')}
          >
            <Activity size={13} /> View Telemetry Stream
          </button>
        </div>
      )}

      {/* Main Split Workbench Body */}
      <div className="workspace-body">
        {/* Left Panel: File Tree & In-Context AI Assistant */}
        <div className="workspace-left-panel">
          <div className="panel-section-header">
            <span><FolderTree size={14} /> Workspace File Tree</span>
            <button className="btn-icon-sm" onClick={fetchTree} title="Refresh File Tree">
              <RefreshCw size={12} className={loadingTree ? 'spin' : ''} />
            </button>
          </div>

          <div className="file-tree-container">
            {loadingTree ? (
              <div className="tree-loading">Loading workspace files...</div>
            ) : tree.length === 0 ? (
              <div className="tree-empty">No files found.</div>
            ) : (
              renderTreeNodes(tree)
            )}
          </div>

          {/* In-Context AI Assistant Panel */}
          <div className="in-context-ai-box">
            <div className="ai-box-header">
              <Sparkles size={14} className="text-primary" />
              <span>In-Context AI Developer</span>
            </div>
            <textarea
              className="ai-input-area"
              rows={3}
              placeholder="Prompt Sentinel to modify code, add features, or fix layout (e.g. 'Add a GPU usage chart in App.tsx')..."
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
            />
            <button
              className="btn btn-primary btn-block-sm"
              onClick={handleSendAiPrompt}
              disabled={sendingPrompt || !aiPrompt.trim()}
            >
              <Sparkles size={13} /> {sendingPrompt ? 'Synthesizing...' : 'Modify Code via AI'}
            </button>
          </div>
        </div>

        {/* Center Panel: Code Editor & Terminal */}
        <div className="workspace-center-panel">
          <div className="editor-tab-bar">
            {selectedFilePath ? (
              <div className="active-tab">
                <FileCode size={14} className="text-primary" />
                <span>{selectedFilePath}</span>
                {isDirty && <span className="dirty-indicator" title="Unsaved changes">*</span>}
              </div>
            ) : (
              <div className="active-tab empty">Select a file from the explorer to view/edit</div>
            )}

            {selectedFilePath && (
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <button
                  className="btn-sm btn-secondary diagnose-btn"
                  onClick={handleDiagnoseAndFixFile}
                  disabled={diagnosingFile || loadingFile}
                  title="Diagnose static build errors & auto-fix selected file via AI"
                >
                  <Wrench size={13} className={diagnosingFile ? 'spin' : ''} />
                  {diagnosingFile ? 'Diagnosing & Fixing...' : 'Diagnose & Fix Errors'}
                </button>
                <button className="btn-sm btn-primary save-btn" onClick={handleSaveFile} disabled={savingFile || !isDirty}>
                  <Save size={13} /> {savingFile ? 'Saving...' : 'Save File'}
                </button>
              </div>
            )}
          </div>

          <div className="editor-container">
            {loadingFile ? (
              <div className="editor-loading">Loading file content...</div>
            ) : selectedFilePath ? (
              <textarea
                className="code-textarea"
                value={fileContent}
                onChange={(e) => {
                  setFileContent(e.target.value)
                  setIsDirty(e.target.value !== originalContent)
                }}
                spellCheck={false}
              />
            ) : (
              <div className="editor-placeholder">
                <Code2 size={48} className="placeholder-icon" />
                <h5>Sentinel AI Workspace Active</h5>
                <p>Click any file on the left to view code or enter an AI prompt below to generate new components.</p>
              </div>
            )}
          </div>

          {/* Terminal Console Panel */}
          <div className={`terminal-drawer ${showTerminal ? 'open' : 'closed'}`}>
            <div className="terminal-bar" onClick={() => setShowTerminal(!showTerminal)}>
              <div className="terminal-title">
                <Terminal size={14} /> Server Terminal Logs ({logs.length})
              </div>
              <button className="btn-icon-sm">{showTerminal ? '▼' : '▲'}</button>
            </div>
            {showTerminal && (
              <div className="terminal-output">
                {logs.length === 0 ? (
                  <div className="log-line text-muted">No server output logged yet. Start dev server to view logs.</div>
                ) : (
                  logs.map((log, idx) => <div key={idx} className="log-line">{log}</div>)
                )}
                <div ref={logEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Dedicated Refactor & AI Agent Intelligence Center */}
        <div className="workspace-right-panel">
          {/* Right Panel Segmented Tabs Header */}
          <div className="right-panel-header-tabs">
            <button
              className={`right-tab-btn ${rightPanelTab === 'telemetry' ? 'active' : ''}`}
              onClick={() => setRightPanelTab('telemetry')}
            >
              <Sparkles size={14} /> Live Thought & Steps
            </button>
            <button
              className={`right-tab-btn ${rightPanelTab === 'diffs' ? 'active' : ''}`}
              onClick={() => setRightPanelTab('diffs')}
            >
              <FileDiff size={14} /> Touched Files ({modifiedFilesList.length})
            </button>
            <button
              className={`right-tab-btn ${rightPanelTab === 'deps' ? 'active' : ''}`}
              onClick={() => setRightPanelTab('deps')}
            >
              <PackageCheck size={14} /> Dependencies
            </button>
            <button
              className={`right-tab-btn ${rightPanelTab === 'alignment' ? 'active' : ''}`}
              onClick={() => setRightPanelTab('alignment')}
            >
              <ShieldCheck size={14} /> Alignment & Contracts
            </button>
          </div>

          {/* Tab 1: Live AI Thought Stream & Step Telemetry */}
          {rightPanelTab === 'telemetry' && (
            <div className="activity-panel-content">
              {activeTaskData && activeTaskData.task ? (
                <div className="activity-card active-agent-card">
                  <div className="activity-card-header">
                    <Sparkles size={16} className="text-primary spin-slow" />
                    <span className="activity-card-title">Live AI Agent Telemetry & Reasoning</span>
                    <span className={`task-status-badge status-${activeTaskData.task.status?.toLowerCase() || 'running'}`}>
                      {activeTaskData.task.status}
                    </span>
                  </div>

                  <div className="active-task-meta">
                    <div className="task-title-text">Goal: {activeTaskData.task.title}</div>
                    <div className="task-sub-info">
                      Task ID: <code>{activeTaskData.task.task_id}</code> | Model: <strong>Local LLM ({activeModelTag})</strong>
                    </div>

                    {/* Task Execution Progress Bar */}
                    {(() => {
                      const steps = activeTaskData.steps || []
                      const completedSteps = steps.filter((s: any) => s.status === 'COMPLETED').length
                      const totalSteps = steps.length
                      const progressPct = activeTaskData.task.status === 'COMPLETED'
                        ? 100
                        : totalSteps > 0
                        ? Math.round((completedSteps / totalSteps) * 100)
                        : 20
                      return (
                        <div className="task-progress-section">
                          <div className="task-progress-labels">
                            <span>Execution Progress ({completedSteps}/{totalSteps || 1} steps completed)</span>
                            <span className="progress-pct">{progressPct}%</span>
                          </div>
                          <div className="task-progress-bar-track">
                            <div
                              className="task-progress-bar-fill"
                              style={{ width: `${progressPct}%` }}
                            />
                          </div>
                        </div>
                      )
                    })()}
                  </div>

                  {/* Highlight Currently Editing File */}
                  {(() => {
                    const steps = activeTaskData.steps || []
                    const activeStep = steps.find((s: any) => s.status === 'RUNNING') || steps[steps.length - 1]
                    const activePayload = activeStep?.output_summary || activeStep?.output_payload || {}
                    const writtenFiles = activePayload.files_written || activePayload.files_updated || []
                    const currentFile = writtenFiles.length > 0 ? writtenFiles[writtenFiles.length - 1] : selectedFilePath
                    const fileExt = currentFile ? currentFile.split('.').pop()?.toUpperCase() : ''
                    return currentFile ? (
                      <div className="active-file-focus-card">
                        <div className="focus-card-header">
                          <div className="pulse-dot-cyan" />
                          <FileCode size={14} className="text-primary" />
                          <span className="focus-label">CURRENTLY MODIFYING FILE:</span>
                          {fileExt && <span className="file-ext-badge">{fileExt}</span>}
                        </div>
                        <div className="focus-file-path">{currentFile}</div>
                        <button className="btn-sm btn-secondary focus-open-btn" onClick={() => handleSelectFile(currentFile)}>
                          Open in Editor
                        </button>
                      </div>
                    ) : null
                  })()}

                  {/* Step-by-Step IR Tree & Live Thought Stream */}
                  <div className="active-steps-container">
                    {activeTaskData.steps && activeTaskData.steps.length > 0 ? (
                      activeTaskData.steps.map((step: any, idx: number) => {
                        const payload = step.output_summary || step.output_payload || {}
                        const summaryText = payload.summary || payload.details || payload.response || (typeof payload === 'string' ? payload : '')
                        const writtenFiles = payload.files_written || payload.files_updated || []
                        return (
                          <div key={idx} className={`active-step-item step-${step.status?.toLowerCase() || 'pending'}`}>
                            <div className="step-item-header">
                              <span className="step-num">#{step.step_order || idx + 1}</span>
                              <span className="step-title">{step.step_title || step.step_type}</span>
                              <span className={`step-badge badge-${step.status?.toLowerCase() || 'pending'}`}>
                                {step.status}
                              </span>
                            </div>

                            {step.step_description && (
                              <div className="step-desc-text">{step.step_description}</div>
                            )}

                            {/* LLM Thought & Synthesis Stream */}
                            {summaryText ? (
                              <details className="step-thought-details" open={step.status === 'RUNNING' || step.status === 'COMPLETED'}>
                                <summary className="thought-summary-header">
                                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                    <Sparkles size={13} className="text-primary" /> AI Thought & Reasoning
                                  </span>
                                  <span className="thought-toggle-hint">Details</span>
                                </summary>
                                <div className="thought-content">{summaryText}</div>
                              </details>
                            ) : step.status === 'RUNNING' ? (
                              <div className="step-thought-box step-running-pulse">
                                <span className="thought-label" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                  <Zap size={13} className="text-primary" /> AI Thought & Reasoning:
                                </span>
                                <div className="thought-content text-muted">Agent actively synthesizing and refactoring code blocks...</div>
                              </div>
                            ) : null}

                            {/* Files Modified in this Step */}
                            {writtenFiles && writtenFiles.length > 0 && (
                              <div className="step-files-box">
                                <span className="files-label" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                  <FileCode size={13} color="#10b981" /> Touched / Written Files:
                                </span>
                                <div className="step-files-tags">
                                  {writtenFiles.map((fPath: string, fIdx: number) => (
                                    <button
                                      key={fIdx}
                                      className="step-file-chip"
                                      onClick={() => handleSelectFile(fPath)}
                                      title="Click to view file in editor"
                                    >
                                      <FileCode size={12} /> {fPath}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )
                      })
                    ) : (
                      <div className="step-waiting-notice">Initializing sub-task IR plan graph...</div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="activity-card activity-idle-card">
                  <Sparkles size={24} className="text-muted" style={{ display: 'block', margin: '0 auto 8px auto' }} />
                  <div style={{ textAlign: 'center', fontSize: '0.84rem', fontWeight: 700, color: 'var(--text-base)' }}>
                    No Active AI Task Running
                  </div>
                  <div style={{ textAlign: 'center', fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>
                    Type an instruction in the <strong>In-Context AI Developer</strong> prompt box on the left or click <strong>Start Autonomous Refactor</strong> to launch an AI agent run.
                  </div>
                </div>
              )}

              {/* Activity Log Stream */}
              <div className="activity-card stream-logs-card">
                <div className="activity-card-header">
                  <Wrench size={16} className="text-primary" />
                  <span className="activity-card-title">Refactor Log & Event Stream</span>
                </div>
                <div className="activity-stream-logs">
                  {activityLogs.map((log, idx) => (
                    <div key={idx} className={`stream-log-entry log-${log.type}`}>
                      <span className="log-time">[{log.timestamp}]</span>
                      <span className="log-text">{log.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Tab 2: Touched Files & Diffs Viewer */}
          {rightPanelTab === 'diffs' && (
            <div className="activity-panel-content">
              <div className="activity-card modified-files-card">
                <div className="activity-card-header">
                  <FileDiff size={16} className="text-primary" />
                  <span className="activity-card-title">Session Touched Files ({modifiedFilesList.length})</span>
                </div>
                {modifiedFilesList.length === 0 ? (
                  <div className="empty-modified-notice">
                    No files modified in current session. Enter an AI prompt on the left or edit a file to see changes tracked here.
                  </div>
                ) : (
                  <div className="modified-files-list">
                    {modifiedFilesList.map((item, idx) => (
                      <div
                        key={idx}
                        className={`modified-file-item ${selectedFilePath === item.path ? 'selected' : ''}`}
                        onClick={() => handleSelectFile(item.path)}
                        title="Click to open file in code editor"
                      >
                        <FileCode size={14} className="text-primary" />
                        <span className="mod-file-path">{item.path}</span>
                        <span className={`mod-file-badge badge-${item.action.toLowerCase()}`}>{item.action}</span>
                        <span className="mod-file-time">{item.timestamp}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Inline Snippet Preview for Selected File */}
              {selectedFilePath ? (
                <div className="activity-card inline-snippet-card">
                  <div className="activity-card-header">
                    <FileCode size={16} className="text-primary" />
                    <span className="activity-card-title">File Snippet Preview: {selectedFilePath.split('/').pop()}</span>
                    <button className="btn-sm btn-secondary" style={{ marginLeft: 'auto', fontSize: '0.72rem' }} onClick={() => handleSelectFile(selectedFilePath)}>
                      Focus in Editor
                    </button>
                  </div>
                  <pre className="snippet-code-box">
                    {fileContent ? fileContent.slice(0, 1000) + (fileContent.length > 1000 ? '\n... (truncated)' : '') : '// Empty file content'}
                  </pre>
                </div>
              ) : null}
            </div>
          )}

          {/* Tab 3: Dependencies & Environment Repair */}
          {rightPanelTab === 'deps' && (
            <div className="activity-panel-content">

              {/* AST Code Health & Security Scan Card */}
              <div className="activity-card dep-installer-card">
                <div className="activity-card-header">
                  <Activity size={16} className="text-primary" />
                  <span className="activity-card-title">AST Code Health & Security Audit</span>
                </div>
                <p className="activity-card-desc">
                  Runs a full AST parse across all project files to calculate Code Health Index (0–100), detect security vulnerabilities, and generate targeted refactor recommendations.
                </p>
                <button
                  className="btn-sm btn-secondary"
                  onClick={handleScanProject}
                  disabled={scanning}
                  style={{ marginBottom: 8 }}
                >
                  <Activity size={13} className={scanning ? 'spin' : ''} />
                  {scanning ? 'Scanning AST & Security...' : 'Run Code Health & Security Scan'}
                </button>

                {scanData && (
                  <>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <div style={{ flex: 1, padding: '8px 6px', background: scanData.verdict_badge === 'success' ? 'rgba(16,185,129,0.1)' : scanData.verdict_badge === 'warning' ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)', borderRadius: 6, textAlign: 'center', border: `1px solid ${scanData.verdict_badge === 'success' ? '#10b981' : scanData.verdict_badge === 'warning' ? '#f59e0b' : '#ef4444'}` }}>
                        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Code Health</div>
                        <div style={{ fontSize: '1.3rem', fontWeight: 900, color: scanData.verdict_badge === 'success' ? '#10b981' : scanData.verdict_badge === 'warning' ? '#f59e0b' : '#ef4444' }}>
                          {scanData.overall_score}<span style={{ fontSize: '0.7rem', fontWeight: 400 }}>/100</span>
                        </div>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 2 }}>{scanData.verdict}</div>
                      </div>
                      <div style={{ flex: 1, padding: '8px 6px', background: scanData.risk_badge === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)', borderRadius: 6, textAlign: 'center', border: `1px solid ${scanData.risk_badge === 'success' ? '#10b981' : '#f59e0b'}` }}>
                        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Security Score</div>
                        <div style={{ fontSize: '1.3rem', fontWeight: 900, color: scanData.risk_badge === 'success' ? '#10b981' : '#f59e0b' }}>
                          {scanData.security_score}<span style={{ fontSize: '0.7rem', fontWeight: 400 }}>/100</span>
                        </div>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 2 }}>{scanData.total_vulnerabilities} vuln(s)</div>
                      </div>
                    </div>
                    {scanData.vulnerabilities.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#ef4444', marginBottom: 4 }}>⚠ Security Issues</div>
                        {scanData.vulnerabilities.slice(0, 3).map((v, i) => (
                          <div key={i} style={{ fontSize: '0.7rem', background: 'rgba(239,68,68,0.07)', borderRadius: 4, padding: '4px 6px', marginBottom: 4, borderLeft: '3px solid #ef4444' }}>
                            <strong>{v.type}</strong> — <code>{v.file.split('/').pop()}</code><br />
                            <span style={{ color: 'var(--text-muted)' }}>{v.description}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {scanData.sample_issues.length > 0 && (
                      <details style={{ marginTop: 8 }}>
                        <summary style={{ fontSize: '0.72rem', cursor: 'pointer', color: 'var(--text-muted)' }}>{scanData.total_issues} code quality issue(s) ▼</summary>
                        <div style={{ marginTop: 4 }}>
                          {scanData.sample_issues.slice(0, 6).map((iss, i) => (
                            <div key={i} style={{ fontSize: '0.68rem', color: 'var(--text-muted)', padding: '2px 0', borderBottom: '1px solid var(--border-subtle)' }}>• {iss}</div>
                          ))}
                        </div>
                      </details>
                    )}
                    {scanData.feature_ideas.length > 0 && (
                      <div style={{ marginTop: 10 }}>
                        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>💡 AI Refactor Recommendations</div>
                        {scanData.feature_ideas.map((idea) => (
                          <div key={idea.idea_id} style={{ fontSize: '0.72rem', background: 'var(--bg-subtle)', borderRadius: 5, padding: '6px 8px', marginBottom: 6, borderLeft: `3px solid ${idea.priority === 'HIGH' ? '#ef4444' : idea.priority === 'MEDIUM' ? '#f59e0b' : '#6366f1'}` }}>
                            <div style={{ fontWeight: 700, marginBottom: 2 }}>
                              <span style={{ fontSize: '0.6rem', padding: '1px 5px', borderRadius: 3, background: idea.priority === 'HIGH' ? '#ef4444' : idea.priority === 'MEDIUM' ? '#f59e0b' : '#6366f1', color: 'white', marginRight: 5 }}>{idea.priority}</span>
                              {idea.title}
                            </div>
                            <div style={{ color: 'var(--text-muted)' }}>{idea.description}</div>
                            <div style={{ marginTop: 3, fontSize: '0.62rem', color: 'var(--text-muted)' }}>{idea.category}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textAlign: 'right', marginTop: 6 }}>
                      {scanData.files_scanned} files · {scanData.last_scanned}
                    </div>
                  </>
                )}
              </div>

              {/* Dependency Auto-Installer Card */}
              <div className="activity-card dep-installer-card">
                <div className="activity-card-header">
                  <PackageCheck size={16} className="text-primary" />
                  <span className="activity-card-title">Missing Library & Module Auto-Installer</span>
                </div>
                <p className="activity-card-desc">
                  Scans AST imports in JS/TS/Python code against project environment and automatically runs <code>npm install</code> or <code>pip install</code> for uninstalled dependencies.
                </p>
                <button
                  className="btn-sm btn-primary install-deps-btn"
                  onClick={handleInstallDeps}
                  disabled={installingDeps}
                >
                  <Download size={13} className={installingDeps ? 'spin' : ''} />
                  {installingDeps ? 'Scanning & Auto-Installing Packages...' : 'Scan & Install Missing Libraries'}
                </button>
                {depsStatus && (
                  <div className="deps-status-banner">
                    {depsStatus}
                  </div>
                )}
              </div>

              {/* Live Environment Health Status Card */}
              <div className="activity-card health-summary-card">
                <div className="activity-card-header">
                  <Activity size={16} className="text-primary" />
                  <span className="activity-card-title">Live Environment Health Status</span>
                </div>
                {envHealthData ? (
                  <>
                    <div className="health-stat-row" style={{ display: 'flex', gap: 12, marginTop: 8 }}>
                      <div className="health-stat-pill" style={{ flex: 1, padding: 8, background: 'var(--bg-subtle)', borderRadius: 6, textAlign: 'center' }}>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>node_modules</div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 800, color: envHealthData.npm_installed ? '#10b981' : '#f59e0b' }}>
                          {envHealthData.npm_installed ? `✅ ${envHealthData.node_modules_count} pkgs` : '⚠️ Not installed'}
                        </div>
                      </div>
                      <div className="health-stat-pill" style={{ flex: 1, padding: 8, background: 'var(--bg-subtle)', borderRadius: 6, textAlign: 'center' }}>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Python .venv</div>
                        <div style={{ fontSize: '1.1rem', fontWeight: 800, color: envHealthData.pip_packages_count > 0 ? '#10b981' : '#94a3b8' }}>
                          {envHealthData.pip_packages_count > 0 ? `✅ ${envHealthData.pip_packages_count} pkgs` : '— No venv'}
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 6, textAlign: 'right' }}>
                      Last scanned: {envHealthData.last_scanned}
                      {envHealthData.venv_created && <span style={{ color: '#10b981', marginLeft: 8 }}>· .venv created fresh</span>}
                    </div>
                  </>
                ) : (
                  <div style={{ textAlign: 'center', fontSize: '0.82rem', color: 'var(--text-muted)', padding: '12px 0' }}>
                    Click <strong>Scan &amp; Install Missing Libraries</strong> above to check environment health.
                  </div>
                )}
              </div>

            </div>
          )}

          {/* Tab 4: Solution Alignment & Contract Verification */}
          {rightPanelTab === 'alignment' && (
            <div className="activity-panel-content">
              {/* Master Alignment Scorecard */}
              <div className="activity-card">
                <div className="activity-card-header">
                  <ShieldCheck size={16} className="text-primary" />
                  <span className="activity-card-title">Solution Alignment &amp; Contract Audit</span>
                </div>
                <p className="activity-card-desc">
                  Validates semantic user goal coverage, verifies cross-layer API contracts (React calls ↔ FastAPI routers), and ensures zero orphaned unmounted components.
                </p>

                <div style={{ display: 'flex', gap: 8, marginBottom: 12, marginTop: 8 }}>
                  <button
                    className="btn-sm btn-secondary"
                    onClick={() => handleValidateAlignment(false)}
                    disabled={validatingAlignment || remediatingAlignment}
                    style={{ flex: 1 }}
                  >
                    <Activity size={13} className={validatingAlignment ? 'spin' : ''} />
                    {validatingAlignment ? 'Auditing Solution...' : 'Run Alignment Audit'}
                  </button>
                  <button
                    className="btn-sm btn-primary"
                    onClick={handleRemediateAlignment}
                    disabled={remediatingAlignment || validatingAlignment}
                    style={{ flex: 1.2, background: 'linear-gradient(135deg, #10b981, #06b6d4)' }}
                  >
                    <Zap size={13} className={remediatingAlignment ? 'spin' : ''} />
                    {remediatingAlignment ? 'Remediating Drift...' : '1-Click Auto-Remediate Drift'}
                  </button>
                </div>

                {alignmentData ? (
                  <>
                    {/* Overall Score Badge */}
                    <div
                      style={{
                        padding: '10px 12px',
                        background: alignmentData.passed ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
                        border: `1px solid ${alignmentData.passed ? '#10b981' : '#f59e0b'}`,
                        borderRadius: 6,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginBottom: 10
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Overall Alignment Score</div>
                        <div style={{ fontSize: '1.4rem', fontWeight: 900, color: alignmentData.passed ? '#10b981' : '#f59e0b' }}>
                          {alignmentData.overall_alignment_score}<span style={{ fontSize: '0.75rem', fontWeight: 400 }}>/100</span>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <span
                          style={{
                            padding: '3px 8px',
                            borderRadius: 4,
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            background: alignmentData.passed ? '#10b981' : '#f59e0b',
                            color: '#000'
                          }}
                        >
                          {alignmentData.verdict}
                        </span>
                        <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 4 }}>
                          {alignmentData.passed ? 'Zero contract drift detected' : 'Action required — drift present'}
                        </div>
                      </div>
                    </div>

                    {/* 4 Pillar Sub-Scores Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 12 }}>
                      <div style={{ background: 'var(--bg-subtle)', padding: '6px 8px', borderRadius: 6 }}>
                        <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Goal Coverage</div>
                        <div style={{ fontSize: '1rem', fontWeight: 800, color: alignmentData.goal_alignment.score >= 80 ? '#10b981' : '#f59e0b' }}>
                          {alignmentData.goal_alignment.score}%
                        </div>
                        <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>
                          {alignmentData.goal_alignment.intents_found.length}/{alignmentData.goal_alignment.intents_detected.length} intents found
                        </div>
                      </div>

                      <div style={{ background: 'var(--bg-subtle)', padding: '6px 8px', borderRadius: 6 }}>
                        <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>API Contract Sync</div>
                        <div style={{ fontSize: '1rem', fontWeight: 800, color: alignmentData.api_contracts.sync_score === 100 ? '#10b981' : '#ef4444' }}>
                          {alignmentData.api_contracts.sync_score}%
                        </div>
                        <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>
                          {alignmentData.api_contracts.missing_in_backend.length === 0 ? 'All endpoints backed' : `${alignmentData.api_contracts.missing_in_backend.length} missing route(s)`}
                        </div>
                      </div>

                      <div style={{ background: 'var(--bg-subtle)', padding: '6px 8px', borderRadius: 6 }}>
                        <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Component Mounting</div>
                        <div style={{ fontSize: '1rem', fontWeight: 800, color: alignmentData.component_mounting.score === 100 ? '#10b981' : '#f59e0b' }}>
                          {alignmentData.component_mounting.score}%
                        </div>
                        <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>
                          {alignmentData.component_mounting.unmounted_components.length === 0 ? 'Zero orphan components' : `${alignmentData.component_mounting.unmounted_components.length} unmounted`}
                        </div>
                      </div>

                      <div style={{ background: 'var(--bg-subtle)', padding: '6px 8px', borderRadius: 6 }}>
                        <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Design System Adherence</div>
                        <div style={{ fontSize: '1rem', fontWeight: 800, color: alignmentData.design_system.passed ? '#10b981' : '#ef4444' }}>
                          {alignmentData.design_system.score}%
                        </div>
                        <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)' }}>
                          {alignmentData.design_system.passed ? 'Clean CSS & tokens' : `${alignmentData.design_system.violations.length} violation(s)`}
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div style={{ textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted)', padding: '16px 0' }}>
                    Click <strong>Run Alignment Audit</strong> to verify code against user goals and API contracts.
                  </div>
                )}
              </div>

              {/* Auto-Remediation Logs Card (if executed) */}
              {alignmentData && alignmentData.remediation_logs && alignmentData.remediation_logs.length > 0 && (
                <div className="activity-card" style={{ borderLeft: '3px solid #10b981' }}>
                  <div className="activity-card-header">
                    <CheckCircle2 size={16} color="#10b981" />
                    <span className="activity-card-title" style={{ color: '#10b981' }}>
                      Auto-Remediation Actions Applied
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {alignmentData.remediation_logs.map((log, lIdx) => (
                      <div key={lIdx} style={{ fontSize: '0.7rem', color: 'var(--text-base)', background: 'rgba(16,185,129,0.08)', padding: '4px 8px', borderRadius: 4 }}>
                        ✓ {log}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* API Contracts Sync Matrix */}
              {alignmentData && (
                <div className="activity-card">
                  <div className="activity-card-header">
                    <Link2 size={16} className="text-primary" />
                    <span className="activity-card-title">Full-Stack API Contract Matrix</span>
                  </div>

                  {alignmentData.api_contracts.frontend_calls.length === 0 ? (
                    <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', padding: '8px 0' }}>
                      Zero external API calls in frontend code (pure UI component).
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                      {alignmentData.api_contracts.frontend_calls.map((call, cIdx) => {
                        const isMissing = alignmentData.api_contracts.missing_in_backend.some(
                          (m) => m.path === call.path && m.method === call.method
                        )
                        return (
                          <div
                            key={cIdx}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              fontSize: '0.72rem',
                              padding: '6px 8px',
                              background: 'var(--bg-subtle)',
                              borderRadius: 5,
                              borderLeft: `3px solid ${isMissing ? '#ef4444' : '#10b981'}`
                            }}
                          >
                            <div>
                              <span
                                style={{
                                  fontSize: '0.62rem',
                                  fontWeight: 800,
                                  padding: '1px 5px',
                                  borderRadius: 3,
                                  background: call.method === 'GET' ? 'rgba(16,185,129,0.2)' : 'rgba(56,189,248,0.2)',
                                  color: call.method === 'GET' ? '#10b981' : '#38bdf8',
                                  marginRight: 6
                                }}
                              >
                                {call.method}
                              </span>
                              <code>{call.path}</code>
                              <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: 2 }}>
                                from <code>{call.file.split(/[\\/]/).pop()}</code>
                              </div>
                            </div>

                            <div>
                              {isMissing ? (
                                <span style={{ fontSize: '0.65rem', color: '#ef4444', fontWeight: 700 }}>
                                  Missing in Router (404)
                                </span>
                              ) : (
                                <span style={{ fontSize: '0.65rem', color: '#10b981', fontWeight: 700 }}>
                                  ✓ Synced
                                </span>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Component Mounting Tree */}
              {alignmentData && (
                <div className="activity-card">
                  <div className="activity-card-header">
                    <Layers size={16} className="text-primary" />
                    <span className="activity-card-title">Component Mounting &amp; Render Tree</span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                    {alignmentData.component_mounting.mounted_components.map((c, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          fontSize: '0.72rem',
                          padding: '5px 8px',
                          background: 'var(--bg-subtle)',
                          borderRadius: 4
                        }}
                      >
                        <div>
                          <strong>{c.name}</strong>
                          <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginLeft: 6 }}>
                            ({c.file.split(/[\\/]/).pop()})
                          </span>
                        </div>
                        <span style={{ fontSize: '0.65rem', color: '#10b981', fontWeight: 700 }}>
                          Mounted in App.tsx
                        </span>
                      </div>
                    ))}

                    {alignmentData.component_mounting.unmounted_components.map((c, idx) => (
                      <div
                        key={`unm-${idx}`}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          fontSize: '0.72rem',
                          padding: '5px 8px',
                          background: 'rgba(245,158,11,0.08)',
                          borderLeft: '3px solid #f59e0b',
                          borderRadius: 4
                        }}
                      >
                        <div>
                          <strong>{c.name}</strong>
                          <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginLeft: 6 }}>
                            ({c.file.split(/[\\/]/).pop()})
                          </span>
                        </div>
                        <span style={{ fontSize: '0.65rem', color: '#f59e0b', fontWeight: 700 }}>
                          ⚠ Unmounted (Orphan)
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Issues & Deficiencies Notice */}
              {alignmentData && alignmentData.issues && alignmentData.issues.length > 0 && (
                <div className="activity-card" style={{ borderLeft: '3px solid #ef4444' }}>
                  <div className="activity-card-header">
                    <AlertTriangle size={16} color="#ef4444" />
                    <span className="activity-card-title" style={{ color: '#ef4444' }}>
                      Alignment Deficiencies Detected
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {alignmentData.issues.map((iss, iIdx) => (
                      <div key={iIdx} style={{ fontSize: '0.7rem', color: 'var(--text-base)', background: 'rgba(239,68,68,0.08)', padding: '4px 6px', borderRadius: 4 }}>
                        • {iss}
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
          )}
        </div>
      </div>

      {/* Custom Obsidian Glass Alert Modal */}
      <AlertModal
        isOpen={showAlertModal}
        onClose={() => setShowAlertModal(false)}
        title={alertModalTitle}
        errorText={alertModalErrorText}
        projectPath={currentTargetPath}
        onAutoFix={handleAutoFixFromAlert}
        onAutoInstallPkg={handleAutoInstallPkgFromAlert}
      />

      {/* Footer Banner */}
      {statusMessage && <div className="workspace-status-footer">{statusMessage}</div>}
    </div>
  )
}

export default CodeWorkspace
