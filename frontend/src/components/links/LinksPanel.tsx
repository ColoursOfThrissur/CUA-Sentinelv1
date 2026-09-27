import React, { useEffect, useState } from 'react'
import {
  Link as LinkIcon,
  Search,
  Plus,
  RefreshCw,
  ExternalLink,
  Tag,
  CheckCircle,
  AlertCircle,
  Clock,
  Sparkles,
  Microscope,
  ShieldCheck,
  Bookmark,
  ChevronDown,
  ChevronUp,
  Zap,
  Globe,
  FileText,
  Layers,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { linksApi, researchApi } from '../../api'
import './LinksPanel.css'

interface BookmarkItem {
  link_id: string
  url: string
  title: string
  domain: string
  summary: string
  tags: string[]
  status: 'PENDING' | 'CRAWLING' | 'INDEXED' | 'FAILED'
  chroma_indexed: number
  created_at: string
}

interface ResearchReportItem {
  task_id: string
  question: string
  depth: 'quick' | 'deep'
  status: string
  created_at: string
  completed_at?: string
  error?: string
}

interface ResearchReportDetail {
  task_id: string
  question: string
  status: string
  created_at: string
  completed_at?: string
  report_markdown: string
  claims: ResearchClaimItem[]
  claims_count: number
}

interface ResearchClaimItem {
  claim_id: string
  claim_text: string
  source_uri: string
  source_authority: 'OFFICIAL_SPEC' | 'OFFICIAL_DOCS' | 'MAINTAINER_REPO' | 'PEER_REVIEWED' | 'COMMUNITY' | 'UNVERIFIED'
  confidence_score: number
  confidence_basis?: string
  retrieval_timestamp: string
  domain: string
}

type SubTab = 'research' | 'claims' | 'bookmarks'

const SUGGESTED_RESEARCH_PROMPTS = [
  'Python 3.13 free-threaded GIL removal benchmarks',
  'Best local SLMs for RTX 3060 12GB VRAM',
  'State of Quantum Error Correction in 2026',
  'FastAPI vs Go Fiber microservices comparison',
]

const DOMAINS = ['ALL', 'AI', 'CODE', 'FINANCE', 'UI_UX', 'PERSONAL', 'OTHER']

export default function LinksPanel() {
  const [subTab, setSubTab] = useState<SubTab>('research')

  // --- Research State ---
  const [researchQuery, setResearchQuery] = useState('')
  const [researchDepth, setResearchDepth] = useState<'quick' | 'deep'>('deep')
  const [researchLoading, setResearchLoading] = useState(false)
  const [reports, setReports] = useState<ResearchReportItem[]>([])
  const [selectedReport, setSelectedReport] = useState<ResearchReportDetail | null>(null)
  const [activeResearchTaskId, setActiveResearchTaskId] = useState<string | null>(null)

  // --- Claims State ---
  const [claims, setClaims] = useState<ResearchClaimItem[]>([])
  const [claimSearch, setClaimSearch] = useState('')
  const [claimDomain, setClaimDomain] = useState('ALL')
  const [claimsLoading, setClaimsLoading] = useState(false)

  // --- Bookmarks State ---
  const [links, setLinks] = useState<BookmarkItem[]>([])
  const [bookmarkSearch, setBookmarkSearch] = useState('')
  const [urlInput, setUrlInput] = useState('')
  const [titleInput, setTitleInput] = useState('')
  const [bookmarkLoading, setBookmarkLoading] = useState(false)

  // Load Reports
  const fetchReports = async () => {
    try {
      const res = await researchApi.getReports(20)
      setReports(res.data?.reports || [])
    } catch (e) {
      console.error('Error fetching research reports', e)
    }
  }

  // Load Claims
  const fetchClaims = async () => {
    setClaimsLoading(true)
    try {
      const domainParam = claimDomain === 'ALL' ? undefined : claimDomain
      const res = await researchApi.getClaims(domainParam, claimSearch || undefined, 50)
      setClaims(res.data?.claims || [])
    } catch (e) {
      console.error('Error fetching research claims', e)
    } finally {
      setClaimsLoading(false)
    }
  }

  // Load Bookmarks
  const fetchLinks = async (q?: string) => {
    setBookmarkLoading(true)
    try {
      const res = await linksApi.list(q)
      setLinks(res.data || [])
    } catch (e) {
      console.error('Error fetching links', e)
    } finally {
      setBookmarkLoading(false)
    }
  }

  useEffect(() => {
    if (subTab === 'research') fetchReports()
    if (subTab === 'claims') fetchClaims()
    if (subTab === 'bookmarks') fetchLinks(bookmarkSearch)
  }, [subTab])

  useEffect(() => {
    if (subTab === 'claims') fetchClaims()
  }, [claimDomain, claimSearch])

  useEffect(() => {
    if (subTab === 'bookmarks') fetchLinks(bookmarkSearch)
  }, [bookmarkSearch])

  // Poll active research task until completed
  useEffect(() => {
    if (!activeResearchTaskId) return
    const interval = setInterval(async () => {
      try {
        const res = await researchApi.getReport(activeResearchTaskId)
        if (res.data?.status === 'COMPLETED' || res.data?.status === 'FAILED') {
          setActiveResearchTaskId(null)
          setResearchLoading(false)
          fetchReports()
          if (res.data?.status === 'COMPLETED') {
            setSelectedReport(res.data)
          }
        }
      } catch (e) {
        console.error('Error polling research task', e)
      }
    }, 4000)
    return () => clearInterval(interval)
  }, [activeResearchTaskId])

  // Handlers
  const handleStartResearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    if (!researchQuery.trim()) return

    setResearchLoading(true)
    try {
      const res = await researchApi.start(researchQuery.trim(), researchDepth)
      if (res.data?.task_id) {
        setActiveResearchTaskId(res.data.task_id)
        fetchReports()
      }
    } catch (e) {
      console.error('Failed to start research', e)
      setResearchLoading(false)
    }
  }

  const handleSelectReport = async (taskId: string) => {
    if (selectedReport?.task_id === taskId) {
      setSelectedReport(null)
      return
    }
    try {
      const res = await researchApi.getReport(taskId)
      setSelectedReport(res.data)
    } catch (e) {
      console.error('Error fetching report detail', e)
    }
  }

  const handleAddLink = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!urlInput.trim()) return
    try {
      await linksApi.add(urlInput.trim(), titleInput.trim() || undefined)
      setUrlInput('')
      setTitleInput('')
      fetchLinks()
    } catch (e) {
      console.error('Error adding link', e)
    }
  }

  const handleCrawl = async (id: string) => {
    try {
      await linksApi.crawl(id)
      fetchLinks(bookmarkSearch)
    } catch (e) {
      console.error('Crawl failed', e)
    }
  }

  return (
    <div className="research-container">
      {/* Segmented Navigation Header */}
      <div className="research-subnav">
        <button
          className={`research-tab-btn ${subTab === 'research' ? 'active' : ''}`}
          onClick={() => setSubTab('research')}
        >
          <Microscope size={15} />
          Autonomous Deep Research
          {reports.length > 0 && <span className="research-tab-badge">{reports.length}</span>}
        </button>

        <button
          className={`research-tab-btn ${subTab === 'claims' ? 'active' : ''}`}
          onClick={() => setSubTab('claims')}
        >
          <ShieldCheck size={15} />
          Verified Knowledge Claims
          {claims.length > 0 && <span className="research-tab-badge">{claims.length}</span>}
        </button>

        <button
          className={`research-tab-btn ${subTab === 'bookmarks' ? 'active' : ''}`}
          onClick={() => setSubTab('bookmarks')}
        >
          <Bookmark size={15} />
          Bookmarks & RAG Memory
          {links.length > 0 && <span className="research-tab-badge">{links.length}</span>}
        </button>
      </div>

      {/* ========================================================================= */}
      {/* SUBTAB 1: AUTONOMOUS DEEP RESEARCH                                         */}
      {/* ========================================================================= */}
      {subTab === 'research' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Research Prompt Hero Card */}
          <div className="research-hero-card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Microscope size={20} color="var(--c-cyan)" />
                <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: 'var(--text-base)' }}>
                  Deep Research Engine & Knowledge Synthesizer
                </h2>
              </div>
              <div className="research-depth-selector">
                <button
                  type="button"
                  className={`depth-pill ${researchDepth === 'quick' ? 'active' : ''}`}
                  onClick={() => setResearchDepth('quick')}
                >
                  <Zap size={12} style={{ display: 'inline', marginRight: 4 }} />
                  Quick (2 nodes)
                </button>
                <button
                  type="button"
                  className={`depth-pill ${researchDepth === 'deep' ? 'active' : ''}`}
                  onClick={() => setResearchDepth('deep')}
                >
                  <Layers size={12} style={{ display: 'inline', marginRight: 4 }} />
                  Deep (4-6 nodes + Deep Scrape)
                </button>
              </div>
            </div>

            <form onSubmit={handleStartResearch} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ position: 'relative' }}>
                <textarea
                  className="input"
                  rows={2}
                  style={{ width: '100%', resize: 'none', paddingRight: 110, fontSize: '0.88rem' }}
                  placeholder="Enter any topic or question to investigate with multi-engine web search & deep article scraping..."
                  value={researchQuery}
                  onChange={(e) => setResearchQuery(e.target.value)}
                  disabled={researchLoading}
                />
                <button
                  type="submit"
                  disabled={researchLoading || !researchQuery.trim()}
                  className="btn btn-primary"
                  style={{
                    position: 'absolute',
                    right: 8,
                    top: 8,
                    bottom: 8,
                    padding: '0 16px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  {researchLoading ? (
                    <>
                      <RefreshCw size={14} className="spin" /> Researching...
                    </>
                  ) : (
                    <>
                      <Sparkles size={14} /> Investigate
                    </>
                  )}
                </button>
              </div>

              {/* Prompt Suggestions */}
              <div className="research-chips-row">
                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Suggestions:</span>
                {SUGGESTED_RESEARCH_PROMPTS.map((prompt, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="research-chip"
                    onClick={() => setResearchQuery(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </form>
          </div>

          {/* Active Live Progress Tracker */}
          {activeResearchTaskId && (
            <div className="research-steps-tracker">
              <RefreshCw size={14} color="var(--c-cyan)" className="spin" />
              <div className="research-step-node running">
                <span>1. Decomposing Plan</span> →
              </div>
              <div className="research-step-node running">
                <span>2. Multi-Engine Web Search</span> →
              </div>
              <div className="research-step-node running">
                <span>3. Deep Article Scraping</span> →
              </div>
              <div className="research-step-node running">
                <span>4. Extracting Verified Claims</span> →
              </div>
              <div className="research-step-node running">
                <span>5. Synthesizing Final Report</span>
              </div>
            </div>
          )}

          {/* Selected Report Full Viewer */}
          {selectedReport && (
            <div className="card card-glow" style={{ padding: 20, border: '1px solid var(--border-cyan)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div>
                  <span className="pill pill-good" style={{ fontSize: '0.7rem', marginBottom: 6, display: 'inline-block' }}>
                    Completed Synthesis
                  </span>
                  <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-base)', margin: 0 }}>
                    {selectedReport.question}
                  </h3>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 4 }}>
                    Task ID: {selectedReport.task_id} • Completed: {selectedReport.completed_at ? new Date(selectedReport.completed_at).toLocaleString() : 'Just now'} • {selectedReport.claims_count} Verified Claims
                  </div>
                </div>
                <button onClick={() => setSelectedReport(null)} className="btn btn-ghost" style={{ fontSize: '0.75rem' }}>
                  Close Report
                </button>
              </div>

              {/* Verified Claims Mini Table */}
              {selectedReport.claims.length > 0 && (
                <div style={{ marginBottom: 20, background: 'var(--bg-input)', padding: 12, borderRadius: 10, border: '1px solid var(--border-mid)' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--c-cyan)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ShieldCheck size={14} /> Extracted Atomic Claims ({selectedReport.claims.length})
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {selectedReport.claims.map((claim) => (
                      <div key={claim.claim_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.78rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 6 }}>
                        <span style={{ color: 'var(--text-base)', flex: 1, paddingRight: 10 }}>• {claim.claim_text}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span className={`auth-badge ${claim.source_authority}`}>{claim.source_authority}</span>
                          <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#10b981' }}>
                            {Math.round(claim.confidence_score * 100)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Render Full Markdown Report */}
              <div className="research-markdown" style={{ borderTop: '1px solid var(--border-mid)', paddingTop: 16 }}>
                <ReactMarkdown>{selectedReport.report_markdown || 'No report markdown recorded.'}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Research Reports Archive List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                Research Sessions History
              </h3>
              <button onClick={fetchReports} className="btn btn-ghost" style={{ fontSize: '0.75rem' }}>
                <RefreshCw size={12} /> Refresh
              </button>
            </div>

            {reports.length === 0 && (
              <div className="card" style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)' }}>
                No research sessions recorded yet. Enter a topic above to launch your first autonomous investigation!
              </div>
            )}

            {reports.map((r) => (
              <div
                key={r.task_id}
                className="card card-hover"
                style={{
                  padding: 14,
                  cursor: 'pointer',
                  border: selectedReport?.task_id === r.task_id ? '1px solid var(--c-cyan)' : undefined,
                }}
                onClick={() => handleSelectReport(r.task_id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <FileText size={16} color="var(--c-cyan)" />
                    <div>
                      <div style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-base)' }}>
                        {r.question}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 2 }}>
                        Depth: {r.depth.toUpperCase()} • Created: {new Date(r.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {r.status === 'COMPLETED' && (
                      <span className="pill pill-good" style={{ fontSize: '0.7rem' }}>
                        COMPLETED
                      </span>
                    )}
                    {r.status === 'RUNNING' && (
                      <span className="pill" style={{ fontSize: '0.7rem', background: 'var(--c-cyan)', color: '#ffffff' }}>
                        <Clock size={11} className="spin" style={{ marginRight: 4 }} /> RUNNING
                      </span>
                    )}
                    {r.status === 'FAILED' && (
                      <span className="pill pill-danger" style={{ fontSize: '0.7rem' }}>
                        FAILED
                      </span>
                    )}
                    {selectedReport?.task_id === r.task_id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB 2: VERIFIED KNOWLEDGE CLAIMS                                       */}
      {/* ========================================================================= */}
      {subTab === 'claims' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Domain Filters & Search Bar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {DOMAINS.map((domain) => (
                <button
                  key={domain}
                  className={`depth-pill ${claimDomain === domain ? 'active' : ''}`}
                  onClick={() => setClaimDomain(domain)}
                  style={{ fontSize: '0.72rem' }}
                >
                  {domain}
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-dim)' }} />
                <input
                  className="input"
                  style={{ paddingLeft: 30 }}
                  placeholder="Filter claims by keyword, specification, or URL..."
                  value={claimSearch}
                  onChange={(e) => setClaimSearch(e.target.value)}
                />
              </div>
              <button onClick={fetchClaims} className="btn btn-ghost" style={{ fontSize: '0.78rem' }}>
                <RefreshCw size={13} className={claimsLoading ? 'spin' : ''} />
              </button>
            </div>
          </div>

          {/* Claims Cards Grid */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {claims.length === 0 && !claimsLoading && (
              <div className="card" style={{ padding: 28, textAlign: 'center', color: 'var(--text-dim)' }}>
                No verified claims recorded yet. Run a research task to extract and persist verified facts in SQLite knowledge.db!
              </div>
            )}

            {claims.map((c) => (
              <div key={c.claim_id} className="card card-hover" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ fontSize: '0.88rem', color: 'var(--text-base)', lineHeight: 1.5, flex: 1 }}>
                    "{c.claim_text}"
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className={`auth-badge ${c.source_authority}`}>{c.source_authority}</span>
                    <span className="pill pill-good" style={{ fontSize: '0.72rem', fontWeight: 700 }}>
                      {Math.round(c.confidence_score * 100)}% Confidence
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.72rem', color: 'var(--text-dim)', borderTop: '1px solid var(--border-subtle)', paddingTop: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Globe size={12} />
                    {c.source_uri ? (
                      <a href={c.source_uri} target="_blank" rel="noreferrer" style={{ color: 'var(--c-cyan)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                        {c.source_uri.length > 50 ? c.source_uri.slice(0, 50) + '...' : c.source_uri} <ExternalLink size={10} />
                      </a>
                    ) : (
                      'Internal Research'
                    )}
                  </div>
                  <div>
                    Domain: <strong>{c.domain}</strong> • Retrieved: {new Date(c.retrieval_timestamp).toLocaleDateString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUBTAB 3: BOOKMARKS & SECOND BRAIN RAG                                    */}
      {/* ========================================================================= */}
      {subTab === 'bookmarks' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Header & Add Form */}
          <div className="card card-glow" style={{ padding: 16, background: 'linear-gradient(135deg, rgba(59,130,246,0.12) 0%, var(--bg-surface) 100%)', border: '1px solid var(--border-cyan)' }}>
            <form onSubmit={handleAddLink} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <LinkIcon size={18} color="var(--c-cyan)" />
                <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-base)', margin: 0 }}>
                  Add Bookmark & Second Brain RAG Indexer
                </h3>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8 }}>
                <input
                  className="input"
                  placeholder="https://example.com/article"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  required
                />
                <input
                  className="input"
                  placeholder="Title (optional)"
                  value={titleInput}
                  onChange={(e) => setTitleInput(e.target.value)}
                />
                <button type="submit" className="btn btn-primary" style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Plus size={14} /> Add & Crawl
                </button>
              </div>
            </form>
          </div>

          {/* Search Bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-dim)' }} />
              <input
                className="input"
                style={{ paddingLeft: 30 }}
                placeholder="Search bookmarked links, tags, or RAG summaries..."
                value={bookmarkSearch}
                onChange={(e) => setBookmarkSearch(e.target.value)}
              />
            </div>
            <button onClick={() => fetchLinks(bookmarkSearch)} className="btn btn-ghost" style={{ fontSize: '0.78rem' }}>
              <RefreshCw size={13} className={bookmarkLoading ? 'spin' : ''} />
            </button>
          </div>

          {/* Bookmarks List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {links.length === 0 && !bookmarkLoading && (
              <div className="card" style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)' }}>
                No bookmarked links found. Add a URL above to crawl and index it into your Second Brain RAG memory.
              </div>
            )}

            {links.map((link) => (
              <div key={link.link_id} className="card card-hover" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <a href={link.url} target="_blank" rel="noreferrer" style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-base)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
                        {link.title || link.domain} <ExternalLink size={12} color="var(--text-muted)" />
                      </a>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>({link.domain})</span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {link.status === 'INDEXED' && (
                      <span className="pill pill-good" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.7rem' }}>
                        <CheckCircle size={11} /> Indexed RAG
                      </span>
                    )}
                    {link.status === 'CRAWLING' && (
                      <span className="pill" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.7rem', background: 'var(--c-cyan)', color: '#ffffff' }}>
                        <Clock size={11} className="spin" /> Crawling
                      </span>
                    )}
                    {link.status === 'FAILED' && (
                      <span className="pill pill-danger" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.7rem' }}>
                        <AlertCircle size={11} /> Crawl Failed
                      </span>
                    )}
                    <button onClick={() => handleCrawl(link.link_id)} className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.7rem' }}>
                      Re-Crawl
                    </button>
                  </div>
                </div>

                {link.summary && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-base)', lineHeight: 1.5, background: 'var(--bg-input)', padding: 10, borderRadius: 8, border: '1px solid var(--border-mid)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, color: 'var(--c-cyan)', fontWeight: 600, fontSize: '0.75rem' }}>
                      <Sparkles size={13} /> 3-Bullet AI Takeaways
                    </div>
                    <div style={{ whiteSpace: 'pre-line' }}>{link.summary}</div>
                  </div>
                )}

                {Array.isArray(link.tags) && link.tags.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                    <Tag size={11} color="var(--text-dim)" />
                    {link.tags.map((t, idx) => (
                      <span key={idx} style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: 4, background: 'var(--bg-subtle-hi)', color: 'var(--text-muted)' }}>
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
