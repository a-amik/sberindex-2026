import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { BIZ_CAT } from '../data/biz'
import { CAT_SHORT, catColor } from '../data/real'
import { useApp } from '../store'

// Мокапы: блоки, где данных ещё нет или расчёт заменён приближением.
// Мокапы: блоки, где данных ещё нет или расчёт заменён приближением. Сейчас таких нет —
// реестр остаётся, чтобы новый блок без данных был помечен с первого дня.
export const MOCKS: Record<string, string> = {}

export function Mock({ k }: { k: string }) {
  return <span className="mock" data-tip={`<b>Мокап</b><br>${MOCKS[k]}`}>Мокап</span>
}

export function Info({ tip }: { tip: string }) {
  return <i className="info" data-tip={tip}>i</i>
}

/** Одна подсказка на всё приложение: читает data-tip у ближайшего предка. */
export function TipLayer() {
  const [st, setSt] = useState<{ html: string; x: number; y: number } | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: 0, top: 0 })
  useEffect(() => {
    let cur: Element | null = null
    const over = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return
      const el = (e.target as Element).closest?.('[data-tip]')
      if (el === cur) return
      cur = el
      if (!el || !el.getAttribute('data-tip')) return setSt(null)
      const r = el.getBoundingClientRect()
      setSt({ html: el.getAttribute('data-tip')!, x: r.left + r.width / 2, y: r.bottom + 8 })
    }
    const hide = () => { cur = null; setSt(null) }
    document.addEventListener('pointerover', over)
    window.addEventListener('scroll', hide, true)
    return () => { document.removeEventListener('pointerover', over); window.removeEventListener('scroll', hide, true) }
  }, [])
  useEffect(() => {
    if (!st || !ref.current) return
    const w = ref.current.offsetWidth, h = ref.current.offsetHeight
    setPos({ left: Math.min(innerWidth - w - 8, Math.max(8, st.x - w / 2)), top: st.y + h > innerHeight - 8 ? st.y - h - 40 : st.y })
  }, [st])
  if (!st) return null
  return <div ref={ref} className="tip" style={pos} dangerouslySetInnerHTML={{ __html: st.html }} />
}

export function Seg<T extends string | number>({ value, items, onChange, label }: { value: T; items: [T, string][]; onChange: (v: T) => void; label?: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {items.map(([v, t]) => <button key={String(v)} aria-pressed={v === value} onClick={() => onChange(v)}>{t}</button>)}
    </div>
  )
}

/** Ряд чипсов в одну строку: лишнее едет вбок, колесо ведёт ряд вбок. */
export function Row({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const wheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
      el.scrollLeft += e.deltaY
      e.preventDefault()
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [])
  return <div ref={ref} className="row-scroll">{children}</div>
}

export function CatChips({ value, onChange }: { value?: number; onChange?: (c: number) => void }) {
  const cat = useApp((s) => s.cat)
  const set = useApp((s) => s.set)
  const biz = useApp((s) => s.mode === 'biz')
  const v = value ?? cat
  return (
    <Row>
      {(biz ? BIZ_CAT : CAT_SHORT).map((name, c) => (
        <button key={c} className="chip" aria-pressed={v === c} onClick={() => (onChange ? onChange(c) : set({ cat: c }))}>
          <i style={{ background: catColor(c) }} />{name}
        </button>
      ))}
    </Row>
  )
}

export interface Col<R> { key: string; title: ReactNode; num?: boolean; get: (r: R) => number | string; render?: (r: R) => ReactNode; tip?: string }

