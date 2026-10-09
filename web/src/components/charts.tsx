import { useEffect, useRef, useState } from 'react'
import { monthShort } from '../data/real'
import { fmt0 } from '../lib/util'

export function useWidth<T extends HTMLElement>(init = 800) {
  const ref = useRef<T>(null)
  const [w, setW] = useState(init)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w] as const
}

export interface Line { key: string; name: string; color: string; v: ArrayLike<number>; from?: number; dash?: boolean; width?: number }
export interface Band { lo: number[]; hi: number[]; from: number; color: string }
export interface Pin { t: number; color: string; tip: string; kind: 'alarm' | 'news' | 'shock' }

/** Линейный график рядов по месяцам: факт, прогнозы, коридор, отметки тревог и новостей. */
/** Ручка времени: пунктир выбранного месяца, который тянут по оси из прошлого в будущее. */
export interface Cursor { t: number; min: number; max: number; onChange: (t: number) => void }
export function LineChart({ lines, n, band, pins = [], origin, height = 300, shade, x0 = 0, yFmt = fmt0, cursor }: { lines: Line[]; n: number; band?: Band; pins?: Pin[]; origin?: number; height?: number; shade?: [number, number]; x0?: number; yFmt?: (v: number) => string; cursor?: Cursor }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const [drag, setDrag] = useState(false)
  const pad = { l: 52, r: 12, t: 12, b: 26 }
  const w = W - pad.l - pad.r, h = height - pad.t - pad.b
  let lo = Infinity, hi = -Infinity
  for (const L of lines) for (let i = L.from ?? 0; i < Math.min(n, (L.from ?? 0) + L.v.length + 999); i++) {
    const v = val(L, i)
    if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v) }
  }
  if (band) band.lo.forEach((v, i) => { lo = Math.min(lo, v); hi = Math.max(hi, band.hi[i]) })
  const span = hi - lo || 1
  lo -= span * 0.08; hi += span * 0.08
  const x = (i: number) => pad.l + (w * i) / Math.max(1, n - 1)
  const y = (v: number) => pad.t + h * (1 - (v - lo) / (hi - lo))
  const ticks = niceTicks(lo, hi, 4)
  const path = (L: Line) => {
    let d = '', on = false
    for (let i = 0; i < n; i++) {
      const v = val(L, i)
      if (!Number.isFinite(v)) { on = false; continue }
      d += `${on ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`
      on = true
    }
    return d
  }
  const step = n <= 12 ? (W < 520 ? 3 : 1) : n > 36 ? (W < 700 ? 12 : 6) : W < 520 ? 6 : 3
  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <svg className={`chart${cursor ? ' scrub' : ''}${drag ? ' dragging' : ''}`} width={W} height={height} onPointerLeave={() => setHover(null)}
        // Нажали в любом месте графика — ручка встаёт туда и едет за пальцем, пока его не отпустят.
        onPointerDown={cursor && ((e) => {
          const r = e.currentTarget.getBoundingClientRect()
          const i = Math.round(((e.clientX - r.left - pad.l) / w) * (n - 1))
          if (i < cursor.min - 1 || i > cursor.max + 1) return
          try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* синтетическое нажатие без указателя */ }
          setDrag(true)
          cursor.onChange(Math.min(cursor.max, Math.max(cursor.min, i)))
        })}
        onPointerUp={() => setDrag(false)} onPointerCancel={() => setDrag(false)}
        onPointerMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
          const i = Math.round(((e.clientX - r.left - pad.l) / w) * (n - 1))
          setHover(i >= 0 && i < n && !drag ? i : null)
          if (drag && cursor) { const t = Math.min(cursor.max, Math.max(cursor.min, i)); if (t !== cursor.t) cursor.onChange(t) }
        }}>
        {shade && <rect x={x(shade[0])} y={pad.t} width={Math.max(0, x(shade[1]) - x(shade[0]))} height={h} fill="var(--hover)" />}
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid-l" x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end">{yFmt(t)}</text>
          </g>
        ))}
        {Array.from({ length: n }, (_, i) => i).filter((i) => i % step === 0).map((i) => (
          <text key={i} x={x(i)} y={height - 6} textAnchor="middle">{monthShort(i + x0)}</text>
        ))}
        {origin !== undefined && <line x1={x(origin)} x2={x(origin)} y1={pad.t} y2={pad.t + h} stroke="var(--text-3)" strokeDasharray="3 4" />}
        {band && (
          <path fill={band.color} opacity={0.16} stroke="none"
            d={`M${band.lo.map((v, i) => `${x(band.from + i)},${y(v)}`).join('L')}L${band.hi.map((v, i) => `${x(band.from + i)},${y(v)}`).reverse().join('L')}Z`} />
        )}
        {lines.map((L) => <path key={L.key} d={path(L)} fill="none" stroke={L.color} strokeWidth={L.width ?? 2} strokeDasharray={L.dash ? '5 4' : undefined} strokeLinejoin="round" strokeLinecap="round" />)}
        {pins.map((p, k) => {
          const base = lines[0] ? val(lines[0], p.t) : NaN
          const cy = p.kind === 'news' ? pad.t + h - 4 : Number.isFinite(base) ? y(base) : pad.t + 8
          return p.kind === 'news'
            ? <rect key={k} x={x(p.t) - 5} y={cy - 5} width={10} height={10} rx={2} fill={p.color} data-tip={p.tip} transform={`rotate(45 ${x(p.t)} ${cy})`} />
            : <circle key={k} cx={x(p.t)} cy={cy} r={p.kind === 'shock' ? 9 : 6} fill={p.kind === 'shock' ? 'none' : p.color} stroke={p.color} strokeWidth={2} data-tip={p.tip} />
        })}
        {cursor && (() => {
          const cx = x(cursor.t), v = lines.map((L) => val(L, cursor.t)).find(Number.isFinite) ?? NaN
          return (
            <g className="cursor" pointerEvents="none">
              <line x1={cx} x2={cx} y1={pad.t} y2={pad.t + h} strokeDasharray="4 4" />
              {Number.isFinite(v) && <circle cx={cx} cy={y(v)} r={6} />}
              <g transform={`translate(${Math.min(W - pad.r - 34, Math.max(pad.l + 34, cx))} ${pad.t + h})`}>
                <rect x={-34} y={-11} width={68} height={22} rx={11} />
                <text y={4} textAnchor="middle">{monthShort(cursor.t + x0)}</text>
              </g>
            </g>
          )
        })()}
        {hover !== null && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + h} stroke="var(--line-2)" />
            {lines.map((L) => { const v = val(L, hover); return Number.isFinite(v) ? <circle key={L.key} cx={x(hover)} cy={y(v)} r={3.5} fill={L.color} /> : null })}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tip" style={{ position: 'absolute', left: Math.min(W - 200, Math.max(0, x(hover) + 12)), top: 8, minWidth: 170 }}>
          <b>{monthShort(hover + x0)}</b>
          {lines.map((L) => { const v = val(L, hover); return Number.isFinite(v) ? <div key={L.key} style={{ display: 'flex', gap: 8 }}><span className="dot" style={{ background: L.color, marginTop: 4 }} /><span style={{ marginRight: 'auto' }}>{L.name}</span><b>{yFmt(v)}</b></div> : null })}
        </div>
      )}
    </div>
  )
}

