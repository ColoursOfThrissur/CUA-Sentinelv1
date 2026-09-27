import React, { useState } from 'react'
import { AppInfo, AppTool } from '../../api'
import { Wrench, Shield, ChevronDown, ChevronRight } from 'lucide-react'

interface AppToolBrowserProps {
  app: AppInfo
  onClose?: () => void
}

export const AppToolBrowser: React.FC<AppToolBrowserProps> = ({ app }) => {
  const [expandedTool, setExpandedTool] = useState<string | null>(null)

  const tools: AppTool[] = app.tools || []

  return (
    <div className="tool-browser-container">
      <div className="tool-browser-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Wrench size={16} style={{ color: 'var(--c-cyan)' }} />
          <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>
            Discovered Capabilities ({tools.length})
          </span>
        </div>
        <div className="pill pill-muted" style={{ fontSize: '0.72rem' }}>
          MCP 2.x Tools
        </div>
      </div>

      {tools.length === 0 ? (
        <div className="tool-empty-state">
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            No tools discovered yet. Connect this application to query its capabilities.
          </p>
        </div>
      ) : (
        <div className="tool-list">
          {tools.map((tool) => {
            const isExpanded = expandedTool === tool.name
            const properties = tool.input_schema?.properties || {}
            const required = (tool.input_schema?.required as string[]) || []

            return (
              <div key={tool.name} className="tool-card">
                <div
                  className="tool-card-head"
                  onClick={() => setExpandedTool(isExpanded ? null : tool.name)}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                    <code className="tool-name">
                      mcp:{app.app_id}:{tool.name}
                    </code>
                    {app.security?.default_risk_level && (
                      <span className="risk-tag">
                        <Shield size={10} /> {app.security.default_risk_level}
                      </span>
                    )}
                  </div>
                  {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </div>

                {tool.description && (
                  <p className="tool-description">{tool.description}</p>
                )}

                {isExpanded && (
                  <div className="tool-params-expanded">
                    <div className="param-header">Input Schema Parameters:</div>
                    {Object.keys(properties).length === 0 ? (
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                        No parameters required.
                      </span>
                    ) : (
                      <div className="param-grid">
                        {Object.entries(properties).map(([paramName, paramSchema]: [string, any]) => {
                          const isReq = required.includes(paramName)
                          return (
                            <div key={paramName} className="param-row">
                              <span className="param-title">
                                {paramName}
                                {isReq && <span className="param-required">*</span>}
                              </span>
                              <span className="param-type">
                                {paramSchema.type || 'any'}
                              </span>
                              {paramSchema.description && (
                                <span className="param-desc">{paramSchema.description}</span>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