/** Таблица: каждая колонка сортируется в обе стороны. */
export function Table<R>({ rows, cols, sort: init, onRow, rowClass, limit }: { rows: R[]; cols: Col<R>[]; sort?: [string, 1 | -1]; onRow?: (r: R) => void; rowClass?: (r: R) => string; limit?: number }) {
  const [sort, setSort] = useState<[string, 1 | -1]>(init ?? [cols[0].key, 1])
  const sorted = useMemo(() => {
    const c = cols.find((x) => x.key === sort[0])
    if (!c) return rows
    return [...rows].sort((a, b) => {
      const x = c.get(a), y = c.get(b)
      const d = typeof x === 'number' && typeof y === 'number' ? (Number.isFinite(x) ? x : Infinity) - (Number.isFinite(y) ? y : Infinity) : String(x).localeCompare(String(y), 'ru')
      return d * sort[1]
    })
  }, [rows, cols, sort])
  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} className={`s ${c.num ? 'n' : ''}`} data-tip={c.tip} onClick={() => setSort(([k, d]) => [c.key, k === c.key ? (-d as 1 | -1) : 1])}>
                {c.title}<span className="ar">{sort[0] === c.key ? (sort[1] === 1 ? '↑' : '↓') : ''}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(limit ? sorted.slice(0, limit) : sorted).map((r, i) => (
            <tr key={i} className={`${onRow ? 'click' : ''} ${rowClass?.(r) ?? ''}`} onClick={onRow ? () => onRow(r) : undefined}>
              {cols.map((c) => <td key={c.key} className={c.num ? 'n' : ''}>{c.render ? c.render(r) : String(c.get(r))}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Tabs<T extends string>({ value, items, onChange }: { value: T; items: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {items.map(([v, t]) => <button key={v} role="tab" aria-selected={v === value} onClick={() => onChange(v)}>{t}</button>)}
    </div>
  )
}

export function Card({ id, title, sub, mock, extra, children }: { id?: string; title: ReactNode; sub?: ReactNode; mock?: string; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="card" id={id}>
      <header>
        <h2>{title}{mock && <Mock k={mock} />}</h2>
        {extra}
        {sub && <p>{sub}</p>}
      </header>
      {children}
    </section>
  )
}

/** Лоадер области: знак в круге и подпись, пока данные едут. */
export function Wait({ label }: { label: string }) {
  return <div className="wait" role="status"><nl-loader variant="link" aria-label={label} />{label}</div>
}

declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'nl-loader': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & { variant?: string; t?: string }
    }
  }
}

/** Список с пиктограммой у каждого пункта: шаги, продукты, обещания. */
export function IconList({ items }: { items: [ReactNode, ReactNode][] }) {
  return <ul className="ic-list">{items.map(([ic, body], i) => <li key={i}><span className="ic">{ic}</span><div>{body}</div></li>)}</ul>
}

/** Нижний лист на телефоне сворачивается жестом вниз: за ручку и шапку всегда, за тело —
 *  когда оно прокручено к началу. Лист идёт за пальцем; дальше порога или быстрым
 *  смахиванием — закрывается, иначе возвращается на место. */
export function useSheetDrag<T extends HTMLElement>(onClose: () => void) {
  const ref = useRef<T>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const el = ref.current
    if (!el || !matchMedia('(max-width: 760px)').matches) return
    let y0 = 0, t0 = 0, dy = 0, on = false, body: HTMLElement | null = null
    const start = (e: TouchEvent) => {
      const t = e.target as HTMLElement
      if (t.closest('input,select,textarea,[role=slider],.row-scroll')) return
      body = t.closest('.sheet-b')
      y0 = e.touches[0].clientY; t0 = performance.now(); dy = 0; on = true
    }
    const move = (e: TouchEvent) => {
      if (!on) return
      const d = e.touches[0].clientY - y0
      if (body && body.scrollTop > 0) { on = false; return }
      if (d <= 0 && dy === 0) { if (body) on = false; return }
      dy = Math.max(0, d)
      e.preventDefault()
      el.style.transition = 'none'
      el.style.transform = `translateY(${dy}px)`
    }
    const end = () => {
      if (!on) return
      on = false
      const v = dy / Math.max(1, performance.now() - t0)
      el.style.transition = 'transform .22s ease-out'
      if (dy > Math.min(140, el.offsetHeight * 0.25) || (dy > 30 && v > 0.6)) {
        el.style.transform = 'translateY(100%)'
        setTimeout(() => close.current(), 200)
      } else el.style.transform = ''
    }
    el.addEventListener('touchstart', start, { passive: true })
    el.addEventListener('touchmove', move, { passive: false })
    el.addEventListener('touchend', end)
    el.addEventListener('touchcancel', end)
    return () => {
      el.removeEventListener('touchstart', start)
      el.removeEventListener('touchmove', move)
      el.removeEventListener('touchend', end)
      el.removeEventListener('touchcancel', end)
    }
  }, [])
  return ref
}
