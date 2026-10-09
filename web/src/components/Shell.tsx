/**
 * Каркас по образцу «Маршрута дня»: колонка разделов во всю высоту слева,
 * знак — в её верхней ячейке; сверху — то, с чем работают каждый день
 * (обзор, карта, шоки), снизу — разбор и показ (модели, детекторы, стенд),
 * под чертой — описание решения. Шапка стоит только над экраном: название,
 * поиск территории (⌘K) и меню «…» с темой и метками мокапов.
 *
 * На телефоне колонки нет: разделы — нижней панелью из пяти, детекторы
 * и «О проекте» уходят в «…», главы страниц — в бургер её шапки.
 */
import { createPortal } from 'react-dom'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { MOS } from '../data/real'
import { ROLE_NAME, type Role } from '../data/biz'
import { useApp, type Screen } from '../store'
import { I } from './icons'
import { useSheetDrag } from './ui'
import { BIZ_CAT } from '../data/biz'
import { CAT_SHORT, catColor } from '../data/real'
import { combine, NONE, PRESETS, scnKeys, scnLabel, WORLD_PRESETS } from '../data/whatif'
import { ScenarioKnobs } from './ScenarioKnobs'

interface Item { key: Screen; label: string; title: string; icon: ReactNode }
// Разделы одни на оба режима: режим меняет язык и число ручек, а не набор разделов.
const MAIN: Item[] = [
  { key: 'sum', label: 'Сводка', title: 'Прогноз спроса, регионы для расширения и сценарии', icon: I.overview },
  { key: 'reg', label: 'Карта', title: 'Карта регионов и муниципалитетов с рекомендациями', icon: I.map },
  { key: 'rank', label: 'Рейтинг', title: 'Регионы по объёму рынка, росту и точности прогноза', icon: I.rank },
  { key: 'cats', label: 'Категории', title: 'Рост трат по категориям и доли рынка', icon: I.cats },
  { key: 'dyn', label: 'Динамика', title: 'Смена мест в рейтинге и траты регионов по месяцам', icon: I.trend },
]
// Внизу колонки — разбор: риски и описание решения (решение участника 04.10.2026).
const UPPER: Item[] = [
  { key: 'risk', label: 'Риски', title: 'Где спрос снизился или вырос', icon: I.shocks },
  { key: 'about', label: 'О проекте', title: 'Надёжность прогноза, модели, детекторы, испытания, данные, методика', icon: I.about },
]
export const TITLES: Record<Screen, string> = { sum: 'Сводка', reg: 'Карта', rank: 'Рейтинг', cats: 'Категории', dyn: 'Динамика', risk: 'Риски', about: 'О проекте' }

export function Rail() {
  const { screen, go, set } = useApp()
  const item = (i: Item) => (
    <button key={i.key} className={`rail-i${screen === i.key ? ' on' : ''}`} aria-current={screen === i.key ? 'page' : undefined} title={i.title} onClick={() => go(i.key)}>
      {i.icon}<span>{i.label}</span>
    </button>
  )
  return (
    <nav className="rail" aria-label="Разделы">
      <button className="rail-brand" title="Неслучайные связи — к сводке" aria-label="Неслучайные связи: к сводке" onClick={() => { set({ sel: null }); go('sum') }}>
        <img src="/brand/mark.svg" alt="" />
      </button>
      {MAIN.map(item)}
      <span className="sp" />
      <hr className="rail-hr" />
      {UPPER.map(item)}
    </nav>
  )
}

// На телефоне пять мест: четыре главных раздела и «Ещё…» — нижний лист с остальными.
const PHONE_MORE: Item[] = [MAIN[4], ...UPPER]
export function PhoneNav() {
  const { screen, go } = useApp()
  const [more, setMore] = useState(false)
  const inMore = PHONE_MORE.some((i) => i.key === screen)
  const btn = (i: Item) => (
    <button key={i.key} className={screen === i.key ? 'on' : ''} aria-current={screen === i.key ? 'page' : undefined} onClick={() => go(i.key)}>
      {i.icon}<span>{i.label}</span>
    </button>
  )
  return (
    <>
      <nav className="pnav" aria-label="Разделы">
        {MAIN.slice(0, 4).map(btn)}
        <button className={inMore ? 'on' : ''} aria-haspopup="dialog" aria-expanded={more} onClick={() => setMore(true)}>
          {inMore ? PHONE_MORE.find((i) => i.key === screen)!.icon : I.more}<span>{inMore ? TITLES[screen] : 'Ещё…'}</span>
        </button>
      </nav>
      {more && <MoreSheet items={PHONE_MORE} close={() => setMore(false)} pick={(k) => { setMore(false); go(k) }} />}
    </>
  )
}

