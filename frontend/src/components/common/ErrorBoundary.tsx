import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: React.ReactNode
  fallbackTitle?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error(`[ErrorBoundary] ${this.props.fallbackTitle || 'Component'} crashed:`, error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card" style={{
          padding: 24,
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          minHeight: 120,
          justifyContent: 'center'
        }}>
          <AlertTriangle size={28} color="var(--c-amber, #f59e0b)" />
          <h4 style={{ margin: 0, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
            {this.props.fallbackTitle || 'This panel'} encountered an error
          </h4>
          <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)', maxWidth: 400 }}>
            {this.state.error?.message || 'An unexpected error occurred.'}
          </p>
          <button
            onClick={this.handleReset}
            className="btn btn-ghost"
            style={{ fontSize: '0.8rem', gap: 6, marginTop: 4 }}
          >
            <RefreshCw size={14} />
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
