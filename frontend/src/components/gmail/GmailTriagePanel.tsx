import { useEffect, useState } from 'react'
import {
  Mail,
  CreditCard,
  PackageCheck,
  ShieldAlert,
  Calendar,
  RefreshCw,
  AlertCircle,
  Filter
} from 'lucide-react'
import { gmailTriageApi } from '../../api'
import './GmailTriagePanel.css'

interface FeedItem {
  item_id: string
  sender: string
  subject: string
  category: 'BILL' | 'DELIVERY' | 'SECURITY' | 'GENERAL'
  amount?: string
  due_date?: string
  priority: 'HIGH' | 'MEDIUM' | 'LOW'
  action_summary: string
  date_received: string
}

export default function GmailTriagePanel() {
  const [feed, setFeed] = useState<FeedItem[]>([])
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [activeCategory, setActiveCategory] = useState<string>('ALL')

  const fetchFeed = async (category = activeCategory) => {
    setLoading(true)
    try {
      const res = await gmailTriageApi.getFeed(category)
      setFeed(res.data)
    } catch (err) {
      console.error('Failed fetching Gmail Triage feed', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFeed()
  }, [activeCategory])

  const handleScan = async () => {
    setScanning(true)
    try {
      await gmailTriageApi.scanInbox()
      fetchFeed()
    } catch (err) {
      console.error('Failed scanning inbox', err)
    } finally {
      setScanning(false)
    }
  }

  const renderCategoryBadge = (cat: string) => {
    switch (cat) {
      case 'BILL':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', fontSize: '0.72rem', fontWeight: 600 }}>
            <CreditCard size={12} /> Bill / Statement
          </span>
        )
      case 'DELIVERY':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', fontSize: '0.72rem', fontWeight: 600 }}>
            <PackageCheck size={12} /> Delivery Update
          </span>
        )
      case 'SECURITY':
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', fontSize: '0.72rem', fontWeight: 600 }}>
            <ShieldAlert size={12} /> Security Alert
          </span>
        )
      default:
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, background: 'var(--bg-subtle-hi)', color: 'var(--text-base)', fontSize: '0.72rem', fontWeight: 600 }}>
            <Mail size={12} /> General Email
          </span>
        )
    }
  }

  return (
    <div className="gmail-triage-panel">
      {/* Header Banner */}
      <div className="card card-glow" style={{ padding: 18, background: 'linear-gradient(135deg, rgba(59,130,246,0.12) 0%, var(--bg-surface) 100%)', border: '1px solid var(--border-cyan)', borderRadius: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Mail size={16} color="var(--c-cyan)" />
              <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--c-cyan)', fontWeight: 700 }}>Smart Gmail Triage & Bill Feed</span>
            </div>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-base)', margin: 0 }}>
              Automated Action Feed
            </h2>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0 0' }}>
              Automatically scans unread Gmail receipts, credit card statements, electricity bills, and delivery tracking updates.
            </p>
          </div>

          <button onClick={handleScan} disabled={scanning} className="btn btn-primary" style={{ fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: 6 }}>
            <RefreshCw size={14} className={scanning ? 'spin' : ''} />
            {scanning ? 'Scanning Gmail...' : 'Scan Inbox Now'}
          </button>
        </div>
      </div>

      {/* Filter Category Chips */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', gap: 4, marginRight: 4 }}>
          <Filter size={13} /> Filter:
        </span>
        {[
          { key: 'ALL', label: 'All Action Items', icon: Mail },
          { key: 'BILL', label: 'Bills & Invoices', icon: CreditCard },
          { key: 'DELIVERY', label: 'Deliveries', icon: PackageCheck },
          { key: 'SECURITY', label: 'Security Alerts', icon: ShieldAlert },
        ].map((btn) => {
          const IconComp = btn.icon
          const isActive = activeCategory === btn.key
          return (
            <button
              key={btn.key}
              onClick={() => setActiveCategory(btn.key)}
              className={isActive ? 'btn btn-primary' : 'btn btn-ghost'}
              style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 5 }}
            >
              <IconComp size={13} />
              {btn.label}
            </button>
          )
        })}
      </div>

      {/* Action Feed Item List Scroll Container */}
      <div className="gmail-triage-scroll-container">
        {feed.length === 0 && !loading && (
          <div className="card" style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)' }}>
            No action items categorized yet. Click <strong>Scan Inbox Now</strong> to fetch recent email statements.
          </div>
        )}

        {feed.map((item) => {
          const isHighPriority = item.priority === 'HIGH'

          return (
            <div
              key={item.item_id}
              className={`gmail-feed-card ${isHighPriority ? 'high-priority' : ''}`}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    {renderCategoryBadge(item.category)}
                    {isHighPriority && (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--c-red)', fontSize: '0.7rem', fontWeight: 700 }}>
                        <AlertCircle size={12} /> High Priority
                      </span>
                    )}
                  </div>
                  <h4 style={{ fontSize: '0.95rem', fontWeight: 700, margin: '2px 0', color: 'var(--text-base)' }}>{item.subject}</h4>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>{item.sender}</p>
                </div>

                <div style={{ textAlign: 'right' }}>
                  {item.amount && (
                    <p style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-base)', margin: 0 }}>
                      {item.amount}
                    </p>
                  )}
                  {item.due_date && (
                    <p style={{ fontSize: '0.72rem', color: 'var(--c-red)', fontWeight: 600, margin: '2px 0 0 0', display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end' }}>
                      <Calendar size={12} /> Due: {item.due_date}
                    </p>
                  )}
                </div>
              </div>

              <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--border-base)', fontSize: '0.78rem', color: 'var(--text-base)' }}>
                {item.action_summary}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