function MoreSheet({ items, close, pick }: { items: Item[]; close: () => void; pick: (k: Screen) => void }) {
  const { screen } = useApp()
  const drag = useSheetDrag<HTMLElement>(close)
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && close()
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [close])
  return createPortal(
    <>
      <div className="sheet-scrim" onClick={close} />
      <aside ref={drag} className="sheet more-sheet" role="dialog" aria-label="Разделы">
        <div className="grab" />
        <div className="sheet-h">
          <div className="sheet-t"><h2>Разделы</h2></div>
          <button className="icon-btn" aria-label="Закрыть" onClick={close}>{I.close}</button>
        </div>
        <div className="sheet-b">
          {items.map((i) => (
            <button key={i.key} className={`more-i${screen === i.key ? ' on' : ''}`} onClick={() => pick(i.key)}>
              <span className="ic">{i.icon}</span><span><b>{i.label}</b><small>{i.title}</small></span>
            </button>
          ))}
        </div>
      </aside>
    </>,
    document.body,
  )
}

export function TopBar({ phone, children }: { phone: boolean; children?: ReactNode }) {
  const { set } = useApp()
  const hidden = useAutoHide(phone)
  if (phone) {
    return (
      <header className={`top${hidden ? ' hide' : ''}`}>
        <span className="brand-sm"><img src="/brand/mark.svg" alt="" />Неслучайные связи</span>
        <span className="fill" />
        <button className="icon-btn" aria-label="Найти территорию" onClick={() => set({ palette: true })}>{I.search}</button>
        <More />
      </header>
    )
  }
  return (
    <header className="top">
      {children}
      <span className="fill" />
      <button className="search-btn" onClick={() => set({ palette: true })} title="Найти территорию (⌘K)">{I.search}<span>Найти территорию</span><kbd>⌘K</kbd></button>
      <span className="top-tools"><More /></span>
    </header>
  )
}

