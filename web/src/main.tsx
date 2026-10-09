import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { loadRegions } from './data/biz'
import { loadLayers } from './data/layers'
import { boot } from './data/real'
import './index.css'

const theme = (() => { try { return localStorage.getItem('nl-theme') } catch { return null } })()
document.documentElement.dataset.theme = theme ?? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')

function failed(e: unknown) {
  // Один недоступный обязательный файл раньше оставлял вечный лоадер: теперь — причина и кнопка повтора.
  const el = document.getElementById('boot')
  if (!el) return
  const msg = e instanceof Error ? e.message : String(e)
  el.innerHTML = `<b>Данные недоступны</b><span style="max-width:360px;text-align:center">${msg}</span><button id="retry" style="padding:8px 16px;border-radius:8px;border:1px solid currentColor;background:none;color:inherit;cursor:pointer">Повторить</button>`
  document.getElementById('retry')?.addEventListener('click', () => location.reload())
}

boot().then(() => Promise.all([loadRegions(), loadLayers().catch(() => null)])).then(() => {
  document.getElementById('boot')?.remove()
  createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
}).catch(failed)
