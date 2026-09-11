import React, { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Bell, Plus, Trash2, RefreshCw, FileSpreadsheet, ShieldCheck, RotateCcw } from 'lucide-react'
import { financeApi } from '../../api'

interface Asset {
  id: number
  asset_symbol: string
  asset_type: string
  asset_name: string
  quantity: number
  buy_price: number
  current_price: number
  price_change_24h: number
  alert_threshold_pct: number
  notes?: string
}

export default function FinancePanel() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [csvText, setCsvText] = useState('')
  const [importing, setImporting] = useState(false)

  // Form state
  const [symbol, setSymbol] = useState('')
  const [name, setName] = useState('')
  const [type, setType] = useState('STOCK')
  const [qty, setQty] = useState('1.0')
  const [buyPrice, setBuyPrice] = useState('0.0')
  const [threshold, setThreshold] = useState('5.0')

  const fetchPortfolio = async () => {
    setLoading(true)
    try {
      const res = await financeApi.getPortfolio()
      setAssets(res.data)
    } catch (e) {
      console.error('Failed to fetch portfolio', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPortfolio()
  }, [])

  const handleAddAsset = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!symbol.trim() || !name.trim()) return
    try {
      await financeApi.upsertAsset({
        symbol: symbol.trim().toUpperCase(),
        asset_type: type,
        name: name.trim(),
        quantity: parseFloat(qty) || 0,
        buy_price: parseFloat(buyPrice) || 0,
        alert_threshold_pct: parseFloat(threshold) || 5.0,
      })
      setSymbol('')
      setName('')
      setShowAdd(false)
      fetchPortfolio()
    } catch (e) {
      console.error('Failed to add asset', e)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || importing) return
    setImporting(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      await financeApi.importFile(formData)
      setShowImport(false)
      fetchPortfolio()
    } catch (err) {
      alert('Failed to parse Excel/CSV statement.')
    } finally {
      setImporting(false)
    }
  }

  const handleImportCsv = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!csvText.trim() || importing) return
    setImporting(true)
    try {
      await financeApi.importCsv(csvText)
      setCsvText('')
      setShowImport(false)
      fetchPortfolio()
    } catch (e) {
      console.error('Failed to import CSV', e)
    } finally {
      setImporting(false)
    }
  }

  const handleDelete = async (sym: string) => {
    try {
      await financeApi.deleteAsset(sym)
      fetchPortfolio()
    } catch (e) {
      console.error('Failed to delete asset', e)
    }
  }

  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to clear all imported portfolio assets?')) return
    try {
      await financeApi.clearPortfolio()
      fetchPortfolio()
    } catch (e) {
      console.error('Failed to clear portfolio', e)
    }
  }

  const handleEvaluate = async () => {
    setEvaluating(true)
    try {
      await financeApi.evaluateAlerts()
      fetchPortfolio()
    } catch (e) {
      console.error('Failed evaluating alerts', e)
    } finally {
      setEvaluating(false)
    }
  }

  const totalInvested = assets.reduce((acc, a) => acc + a.quantity * a.buy_price, 0)
  const totalCurrentValue = assets.reduce((acc, a) => acc + a.quantity * (a.current_price || a.buy_price), 0)
  const totalProfitLoss = totalCurrentValue - totalInvested
  const totalPLPct = totalInvested > 0 ? (totalProfitLoss / totalInvested) * 100 : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Portfolio & Demat Overview Banner */}
      <div className="card card-glow" style={{ padding: 18, background: 'var(--bg-surface)', border: '1px solid var(--border-base)', borderRadius: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <ShieldCheck size={14} color="var(--c-green)" />
              <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--c-green)', fontWeight: 700 }}>Read-Only Portfolio & Demat Sync</span>
            </div>
            <h2 style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--text-base)', margin: 0 }}>
              ₹{totalCurrentValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </h2>
            <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: '0.78rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Invested: ₹{totalInvested.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
              <span style={{ color: totalProfitLoss >= 0 ? 'var(--c-green)' : 'var(--c-red)', fontWeight: 600 }}>
                P/L: {totalProfitLoss >= 0 ? '+' : ''}₹{totalProfitLoss.toLocaleString('en-IN', { maximumFractionDigits: 2 })} ({totalPLPct >= 0 ? '+' : ''}{totalPLPct.toFixed(2)}%)
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button onClick={handleEvaluate} disabled={evaluating} className="btn btn-ghost" style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 6 }}>
              <RefreshCw size={13} className={evaluating ? 'spin' : ''} />
              {evaluating ? 'Evaluating...' : 'Check Alerts (Δ >= 5%)'}
            </button>
            <button onClick={() => setShowImport(!showImport)} className="btn btn-ghost" style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 6 }}>
              <FileSpreadsheet size={14} color="var(--c-cyan)" /> Import Excel / CSV (.xlsx)
            </button>
            {assets.length > 0 && (
              <button onClick={handleClearAll} className="btn btn-ghost" style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 6, color: 'var(--c-red)' }} title="Clear all assets">
                <RotateCcw size={13} /> Clear Portfolio
              </button>
            )}
            <button onClick={() => setShowAdd(!showAdd)} className="btn btn-primary" style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Plus size={14} /> Add Ticker
            </button>
          </div>
        </div>
      </div>

      {/* Demat Excel / CSV Import Box */}
      {showImport && (
        <form onSubmit={handleImportCsv} className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, background: 'var(--bg-surface)', border: '1px solid var(--border-mid)', borderRadius: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <FileSpreadsheet size={16} color="var(--c-cyan)" />
            <h3 style={{ fontSize: '0.9rem', color: 'var(--text-base)', margin: 0, fontWeight: 700 }}>Import Read-Only Demat Statement (.xlsx or .csv)</h3>
          </div>
          
          <div style={{ padding: 12, background: 'var(--bg-surface-lo)', borderRadius: 8, border: '1px dashed var(--border-cyan)', textAlign: 'center' }}>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-base)', fontWeight: 600, margin: '0 0 6px 0' }}>Upload Excel (.xlsx) or CSV File from Zerodha, Groww, Indmoney, AngelOne, Upstox, etc.</p>
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileUpload}
              style={{ fontSize: '0.8rem', color: 'var(--c-cyan)' }}
            />
          </div>

          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '4px 0 0 0' }}>
            Or paste raw text lines formatted as: <code>Symbol, Quantity, BuyPrice, Name</code>
          </p>
          <textarea
            className="input"
            rows={3}
            value={csvText}
            onChange={(e) => setCsvText(e.target.value)}
            placeholder="RELIANCE, 10, 2900.50, Reliance Industries&#10;INFY, 15, 1850.00, Infosys Ltd&#10;TATAMOTORS, 25, 1010, Tata Motors"
            style={{ fontFamily: 'monospace', fontSize: '0.8rem', resize: 'vertical' }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" onClick={() => setShowImport(false)} className="btn btn-ghost" style={{ fontSize: '0.75rem' }}>Cancel</button>
            <button type="submit" disabled={importing || !csvText.trim()} className="btn btn-primary" style={{ fontSize: '0.75rem' }}>
              {importing ? 'Importing...' : 'Parse Text Lines'}
            </button>
          </div>
        </form>
      )}

      {/* Add Asset Form Card */}
      {showAdd && (
        <form onSubmit={handleAddAsset} className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, background: 'var(--bg-surface)', border: '1px solid var(--border-mid)', borderRadius: 12 }}>
          <h3 style={{ fontSize: '0.9rem', color: 'var(--text-base)', margin: 0, fontWeight: 700 }}>Add Market Ticker / Asset</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Symbol</label>
              <input className="input" placeholder="RELIANCE / INFY / BTC-USD" value={symbol} onChange={(e) => setSymbol(e.target.value)} required />
            </div>
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Name</label>
              <input className="input" placeholder="Reliance Industries" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Asset Type</label>
              <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
                <option value="STOCK">Stock</option>
                <option value="CRYPTO">Crypto</option>
                <option value="COMMODITY">Commodity</option>
                <option value="FOREX">Forex</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Quantity</label>
              <input className="input" type="number" step="any" value={qty} onChange={(e) => setQty(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Buy Price (₹)</label>
              <input className="input" type="number" step="any" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Alert Trigger (Δ %)</label>
              <input className="input" type="number" step="0.5" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
            <button type="button" onClick={() => setShowAdd(false)} className="btn btn-ghost" style={{ fontSize: '0.75rem' }}>Cancel</button>
            <button type="submit" className="btn btn-primary" style={{ fontSize: '0.75rem' }}>Save Ticker</button>
          </div>
        </form>
      )}

      {/* Asset Grid Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
        {assets.length === 0 && !loading && (
          <div className="card" style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', gridColumn: '1 / -1' }}>
            No assets added yet. Import Demat CSV or add stock/crypto tickers to enable price shift monitoring.
          </div>
        )}
        {assets.map((asset) => {
          const isPositive = asset.price_change_24h >= 0
          const alertTriggered = Math.abs(asset.price_change_24h) >= asset.alert_threshold_pct
          const value = asset.quantity * (asset.current_price || asset.buy_price)

          return (
            <div key={asset.asset_symbol} className="card" style={{ padding: 14, position: 'relative', border: alertTriggered ? '1px solid #f59e0b' : '1px solid var(--border-base)', borderRadius: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <span style={{ fontSize: '0.68rem', padding: '2px 6px', borderRadius: 4, background: 'var(--bg-subtle-hi)', color: 'var(--text-base)', fontWeight: 600 }}>{asset.asset_type}</span>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, margin: '6px 0 2px 0', color: 'var(--text-base)' }}>{asset.asset_symbol}</h4>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 140 }}>{asset.asset_name}</p>
                </div>
                <button onClick={() => handleDelete(asset.asset_symbol)} className="btn btn-ghost" style={{ padding: 4, color: 'var(--text-dim)' }}>
                  <Trash2 size={13} />
                </button>
              </div>

              <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                <div>
                  <p style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-base)', margin: 0 }}>
                    ₹{(asset.current_price || asset.buy_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </p>
                  <p style={{ fontSize: '0.72rem', color: 'var(--text-dim)', margin: 0 }}>
                    {asset.quantity > 0 ? `${asset.quantity} units (₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })})` : 'Watchlist Only'}
                  </p>
                </div>
                <span className={`pill ${isPositive ? 'pill-good' : 'pill-danger'}`} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', fontWeight: 600 }}>
                  {isPositive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                  {asset.price_change_24h > 0 ? '+' : ''}{asset.price_change_24h}%
                </span>
              </div>

              {alertTriggered && (
                <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px solid rgba(245,158,11,0.2)', display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.7rem', color: '#f59e0b' }}>
                  <Bell size={12} /> Alert Triggered (|Δ| ≥ {asset.alert_threshold_pct}%)
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
