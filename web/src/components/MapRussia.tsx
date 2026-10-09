import type React from 'react'
import { geoArea, geoMercator, geoCentroid, geoPath, type GeoPermissibleObjects } from 'd3-geo'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Mo } from '../data/real'
import { I } from './icons'

let LAND: GeoPermissibleObjects | null = null
const landReady = fetch('/data/russia.json').then((r) => r.json()).then((j) => (LAND = j))
export interface Shape { name: string; lx: number; ly: number; geometry: GeoPermissibleObjects | null }
// Соседи — грубо, для ориентира: где граница и с кем.
let NB: { features: { properties: { name: string }; geometry: GeoPermissibleObjects }[] } | null = null
const nbReady = fetch('/data/neighbours.json').then((r) => r.json()).then((j) => (NB = j))
// Регионы, которые Конституция РФ относит к России, но по которым нет данных СберИндекса:
// серым со штриховкой — данных и прогнозов нет, в том числе из-за боевых действий.
let EXTRA: { features: { properties: { name: string }; geometry: GeoPermissibleObjects }[] } | null = null
const extraReady = fetch('/data/extra_regions.json').then((r) => r.json()).then((j) => (EXTRA = j))
// Крупнейшие соседи подписаны на масштабе страны.
const NB_LABEL = new Set(['Казахстан', 'Китай', 'Монголия', 'Финляндия', 'Украина', 'Беларусь', 'Норвегия', 'Япония'])
let MSK: Record<string, Shape> | null = null
const mskReady = fetch('/data/cities.json').then((r) => r.json()).then((j) => (MSK = j))

// Контуры всех МО (mo_shapes.py): грузятся в фоне, до них карта стоит точками.
let SHAPES: Record<string, GeoPermissibleObjects> | null = null
// Контур больше полусферы — это вывернутое кольцо: d3 закрасил бы им весь шар. Разворачиваем.
type Geo = { type: string; coordinates: number[][][] | number[][][][] }
// Проверяется каждая часть мультиполигона отдельно: вывернутой бывает одна, остальные трогать нельзя.
const fixPoly = (poly: number[][][]) => (geoArea({ type: 'Polygon', coordinates: poly } as never) > 2 * Math.PI ? poly.map((ring) => [...ring].reverse()) : poly)
const rewind = (g: Geo): Geo => ({ type: g.type, coordinates: g.type === 'Polygon' ? fixPoly(g.coordinates as number[][][]) : (g.coordinates as number[][][][]).map(fixPoly) })
const shapesReady = fetch('/data/shapes.json').then((r) => r.json()).then((j: Record<string, Geo>) => (SHAPES = Object.fromEntries(Object.entries(j).map(([k, g]) => [k, rewind(g) as never]))))

export interface Dot { mo: Mo; v: number; tip: string }
interface View { k: number; x: number; y: number }

const K_MAX = 700
// Наружу карта отдаляется на четверть: видны соседи вокруг России, но не край мира.
// Карта мира с центром на 100° в. д. кончается на 80° з. д., и при сильном отдалении по краям была пустота.
const K_MIN = 0.75
// С этого увеличения районы Москвы и округа Петербурга рисуются контурами, а не точками; с K_LABEL — подписаны.
const K_SHAPES = 14
const K_LABEL = 45
// Города федерального значения на масштабе страны — значками: их районы там меньше пикселя.
// Значки городов — силуэты, по которым город узнают без подписи: Спасская башня со звездой
// и шпиль Адмиралтейства с корабликом. Поле 24 × 24 с центром в нуле; вырезы — evenodd.
const KREMLIN = 'M-6.5 10V3.5H-5V2H-3.6V3.5H-2.2V2H2.2V3.5H3.6V2H5V3.5H6.5V10ZM-1.6 10V7A1.6 1.6 0 0 1 1.6 7V10ZM-3.4 2V-1.8H3.4V2ZM-1 1V-0.6H1V1ZM-2.6 -1.8L0 -8.6L2.6 -1.8ZM0 -9.4L.55 -10.6L1.8 -10.7L.85 -11.5L1.15 -12.7L0 -12L-1.15 -12.7L-.85 -11.5L-1.8 -10.7L-.55 -10.6Z'
const ADMIRALTY = 'M-8 10V5.6H8V10ZM-6.6 9V6.8H-5.6V9ZM-4.4 9V6.8H-3.4V9ZM3.4 9V6.8H4.4V9ZM5.6 9V6.8H6.6V9ZM-1.4 10V7.4A1.4 1.4 0 0 1 1.4 7.4V10ZM-3.2 5.6V1H3.2V5.6ZM-2 1V-1.6H2V1ZM-.7 -1.6L0 -9.4L.7 -1.6ZM-2.6 -10.2H2.6L1.6 -9.2H-1.6ZM-.25 -10.2V-12.8L1.6 -10.6Z'
const CITIES = [{ code: 'МСК', region: 'Москва', at: [37.62, 55.75] as [number, number], d: KREMLIN }, { code: 'СПБ', region: 'Санкт-Петербург', at: [30.32, 59.94] as [number, number], d: ADMIRALTY }]

