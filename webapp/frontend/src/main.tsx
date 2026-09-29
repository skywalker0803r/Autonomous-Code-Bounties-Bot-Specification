import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Registers the no-op service worker in public/sw.js so the app is
// installable on Android/Chrome ("Add to Home Screen") and opens in its
// own standalone window instead of a browser tab.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Installability is a nice-to-have, not a requirement to use the app.
    })
  })
}
