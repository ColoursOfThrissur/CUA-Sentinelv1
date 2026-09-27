import { useState, useEffect } from 'react'
import {
  Check,
  Eye,
  Pencil,
  ShieldAlert,
  TriangleAlert,
  X,
  Sparkles,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronUp,
  FolderGit2
} from 'lucide-react'
import { useSentinelStore } from '../../store'
import { hitlApi, improvementsApi, ImprovementProposal } from '../../api'
import './HITLPanel.css'

const RISK: Record<number, { label: string; cardClass: string; textClass: string; Icon: typeof Eye }> = {
  0: { label: 'Read Only',        cardClass: 'risk-card-0', textClass: 'risk-text-0', Icon: Eye },
  1: { label: 'Local Write',      cardClass: 'risk-card-1', textClass: 'risk-text-1', Icon: Pencil },
  2: { label: 'Project Mutation', cardClass: 'risk-card-2', textClass: 'risk-text-2', Icon: TriangleAlert },
  3: { label: 'Destructive',      cardClass: 'risk-card-3', textClass: 'risk-text-3', Icon: ShieldAlert },
}

export default function HITLPanel() {
  const { hitlPending, setHitlPending } = useSentinelStore()
  const pendingApprovals = Array.isArray(hitlPending) ? hitlPending : []

  const [activeTab, setActiveTab] = useState<'approvals' | 'suggestions'>('approvals')
  const [proposals, setProposals] = useState<ImprovementProposal[]>([])
  const [loadingProposals, setLoadingProposals] = useState(false)
  const [actionInProgress, setActionInProgress] = useState<Record<string, 'approving' | 'rejecting'>>({})
  const [expandedProposals, setExpandedProposals] = useState<Record<string, boolean>>({})
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

  const fetchProposals = async () => {
    setLoadingProposals(true)
    try {
      const res = await improvementsApi.list('PENDING')
      setProposals(Array.isArray(res.data) ? res.data : [])
    } catch {
      // Keep existing list on transient failure
    } finally {
      setLoadingProposals(false)
    }
  }

  useEffect(() => {
    fetchProposals()
    const timer = setInterval(fetchProposals, 12000)
    return () => clearInterval(timer)
  }, [])

  // Auto-switch to suggestions if approvals is 0 and suggestions > 0 on first load
  useEffect(() => {
    if (pendingApprovals.length === 0 && proposals.length > 0 && activeTab === 'approvals') {
      setActiveTab('suggestions')
    }
  }, [proposals.length, pendingApprovals.length])

  const [resolvingAll, setResolvingAll] = useState(false)

  const resolveApproval = async (approvalId: string, approved: boolean) => {
    await hitlApi.resolve(approvalId, approved)
    setHitlPending(pendingApprovals.filter((h) => h.approval_id !== approvalId))
  }

  const handleApproveAll = async () => {
    if (pendingApprovals.length === 0) return
    setResolvingAll(true)
    try {
      await hitlApi.resolveAll(true, pendingApprovals.map((h) => h.approval_id))
      setHitlPending([])
      setStatusMessage('Approved all pending actions')
      setTimeout(() => setStatusMessage(null), 3000)
    } catch {
      setStatusMessage('Failed to approve all actions')
      setTimeout(() => setStatusMessage(null), 3000)
    } finally {
      setResolvingAll(false)
    }
  }

  const handleApproveProposal = async (proposalId: string) => {
    setActionInProgress((prev) => ({ ...prev, [proposalId]: 'approving' }))
    try {
      const res = await improvementsApi.approve(proposalId)
      setProposals((prev) => prev.filter((p) => p.proposal_id !== proposalId))
      setStatusMessage(`Enqueued refactor task ${res.data?.enqueued_task_id ? `#${res.data.enqueued_task_id.slice(0, 8)}` : ''}`)
      setTimeout(() => setStatusMessage(null), 4000)
    } catch {
      setStatusMessage('Failed to approve proposal')
      setTimeout(() => setStatusMessage(null), 4000)
    } finally {
      setActionInProgress((prev) => {
        const next = { ...prev }
        delete next[proposalId]
        return next
      })
    }
  }

  const handleRejectProposal = async (proposalId: string) => {
    setActionInProgress((prev) => ({ ...prev, [proposalId]: 'rejecting' }))
    try {
      await improvementsApi.reject(proposalId)
      setProposals((prev) => prev.filter((p) => p.proposal_id !== proposalId))
    } catch {
      setStatusMessage('Failed to reject proposal')
      setTimeout(() => setStatusMessage(null), 4000)
    } finally {
      setActionInProgress((prev) => {
        const next = { ...prev }
        delete next[proposalId]
        return next
      })
    }
  }

  const toggleExpand = (proposalId: string) => {
    setExpandedProposals((prev) => ({ ...prev, [proposalId]: !prev[proposalId] }))
  }

  return (
    <div className="card hitl-panel">
      <div className="hitl-header">
        <div className="hitl-tabs">
          <button
            type="button"
            className={`hitl-tab-btn ${activeTab === 'approvals' ? 'active' : ''}`}
            onClick={() => setActiveTab('approvals')}
          >
            Approvals
            {pendingApprovals.length > 0 && (
              <span className="hitl-tab-badge">{pendingApprovals.length}</span>
            )}
          </button>
          <button
            type="button"
            className={`hitl-tab-btn ${activeTab === 'suggestions' ? 'active' : ''}`}
            onClick={() => setActiveTab('suggestions')}
          >
            <Sparkles size={12} />
            Suggestions
            {proposals.length > 0 && (
              <span className="hitl-tab-badge badge-cyan">{proposals.length}</span>
            )}
          </button>
        </div>

        <button
          type="button"
          onClick={fetchProposals}
          className="hitl-refresh-btn"
          title="Refresh improvement suggestions"
          disabled={loadingProposals}
        >
          <RefreshCw size={13} className={loadingProposals ? 'animate-spin' : ''} />
        </button>
      </div>

      {statusMessage && (
        <div style={{ fontSize: '0.74rem', color: 'var(--c-cyan)', background: 'rgba(6,182,212,0.1)', padding: '4px 8px', borderRadius: 4 }}>
          {statusMessage}
        </div>
      )}

      {/* Tab: Tool Execution Approvals */}
      {activeTab === 'approvals' && (
        <>
          {pendingApprovals.length === 0 ? (
            <div className="hitl-empty">
              <div className="empty-icon hitl-empty-icon"><Check size={15} /></div>
              <p className="hitl-empty-text">All tool actions approved</p>
            </div>
          ) : (
            <>
              {pendingApprovals.length > 1 && (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
                  <button
                    type="button"
                    className="btn-approve"
                    style={{ padding: '6px 14px', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
                    onClick={handleApproveAll}
                    disabled={resolvingAll}
                  >
                    <Check size={14} />
                    {resolvingAll ? 'Approving All...' : `Approve All (${pendingApprovals.length})`}
                  </button>
                </div>
              )}
              {pendingApprovals.map((h) => {
              const risk      = RISK[h.risk_level] ?? RISK[3]
              const RiskIcon  = risk.Icon
              const expiresIn = Math.max(0, Math.floor((new Date(h.expires_at).getTime() - Date.now()) / 60000))
              return (
                <div key={h.approval_id} className={`risk-card ${risk.cardClass} animate-fade-in`}>
                  <div className="risk-card-header">
                    <span className={`risk-card-label ${risk.textClass}`}><RiskIcon size={13} />{risk.label}</span>
                    <span className="risk-card-expiry">{expiresIn > 0 ? `${expiresIn}m left` : 'expiring'}</span>
                  </div>
                  <p className="risk-card-desc">{h.action_description}</p>
                  <div className="risk-card-actions">
                    <button className="btn-approve" onClick={() => resolveApproval(h.approval_id, true)}>
                      <Check size={13} />Approve
                    </button>
                    <button className="btn-reject" onClick={() => resolveApproval(h.approval_id, false)}>
                      <X size={13} />Reject
                    </button>
                  </div>
                </div>
              )
            })}
          </>
          )}
        </>
      )}

      {/* Tab: Autonomous Suggestions Feed */}
      {activeTab === 'suggestions' && (
        <>
          {loadingProposals && proposals.length === 0 ? (
            <div className="hitl-empty">
              <Loader2 size={16} className="animate-spin" color="var(--c-cyan)" />
              <p className="hitl-empty-text">Scanning project improvements...</p>
            </div>
          ) : proposals.length === 0 ? (
            <div className="hitl-empty">
              <div className="empty-icon hitl-empty-icon"><Check size={15} /></div>
              <p className="hitl-empty-text">No pending suggestions. ImprovementScout is monitoring your codebases.</p>
            </div>
          ) : (
            proposals.map((p) => {
              const riskClass = p.risk_level === 'HIGH' ? 'risk-pill-high' : (p.risk_level === 'MEDIUM' ? 'risk-pill-medium' : 'risk-pill-low')
              const isExpanded = Boolean(expandedProposals[p.proposal_id])
              const action = actionInProgress[p.proposal_id]

              return (
                <div key={p.proposal_id} className="suggestion-card animate-fade-in">
                  <div className="suggestion-header">
                    <span className="suggestion-proj">
                      <FolderGit2 size={11} style={{ display: 'inline', marginRight: 4 }} />
                      {p.project_name || p.project_id}
                    </span>
                    <span className={riskClass}>{p.risk_level || 'LOW'} RISK</span>
                  </div>

                  <div className="suggestion-title">{p.title}</div>
                  <div className="suggestion-rationale">{p.rationale}</div>

                  {Array.isArray(p.affected_files) && p.affected_files.length > 0 && (
                    <div className="suggestion-files">
                      {p.affected_files.map((f, i) => (
                        <span key={i} className="suggestion-file-chip" title={f}>
                          {f.split(/[\\/]/).pop()}
                        </span>
                      ))}
                    </div>
                  )}

                  {p.suggested_changes && (
                    <div>
                      <button
                        type="button"
                        className="suggestion-toggle-btn"
                        onClick={() => toggleExpand(p.proposal_id)}
                      >
                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                        {isExpanded ? 'Hide changes' : 'Inspect suggested changes'}
                      </button>
                      {isExpanded && (
                        <pre className="suggestion-details-box" style={{ marginTop: 6 }}>
                          {p.suggested_changes}
                        </pre>
                      )}
                    </div>
                  )}

                  <div className="suggestion-actions">
                    <button
                      type="button"
                      className="btn-approve"
                      onClick={() => handleApproveProposal(p.proposal_id)}
                      disabled={Boolean(action)}
                    >
                      <Check size={13} />
                      {action === 'approving' ? 'Approving...' : 'Approve'}
                    </button>
                    <button
                      type="button"
                      className="btn-reject"
                      onClick={() => handleRejectProposal(p.proposal_id)}
                      disabled={Boolean(action)}
                    >
                      <X size={13} />
                      {action === 'rejecting' ? 'Rejecting...' : 'Reject'}
                    </button>
                  </div>
                </div>
              )
            })
          )}
        </>
      )}
    </div>
  )
}