/**
 * Россия на плоской карте (Меркатор, как у Яндекса, центр 100° в. д.): Чукотка не рвётся,
 * север не раздувается вдвое, как в Меркаторе. Зум — колесом у курсора, щипком,
 * двойным нажатием и кнопками; карта тащится мышью и пальцем. Точки и линии
 * держат экранный размер при любом увеличении.
 */
export interface Mark { lon: number; lat: number; name: string; color: string; glyph: string; tip: string }

export function MapRussia({ dots, color, onPick, selected, focus, pad = 16, inset = 0, mini = false, marks = [], keep, tools }: {
  dots: Dot[]; color: (v: number) => string; onPick: (m: Mo) => void; selected?: number | null
  /** Меняется — карта перелетает к выбранной территории. */
  focus?: number; pad?: number
  /** Сколько пикселей слева закрыто шторкой: центр видимой части сдвигается вправо. */
  inset?: number
  /** Мини-карта: без зума и кнопок, только наведение и выбор. */
  mini?: boolean
  /** Свои кнопки в панели карты — например, слои; встают отдельной группой под городами. */
  tools?: React.ReactNode
  /** Значки точечных слоёв. */
  marks?: Mark[]
  /** Если задано — МО вне набора притушены: слой работает фильтром. */
  keep?: Set<number> | null
}) {
  const [hoverRk, setHoverRk] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState({ w: 800, h: 500 })
  const [land, setLand] = useState(LAND)
  const [msk, setMsk] = useState(MSK)
  const [shp, setShp] = useState(SHAPES)
  const [nb, setNb] = useState(NB)
  const [extra, setExtra] = useState(EXTRA)
  useEffect(() => { if (!extra) extraReady.then(setExtra) }, [extra])
  useEffect(() => { if (!nb) nbReady.then(setNb) }, [nb])
  useEffect(() => { if (!shp) shapesReady.then(setShp) }, [shp])
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 })
  const viewRef = useRef(view)
  viewRef.current = view
  useEffect(() => { if (!land) landReady.then(setLand) }, [land])
  useEffect(() => { if (!msk) mskReady.then(setMsk) }, [msk])
  // Мерим область сразу, до первой отрисовки, — иначе карта на миг встаёт в запасной размер.
  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect()
    if (r?.width && r.height) setBox({ w: r.width, h: r.height })
  }, [])
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setBox({ w: Math.max(260, e.contentRect.width), h: Math.max(200, e.contentRect.height) }))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  const { w, h } = box
  const proj = useMemo(() => {
    // Плоская карта, как у Яндекса и Google: Меркатор с центром на 100° в. д., чтобы Чукотка не рвалась на краю.
    // Север у Меркатора растянут — Таймыр и острова крупнее, чем в атласе, — зато картина привычна глазу.
    const p = geoMercator().rotate([-100, 0])
    if (land) p.fitExtent([[pad, pad], [w - pad, h - pad]], land as never)
    return p
  }, [land, w, h, pad])
  const path = useMemo(() => geoPath(proj), [proj])
  const landD = useMemo(() => (land ? path(land) ?? '' : ''), [land, path])
  const extras = useMemo(() => (extra ? extra.features.map((f) => ({ name: f.properties.name, d: path(rewind(f.geometry as never) as never) ?? '' })) : []), [extra, path])
  const nbs = useMemo(() => (nb ? nb.features.map((f) => ({ name: f.properties.name, d: path(f.geometry) ?? '', c: proj(geoCentroid(f.geometry as never)) })) : []), [nb, path, proj])
  const shapes = useMemo(() => (msk ? Object.entries(msk).filter(([, s]) => s.geometry).map(([id, s]) => ({ id: +id, s, d: path(s.geometry!) ?? '', c: proj([s.lx, s.ly]) })) : []), [msk, path, proj])
  const moPaths = useMemo(() => (shp ? new Map(Object.entries(shp).map(([id, g]) => [+id, path(g) ?? ''])) : new Map<number, string>()), [shp, path])
  const xy = useMemo(() => new Map(dots.filter((d) => d.mo.lat !== null).map((d) => [d.mo.id, proj([d.mo.lon!, d.mo.lat!])])), [dots, proj])
  const byId = useMemo(() => new Map(dots.map((d) => [d.mo.id, d])), [dots])

  // ── Вид: колесо у курсора, перетаскивание, щипок, двойное нажатие, перелёт
  // Сдвиг ограничен рамкой вокруг России: от Атлантики до Тихого океана, от тропиков до полюса.
  // Дальше этой рамки карта мира кончается (центр на 100° в. д.), и за краем была пустота.
  const frame = useMemo(() => {
    const a = proj([-25, 84]), b = proj([215, 5])
    return a && b ? [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])] : null
  }, [proj])
  const clampView = (v: View): View => {
    const k = Math.min(K_MAX, Math.max(K_MIN, v.k))
    if (!frame) return { k, x: v.x, y: v.y }
    // Экран w × h показывает мир от (−x/k) до ((w − x)/k); рамка шире экрана — держим экран внутри,
    // уже экрана — держим её посередине.
    const fit = (lo: number, hi: number, size: number, off: number) => {
      const a = size - hi * k, b = -lo * k
      return a <= b ? Math.min(b, Math.max(a, off)) : (a + b) / 2
    }
    return { k, x: fit(frame[0], frame[2], w, v.x), y: fit(frame[1], frame[3], h, v.y) }
  }
  const zoomAt = (f: number, cx: number, cy: number) => setView((v) => {
    const k = Math.min(K_MAX, Math.max(K_MIN, v.k * f))
    const r = k / v.k
    return clampView({ k, x: cx - (cx - v.x) * r, y: cy - (cy - v.y) * r })
  })
  const anim = useRef(0)
  const flyTo = (to: View) => {
    cancelAnimationFrame(anim.current)
    const from = viewRef.current, t0 = performance.now()
    const dur = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500
    const cx = (w - inset) / 2 + inset, cy = h / 2
    const a = [(cx - from.x) / from.k, (cy - from.y) / from.k], b = [(cx - to.x) / to.k, (cy - to.y) / to.k]
    const step = (now: number) => {
      const p = dur ? Math.min(1, (now - t0) / dur) : 1
      const e = 1 - Math.pow(1 - p, 3)
      // Масштаб идёт по логарифму: иначе перелёт в сто раз проскакивает середину мгновенно.
      const k = Math.exp(Math.log(from.k) + (Math.log(to.k) - Math.log(from.k)) * e)
      const gx = a[0] + (b[0] - a[0]) * e, gy = a[1] + (b[1] - a[1]) * e
      setView({ k, x: cx - gx * k, y: cy - gy * k })
      if (p < 1) anim.current = requestAnimationFrame(step)
    }
    anim.current = requestAnimationFrame(step)
  }
  const centerOn = (p: [number, number] | null | undefined, k: number) => {
    if (!p) return
    const cx = (w - inset) / 2 + inset, cy = h / 2
    flyTo({ k, x: cx - p[0] * k, y: cy - p[1] * k })
  }
  useEffect(() => {
    if (!focus || selected == null) return
    const s = msk?.[selected]
    if (s) centerOn(proj([s.lx, s.ly]) as [number, number], Math.max(viewRef.current.k, 70))
    else centerOn(xy.get(selected) as [number, number] | undefined, Math.max(viewRef.current.k, 4))
  }, [focus])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const wheel = (e: WheelEvent) => {
      if (mini) return
      e.preventDefault()
      cancelAnimationFrame(anim.current)
      const r = el.getBoundingClientRect()
      zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0025)), e.clientX - r.left, e.clientY - r.top)
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [w, h])
  const ptrs = useRef(new Map<number, { x: number; y: number }>())
  const moved = useRef(false)
  const [drag, setDrag] = useState(false)
  const pinch = useRef<number | null>(null)
  const local = (e: { clientX: number; clientY: number }) => { const r = ref.current!.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top } }
  const onDown = (e: React.PointerEvent) => {
    ptrs.current.set(e.pointerId, local(e))
    moved.current = false
    cancelAnimationFrame(anim.current)
  }
  const onMove = (e: React.PointerEvent) => {
    const prev = ptrs.current.get(e.pointerId)
    if (!prev) return
    const cur = local(e)
    if (ptrs.current.size === 2) {
      ptrs.current.set(e.pointerId, cur)
      const [a, b] = [...ptrs.current.values()]
      const d = Math.hypot(a.x - b.x, a.y - b.y)
      if (pinch.current) zoomAt(d / pinch.current, (a.x + b.x) / 2, (a.y + b.y) / 2)
      pinch.current = d
      moved.current = true
      return
    }
    const dx = cur.x - prev.x, dy = cur.y - prev.y
    if (!moved.current && Math.abs(dx) + Math.abs(dy) > 3) { moved.current = true; setDrag(true) }
    if (moved.current && !mini) setView((v) => clampView({ ...v, x: v.x + dx, y: v.y + dy }))
    ptrs.current.set(e.pointerId, cur)
  }
  const onUp = (e: React.PointerEvent) => {
    ptrs.current.delete(e.pointerId)
    if (ptrs.current.size < 2) pinch.current = null
    if (!ptrs.current.size) setDrag(false)
  }
  // Нажатие после перетаскивания — не выбор: карту тащили, а не тыкали в точку.
  const pick = (m: Mo) => { if (!moved.current) onPick(m) }

  const { k, x: tx, y: ty } = view
  const showShapes = k >= K_SHAPES && shapes.length > 0
  const shaped = useMemo(() => new Set(shapes.map((s) => s.id)), [shapes])
  const scale = Math.min(w / 1000, h / 560)
  const sorted = useMemo(() => [...dots].filter((d) => d.mo.lat !== null).sort((a, b) => b.mo.pop - a.mo.pop), [dots])
  const P = (p: [number, number]) => [p[0] * k + tx, p[1] * k + ty]

  return (
    <div ref={ref} className={`map${drag ? ' drag' : ''}`}
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onPointerLeave={onUp}
      onDoubleClick={(e) => { if (mini) return; const p = local(e); zoomAt(2.5, p.x, p.y) }}>
      {/* Наведение подсвечивает весь регион: правило по data-rk, а не перерисовка контуров. */}
      {hoverRk !== null && <style>{`.map svg [data-rk]:not([data-rk="${hoverRk}"]){opacity:.45}.map svg [data-rk="${hoverRk}"]{stroke:var(--text);stroke-width:.9px}`}</style>}
      <svg width={w} height={h} role="img" aria-label="Карта муниципалитетов" onPointerLeave={() => setHoverRk(null)}>
        <defs><pattern id="nodata-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--map-land)" /><line x1="0" y1="0" x2="0" y2="6" stroke="var(--text-3)" strokeWidth="1.6" opacity=".55" /></pattern></defs>
        <g transform={`translate(${tx} ${ty}) scale(${k})`}>
          {nbs.map((x) => <path key={x.name} className="nb" d={x.d} vectorEffect="non-scaling-stroke" />)}
          <path className="land" d={landD} vectorEffect="non-scaling-stroke" />
          {extras.map((x) => <path key={x.name} className="nodata" d={x.d} vectorEffect="non-scaling-stroke" data-tip={`<b>${x.name}</b><br>Нет надёжных данных и прогнозов: СберИндекс не публикует траты региона; идут боевые действия`} />)}
          {dots.map((d) => {
            const dd = moPaths.get(d.mo.id)
            if (!dd || (showShapes && shaped.has(d.mo.id))) return null
            const sel = d.mo.id === selected
            return <path key={d.mo.id} d={dd} fill={color(d.v)} stroke={sel ? 'var(--text)' : 'var(--surface)'} strokeWidth={sel ? 2 : 0.35} data-rk={d.mo.rk} opacity={keep && !keep.has(d.mo.id) ? 0.18 : undefined}
              vectorEffect="non-scaling-stroke" data-tip={d.tip} onClick={() => pick(d.mo)} onPointerEnter={() => setHoverRk(d.mo.rk)} className="mo-shape" />
          })}
          {showShapes && shapes.map(({ id, s, d }) => {
            const dot = byId.get(id)
            const sel = id === selected
            return <path key={id} d={d} fill={dot ? color(dot.v) : 'var(--surface-3)'} fillOpacity={0.92} stroke={sel ? 'var(--text)' : 'var(--surface)'} strokeWidth={sel ? 2.5 : 0.8}
              vectorEffect="non-scaling-stroke" data-tip={dot?.tip ?? s.name} onClick={() => dot && pick(dot.mo)} style={{ cursor: 'pointer' }} />
          })}
        </g>
        {land && sorted.map((d) => {
          if (showShapes && shaped.has(d.mo.id)) return null
          // Точкой рисуется только МО без контура: у остальных есть заливка.
          if (moPaths.has(d.mo.id)) return null
          const p = xy.get(d.mo.id)
          if (!p) return null
          const [cx, cy] = P(p as [number, number])
          if (cx < -20 || cy < -20 || cx > w + 20 || cy > h + 20) return null
          const r = Math.max(1.6, Math.min(9, Math.sqrt(d.mo.pop / 4000))) * Math.max(0.65, scale) * Math.min(1.5, Math.pow(k, 0.1))
          const sel = d.mo.id === selected
          return <circle key={d.mo.id} cx={cx} cy={cy} r={sel ? r + 4 : r} fill={color(d.v)} fillOpacity={0.88} data-rk={d.mo.rk} onPointerEnter={() => setHoverRk(d.mo.rk)}
            stroke={sel ? 'var(--text)' : 'var(--surface)'} strokeWidth={sel ? 2.5 : 0.5} data-tip={d.tip} onClick={() => pick(d.mo)} />
        })}
        {marks.map((m, i) => {
          const p0 = proj([m.lon, m.lat])
          if (!p0) return null
          const [cx, cy] = P(p0 as [number, number])
          if (cx < -10 || cy < -10 || cx > w + 10 || cy > h + 10) return null
          return <g key={i} className="mk" transform={`translate(${cx} ${cy})`} data-tip={m.tip}><circle r={7} fill={m.color} stroke="var(--surface)" strokeWidth={1.5} /><text y={3.2} textAnchor="middle">{m.glyph}</text></g>
        })}
        {k < 4 && nbs.filter((x) => NB_LABEL.has(x.name) && x.c).map((x) => { const [cx, cy] = P(x.c as [number, number]); return <text key={x.name} x={cx} y={cy} textAnchor="middle" className="nb-label">{x.name}</text> })}
        {showShapes && k >= K_LABEL && labels(shapes, P, w, h, selected).map(({ id, x, y, name }) => <text key={id} x={x} y={y} textAnchor="middle" className="map-label">{name}</text>)}
      </svg>
      {!mini && <div className="map-zoom" onPointerDown={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}>
        <button className="icon-btn" aria-label="Приблизить" data-tip="Приблизить" onClick={() => zoomAt(2, (w - inset) / 2 + inset, h / 2)}>{I.plus}</button>
        <button className="icon-btn" aria-label="Отдалить" data-tip="Отдалить" onClick={() => zoomAt(0.5, (w - inset) / 2 + inset, h / 2)}>{I.minus}</button>
        <hr className="map-hr" />
        <button className="icon-btn" aria-label="Вся страна" data-tip="<b>Вся страна</b><br>Вернуть карту к исходному виду" onClick={() => flyTo({ k: 1, x: 0, y: 0 })}>{I.map}</button>
        {CITIES.map((c) => (
          <button key={c.code} className="icon-btn" aria-label={c.region} data-tip={`<b>${c.region}</b><br>Показать районы города`} onClick={() => centerOn(proj(c.at) as [number, number], 90)}>
            <svg width="20" height="20" viewBox="-13 -14 26 26" aria-hidden="true"><path d={c.d} fill="currentColor" fillRule="evenodd" /></svg>
          </button>
        ))}
        {tools && <><hr className="map-hr" />{tools}</>}
      </div>}
    </div>
  )
}

