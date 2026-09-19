import React, { useEffect, useState } from 'react'
import { Link as LinkIcon, Search, Plus, RefreshCw, ExternalLink, Tag, CheckCircle, AlertCircle, Clock, Sparkles } from 'lucide-react'
import { linksApi } from '../../api'

interface Bookmark {
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

export default function LinksPanel() {
  const [links, setLinks] = useState<Bookmark[]>([])
  const [search, setSearch] = useState('')
  const [urlInput, setUrlInput] = useState('')
  const [titleInput, setTitleInput] = useState('')
  const [loading, setLoading] = useState(false)

  const fetchLinks = async (q?: string) => {
    setLoading(true)
    try {
      const res = await linksApi.list(q)
      setLinks(res.data)
    } catch (e) {
      console.error('Error fetching links', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLinks(search)
  }, [search])

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
      fetchLinks(search)
    } catch (e) {
      console.error('Crawl failed', e)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header & Add Form */}
      <div className="card card-glow" style={{ padding: 16, background: 'linear-gradient(135deg, rgba(59,130,246,0.12) 0%, var(--bg-surface) 100%)', border: '1px solid var(--border-cyan)' }}>
        <form onSubmit={handleAddLink} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <LinkIcon size={18} color="var(--c-cyan)" />
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-base)', margin: 0 }}>Add Bookmark & Second Brain RAG Indexer</h3>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8 }}>
            <input className="input" placeholder="https://example.com/article" value={urlInput} onChange={(e) => setUrlInput(e.target.value)} required />
            <input className="input" placeholder="Title (optional)" value={titleInput} onChange={(e) => setTitleInput(e.target.value)} />
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
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button onClick={() => fetchLinks(search)} className="btn btn-ghost" style={{ fontSize: '0.78rem' }}>
          <RefreshCw size={13} className={loading ? 'spin' : ''} />
        </button>
      </div>

      {/* Bookmarks List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {links.length === 0 && !loading && (
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
  )
}
