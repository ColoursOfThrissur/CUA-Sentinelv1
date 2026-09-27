import React, { useState, useEffect } from 'react'
import {
  PackageCheck,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  X,
  RefreshCw,
  Terminal,
  Ban
} from 'lucide-react'
import { dependencyPlansApi } from '../../api'
import './DependencyPlansModal.css'

interface DependencyPlan {
  plan_id: string
  project_path: string
  ecosystem: string
  package_name: string
  requested_spec: string
  reason: string
  evidence: Array<{ source?: string; manifest?: string }>
  manifest_path: string
  lockfile_path: string | null
  command: string[]
  plan_hash: string
  status: 'PLANNED' | 'AWAITING_APPROVAL' | 'APPROVED' | 'EXECUTING' | 'SUCCEEDED' | 'FAILED' | 'REJECTED' | 'EXPIRED'
  is_pinned: boolean
  created_at: string
  expires_at: string
  approved_at: string | null
  executed_at: string | null
  result: Record<string, any> | null
}

interface Props {
  isOpen: boolean
  onClose: () => void
  projectPath?: string
}

export const DependencyPlansModal: React.FC<Props> = ({ isOpen, onClose, projectPath }) => {
  const [plans, setPlans] = useState<DependencyPlan[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [filter, setFilter] = useState<'ALL' | 'PENDING' | 'APPROVED' | 'HISTORY'>('ALL')
  const [allowUnpinnedMap, setAllowUnpinnedMap] = useState<Record<string, boolean>>({})
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})
  const [actionError, setActionError] = useState<Record<string, string>>({})

  const fetchPlans = async () => {
    setLoading(true)
    try {
      const resp = await dependencyPlansApi.list()
      const allPlans: DependencyPlan[] = resp.data || []
      const filtered = projectPath
        ? allPlans.filter(p => p.project_path.toLowerCase() === projectPath.toLowerCase())
        : allPlans
      setPlans(filtered)
    } catch (err: any) {
      console.error('Failed to load dependency plans:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      fetchPlans()
    }
  }, [isOpen, projectPath])

  if (!isOpen) return null

  const handleApprove = async (plan: DependencyPlan) => {
    const unpinnedAllowed = allowUnpinnedMap[plan.plan_id] || false
    setActionLoading(prev => ({ ...prev, [plan.plan_id]: true }))
    setActionError(prev => ({ ...prev, [plan.plan_id]: '' }))
    try {
      await dependencyPlansApi.approve(plan.plan_id, plan.plan_hash, unpinnedAllowed)
      await fetchPlans()
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Approval failed'
      setActionError(prev => ({ ...prev, [plan.plan_id]: msg }))
    } finally {
      setActionLoading(prev => ({ ...prev, [plan.plan_id]: false }))
    }
  }

  const handleExecute = async (plan: DependencyPlan) => {
    setActionLoading(prev => ({ ...prev, [plan.plan_id]: true }))
    setActionError(prev => ({ ...prev, [plan.plan_id]: '' }))
    try {
      await dependencyPlansApi.execute(plan.plan_id, plan.plan_hash)
      await fetchPlans()
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Execution failed'
      setActionError(prev => ({ ...prev, [plan.plan_id]: msg }))
    } finally {
      setActionLoading(prev => ({ ...prev, [plan.plan_id]: false }))
    }
  }

  const handleReject = async (plan: DependencyPlan) => {
    const reason = window.prompt('Reason for rejecting this dependency plan:', 'Rejected by operator')
    if (reason === null) return
    setActionLoading(prev => ({ ...prev, [plan.plan_id]: true }))
    try {
      await dependencyPlansApi.reject(plan.plan_id, reason)
      await fetchPlans()
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Rejection failed'
      setActionError(prev => ({ ...prev, [plan.plan_id]: msg }))
    } finally {
      setActionLoading(prev => ({ ...prev, [plan.plan_id]: false }))
    }
  }

  const handleRollback = async (plan: DependencyPlan) => {
    if (!window.confirm(`Rollback pre-execution backup for ${plan.package_name}?`)) return
    setActionLoading(prev => ({ ...prev, [plan.plan_id]: true }))
    try {
      await dependencyPlansApi.rollback(plan.plan_id)
      await fetchPlans()
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Rollback failed'
      setActionError(prev => ({ ...prev, [plan.plan_id]: msg }))
    } finally {
      setActionLoading(prev => ({ ...prev, [plan.plan_id]: false }))
    }
  }

  const displayedPlans = plans.filter(p => {
    if (filter === 'PENDING') return p.status === 'PLANNED' || p.status === 'AWAITING_APPROVAL'
    if (filter === 'APPROVED') return p.status === 'APPROVED'
    if (filter === 'HISTORY') return p.status === 'SUCCEEDED' || p.status === 'FAILED' || p.status === 'REJECTED' || p.status === 'EXPIRED'
    return true
  })

  return (
    <div className="dep-modal-overlay" onClick={onClose}>
      <div className="dep-modal" onClick={e => e.stopPropagation()}>
        <div className="dep-modal-header">
          <div className="dep-header-title">
            <PackageCheck size={20} className="text-cyan-400" />
            <h3>Dependency Change Governance</h3>
            {loading && <RefreshCw size={15} className="dep-icon-spin text-slate-400" />}
          </div>
          <button className="dep-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="dep-filter-bar">
          <button
            className={`dep-filter-btn ${filter === 'ALL' ? 'active' : ''}`}
            onClick={() => setFilter('ALL')}
          >
            All Plans ({plans.length})
          </button>
          <button
            className={`dep-filter-btn ${filter === 'PENDING' ? 'active' : ''}`}
            onClick={() => setFilter('PENDING')}
          >
            Awaiting Approval ({plans.filter(p => p.status === 'PLANNED' || p.status === 'AWAITING_APPROVAL').length})
          </button>
          <button
            className={`dep-filter-btn ${filter === 'APPROVED' ? 'active' : ''}`}
            onClick={() => setFilter('APPROVED')}
          >
            Approved ({plans.filter(p => p.status === 'APPROVED').length})
          </button>
          <button
            className={`dep-filter-btn ${filter === 'HISTORY' ? 'active' : ''}`}
            onClick={() => setFilter('HISTORY')}
          >
            History ({plans.filter(p => ['SUCCEEDED', 'FAILED', 'REJECTED', 'EXPIRED'].includes(p.status)).length})
          </button>
        </div>

        <div className="dep-modal-body">
          {displayedPlans.length === 0 ? (
            <div className="dep-empty-state">
              <p>No dependency plans found for this filter.</p>
              <small>Plans are generated automatically by import scanning before any packages are modified.</small>
            </div>
          ) : (
            displayedPlans.map(plan => {
              const isLoading = actionLoading[plan.plan_id]
              const errorMsg = actionError[plan.plan_id]
              return (
                <div key={plan.plan_id} className="dep-plan-card">
                  <div className="dep-plan-card-header">
                    <div className="dep-pkg-meta">
                      <span className="dep-pkg-name">{plan.package_name}</span>
                      <span className={`dep-eco-badge ${plan.ecosystem}`}>{plan.ecosystem}</span>
                      <span className={`dep-pin-badge ${plan.is_pinned ? 'pinned' : 'unpinned'}`}>
                        {plan.is_pinned ? 'PINNED' : 'UNPINNED SPEC'}
                      </span>
                    </div>
                    <span className={`dep-status-badge ${plan.status.toLowerCase()}`}>
                      {plan.status.replace('_', ' ')}
                    </span>
                  </div>

                  <div className="dep-plan-detail">
                    <div><strong>Spec:</strong> <code>{plan.requested_spec}</code></div>
                    <div><strong>Reason:</strong> {plan.reason}</div>
                    <div><strong>Manifest:</strong> <code>{plan.manifest_path}</code></div>
                  </div>

                  <div className="dep-cmd-box">
                    <Terminal size={14} className="dep-cmd-prefix" />
                    <span>{plan.command.join(' ')}</span>
                  </div>

                  {errorMsg && (
                    <div className="dep-error-banner">
                      <AlertTriangle size={14} /> {errorMsg}
                    </div>
                  )}

                  {plan.result?.error && (
                    <div className="dep-error-banner">
                      <AlertTriangle size={14} /> Execution Error: {plan.result.error}
                    </div>
                  )}

                  <div className="dep-plan-actions">
                    {(plan.status === 'PLANNED' || plan.status === 'AWAITING_APPROVAL') && (
                      <>
                        {!plan.is_pinned && (
                          <label className="dep-unpinned-check">
                            <input
                              type="checkbox"
                              checked={allowUnpinnedMap[plan.plan_id] || false}
                              onChange={e =>
                                setAllowUnpinnedMap(prev => ({ ...prev, [plan.plan_id]: e.target.checked }))
                              }
                            />
                            Allow unpinned version constraint
                          </label>
                        )}
                        <button
                          className="dep-btn-reject"
                          onClick={() => handleReject(plan)}
                          disabled={isLoading}
                        >
                          <Ban size={14} /> Reject
                        </button>
                        <button
                          className="dep-btn-approve"
                          onClick={() => handleApprove(plan)}
                          disabled={isLoading}
                        >
                          <ShieldCheck size={14} /> {isLoading ? 'Approving...' : 'Approve Plan'}
                        </button>
                      </>
                    )}

                    {plan.status === 'APPROVED' && (
                      <button
                        className="dep-btn-execute"
                        onClick={() => handleExecute(plan)}
                        disabled={isLoading}
                      >
                        <Play size={14} /> {isLoading ? 'Installing...' : 'Execute Installation'}
                      </button>
                    )}

                    {plan.status === 'FAILED' && (
                      <button
                        className="dep-btn-rollback"
                        onClick={() => handleRollback(plan)}
                        disabled={isLoading}
                      >
                        <RotateCcw size={14} /> {isLoading ? 'Restoring...' : 'Rollback to Backup'}
                      </button>
                    )}

                    {plan.status === 'SUCCEEDED' && (
                      <div className="text-xs text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={14} /> Installed successfully ({plan.executed_at?.slice(0, 19).replace('T', ' ')})
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

export default DependencyPlansModal