/** Подписи районов без наложений: выбранный — первым, дальше по очереди, лишние пропускаются. */
function labels(shapes: { id: number; s: Shape; c: [number, number] | null }[], P: (p: [number, number]) => number[], w: number, h: number, selected?: number | null) {
  const out: { id: number; x: number; y: number; name: string }[] = []
  const boxes: number[][] = []
  const order = [...shapes].sort((a, b) => (b.id === selected ? 1 : 0) - (a.id === selected ? 1 : 0))
  for (const { id, s, c } of order) {
    if (!c) continue
    const [x, y] = P(c)
    if (x < 0 || y < 0 || x > w || y > h) continue
    const hw = s.name.length * 3.3 + 4, b = [x - hw, y - 11, x + hw, y + 4]
    if (boxes.some((q) => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])) continue
    boxes.push(b)
    out.push({ id, x, y, name: s.name })
  }
  return out
}

/** Расходящаяся шкала: минус — красный, ноль — серый, плюс — зелёный. */
export function diverging(lim: number) {
  return (v: number) => {
    if (!Number.isFinite(v)) return 'var(--text-3)'
    const t = Math.max(-1, Math.min(1, v / lim))
    return `color-mix(in srgb, ${t < 0 ? 'var(--warn)' : 'var(--ok)'} ${Math.round(15 + 85 * Math.abs(t))}%, var(--surface-3))`
  }
}
