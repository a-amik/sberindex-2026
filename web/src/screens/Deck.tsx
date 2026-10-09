import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Card, Seg } from '../components/ui'
import { Slot } from '../components/Shell'

// Презентация решения — первая страница раздела «О проекте». Слайды — живая копия чистовой
// презентации (public/about/live, сборка web/scripts/export_deck.py) прямо в странице:
// стили слайдов закрыты теневым узлом, чтобы не задеть сервис. PDF — печать чистовой.
const BASE = '/about/deck'
export const DECK_NAV: [string, string][] = []

/** Заголовки слайдов и части, к которым они относятся: подписи миниатюр, содержание, alt. */
const SLIDES: [string, string][] = [
  ['Индекс перемен', 'Титул'],
  ['Цель', ''],
  ['Прогнозируем траты 2 190 муниципалитетов и находим сдвиги', 'Цель'],
  ['Ошибка почти вдвое ниже, чем у Prophet; при паводках 2024 доля рядов с сигналом выросла в 2,2 раза', 'Главное'],
  ['Чем наша модель отличается от базовой', ''],
  ['Prophet строит модель для каждого ряда; мы оцениваем сезонность по всем муниципалитетам', 'Отличия от базовой модели'],
  ['Траты муниципалитета = общая динамика группы × его относительный уровень', 'Модель'],
  ['У ансамбля наименьшая ошибка на 3, 6 и 12 месяцев; на месяц Chronos-2 точнее на 1 ₽', 'Выбор модели'],
  ['Ошибка ниже, чем у Prophet, на 45, 26, 16 и 47 %', 'Результат'],
  ['Во всех шести категориях ошибка ниже, чем у Prophet, на 5—57 %', 'Категории'],
  ['Что сработало', ''],
  ['Больше всего дала общая динамика группы: 211 ₽ из 273 ₽ снижения ошибки', 'Вклад'],
  ['Chronos-2: прогноз относительного уровня трат муниципалитета снизил ошибку с 660 до 325 ₽', 'Нейросеть'],
  ['Недельный ряд СберИндекса снизил ошибку прогноза на 6 месяцев на 8,7 %', 'Внешние признаки'],
  ['Выбрали два детектора из шести: на искусственных сдвигах 76 % сигналов верны', 'Детекторы'],
  ['Паводки 2024: в пострадавших регионах доля рядов с сигналом выросла в 2,2 раза', 'Реальный шок'],
  ['215 тыс. новостей привязаны к месту и месяцу; в проверенной выборке 94 % привязок к территории верны', 'Новости'],
  ['Спад трат в районах в апреле 2023 — особенность данных: −20 % против −0,3 % по стране', 'Качество данных'],
  ['Что не сработало', ''],
  ['Восемь признаков, которые прогноз не улучшили', 'Признаки'],
  ['На региональную составляющую приходится 23—32 ₽ ошибки из 302—538 ₽', 'Почему'],
  ['Отбросили три идеи: новости в прогнозе, проверку PELT и прогноз шока', 'Идеи'],
  ['Кто будет пользоваться', ''],
  ['Четыре роли: у каждой свой вопрос, экран и сценарий', 'Роли'],
  ['Ритейл: 26 регионов для проверки перед открытием точек', 'Ритейл'],
  ['Банк: прогноз на квартал со средней ошибкой 4,5 %', 'Банк'],
  ['Власти региона: 21 просадка спроса за полгода', 'Власти региона'],
  ['СберИндекс: 168 сигналов за два года для проверки перед публикацией', 'СберИндекс'],
  ['Предлагаем пилот в одном регионе', 'Пилот'],
  ['Как устроено и как воспроизвести', ''],
  ['Три расчёта каждый месяц', 'Как устроено'],
  ['Раз в месяц, одной командой', 'Воспроизводимость'],
  ['Неслучайные связи', 'Финал'],
  ['Модель выбирали на одних месяцах, а итоговую ошибку считали на других', 'Приложение · проверка'],
  ['Сравниваем с самой точной настройкой Prophet — по умолчанию', 'Приложение · база'],
  ['Что может изменить выводы', 'Приложение · ограничения'],
]
/** Части презентации: разделители (без подписи части) открывают группу в содержании. */
/** Части презентации: разделители (без подписи части) открывают группу в содержании. */
const PARTS = SLIDES.reduce<{ title: string; from: number; items: number[] }[]>((acc, [t, part], i) => {
  if (i === 0) return [{ title: 'Начало', from: 0, items: [0] }]
  if (!part) acc.push({ title: t, from: i, items: [i] })
  else if (i >= 33 && acc[acc.length - 1].title !== 'Приложение') acc.push({ title: 'Приложение', from: i, items: [i] })
  else acc[acc.length - 1].items.push(i)
  return acc
}, [])

