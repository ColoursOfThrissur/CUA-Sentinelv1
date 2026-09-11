import React, { useEffect, useState } from 'react'
import { Bell, Send, X, Bot, Mail, CheckCircle2 } from 'lucide-react'
import { notificationsApi } from '../../api'

export default function NotificationModal({ onClose }: { onClose: () => void }) {
  const [activeTab, setActiveTab] = useState<'discord' | 'email'>('discord')
  const [discordWebhook, setDiscordWebhook] = useState('')
  const [discordToken, setDiscordToken]     = useState('')
  const [discordUserId, setDiscordUserId]   = useState('')
  const [discordChannelId, setDiscordChannelId] = useState('')

  const [smtpUser, setSmtpUser]             = useState('')
  const [smtpAppPass, setSmtpAppPass]       = useState('')
  const [recipientEmail, setRecipientEmail] = useState('')

  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  useEffect(() => {
    notificationsApi.getSettings().then((res) => {
      const d = res.data
      setDiscordWebhook(d.discord_webhook_url || '')
      setDiscordToken(d.discord_bot_token || '')
      setDiscordUserId(d.discord_allowed_user_id || '')
      setDiscordChannelId(d.discord_channel_id || '')
      setSmtpUser(d.smtp_user || '')
      setSmtpAppPass(d.smtp_app_password || '')
      setRecipientEmail(d.recipient_email || '')
    })
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setTestResult(null)
    try {
      await notificationsApi.updateSettings({
        discord_webhook_url: discordWebhook.trim(),
        discord_bot_token: discordToken.trim(),
        discord_allowed_user_id: discordUserId.trim(),
        discord_channel_id: discordChannelId.trim(),
        smtp_user: smtpUser.trim(),
        smtp_app_password: smtpAppPass.trim(),
        recipient_email: recipientEmail.trim(),
      })
      setTestResult('Integration settings saved successfully!')
    } catch {
      setTestResult('Error saving settings')
    } finally {
      setSaving(false)
    }
  }

  const handleTestDiscord = async () => {
    setTesting(true)
    setTestResult(null)

    // Auto-sanitize if user pasted an OAuth bot invite link into the Webhook field
    let cleanWebhook = discordWebhook.trim()
    if (cleanWebhook.includes('oauth2/authorize')) {
      cleanWebhook = ''
      setDiscordWebhook('')
    }

    try {
      await notificationsApi.updateSettings({
        discord_webhook_url: cleanWebhook,
        discord_bot_token: discordToken.trim(),
        discord_allowed_user_id: discordUserId.trim(),
        discord_channel_id: discordChannelId.trim(),
      })

      if (discordToken.trim()) {
        const res = await notificationsApi.testDiscordBot()
        setTestResult(`Discord Bot Token Verified! ✅ Bot Name: ${res.data.username}`)
      } else if (cleanWebhook) {
        const res = await notificationsApi.sendTest({
          title: 'CUA-Sentinel Discord Webhook Test',
          message: 'Push alert test from CUA-Sentinel AI Personal Assistant.',
          severity: 'INFO',
        })
        setTestResult(res.data.results.discord ? 'Discord Webhook Alert Sent ✅' : 'Discord Webhook test failed.')
      } else {
        setTestResult('Please enter a Discord Bot Token or Webhook URL to test.')
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Error testing Discord connection. Check your Bot Token.'
      setTestResult(`❌ ${msg}`)
    } finally {
      setTesting(false)
    }
  }

  const handleTestGmail = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      await notificationsApi.updateSettings({
        smtp_user: smtpUser.trim(),
        smtp_app_password: smtpAppPass.trim(),
        recipient_email: recipientEmail.trim(),
      })
      const res = await notificationsApi.testGmailSync()
      setTestResult(`Gmail IMAP Sync Success! ✅ ${res.data.message}`)
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Error testing Gmail IMAP sync'
      setTestResult(`❌ ${msg}`)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.65)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}>
      <div className="card card-glow" style={{ width: '100%', maxWidth: 540, padding: 20, background: 'var(--bg-surface)', border: '1px solid var(--border-mid)', display: 'flex', flexDirection: 'column', gap: 16, borderRadius: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Bell size={18} color="var(--c-cyan)" />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-base)', margin: 0 }}>Integrations & Endpoint Manager</h3>
          </div>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-base)', gap: 12 }}>
          <button
            type="button"
            onClick={() => setActiveTab('discord')}
            style={{ padding: '8px 12px', fontSize: '0.82rem', fontWeight: 600, color: activeTab === 'discord' ? 'var(--c-cyan)' : 'var(--text-muted)', borderBottom: activeTab === 'discord' ? '2px solid var(--c-cyan)' : '2px solid transparent', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Bot size={14} /> Discord 2-Way Bot
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('email')}
            style={{ padding: '8px 12px', fontSize: '0.82rem', fontWeight: 600, color: activeTab === 'email' ? 'var(--c-cyan)' : 'var(--text-muted)', borderBottom: activeTab === 'email' ? '2px solid var(--c-cyan)' : '2px solid transparent', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Mail size={14} /> Gmail & Email Sync
          </button>
        </div>

        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {activeTab === 'discord' ? (
            <>
              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                  Discord Webhook URL <span style={{ color: 'var(--text-dim)', fontWeight: 400 }}>(Optional - Starts with https://discord.com/api/webhooks/...)</span>
                </label>
                <input
                  className="input"
                  placeholder="https://discord.com/api/webhooks/12345/abcde..."
                  value={discordWebhook}
                  onChange={(e) => setDiscordWebhook(e.target.value)}
                />
                {discordWebhook.includes('oauth2/authorize') && (
                  <p style={{ fontSize: '0.72rem', color: 'var(--c-red)', marginTop: 4 }}>
                    ⚠️ <strong>Incorrect URL format!</strong> You pasted an <em>OAuth Bot Invite Link</em>. That link should be opened in your browser to invite your bot. Leave this field blank or use a Webhook URL from Discord Channel Settings ➔ Integrations ➔ Webhooks.
                  </p>
                )}
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Discord Bot Token (2-Way Remote Control)</label>
                <input className="input" type="password" placeholder="MTU0... (Bot Token from Discord Dev Portal)" value={discordToken} onChange={(e) => setDiscordToken(e.target.value)} />
                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Enables 2-way Discord commands (!price, !cua screenshot, !link, deep research).</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Allowed User ID (Whitelist)</label>
                  <input className="input" placeholder="678791265420050442" value={discordUserId} onChange={(e) => setDiscordUserId(e.target.value)} />
                </div>
                <div>
                  <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Default Channel ID</label>
                  <input className="input" placeholder="123456789012345678" value={discordChannelId} onChange={(e) => setDiscordChannelId(e.target.value)} />
                </div>
              </div>
            </>
          ) : (
            <>
              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Gmail Address / Username</label>
                <input className="input" placeholder="your.name@gmail.com" value={smtpUser} onChange={(e) => setSmtpUser(e.target.value)} />
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Gmail App Password</label>
                <input className="input" type="password" placeholder="abcd efgh ijkl mnop" value={smtpAppPass} onChange={(e) => setSmtpAppPass(e.target.value)} />
                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Generate 16-character App Password in Google Security Settings.</span>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Recipient Email (for Morning Digests & Alerts)</label>
                <input className="input" placeholder="your.email@gmail.com" value={recipientEmail} onChange={(e) => setRecipientEmail(e.target.value)} />
              </div>
            </>
          )}

          {testResult && (
            <div style={{ padding: '8px 12px', borderRadius: 6, background: 'var(--bg-input)', border: '1px solid var(--border-mid)', fontSize: '0.78rem', color: 'var(--c-cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <CheckCircle2 size={14} color="var(--c-cyan)" /> {testResult}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
            <button type="button" onClick={activeTab === 'discord' ? handleTestDiscord : handleTestGmail} disabled={testing} className="btn btn-ghost" style={{ fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Send size={13} /> {testing ? 'Testing...' : activeTab === 'discord' ? 'Test Discord Connection' : 'Test Gmail IMAP Sync'}
            </button>

            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" onClick={onClose} className="btn btn-ghost" style={{ fontSize: '0.78rem' }}>Close</button>
              <button type="submit" disabled={saving} className="btn btn-primary" style={{ fontSize: '0.78rem' }}>
                {saving ? 'Saving...' : 'Save Config'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