function val(L: Line, i: number) {
  const k = i - (L.from ?? 0)
  return k >= 0 && k < L.v.length ? L.v[k] : NaN
}

export function niceTicks(lo: number, hi: number, n: number) {
  const raw = (hi - lo) / n
  const p = 10 ** Math.floor(Math.log10(raw))
  const s = [1, 2, 2.5, 5, 10].map((k) => k * p).find((k) => k >= raw) ?? p * 10
  const out: number[] = []
  for (let t = Math.ceil(lo / s) * s; t <= hi; t += s) out.push(+t.toFixed(6))
  return out
}

/** Полоса счёта детектора: столбик на месяц, порог пунктиром. */
export function ScoreStrip({ s, thr, n, color, height = 64 }: { s: ArrayLike<number>; thr: number; n: number; color: string; height?: number }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const pad = { l: 52, r: 12, t: 4, b: 4 }
  const w = W - pad.l - pad.r
  // Баллы детекторов неотрицательны: столбик растёт от нуля, порог — одна черта.
  let mx = thr * 1.5
  for (let i = 0; i < s.length; i++) if (Number.isFinite(s[i])) mx = Math.max(mx, s[i])
  const base = height - pad.b
  const y = (v: number) => base - (v / mx) * (base - pad.t)
  const bw = Math.max(2, (w / n) * 0.55)
  const x = (i: number) => pad.l + (w * i) / Math.max(1, n - 1)
  return (
    <div ref={ref}>
      <svg className="chart" width={W} height={height}>
        <line className="grid-l" x1={pad.l} x2={W - pad.r} y1={base} y2={base} />
        <line x1={pad.l} x2={W - pad.r} y1={y(thr)} y2={y(thr)} stroke="var(--warn)" strokeDasharray="3 4" opacity={0.7} />
        <text x={pad.l - 8} y={y(thr) + 4} textAnchor="end">порог</text>
        {Array.from(s).map((v, i) => (i < n && v > 0 ? (
          <rect key={i} x={x(i) - bw / 2} width={bw} y={y(v)} height={Math.max(1, base - y(v))} rx={1.5}
            fill={v > thr ? 'var(--warn)' : color} opacity={v > thr ? 1 : 0.55} data-tip={`${monthShort(i)}: ${v.toFixed(2)}`} />
        ) : null))}
      </svg>
    </div>
  )
}