const Ic = {
  prev: <svg viewBox="0 0 24 24" className="i"><path d="M15 6l-6 6 6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  next: <svg viewBox="0 0 24 24" className="i"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  full: <svg viewBox="0 0 24 24" className="i"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  close: <svg viewBox="0 0 24 24" className="i"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>,
  exit: <svg viewBox="0 0 24 24" className="i"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  pdf: <svg viewBox="0 0 24 24" className="i"><path d="M12 4v11m-4-4l4 4 4-4M5 20h14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
}

const LIVE = '/about/live'
const N = SLIDES.length
const thumb = (i: number) => `${BASE}/thumb/${String(i + 1).padStart(2, '0')}.webp`
let deck: Promise<[string, string]> | null = null
const load = () => (deck ??= Promise.all([fetch(`${LIVE}/deck.css`).then((r) => r.text()), fetch(`${LIVE}/deck.html`).then((r) => r.text())]))
// Шрифты слайдов объявляются в документе: внутри теневого узла @font-face не действует.
function fonts() {
  if (document.getElementById('deck-fonts')) return
  const l = Object.assign(document.createElement('link'), { id: 'deck-fonts', rel: 'stylesheet', href: `${LIVE}/deck-fonts.css` })
  document.head.appendChild(l)
}
// Свои правила поверх оболочки: холст 1600×900 ужимается масштабом --k, лента — столбик экранов.
const LOCAL = `
:host { display: block; }
.deck-body { margin: 0; padding: 0; background: none; display: flex; flex-direction: column; gap: 16px; }
.slide { margin: 0 !important; padding: 0 !important; border: 0 !important; display: block !important; flex: none;
  width: calc(1600px * var(--k)); height: calc(900px * var(--k)); overflow: hidden; border-radius: 12px; box-shadow: 0 0 0 1px rgba(0,0,0,.08); align-self: center; }
.slide > .slide-in { transform: scale(var(--k)); transform-origin: 0 0; }
.deck-body.single .slide:not(.on) { display: none !important; }
.deck-body.single .slide { cursor: pointer; }
`
type View = 'list' | 'single'
// Телефон лёжа: во весь экран слайд занимает экран целиком, подпись и лента прячутся.
const LIE = '(orientation: landscape) and (max-height: 540px)'
type Lockable = ScreenOrientation & { lock?: (o: string) => Promise<void> }
const lockLand = () => { if (matchMedia('(pointer: coarse)').matches) (screen.orientation as Lockable)?.lock?.('landscape').catch(() => {}) }
const unlock = () => { try { screen.orientation?.unlock?.() } catch { /* не умеет — и не надо */ } }
const readView = (): View => { try { return localStorage.getItem('nl-deck-view') === 'single' ? 'single' : 'list' } catch { return 'list' } }

