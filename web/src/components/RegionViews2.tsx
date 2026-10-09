/**
 * Ещё шесть видов регионов из списка «восемь форм» (решение участника 04.10.2026):
 * рейтинг-полосы, ранговые дорожки, малые кратные и дерево рынка — экраном «Регионы»;
 * веер сценариев и профиль региона — в карточке региона. Данные те же, что у списка
 * (regionStats, ряды МО) и тот же сценарий из store.
 */
import { useMemo, useState } from 'react'
import { LineChart, useWidth } from './charts'
import { Seg } from './ui'
import { diverging } from './MapRussia'
import { BIZ_CAT, bn, REC_COLOR, REC_NAME, regionSeries, regionStats, type RegionStat, type Role } from '../data/biz'
import { ALARMS, catColor, FIRST_FC, INDUSTRY, monthShort, MOS } from '../data/real'
import { ALL_PRESETS, geoCountry, geoRegion, monthlyEffect, PRESETS, scnKeys, unproven, yearEffect } from '../data/whatif'
import { fmt1, fmt2, signed } from '../lib/util'
import { useApp } from '../store'

const pp = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmt1(Math.abs(x * 100))} %`
const short = (n: string) => n.replace('Республика ', 'Респ. ').replace(' область', ' обл.').replace(' автономный округ', ' АО').replace(' край', ' кр.')
const Y_of = (target: number) => Math.min(2, Math.max(0, Math.floor((target - FIRST_FC) / 12)))

/** 1. Рейтинг-полосы: длина — рынок, цвет — рекомендация, рядом рост; сортировка переключается. */
export function RatingBars({ list, national, role, onPick }: { list: RegionStat[]; national: number; role: Role; onPick: (rk: number) => void }) {
  const { selRk, cat, scn, target } = useApp()
  const [by, setBy] = useState<'market' | 'growth' | 'wape'>('market')
  const on = scn.key !== 'base', Y = Y_of(target)
  const rows = useMemo(() => list.filter((r) => r.market > 0).map((r) => ({ r, g: r.growth + (on ? yearEffect(cat, scn.f, Y, geoRegion(r.rk)).e / 100 : 0) }))
    .sort((a, b) => (by === 'market' ? b.r.market - a.r.market : by === 'growth' ? b.g - a.g : a.r.wape - b.r.wape)), [list, by, on, cat, scn, Y])
  const mx = Math.max(...rows.map((x) => x.r.market), 1)
  return (
    <div className="view-pane sc">
      <div className="view-h">
        <b>Рейтинг регионов</b>
        <span className="small">Полоса — рынок за 12 месяцев, цвет — рекомендация; справа рост{on ? ' со сценарием' : ''} и ошибка прогноза</span>
        <div style={{ alignSelf: 'flex-start', marginTop: 4 }}><Seg value={by} onChange={setBy} items={[['market', 'По рынку'], ['growth', 'По росту'], ['wape', 'По ошибке']]} /></div>
      </div>
      <div className="rbars">
        {rows.map(({ r, g }, i) => (
          <button key={r.rk} className={selRk === r.rk ? 'on' : ''} onClick={() => onPick(r.rk)} data-tip={`<b>${r.name}</b><br>${REC_NAME[role][r.rec]}<br>Рынок ${bn(r.market)}`}>
            <small>{i + 1}</small><span>{r.name}</span>
            <i><em style={{ width: `${(100 * r.market) / mx}%`, background: REC_COLOR[r.rec] }} /></i>
            <b className={g >= national ? 'good' : ''}>{pp(g)}</b><small>{fmt1(r.wape * 100)} %</small>
          </button>
        ))}
      </div>
    </div>
  )
}

/** 4. Ранговые дорожки: место региона по росту за 12 месяцев на каждый месяц, с декабря 2024 по декабрь 2027 года. */
export function RankLanes({ list, onPick }: { list: RegionStat[]; onPick: (rk: number) => void }) {
  const [ref, w] = useWidth<HTMLDivElement>(900)
  const { cat, selRk, target } = useApp()
  const t0 = 23, n = 60 - t0
  const lanes = useMemo(() => {
    const regs = list.filter((r) => r.market > 0).map((r) => {
      const s = regionSeries(cat, r.rk)
      const g = Array.from({ length: n }, (_, k) => { const t = t0 + k; let a = 0, b = 0; for (let i = t - 11; i <= t; i++) { a += s[i]; b += s[i - 12] } return a / b - 1 })
      return { r, g }
    }).filter((x) => x.g.every(Number.isFinite))
    const rank = regs.map(() => new Array(n).fill(0))
    for (let k = 0; k < n; k++) [...regs.keys()].sort((a, b) => regs[b].g[k] - regs[a].g[k]).forEach((ri, place) => { rank[ri][k] = place + 1 })
    return regs.map((x, i) => ({ ...x, rank: rank[i] }))
  }, [list, cat])
  const N = lanes.length, H = Math.max(420, N * 7 + 60)
  const pad = { l: 40, r: 170, t: 16, b: 30 }
  const X = (k: number) => pad.l + (k / (n - 1)) * (w - pad.l - pad.r)
  const Yr = (p: number) => pad.t + ((p - 1) / Math.max(1, N - 1)) * (H - pad.t - pad.b)
  const kT = Math.min(n - 1, Math.max(0, target - t0))
  const top = new Set([...lanes].sort((a, b) => a.rank[kT] - b.rank[kT]).slice(0, 8).map((x) => x.r.rk))
  const path = (rk: number[]) => rk.map((p, k) => `${k ? 'L' : 'M'}${X(k).toFixed(1)},${Yr(p).toFixed(1)}`).join('')
  return (
    <div ref={ref} className="view-pane sc">
      <div className="view-h">
        <b>Места в рейтинге</b>
        <span className="small">Место по росту трат за 12 месяцев; линия — регион. Выделены восемь лидеров и выбранный регион. До января 2025 года — факт, затем прогноз</span>
      </div>
      <svg width={w} height={H} className="lanes" role="img" aria-label="Места регионов в рейтинге">
        <rect x={X(0)} y={pad.t} width={X(FIRST_FC - t0) - X(0)} height={H - pad.t - pad.b} className="fact" />
        {[0, 12, 24, 36].filter((k) => k < n).map((k) => <text key={k} x={X(k)} y={H - 8} textAnchor="middle" className="ax">{monthShort(t0 + k)}</text>)}
        <line x1={X(kT)} x2={X(kT)} y1={pad.t} y2={H - pad.b} className="now" />
        {lanes.filter((x) => !top.has(x.r.rk) && x.r.rk !== selRk).map((x) => <path key={x.r.rk} d={path(x.rank)} className="lane" onClick={() => onPick(x.r.rk)} data-tip={`<b>${x.r.name}</b><br>${x.rank[kT]}-е место · рост ${pp(x.g[kT])}`} />)}
        {(() => {
          // Подписи справа раздвигаются, чтобы не налезать: не ближе 13 px друг к другу.
          const on = lanes.filter((x) => top.has(x.r.rk) || x.r.rk === selRk).sort((a, b) => a.rank[n - 1] - b.rank[n - 1])
          let prev = -Infinity
          const ly = on.map((x) => { const y = Math.max(Yr(x.rank[n - 1]) + 4, prev + 13); prev = y; return y })
          return on.map((x, i) => (
            <g key={x.r.rk} className={`lane-on${x.r.rk === selRk ? ' sel' : ''}`} onClick={() => onPick(x.r.rk)} data-tip={`<b>${x.r.name}</b><br>${x.rank[kT]}-е место · рост ${pp(x.g[kT])}`}>
              <path d={path(x.rank)} style={{ stroke: REC_COLOR[x.r.rec] }} />
              <text x={w - pad.r + 6} y={ly[i]}>{x.rank[n - 1]}. {short(x.r.name)}</text>
            </g>
          ))
        })()}
        {[1, Math.round(N / 2), N].map((p) => <text key={p} x={pad.l - 8} y={Yr(p) + 4} textAnchor="end" className="ax">{p}</text>)}
      </svg>
    </div>
  )
}

/** 6. Малые кратные: ряд каждого региона в своей клетке, индекс к среднему 2023 года = 100 — одна шкала на всех. */
export function SmallMultiples({ list, onPick }: { list: RegionStat[]; onPick: (rk: number) => void }) {
  const { cat, selRk } = useApp()
  const regs = useMemo(() => list.filter((r) => r.market > 0).sort((a, b) => b.market - a.market).map((r) => {
    const s = regionSeries(cat, r.rk)
    const b = s.slice(0, 12).reduce((a, x) => a + x, 0) / 12
    const ids = new Set(MOS.filter((m) => m.rk === r.rk).map((m) => m.id))
    const al = new Set(ALARMS.filter((a) => a[1] === cat && ids.has(a[0])).map((a) => a[2]))
    return { r, v: s.map((x) => (100 * x) / b), al }
  }), [list, cat])
  const lo = Math.min(...regs.flatMap((x) => x.v.filter(Number.isFinite))), hi = Math.max(...regs.flatMap((x) => x.v.filter(Number.isFinite)))
  const W = 150, H = 54
  const X = (t: number) => 2 + (t / 59) * (W - 4), Yv = (v: number) => H - 2 - ((v - lo) / (hi - lo)) * (H - 4)
  const line = (v: number[], a: number, b: number) => v.slice(a, b).map((x, i) => `${i ? 'L' : 'M'}${X(a + i).toFixed(1)},${Yv(x).toFixed(1)}`).join('')
  return (
    <div className="view-pane sc">
      <div className="view-h">
        <b>Траты регионов</b>
        <span className="small">Траты на жителя, среднее за 2023 год = 100. Сплошная — факт, пунктир — прогноз; красные отметки — месяцы сигналов в муниципалитетах. Общая шкала: {Math.round(lo)}…{Math.round(hi)}</span>
      </div>
      <div className="smult">
        {regs.map((x) => (
          <button key={x.r.rk} className={selRk === x.r.rk ? 'on' : ''} onClick={() => onPick(x.r.rk)} data-tip={`<b>${x.r.name}</b><br>Рынок ${bn(x.r.market)} · рост ${pp(x.r.growth)}`}>
            <span>{short(x.r.name)}</span>
            <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
              <line x1={X(FIRST_FC - 0.5)} x2={X(FIRST_FC - 0.5)} y1={0} y2={H} className="div" />
              {[...x.al].map((t) => <line key={t} x1={X(t)} x2={X(t)} y1={H - 6} y2={H} className="al" />)}
              <path d={line(x.v, 0, FIRST_FC)} className="fact" />
              <path d={line(x.v, FIRST_FC - 1, 60)} className="fc" style={{ stroke: catColor(cat) }} />
            </svg>
          </button>
        ))}
      </div>
    </div>
  )
}

/** 7. Дерево рынка: площадь — рынок региона за 12 месяцев, цвет — рост к стране. Раскладка — squarified. */
export function MarketTree({ list, national, onPick }: { list: RegionStat[]; national: number; onPick: (rk: number) => void }) {
  const [ref, w] = useWidth<HTMLDivElement>(900)
  const { selRk } = useApp()
  const H = Math.max(420, Math.min(720, w * 0.62))
  const items = list.filter((r) => r.market > 0).sort((a, b) => b.market - a.market)
  const rects = useMemo(() => squarify(items.map((r) => r.market), 0, 0, w, H), [items, w, H])
  const total = items.reduce((s, r) => s + r.market, 0)
  const color = diverging(0.06)
  return (
    <div ref={ref} className="view-pane sc">
      <div className="view-h">
        <b>Доли рынка</b>
        <span className="small">Площадь — рынок за 12 месяцев; цвет — рост к стране ({pp(national)}): зелёный — выше, красный — ниже</span>
      </div>
      <svg width={w} height={H} className="tree" role="img" aria-label="Дерево рынка">
        {rects.map((q, i) => {
          const r = items[i]
          const fits = q.w > 70 && q.h > 30
          return (
            <g key={r.rk} className={selRk === r.rk ? 'on' : ''} onClick={() => onPick(r.rk)} data-tip={`<b>${r.name}</b><br>${bn(r.market)} · ${fmt1((100 * r.market) / total)} % рынка<br>рост ${pp(r.growth)}`}>
              <rect x={q.x + 1} y={q.y + 1} width={Math.max(0, q.w - 2)} height={Math.max(0, q.h - 2)} rx={3} style={{ fill: color(r.growth - national) }} />
              {fits && <text x={q.x + 8} y={q.y + 18}>{short(r.name)}</text>}
              {fits && q.h > 46 && <text x={q.x + 8} y={q.y + 34} className="sub">{bn(r.market)} · {pp(r.growth)}</text>}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function squarify(vals: number[], x: number, y: number, w: number, h: number) {
  const out: { x: number; y: number; w: number; h: number }[] = []
  const total = vals.reduce((a, b) => a + b, 0)
  const scale = (w * h) / total
  const area = vals.map((v) => v * scale)
  const worst = (row: number[], side: number) => { const s = row.reduce((a, b) => a + b, 0), mx = Math.max(...row), mn = Math.min(...row); return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn)) }
  let i = 0
  while (i < area.length) {
    const side = Math.min(w, h)
    const row = [area[i]]
    let j = i + 1
    while (j < area.length && worst([...row, area[j]], side) <= worst(row, side)) { row.push(area[j]); j++ }
    const s = row.reduce((a, b) => a + b, 0)
    if (w >= h) { const rw = s / h; let yy = y; for (const a of row) { out.push({ x, y: yy, w: rw, h: a / rw }); yy += a / rw } x += rw; w -= rw }
    else { const rh = s / w; let xx = x; for (const a of row) { out.push({ x: xx, y, w: a / rh, h: rh }); xx += a / rh } y += rh; h -= rh }
    i = j
  }
  return out
}

/** 5. Веер сценариев по региону: базовый прогноз и каждый сценарий своим цветом на год выбранного месяца. */
const FAN = ['#2563eb', '#d97706', '#dc2626', '#0891b2', '#7c3aed', '#16a34a', '#db2777']
export function ScenarioFan({ rk }: { rk: number }) {
  const { cat, target, scn } = useApp()
  const Y = Y_of(target), y0 = FIRST_FC + 12 * Y
  const s = regionSeries(cat, rk), geo = geoRegion(rk)
  const keys = scnKeys(scn.key)
  const shown = [...PRESETS, ...ALL_PRESETS.filter((p) => keys.includes(p.key) && !PRESETS.includes(p))]
  const lines = shown.map((p, i) => {
    const e = monthlyEffect(cat, p.f, Y, geo)
    const weak = unproven(cat, p.f)
    return { key: p.key, name: `${p.name}${weak ? ' (связь не подтверждена)' : ''}`, color: weak ? 'var(--text-3)' : FAN[i % FAN.length], v: [s[y0 - 1], ...e.map((m, k) => s[y0 + k] * (1 + m.e / 100))], from: y0 - 1, width: keys.includes(p.key) ? 2.6 : 1.4, dash: weak }
  })
  const rows = shown.map((p) => ({ p, e: yearEffect(cat, p.f, Y, geo).e, weak: unproven(cat, p.f) })).sort((a, b) => b.e - a.e)
  return (
    <div>
      <h3>Сценарии, {2025 + Y} год</h3>
      <LineChart n={12 + 2} x0={y0 - 2} height={200} yFmt={(v) => `${Math.round(v / 1000)} тыс.`} lines={[
        { key: 'b', name: 'Без сценария', color: 'var(--text)', v: s.slice(y0 - 2, y0 + 12), width: 2.2 },
        ...lines.map((L) => ({ ...L, from: L.from - (y0 - 2) })),
      ]} />
      <div className="fan-legend small">
        {rows.map(({ p, e, weak }, i) => <span key={p.key} style={{ color: weak ? 'var(--text-3)' : undefined }}><i style={{ background: weak ? 'var(--text-3)' : FAN[shown.indexOf(p) % FAN.length] }} />{p.name}: {weak ? 'не подтверждено' : `${signed(e, fmt2)} %`}{i === 0 ? '' : ''}</span>)}
      </div>
    </div>
  )
}

/** 8. Профиль региона против страны: доли отраслей занятости и рост по категориям. */
export function RegionProfile({ rk, role }: { rk: number; role: Role }) {
  const { target } = useApp()
  const g = geoRegion(rk), c = geoCountry()
  const RU: Record<string, string> = { manuf: 'Обработка', mining: 'Добыча', agri: 'Сельское хозяйство', budget: 'Бюджетный сектор' }
  const groups = (INDUSTRY?.groups ?? Object.keys(RU)).map((k) => RU[k] ?? k)
  const cats = BIZ_CAT.map((name, ci) => { const st = regionStats(ci, role, undefined, target); return { name, r: st.list.find((x) => x.rk === rk)?.growth ?? NaN, n: st.national } })
  const mxS = Math.max(...g, ...c, 0.05), mxG = Math.max(...cats.flatMap((x) => [Math.abs(x.r), Math.abs(x.n)]).filter(Number.isFinite), 0.05)
  const pair = (name: string, a: number, b: number, mx: number, fmt: (v: number) => string, key: string) => (
    <div key={key} className="prof-row" data-tip={`<b>${name}</b><br>регион ${fmt(a)} · страна ${fmt(b)}`}>
      <span>{name}</span>
      <i><em style={{ width: `${(100 * Math.abs(a)) / mx}%` }} /><s style={{ left: `${(100 * Math.abs(b)) / mx}%` }} /></i>
      <b>{Number.isFinite(a) ? fmt(a) : '—'}</b>
    </div>
  )
  return (
    <div>
      <h3>Профиль региона</h3>
      <p className="small" style={{ margin: '0 0 8px' }}>Полоса — регион, черта — страна. Доли отраслей объясняют различия влияния сценариев «нефть» и «урожай»</p>
      <div className="prof">
        <small>Доля занятых</small>
        {groups.map((name, i) => pair(name, g[i], c[i], mxS, (v) => `${fmt1(v * 100)} %`, `g${i}`))}
        <small>Рост за 12 месяцев</small>
        {cats.map((x, i) => pair(x.name, x.r, x.n, mxG, pp, `c${i}`))}
      </div>
    </div>
  )
}
