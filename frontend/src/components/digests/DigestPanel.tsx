import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Sparkles, RefreshCw, FileText, Landmark, Mail, Globe, Maximize2, X, Calendar, Download } from 'lucide-react'
import { digestsApi } from '../../api'
import './DigestPanel.css'

export interface DailyDigestData {
  digest_id: string
  title: string
  full_markdown: string
  portfolio_summary?: string
  email_summary?: string
  tech_summary?: string
  created_at: string
}

type DigestTab = 'PORTFOLIO' | 'EMAIL' | 'TECH' | 'FULL'

export default function DigestPanel() {
  const [digest, setDigest] = useState<DailyDigestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [activeSection, setActiveSection] = useState<DigestTab>('PORTFOLIO')
  const [showModal, setShowModal] = useState(false)

  const loadLatestDigest = async () => {
    try {
      const res = await digestsApi.getLatest()
      if (res.data?.digest) {
        setDigest(res.data.digest)
      }
    } catch {
      // Ignore background load failures
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLatestDigest()
  }, [])

  const handleGenerateDigest = async () => {
    setGenerating(true)
    try {
      const res = await digestsApi.generate()
      if (res.data?.digest) {
        setDigest(res.data.digest)
      }
    } catch (err) {
      alert('Failed to generate daily digest.')
    } finally {
      setGenerating(false)
    }
  }

  const handleDownloadDigest = () => {
    if (!digest?.full_markdown) return
    const blob = new Blob([digest.full_markdown], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `Sentinel-Digest-${new Date(digest.created_at).toISOString().slice(0,10)}.md`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  if (loading) {
    return (
      <div className="card digest-panel">
        <div className="digest-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Sparkles size={14} style={{ color: 'var(--c-purple)' }} />
            <span style={{ fontSize: '0.85rem', color: 'var(--text-base)', fontWeight: 700 }}>Operations Digest</span>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ height: 16, borderRadius: 6, width: `${70 + i * 8}%` }} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="card digest-panel">
        {/* Header */}
        <div className="digest-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Sparkles size={16} style={{ color: 'var(--c-purple)' }} />
            <div>
              <h3 style={{ fontSize: '0.9rem', color: 'var(--text-base)', margin: 0, fontWeight: 700 }}>Executive Digest</h3>
              {digest && (
                <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Calendar size={11} /> {new Date(digest.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {digest && (
              <>
                <button
                  onClick={handleDownloadDigest}
                  className="btn btn-ghost"
                  style={{ padding: '4px 6px', color: 'var(--c-green)' }}
                  title="Export Report (.md)"
                >
                  <Download size={13} />
                </button>
                <button
                  onClick={() => setShowModal(true)}
                  className="btn btn-ghost"
                  style={{ padding: '4px 6px', color: 'var(--text-muted)' }}
                  title="View Full Executive Report"
                >
                  <Maximize2 size={13} />
                </button>
              </>
            )}
            <button
              onClick={handleGenerateDigest}
              disabled={generating}
              className="btn btn-ghost"
              style={{ padding: '4px 8px', fontSize: '0.72rem', gap: 4, color: 'var(--c-cyan)' }}
              title="Compile fresh daily report"
            >
              <RefreshCw size={12} className={generating ? 'spin' : ''} />
              {generating ? 'Compiling...' : 'Generate New'}
            </button>
          </div>
        </div>

        {digest ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* Section Switcher Tabs */}
            <div style={{ display: 'flex', gap: 4, background: 'var(--bg-input)', padding: 3, borderRadius: 8, border: '1px solid var(--border-base)' }}>
              {[
                { key: 'PORTFOLIO', label: 'Portfolio', icon: Landmark },
                { key: 'EMAIL', label: 'Gmail', icon: Mail },
                { key: 'TECH', label: 'Tech Radar', icon: Globe },
                { key: 'FULL', label: 'Full Markdown', icon: FileText },
              ].map((tab) => {
                const IconComp = tab.icon
                const isActive = activeSection === tab.key
                return (
                  <button
                    key={tab.key}
                    onClick={() => setActiveSection(tab.key as DigestTab)}
                    className={`digest-tab-btn ${isActive ? 'active' : ''}`}
                    style={{ flex: 1, justifyContent: 'center' }}
                  >
                    <IconComp size={12} />
                    {tab.label}
                  </button>
                )
              })}
            </div>

            {/* Active Content Card */}
            <div className="digest-section-card animate-fade-in">
              {activeSection === 'PORTFOLIO' && (
                <div className="digest-markdown">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, color: 'var(--c-green)', fontWeight: 700, fontSize: '0.82rem' }}>
                    <Landmark size={15} /> Portfolio Valuation & Shift Digest
                  </div>
                  <ReactMarkdown>{digest.portfolio_summary || 'No portfolio tracked.'}</ReactMarkdown>
                </div>
              )}

              {activeSection === 'EMAIL' && (
                <div className="digest-markdown">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, color: 'var(--c-cyan)', fontWeight: 700, fontSize: '0.82rem' }}>
                    <Mail size={15} /> Gmail Inbox & Action Feed Highlights
                  </div>
                  <ReactMarkdown>{digest.email_summary || 'No unread email updates.'}</ReactMarkdown>
                </div>
              )}

              {activeSection === 'TECH' && (
                <div className="digest-markdown">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, color: 'var(--c-purple)', fontWeight: 700, fontSize: '0.82rem' }}>
                    <Globe size={15} /> AI & Technology Radar
                  </div>
                  <ReactMarkdown>{digest.tech_summary || 'Tech radar clear.'}</ReactMarkdown>
                </div>
              )}

              {activeSection === 'FULL' && (
                <div className="digest-markdown">
                  <ReactMarkdown>{digest.full_markdown}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="digest-empty" style={{ padding: '20px 8px', textAlign: 'center' }}>
            <div style={{ display: 'inline-flex', padding: 10, borderRadius: 10, background: 'var(--bg-input)', marginBottom: 8 }}>
              <FileText size={20} color="var(--c-purple)" />
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
              No operations digest generated today.
            </p>
            <button
              onClick={handleGenerateDigest}
              disabled={generating}
              className="btn btn-primary"
              style={{ marginTop: 10, fontSize: '0.78rem', padding: '6px 12px' }}
            >
              {generating ? 'Compiling Report...' : 'Generate Daily Operations Digest'}
            </button>
          </div>
        )}
      </div>

      {/* Fullscreen Report Modal */}
      {showModal && digest && (
        <div className="digest-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="digest-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="digest-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Sparkles size={18} color="var(--c-purple)" />
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-base)', margin: 0 }}>{digest.title}</h3>
              </div>
              <button onClick={() => setShowModal(false)} className="btn btn-ghost" style={{ padding: 6, color: 'var(--text-muted)' }}>
                <X size={18} />
              </button>
            </div>
            <div className="digest-modal-body digest-markdown">
              <ReactMarkdown>{digest.full_markdown}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
