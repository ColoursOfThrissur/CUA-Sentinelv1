import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// Force unregister stale service workers on every load
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((r) => r.unregister())
  })
  caches.keys().then((keys) => keys.forEach((k) => caches.delete(k)))
}

const setVh = () => document.documentElement.style.setProperty('--vh', `${window.innerHeight * 0.01}px`)
setVh()
window.addEventListener('resize', setVh)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
