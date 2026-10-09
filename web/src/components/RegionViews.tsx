/**
 * Виды регионов помимо карты (решение участника 04.10.2026): карта отвечает на «где»,
 * а сравнить 85 регионов по заливке нельзя. Квадрант «рост против масштаба» отвечает
 * на «кого выбрать», тепловая таблица «регион × категория» — на «с чем заходить».
 * Оба берут те же данные, что список (regionStats), и тот же сценарий из store.
 */
import { useMemo } from 'react'
import { useWidth } from './charts'
import { diverging } from './MapRussia'
import { BIZ_CAT, bn, REC_COLOR, REC_NAME, regionStats, type RegionStat, type Role } from '../data/biz'
import { FIRST_FC, META, PEOPLE } from '../data/real'
import { geoRegion, scnLabel, yearEffect } from '../data/whatif'
import { fmt1 } from '../lib/util'
import { useApp } from '../store'

const pp = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmt1(Math.abs(x * 100))} %`

/** Квадрант: по горизонтали рынок (лог), по вертикали рост за 12 месяцев; точка — регион, цвет — рекомендация.
 * Со сценарием точка уезжает по вертикали, хвост показывает, откуда. */
export function Quadrant({ list, national, role, onPick }: { list: RegionStat[]; national: number; role: Role; onPick: (rk: number) => void }) {
  const [ref, w] = useWidth<HTMLDivElement>(900)
  const { cat, scn, selRk, target } = useApp()
  const Y = Math.floor((target - FIRST_FC) / 12)
  const on = scn.key !== 'base'
  const pts = useMemo(() => list.filter((r) => r.market > 0 && Number.isFinite(r.growth)).map((r) => {
    const e = on ? yearEffect(cat, scn.f, Y, geoRegion(r.rk)).e / 100 : 0
    return { r, x: Math.log10(r.market), g0: r.growth, g: r.growth + e }
  }), [list, on, cat, scn, Y])
  const H = Math.max(360, Math.min(620, w * 0.55))
  const pad = { l: 56, r: 24, t: 20, b: 40 }
  const xs = pts.map((p) => p.x), ys = pts.flatMap((p) => [p.g, p.g0])
  const x0 = Math.min(...xs) - 0.1, x1 = Math.max(...xs) + 0.1
  const y0 = Math.min(...ys, national) - 0.02, y1 = Math.max(...ys, national) + 0.02
  const X = (x: number) => pad.l + ((x - x0) / (x1 - x0)) * (w - pad.l - pad.r)
  const Yp = (y: number) => pad.t + (1 - (y - y0) / (y1 - y0)) * (H - pad.t - pad.b)
  const medX = pts.length ? [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)] : 0
  const xt = [1e9, 1e10, 1e11, 1e12, 1e13].filter((v) => Math.log10(v) > x0 && Math.log10(v) < x1)
  const yt: number[] = []
  for (let v = Math.ceil(y0 * 20) / 20; v <= y1; v += 0.05) yt.push(+v.toFixed(2))
  const big = new Set([...pts].sort((a, b) => b.r.market - a.r.market).slice(0, 10).map((p) => p.r.rk))
  const rad = (r: RegionStat) => Math.max(4, Math.min(16, Math.sqrt(r.pop / 60000)))
  const short = (n: string) => n.replace('Республика ', 'Респ. ').replace(' область', ' обл.')
  // Подписи без наложений: справа от точки, у правого края — слева; стоящие друг на друге раздвигаются вниз.
  const labels = useMemo(() => {
    const L = pts.filter((p) => big.has(p.r.rk) || selRk === p.r.rk).map((p) => {
      const left = X(p.x) > w - pad.r - 130
      return { rk: p.r.rk, text: short(p.r.name), x: X(p.x) + (left ? -(rad(p.r) + 4) : rad(p.r) + 4), y: Yp(p.g) + 4, left, w: short(p.r.name).length * 6.4 }
    }).sort((a, b) => a.y - b.y)
    for (let i = 0; i < L.length; i++) for (let j = 0; j < i; j++) {
      const a = L[j], b = L[i]
      const ax0 = a.left ? a.x - a.w : a.x, bx0 = b.left ? b.x - b.w : b.x
      if (Math.abs(b.y - a.y) < 13 && ax0 < bx0 + b.w && bx0 < ax0 + a.w) b.y = a.y + 13
    }
    return new Map(L.map((l) => [l.rk, l]))
  }, [pts, w, selRk])
  const narrow = w < 640
  return (
    <div ref={ref} className="view-pane sc">
      <div className="view-h">
        <b>Рост и рынок</b>
        <span className="small">Точка — регион, размер — население, цвет — рекомендация; линии — медианный рынок и рост по стране{on ? `; сценарий «${scnLabel(scn.key)}» меняет положение точек, линия — исходное положение` : ''}</span>
      </div>
      <svg width={w} height={H} className="quad" role="img" aria-label="Квадрант регионов">
        {xt.map((v) => <g key={v}><line x1={X(Math.log10(v))} x2={X(Math.log10(v))} y1={pad.t} y2={H - pad.b} className="grid" /><text x={X(Math.log10(v))} y={H - pad.b + 16} textAnchor="middle" className="ax">{bn(v)}</text></g>)}
        {yt.map((v) => <g key={v}><line x1={pad.l} x2={w - pad.r} y1={Yp(v)} y2={Yp(v)} className="grid" /><text x={pad.l - 8} y={Yp(v) + 4} textAnchor="end" className="ax">{pp(v)}</text></g>)}
        <line x1={X(medX)} x2={X(medX)} y1={pad.t} y2={H - pad.b} className="mid" />
        <line x1={pad.l} x2={w - pad.r} y1={Yp(national)} y2={Yp(national)} className="mid" />
        <text x={w - pad.r} y={Yp(national) - 6} textAnchor="end" className="ax">страна {pp(national)}</text>
        <text x={X(medX) + 6} y={pad.t + 12} className="ax">медианный рынок</text>
        {!narrow && <><text x={w - pad.r} y={pad.t + 12} textAnchor="end" className="corner">крупные, опережающие</text>
        <text x={pad.l + 6} y={pad.t + 12} className="corner">малые, опережающие</text>
        <text x={w - pad.r} y={H - pad.b - 6} textAnchor="end" className="corner">крупные, отстающие</text>
        <text x={pad.l + 6} y={H - pad.b - 6} className="corner">малые, отстающие</text></>}
        {on && pts.map((p) => Math.abs(p.g - p.g0) > 0.0005 && <line key={`t${p.r.rk}`} x1={X(p.x)} x2={X(p.x)} y1={Yp(p.g0)} y2={Yp(p.g)} className="tail" />)}
        {pts.map((p) => (
          <g key={p.r.rk} className={`pt${selRk === p.r.rk ? ' on' : ''}`} transform={`translate(${X(p.x)} ${Yp(p.g)})`} onClick={() => onPick(p.r.rk)}
            data-tip={`<b>${p.r.name}</b><br>${REC_NAME[role][p.r.rec]}<br>Рынок ${bn(p.r.market)} · рост ${pp(p.g0)}${on ? ` → ${pp(p.g)} со сценарием` : ''}`}>
            <circle r={rad(p.r)} fill={REC_COLOR[p.r.rec]} />
          </g>
        ))}
        {[...labels.values()].map((l) => <text key={l.rk} x={l.x} y={l.y} textAnchor={l.left ? 'end' : 'start'} className={`lbl${selRk === l.rk ? ' on' : ''}`}>{l.text}</text>)}
      </svg>
    </div>
  )
}

/** Тепловая таблица «регион × категория»: рост за 12 месяцев к росту по стране в той же категории, п. п. */
export function CatHeat({ role, onPick }: { role: Role; onPick: (rk: number) => void }) {
  const { selRk, target, mode, th } = useApp()
  const stats = useMemo(() => BIZ_CAT.map((_, c) => regionStats(c, role, mode === 'pro' ? th : undefined, target)), [role, target, mode, th])
  const base = stats[0].list.filter((r) => r.market > 0).sort((a, b) => b.market - a.market)
  const color = diverging(0.08)
  const mig = diverging(8)
  return (
    <div className="view-pane sc">
      <div className="view-h">
        <b>Рост по категориям</b>
        <span className="small">Рост за 12 месяцев к стране в той же категории, п. п.: зелёный — выше, красный — ниже; регионы по объёму рынка. Приток — сальдо внутренней миграции 2023 года на 1 000 жителей, связан с ростом следующего года</span>
      </div>
      <table className="heat">
        <thead><tr><th>Регион</th><th>Приток людей</th>{BIZ_CAT.map((n, c) => <th key={c}><span className="dot" style={{ background: `var(--c-${META.cats[c] === 'Все категории' ? 'all' : ['all', 'food', 'health', 'cafe', 'transport', 'market'][c]})`, margin: '0 6px 0 0' }} />{n}</th>)}</tr></thead>
        <tbody>
          {base.map((r) => (
            <tr key={r.rk} className={selRk === r.rk ? 'on' : ''} onClick={() => onPick(r.rk)}>
              <td><span className="nw">{r.name}</span><small>{bn(r.market)}</small></td>
              {(() => { const m = PEOPLE?.regions[r.rk]?.[0] ?? null; const cm = PEOPLE?.country[0] ?? 0; return <td style={{ background: m === null ? 'none' : mig(m) }} data-tip={m === null ? 'нет данных' : `<b>${r.name}</b><br>сальдо внутренней миграции за последний доступный год: ${m > 0 ? '+' : m < 0 ? '−' : ''}${fmt1(Math.abs(m))} на 1 000 жителей; по стране ${cm > 0 ? '+' : ''}${fmt1(cm)}`}>{m === null ? '—' : `${m > 0 ? '+' : m < 0 ? '−' : ''}${fmt1(Math.abs(m))}`}</td> })()}
              {BIZ_CAT.map((n, c) => {
                const s = stats[c], rr = s.list.find((x) => x.rk === r.rk)
                const d = rr && Number.isFinite(rr.growth) ? rr.growth - s.national : NaN
                return <td key={c} style={{ background: color(d) }} data-tip={`<b>${r.name}</b> · ${n}<br>${rr && Number.isFinite(rr.growth) ? `рост ${pp(rr.growth)} при ${pp(s.national)} по стране` : 'нет данных'}`}>{Number.isFinite(d) ? `${d > 0 ? '+' : d < 0 ? '−' : ''}${fmt1(Math.abs(d * 100))}` : '—'}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
