import React, { useState } from 'react'
import { ShieldAlert, Terminal, Wrench, PackageCheck, Copy, Check, X, Server, Layout } from 'lucide-react'
import './AlertModal.css'

export interface AlertModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  errorText: string
  projectPath?: string
  onAutoFix?: (errorDetail: string) => void
  onAutoInstallPkg?: (pkgName: string, ecosystem: string) => void
}

export const AlertModal: React.FC<AlertModalProps> = ({
  isOpen,
  onClose,
  title,
  errorText,
  onAutoFix,
  onAutoInstallPkg
}) => {
  const [activeTab, setActiveTab] = useState<'backend' | 'frontend'>('backend')
  const [copied, setCopied] = useState(false)
  const [fixing, setFixing] = useState(false)
  const [installing, setInstalling] = useState(false)

  if (!isOpen) return null

  // Parse missing package name if present
  let missingPkg = ''
  let ecosystem = 'npm'
  const pyMatch = errorText.match(/ModuleNotFoundError:\s*No module named ['"]([^'"]+)['"]/)
  if (pyMatch) {
    missingPkg = pyMatch[1]
    ecosystem = 'pip'
  } else {
    const npmMatch = errorText.match(/Failed to resolve import ["']([^"']+)["']/) || errorText.match(/Cannot find module ["']([^"']+)["']/)
    if (npmMatch) {
      missingPkg = npmMatch[1].split('/')[0]
      ecosystem = 'npm'
    }
  }

  const handleCopyTrace = () => {
    navigator.clipboard.writeText(errorText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleTriggerFix = async () => {
    if (!onAutoFix) return
    setFixing(true)
    try {
      await onAutoFix(errorText)
    } finally {
      setFixing(false)
      onClose()
    }
  }

  const handleTriggerInstall = async () => {
    if (!onAutoInstallPkg || !missingPkg) return
    setInstalling(true)
    try {
      await onAutoInstallPkg(missingPkg, ecosystem)
    } finally {
      setInstalling(false)
      onClose()
    }
  }

  return (
    <div className="alert-modal-overlay" onClick={onClose}>
      <div className="alert-modal-container glass-card" onClick={(e) => e.stopPropagation()}>

        {/* Modal Header */}
        <div className="alert-modal-header">
          <div className="alert-title-box">
            <ShieldAlert size={20} className="text-danger spin-pulse" />
            <span className="alert-modal-title">{title}</span>
          </div>
          <button className="alert-close-btn" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {/* Dual Stack Diagnostics Tabs */}
        <div className="alert-stack-tabs">
          <button
            className={`alert-tab-btn ${activeTab === 'backend' ? 'active' : ''}`}
            onClick={() => setActiveTab('backend')}
          >
            <Server size={14} /> Backend Diagnostics (FastAPI/Python)
          </button>
          <button
            className={`alert-tab-btn ${activeTab === 'frontend' ? 'active' : ''}`}
            onClick={() => setActiveTab('frontend')}
          >
            <Layout size={14} /> Frontend Diagnostics (React/Vite)
          </button>
        </div>

        {/* Traceback Body */}
        <div className="alert-modal-body">
          {missingPkg && (
            <div className="missing-pkg-banner">
              <PackageCheck size={16} className="text-warn" />
              <div>
                <strong>Missing {ecosystem.toUpperCase()} Library Detected:</strong> <code>{missingPkg}</code>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  This error was caused by an uninstalled package in your solution.
                </div>
              </div>
            </div>
          )}

          <div className="traceback-box">
            <div className="traceback-header">
              <Terminal size={13} /> Log / Traceback ({activeTab.toUpperCase()})
            </div>
            <pre className="traceback-content">
              {errorText || 'No explicit traceback logs captured.'}
            </pre>
          </div>
        </div>

        {/* Action Footer */}
        <div className="alert-modal-footer">
          <button className="btn-sm btn-ghost" onClick={handleCopyTrace}>
            {copied ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
            {copied ? 'Copied Traceback' : 'Copy Trace'}
          </button>

          <div style={{ display: 'flex', gap: 8 }}>
            {missingPkg && onAutoInstallPkg && (
              <button
                className="btn-sm btn-primary"
                onClick={handleTriggerInstall}
                disabled={installing}
                style={{ background: 'var(--c-cyan)', borderColor: 'var(--c-cyan)' }}
              >
                <PackageCheck size={13} className={installing ? 'spin' : ''} />
                {installing ? `Installing ${missingPkg}...` : `Auto-Install ${missingPkg}`}
              </button>
            )}

            {onAutoFix && (
              <button
                className="btn-sm btn-primary"
                onClick={handleTriggerFix}
                disabled={fixing}
              >
                <Wrench size={13} className={fixing ? 'spin' : ''} />
                {fixing ? 'Launching Auto-Fix Agent...' : '⚡ Auto-Fix Code with AI'}
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}

export default AlertModal