/** Горизонтальные столбики: модель — значение, лучший выделен. */
export function Bars({ rows, fmt, ref0, refName }: { rows: { name: string; v: number; color: string; best?: boolean }[]; fmt: (v: number) => string; ref0?: number; refName?: string }) {
  const mx = Math.max(...rows.map((r) => r.v), ref0 ?? 0) || 1
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, position: 'relative' }}>
      {rows.map((r) => (
        <div key={r.name} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 34%) minmax(0, 1fr) 64px', gap: 12, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: r.best ? 'var(--text)' : 'var(--text-2)', fontWeight: r.best ? 600 : 400 }}>{r.name}</span>
          <div style={{ position: 'relative', height: 22 }}>
            <div style={{ position: 'absolute', inset: '3px auto 3px 0', width: `${(100 * r.v) / mx}%`, background: r.color, borderRadius: 6, opacity: r.best ? 1 : 0.7, transition: 'width .4s' }} />
            {ref0 !== undefined && <div data-tip={refName} style={{ position: 'absolute', top: -3, bottom: -3, left: `${(100 * ref0) / mx}%`, borderLeft: '2px dashed var(--text-3)' }} />}
          </div>
          <b style={{ textAlign: 'right', fontSize: 13, fontWeight: 600 }}>{fmt(r.v)}</b>
        </div>
      ))}
    </div>
  )
}

/** Столбики по месяцам истории: подпись года под январём. */
export function MonthBars({ values, color, height = 180, fmt = fmt0 }: { values: number[]; color: string; height?: number; fmt?: (v: number) => string }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const pad = { l: 36, r: 6, t: 10, b: 24 }
  const w = W - pad.l - pad.r, h = height - pad.t - pad.b
  const mx = Math.max(1, ...values)
  const ticks = niceTicks(0, mx, 3)
  const bw = (w / values.length) * 0.66
  const x = (i: number) => pad.l + (w * (i + 0.5)) / values.length
  const y = (v: number) => pad.t + h * (1 - v / mx)
  return (
    <div ref={ref}>
      <svg className="chart" width={W} height={height}>
        {ticks.map((t) => <g key={t}><line className="grid-l" x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} /><text x={pad.l - 6} y={y(t) + 4} textAnchor="end">{fmt(t)}</text></g>)}
        {values.map((v, i) => <rect key={i} x={x(i) - bw / 2} y={y(v)} width={bw} height={Math.max(0, pad.t + h - y(v))} rx={2} fill={color} opacity={0.85} data-tip={`${monthShort(i)}: ${fmt(v)}`} />)}
        {values.map((_, i) => (i % (W < 520 ? 6 : 3) === 0 ? <text key={i} x={x(i)} y={height - 6} textAnchor="middle">{monthShort(i)}</text> : null))}
      </svg>
    </div>
  )
}
