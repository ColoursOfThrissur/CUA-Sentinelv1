import { Check, Eye, Pencil, ShieldAlert, TriangleAlert, X } from 'lucide-react'
import { useSentinelStore } from '../../store'
import { hitlApi } from '../../api'
import './HITLPanel.css'

const RISK: Record<number, { label: string; cardClass: string; textClass: string; Icon: typeof Eye }> = {
  0: { label: 'Read Only',        cardClass: 'risk-card-0', textClass: 'risk-text-0', Icon: Eye },
  1: { label: 'Local Write',      cardClass: 'risk-card-1', textClass: 'risk-text-1', Icon: Pencil },
  2: { label: 'Project Mutation', cardClass: 'risk-card-2', textClass: 'risk-text-2', Icon: TriangleAlert },
  3: { label: 'Destructive',      cardClass: 'risk-card-3', textClass: 'risk-text-3', Icon: ShieldAlert },
}

export default function HITLPanel() {
  const { hitlPending, setHitlPending } = useSentinelStore()
  const pending = Array.isArray(hitlPending) ? hitlPending : []

  const resolve = async (approvalId: string, approved: boolean) => {
    await hitlApi.resolve(approvalId, approved)
    setHitlPending(pending.filter((h) => h.approval_id !== approvalId))
  }

  if (pending.length === 0) {
    return (
      <div className="card hitl-panel">
        <span className="section-label">Approvals</span>
        <div className="hitl-empty">
          <div className="empty-icon hitl-empty-icon"><Check size={15} /></div>
          <p className="hitl-empty-text">All clear</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card hitl-panel">
      <div className="hitl-header">
        <span className="section-label">Approvals</span>
        <span className="pill pill-pending">{pending.length} pending</span>
      </div>

      {pending.map((h) => {
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
              <button className="btn-approve" onClick={() => resolve(h.approval_id, true)}><Check size={13} />Approve</button>
              <button className="btn-reject"  onClick={() => resolve(h.approval_id, false)}><X size={13} />Reject</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