export function DeckBody() {
  const [at, setAt] = useState(0)
  const [view, setView] = useState<View>(readView)
  const [full, setFull] = useState(false)
  const [ready, setReady] = useState(false)
  const touch = useRef<[number, number] | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const host = useRef<HTMLDivElement>(null)
  const strip = useRef<HTMLDivElement>(null)
  const go = useCallback((i: number) => setAt(Math.max(0, Math.min(N - 1, i))), [])
  const pickView = (v: View) => { setView(v); try { localStorage.setItem('nl-deck-view', v) } catch { /* без памяти */ } }

  // Экраны — в теневой узел; ссылки «#show/N» внутри слайдов ведут на слайд.
  useEffect(() => {
    const el = host.current
    if (!el) return
    fonts()
    let alive = true
    load().then(([css, html]) => {
      if (!alive) return
      const root = el.shadowRoot ?? el.attachShadow({ mode: 'open' })
      root.innerHTML = `<style>${css}${LOCAL}</style><div class="deck-body">${html}</div>`
      root.querySelectorAll('.slide').forEach((s) => {
        const inner = document.createElement('div')
        inner.className = 'slide-in'
        while (s.firstChild) inner.appendChild(s.firstChild)
        s.appendChild(inner)
      })
      root.addEventListener('click', (e) => {
        const t = e.target as HTMLElement
        const a = t.closest('a[href^="#show/"]')
        if (a) { e.preventDefault(); const n = +a.getAttribute('href')!.split('/')[1] - 1; setAt(n); jump.current(n); return }
        if (t.closest('a')) return
        if (root.querySelector('.deck-body.single')) setAt((i) => Math.min(N - 1, i + 1))
      })
      setReady(true)
    })
    return () => { alive = false }
  }, [])
  // В ленте переход по ссылке прокручивает к слайду, в показе по одному — открывает его.
  const jump = useRef((n: number) => { const s = host.current?.shadowRoot?.querySelectorAll('.slide')[n]; if (s && !host.current?.shadowRoot?.querySelector('.deck-body.single')) s.scrollIntoView({ behavior: 'smooth', block: 'start' }) })

  useLayoutEffect(() => {
    const root = host.current?.shadowRoot
    if (!ready || !root) return
    root.querySelector('.deck-body')?.classList.toggle('single', view === 'single')
    root.querySelectorAll('.slide').forEach((s, i) => s.classList.toggle('on', i === at))
  }, [ready, view, at])

  // Масштаб холста: по ширине страницы; во весь экран — чтобы слайд целиком влез в окно.
  useEffect(() => {
    const el = host.current, b = box.current
    if (!el || !b) return
    const fit = () => {
      const fs = !!document.fullscreenElement || full
      const lie = fs && matchMedia(LIE).matches
      const w = el.clientWidth, h = b.clientHeight - (view === 'single' && !lie ? 150 : lie ? 8 : 32)
      el.style.setProperty('--k', String(Math.max(0.1, fs ? Math.min(w / 1600, h / 900) : w / 1600)))
    }
    fit()
    const mq = matchMedia(LIE)
    mq.addEventListener('change', fit)
    const ro = new ResizeObserver(fit)
    ro.observe(el); ro.observe(b)
    return () => { ro.disconnect(); mq.removeEventListener('change', fit) }
  }, [full, view])

  const toggle = () => {
    if (document.fullscreenElement) { document.exitFullscreen?.(); return }
    if (full) { setFull(false); return }
    const el = box.current
    if (el?.requestFullscreen) el.requestFullscreen().then(lockLand, () => setFull(true))
    else setFull(true)
  }
  const exit = () => { if (document.fullscreenElement) document.exitFullscreen?.(); setFull(false) }
  useEffect(() => {
    const on = () => { setFull(!!document.fullscreenElement); if (!document.fullscreenElement) unlock() }
    document.addEventListener('fullscreenchange', on)
    return () => document.removeEventListener('fullscreenchange', on)
  }, [])
  // Клавиши листают показ по одному, пока он на экране.
  useEffect(() => {
    if (view !== 'single') return
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest('input,textarea,select')) return
      const r = box.current?.getBoundingClientRect()
      if (!(full || document.fullscreenElement || (r && r.top < innerHeight && r.bottom > 0))) return
      if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') { e.preventDefault(); go(at + 1) }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); go(at - 1) }
      else if (e.key === 'Home') go(0)
      else if (e.key === 'End') go(N - 1)
      else if (e.key === 'Escape' && full && !document.fullscreenElement) setFull(false)
    }
    addEventListener('keydown', key)
    return () => removeEventListener('keydown', key)
  }, [view, at, full, go])
  useEffect(() => {
    const s = strip.current, t = s?.children[at] as HTMLElement | undefined
    if (s && t) s.scrollTo({ left: t.offsetLeft - s.clientWidth / 2 + t.clientWidth / 2, behavior: 'smooth' })
  }, [at, view])

  const tools = <>
    <Seg value={view} onChange={pickView} items={[['list', 'Друг за другом'], ['single', 'По одному']]} label="Вид слайдов" />
    <button className="btn ghost icon-only" onClick={toggle} aria-pressed={full} aria-label={full ? 'Свернуть' : 'На весь экран'} data-tip={full ? 'Свернуть' : 'На весь экран'}>{full ? Ic.exit : Ic.full}</button>
    <a className="btn" href={`${BASE}/indeks-peremen.pdf`} download="Индекс перемен — Неслучайные связи.pdf">{Ic.pdf}<span className="desk-only">Скачать&nbsp;</span>PDF</a>
  </>
  return (
    <>
      <Slot id="top-tools" fallback={<div className="deck-tools">{tools}</div>}>{tools}</Slot>
      <div id="dk-show" ref={box} className={`deck ${view}${full ? ' deck-full' : ''}`} aria-roledescription="презентация"
        onTouchStart={(e) => { touch.current = [e.touches[0].clientX, e.touches[0].clientY] }}
        onTouchEnd={(e) => {
          const t0 = touch.current; touch.current = null
          if (!t0) return
          const dx = e.changedTouches[0].clientX - t0[0], dy = e.changedTouches[0].clientY - t0[1]
          if (view === 'single' && Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) go(at + (dx < 0 ? 1 : -1))
          else if (full && view === 'single' && dy > 80 && Math.abs(dy) > Math.abs(dx) * 1.5) exit()
        }}>
        {full && <button className="deck-exit" onClick={exit} aria-label="Выйти из полноэкранного режима">{Ic.close}</button>}
        <div className="deck-stage">
          <div ref={host} className="deck-host" />
          {view === 'single' && <>
            <button className="deck-nav prev" aria-label="Предыдущий слайд" disabled={at === 0} onClick={() => go(at - 1)}>{Ic.prev}</button>
            <button className="deck-nav next" aria-label="Следующий слайд" disabled={at === N - 1} onClick={() => go(at + 1)}>{Ic.next}</button>
          </>}
        </div>
        {view === 'single' && <>
          <div className="deck-bar"><span className="deck-count"><b>{at + 1}</b> / {N}</span><span className="deck-title">{SLIDES[at][1] ? <small>{SLIDES[at][1]}</small> : null}{SLIDES[at][0]}</span></div>
          <div className="deck-strip sc" ref={strip} role="tablist" aria-label="Слайды" onWheel={(e) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && strip.current) strip.current.scrollLeft += e.deltaY }}>
            {SLIDES.map(([t], i) => (
              <button key={i} role="tab" aria-selected={i === at} className={i === at ? 'on' : ''} onClick={() => go(i)} data-tip={`${i + 1}. ${t}`}>
                <img src={thumb(i)} alt="" loading="lazy" width={160} height={90} /><span>{i + 1}</span>
              </button>
            ))}
          </div>
        </>}
      </div>
      {view === 'single' && (
        <Card id="dk-toc" title="Содержание">
          <div className="deck-toc">
            {PARTS.map((p) => (
              <section key={p.from}>
                <h3>{p.title}</h3>
                <ol>
                  {p.items.filter((i) => SLIDES[i][1] !== '' || i === 0).map((i) => (
                    <li key={i}><button className={i === at ? 'on' : ''} onClick={() => { go(i); document.getElementById('dk-show')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}><span>{i + 1}</span>{SLIDES[i][0]}</button></li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}