function More() {
  const { theme, marks, set, mode, setMode, role } = useApp()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const off = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', off)
    addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', off); removeEventListener('keydown', esc) }
  }, [open])
  const act = (f: () => void) => () => { setOpen(false); f() }
  return (
    <div className="menu-wrap" ref={ref}>
      {/* Аватар вместо «…»: буква — режим, А — аналитик, Б — бизнес; внутри — профиль и настройки. */}
      <button className={`avatar ${mode}`} aria-label={`Профиль: ${mode === 'biz' ? 'для бизнеса' : 'для аналитика'}`} title={`${mode === 'biz' ? 'Для бизнеса' : 'Для аналитика'} · ${ROLE_NAME[role]}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>{mode === 'biz' ? 'Б' : 'А'}</button>
      {open && (
        <div className="menu" role="menu">
          <small className="menu-h">Режим</small>
          {(['biz', 'pro'] as const).map((m) => <button key={m} onClick={act(() => setMode(m))} aria-checked={mode === m} role="menuitemradio">{mode === m ? I.check : <span className="i" />}{m === 'biz' ? 'Для бизнеса' : 'Для аналитика'}</button>)}
          <>
            <small className="menu-h">Профиль заказчика</small>
            {(Object.keys(ROLE_NAME) as Role[]).map((r) => <button key={r} onClick={act(() => set({ role: r }))} aria-checked={role === r} role="menuitemradio">{role === r ? I.check : <span className="i" />}{ROLE_NAME[r]}</button>)}
          </>
          <hr />
          <button onClick={act(() => set({ theme: theme === 'dark' ? 'light' : 'dark' }))}>{theme === 'dark' ? I.sun : I.moon}{theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}</button>
          {mode === 'pro' && <button onClick={act(() => set({ marks: !marks }))}>{I.tag}{marks ? 'Скрыть пометки макетов' : 'Показать пометки макетов'}</button>}
        </div>
      )}
    </div>
  )
}

/** Поиск территории по имени и субъекту: ⌘K или кнопка в шапке. */
export function Palette() {
  const { palette, set, openMo } = useApp()
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); set({ palette: !useApp.getState().palette }) }
    }
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [set])
  const found = useMemo(() => {
    const s = q.trim().toLowerCase()
    const list = s ? MOS.filter((m) => m.name.toLowerCase().includes(s) || m.full.toLowerCase().includes(s) || m.region.toLowerCase().includes(s)) : [...MOS].sort((a, b) => b.pop - a.pop)
    return list.slice(0, 40)
  }, [q])
  if (!palette) return null
  const close = () => { set({ palette: false }); setQ('') }
  return (
    <div className="pal-bg" onPointerDown={(e) => e.target === e.currentTarget && close()}>
      <div className="pal" role="dialog" aria-label="Поиск территории">
        <input autoFocus placeholder="Город, район или субъект" value={q} onChange={(e) => { setQ(e.target.value); setI(0) }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { setI((x) => Math.min(found.length - 1, x + 1)); e.preventDefault() }
            if (e.key === 'ArrowUp') { setI((x) => Math.max(0, x - 1)); e.preventDefault() }
            if (e.key === 'Enter' && found[i]) { openMo(found[i].id); setQ('') }
            if (e.key === 'Escape') close()
          }} />
        <div className="pal-list sc">
          {found.map((m, k) => <button key={m.id} className={k === i ? 'on' : ''} onClick={() => { openMo(m.id); setQ('') }}>{m.name}<small>{m.region}</small></button>)}
          {!found.length && <p className="small" style={{ padding: 12 }}>Территории не найдены</p>}
        </div>
      </div>
    </div>
  )
}

/**
 * Страница раздела: колонка слева, на телефоне — бургер в шапке страницы. Как в «О проекте»
 * у «Маршрута дня»: если у раздела несколько страниц, в колонке — страницы, а под открытой —
 * её главы.
 */
export function Page({ nav, active, onNav, tools, children, pages, page, onPage }: {
  nav: [string, string][]; active: string; onNav: (id: string) => void; tools?: ReactNode; children: ReactNode
  pages?: [string, string, ReactNode?][]; page?: string; onPage?: (key: string) => void
}) {
  const [burger, setBurger] = useState(false)
  const screen = useApp((s) => s.screen)
  const chapters = (indent: boolean, close?: () => void) => nav.map(([id, t]) => (
    <button key={id} className={`${active === id ? 'on' : ''}${indent ? ' sub' : ''}`} onClick={() => { close?.(); onNav(id) }}>{t}</button>
  ))
  const tree = (close?: () => void) => pages
    ? pages.map(([k, t, ic]) => (
      <div key={k} style={{ display: 'contents' }}>
        <button className={`page-link${k === page ? ' cur' : ''}`} onClick={() => { close?.(); onPage?.(k) }}>{ic}<span>{t}</span></button>
        {k === page && chapters(true, close)}
        {k === 'deck' && <hr className="page-sep" />}
      </div>
    ))
    : chapters(false, close)
  return (
    <div className="page">
      <nav className="page-nav sc" aria-label="Страницы и главы">
        {screen !== 'about' && <small>{TITLES[screen]}</small>}
        {tree()}
      </nav>
      <div className="page-main sc" id="page-main">
        <div className="page-in">
          <div className="phone-only" style={{ display: 'flex', alignItems: 'center', gap: 8, position: 'relative' }}>
            <h1 style={{ fontSize: 22, marginRight: 'auto' }}>{pages ? <><small className="page-sup">{TITLES[screen]}</small>{pages.find((p) => p[0] === page)?.[1]}</> : TITLES[screen]}</h1>
            <button className="icon-btn" aria-label="Страницы и главы" aria-expanded={burger} onClick={() => setBurger((b) => !b)}>{I.menu}</button>
            {burger && <div className="menu sc" style={{ top: 40, maxHeight: '70vh' }}>{tree(() => setBurger(false))}</div>}
          </div>
          {tools && <div className="page-tools">{tools}</div>}
          {children}
        </div>
      </div>
    </div>
  )
}

/** Глава под курсором прокрутки: подсвечивает её в колонке. */
export function useSections(ids: string[]) {
  const [active, setActive] = useState(ids[0])
  useEffect(() => {
    const root = document.getElementById('page-main')
    if (!root) return
    const io = new IntersectionObserver((es) => {
      const vis = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (vis[0]) setActive(vis[0].target.id)
    }, { root: innerWidth > 760 ? root : null, rootMargin: '0px 0px -60% 0px' })
    ids.forEach((id) => { const el = document.getElementById(id); if (el) io.observe(el) })
    return () => io.disconnect()
  }, [ids.join()])
  const go = (id: string) => { setActive(id); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  return [active, go] as const
}

// Шапка на телефоне уходит по скроллу вниз и возвращается от движения вверх.
function useAutoHide(on: boolean) {
  const [hide, setHide] = useState(false)
  useEffect(() => {
    if (!on) return
    let y = scrollY, acc = 0
    const f = () => {
      const dy = scrollY - y
      y = scrollY
      if (scrollY < 50 || document.querySelector('.sheet')) { acc = 0; return setHide(false) }
      if (Math.abs(dy) > 400) return
      if (Math.sign(dy) !== Math.sign(acc)) acc = 0
      acc += dy
      if (acc > 8) setHide(true)
      else if (acc < -40) setHide(false)
    }
    addEventListener('scroll', f, { passive: true })
    const back = () => setHide(false)
    addEventListener('focusin', back)
    return () => { removeEventListener('scroll', f); removeEventListener('focusin', back) }
  }, [on])
  return hide
}

export function usePhone() {
  const q = '(max-width: 760px)'
  const [p, setP] = useState(() => matchMedia(q).matches)
  useEffect(() => {
    const m = matchMedia(q)
    const f = () => setP(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  return p
}


/**
 * Сквозные фильтры в верхней строке, рядом с календарём и в том же виде: тип покупок
 * и сценарий. Одни на все экраны — категория и сценарий лежат в store. Сценарий — список
 * с галочками: пресеты сочетаются, факторы складываются (решение участника 04.10.2026);
 * своё сочетание раскрывает ручки под верхней строкой.
 */
function useMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const off = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', off)
    addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', off); removeEventListener('keydown', esc) }
  }, [open])
  return { open, setOpen, ref }
}

export function CatMenu() {
  const { cat, set, mode } = useApp()
  const { open, setOpen, ref } = useMenu()
  const names = mode === 'biz' ? BIZ_CAT : CAT_SHORT
  return (
    <div className="menu-wrap mp" ref={ref}>
      <button className="mp-btn" aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((o) => !o)} title="Категория покупок">
        {I.bag}<span>{names[cat]}</span><i className="mp-dot" style={{ background: catColor(cat) }} />
      </button>
      {open && (
        <div className="menu" role="menu">
          <small className="menu-h">Покупки</small>
          {names.map((name, c) => (
            <button key={c} role="menuitemradio" aria-checked={cat === c} onClick={() => { set({ cat: c }); setOpen(false) }}>
              {cat === c ? I.check : <span className="i" />}<i className="dot" style={{ background: catColor(c), margin: 0 }} />{name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function ScenarioMenu() {
  const { set, scn, selRk } = useApp()
  const { open, setOpen, ref } = useMenu()
  const keys = scnKeys(scn.key)
  const apply = (next: string[]) => {
    const f = combine(next)
    const s = useApp.getState().scn
    set({ scn: { ...s, key: next.length ? next.join('+') : 'base', f, scope: f.flood ? 'region' : s.scope } })
    if (f.flood && selRk === null) set({ selRk: 0 })
  }
  const toggle = (k: string) => apply(keys.includes(k) ? keys.filter((x) => x !== k) : [...keys, k])
  const custom = () => { const s = useApp.getState().scn; set({ scn: { ...s, key: 'custom', f: s.key === 'base' ? { ...NONE } : s.f }, knobs: true }); setOpen(false) }
  const label = scn.key === 'base' ? 'Базовый прогноз' : scn.key === 'custom' ? 'Своё сочетание' : keys.length === 1 ? scnLabel(scn.key) : `${keys.length} ${keys.length < 5 ? 'сценария' : 'сценариев'} вместе`
  const item = (p: { key: string; name: string; text: string }) => (
    <button key={p.key} role="menuitemcheckbox" aria-checked={keys.includes(p.key)} onClick={() => toggle(p.key)} data-tip={p.text}>
      {keys.includes(p.key) ? I.check : <span className="i" />}{p.name}
    </button>
  )
  return (
    <div className="menu-wrap mp" ref={ref}>
      <button className={`mp-btn${scn.key !== 'base' ? ' on' : ''}`} aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((o) => !o)} title={scn.key !== 'base' ? scnLabel(scn.key) : 'Сценарий'}>
        {I.fork}<span>{label}</span>
      </button>
      {open && (
        <div className="menu" role="menu">
          <button role="menuitemradio" aria-checked={scn.key === 'base'} onClick={() => { apply([]); setOpen(false) }}>{scn.key === 'base' ? I.check : <span className="i" />}Базовый прогноз</button>
          <small className="menu-h">Сочетайте сценарии</small>
          {PRESETS.map(item)}
          <small className="menu-h">Сценарии мировой экономики</small>
          {WORLD_PRESETS.map(item)}
          <hr />
          <button role="menuitem" onClick={custom}>{scn.key === 'custom' ? I.check : <span className="i" />}Своё сочетание…</button>
        </div>
      )}
    </div>
  )
}

/** Своё сочетание — сайд-шитом справа от уже открытого шита (или от края, если шита нет). */
export function FilterBar() {
  const { scn, mode, knobs, set } = useApp()
  const show = knobs && (scn.key === 'custom' || mode === 'pro')
  const [left, setLeft] = useState(0)
  useEffect(() => {
    if (!show) return
    const body = document.querySelector('.body')
    if (!body) return
    const place = () => {
      const b = body.getBoundingClientRect()
      const r = [...body.querySelectorAll('.sheet:not(.knobs-sheet)')].map((x) => x.getBoundingClientRect().right - b.left)
      setLeft(r.length ? Math.max(...r) : 0)
    }
    place()
    const mo = new MutationObserver(place)
    mo.observe(body, { childList: true, subtree: true })
    addEventListener('resize', place)
    return () => { mo.disconnect(); removeEventListener('resize', place) }
  }, [show])
  if (!show) return null
  const close = () => set({ knobs: false })
  return createPortal(
    <>
      <div className="sheet-scrim knobs-scrim" onClick={close} />
      <KnobsSheet left={left} close={close} />
    </>,
    document.querySelector('.body') ?? document.body,
  )
}

/**
 * Место в полосе шапки, куда страница кладёт свой заголовок и ручки (порталом).
 * Узел появляется после отрисовки шапки, поэтому ищем его кадр за кадром. Нет узла
 * (телефон: шапка без слотов) — показываем fallback на месте.
 */
export function Slot({ id, children, fallback = null }: { id: string; children: ReactNode; fallback?: ReactNode }) {
  const [el, setEl] = useState<HTMLElement | null>(null)
  useEffect(() => {
    let raf = 0, n = 0
    const find = () => { const e = document.getElementById(id); if (e) setEl(e); else if (n++ < 30) raf = requestAnimationFrame(find) }
    find()
    return () => cancelAnimationFrame(raf)
  }, [id])
  return el ? createPortal(children, el) : <>{fallback}</>
}

function KnobsSheet({ left, close }: { left: number; close: () => void }) {
  const drag = useSheetDrag<HTMLElement>(close)
  return (
    <aside ref={drag} className="sheet knobs-sheet" role="dialog" aria-label="Своё сочетание" style={{ left }}>
      <div className="grab" />
      <div className="sheet-h">
        <div className="sheet-t"><h2>Своё сочетание</h2></div>
        <button className="icon-btn" aria-label="Закрыть" onClick={close}>{I.close}</button>
      </div>
      <div className="sheet-b sc"><ScenarioKnobs /></div>
    </aside>
  )
}
