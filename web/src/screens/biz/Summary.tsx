import { LineChart, MonthBars } from '../../components/charts'
import { MapRussia } from '../../components/MapRussia'
import { Card, Info } from '../../components/ui'
import { BIZ_CAT, bn, errAt, nationalSeries, regionSeries, REC_COLOR, REC_NAME, regionStats, strengthWord, type Rec } from '../../data/biz'
import { ALARMS, catColor, FIRST_FC, META, mo, MOS, monthIn, monthLong, monthShort } from '../../data/real'
import { combine, evidence, geoCountry, geoRegion, measuresOnly, monthlyEffect, NONE, PRESETS, scnKeys, scnLabel, unproven, yearEffect } from '../../data/whatif'
import { SensCard } from './WhatIf'
import { fmt0, fmt1, fmt2, signed } from '../../lib/util'
import { useApp } from '../../store'
import { metric, OverviewTech } from '../Overview'

const pp = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmt1(Math.abs(x * 100))}\u00a0%`
const RECS: Rec[] = ['own', 'partner', 'watch', 'blind']
const tone = (w: number) => (w < 0.05 ? 'var(--ok)' : w < 0.09 ? 'var(--shift)' : 'var(--warn)')

/**
 * Сводка — лист сценарного моделирования. Без сценария это картинка прогноза: траектория
 * с коридором точности, рост категорий, карта рекомендаций, «торнадо» сценариев, тревоги.
 * Сценарий из строки фильтров ложится на те же виджеты: линия поверх прогноза и цифры
 * с разницей, рост категорий со сценарием, на карте — где скажется сильнее. Своих пустых
 * виджетов у сценария нет. Пунктир на графике — ручка времени: его тянут из прошлого в будущее.
 */
export function Summary() {
  const { cat, role, set, go, mode, target, setTarget, scn, selRk } = useApp()
  const { list: all, national, month } = regionStats(cat, role, mode === 'pro' ? useApp.getState().th : undefined, target)
  const er = errAt(cat, target)
  const past = target < FIRST_FC
  // Сценарий ложится на год выбранного месяца; для прошлого месяца — на 2025 год.
  const Y = Math.min(2, Math.max(0, Math.floor((target - FIRST_FC) / 12)))
  const errs = META.horizonErr[META.cats[cat]] ?? META.horizonErr['Все']
  const iv = META.interval90?.[META.cats[cat]] ?? META.interval90?.['Все'] ?? []
  const on = scn.key !== 'base'
  // Паводок — сценарий региона: тогда весь лист про выбранный регион.
  const rk = on && scn.scope === 'region' ? selRk ?? all[0]?.rk ?? null : null
  const reg = rk === null ? null : all.find((r) => r.rk === rk) ?? null
  const list = reg ? [reg] : all
  const geo = reg ? geoRegion(reg.rk) : geoCountry()
  const base = reg ? regionSeries(cat, reg.rk) : nationalSeries(cat)
  const eff = on ? monthlyEffect(cat, scn.f, Y, geo) : []
  const y0 = FIRST_FC + 12 * Y
  const scnS = on ? base.map((v, t) => (t >= y0 && t < y0 + 12 ? v * (1 + eff[t - y0].e / 100) : v)) : base
  const ye = on ? yearEffect(cat, scn.f, Y, geo) : { e: 0, sd: 0 }
  const weak = on && unproven(cat, scn.f), meas = on && measuresOnly(cat, scn.f)
  const ev = on ? evidence(cat, scn.f) : []
  // Цифры героя: прогноз без сценария и разница, которую даёт сценарий, — из одного ряда.
  const lo = Math.max(12, target - 11)
  const sum = (s: number[], from: number, to: number) => { let a = 0; for (let i = from; i <= to; i++) a += s[i]; return a }
  const g12 = (s: number[]) => sum(s, lo, target) / sum(base, lo - 12, target - 12) - 1
  const dMonth = on ? scnS[target] / base[target] - 1 : 0
  const dYear = on ? g12(scnS) - g12(base) : 0
  const baseMonth = reg ? base[target] / base[target - 12] - 1 : month
  const baseYear = reg ? reg.growth : national
  const market = list.reduce((s, r) => s + r.market, 0)
  const dMarket = on ? market * (sum(scnS, lo, target) / sum(base, lo, target) - 1) : 0
  const byCat = BIZ_CAT.map((name, c) => {
    const st = regionStats(c, role, undefined, target)
    const g = reg ? st.list.find((r) => r.rk === reg.rk)?.growth ?? NaN : st.national
    return { name, c, g, e: on ? yearEffect(c, scn.f, Y, geo).e / 100 : 0 }
  }).filter((x) => Number.isFinite(x.g))
  const T = META.periods.length
  const months = Array.from({ length: T }, (_, t) => ALARMS.filter((a) => a[1] === cat && a[2] === t).length)
  const recent = ALARMS.filter((a) => a[1] === cat && a[2] >= T - 3).sort((a, b) => Math.abs(b[6] ?? 0) - Math.abs(a[6] ?? 0))
  const recOf = new Map(all.map((r) => [r.rk, r.rec]))
  // Карта: без сценария — рекомендации; со сценарием — изменение спроса по регионам, в процентах.
  const hitE = new Map(on ? all.map((r) => [r.rk, yearEffect(cat, scn.f, Y, geoRegion(r.rk)).e]) : [])
  const hitMx = Math.max(0.05, ...[...hitE.values()].map(Math.abs))
  const dots = MOS.map((m) => on
    ? { mo: m, v: hitE.get(m.rk) ?? 0, tip: `<b>${m.region}</b><br>${signed(hitE.get(m.rk) ?? 0, fmt2)} % спроса за ${2025 + Y} год` }
    : { mo: m, v: RECS.indexOf(recOf.get(m.rk) ?? 'blind'), tip: `<b>${m.region}</b><br>${REC_NAME[role][recOf.get(m.rk) ?? 'blind']}` })
  const hit = on ? [...all].map((r) => ({ r, rub: (r.market * (hitE.get(r.rk) ?? 0)) / 100 })).sort((a, b) => Math.abs(b.rub) - Math.abs(a.rub)).slice(0, 3) : []
  const openReg = (rk: number) => { set({ selRk: rk }); go('reg') }
  const scen = PRESETS.map((p) => { const e = yearEffect(cat, p.f, Y, geo); return { p, e: e.e, rub: (market * e.e) / 100, weak: unproven(cat, p.f), flood: p.f.flood } })
  const ens = metric('ensemble', 3), pro = metric('prophet_default', 3)
  const scnName = scnLabel(scn.key)
  const toggle = (key: string) => {
    const ks = scnKeys(useApp.getState().scn.key)
    const next = ks.includes(key) ? ks.filter((x) => x !== key) : [...ks, key]
    const f = combine(next)
    set({ scn: { key: next.length ? next.join('+') : 'base', f, scope: f.flood ? 'region' : 'country' } })
  }
  const diff = (d: number, money = false) => !on || past ? null
    : Math.abs(money ? d / Math.max(1, market) : d) < 0.00005 ? null
    : <small className={weak || meas ? 'muted' : d < -0.0005 ? 'bad' : d > 0.0005 ? 'good' : 'muted'}>{money ? `${d >= 0 ? '+' : '−'}${bn(Math.abs(d))}` : `${d >= 0 ? '+' : '−'}${fmt2(Math.abs(d * 100))} п. п.`} сценарий</small>
  const M = monthLong(target)
  // Сценарий, который не трогает ни выбранный месяц, ни окно года до него, — одна метка, а не три пустые подписи.
  const idle = on && !past && Math.abs(dMonth) < 0.00005 && Math.abs(dYear) < 0.00005

  return (
    <div className="page-main sc" style={{ flex: 1 }}>
      <div className="page-in" style={{ maxWidth: 1240 }}>
        <h1 className="page-h">Сводка</h1>
        {mode === 'pro' && <><h2 className="tech-h">Для аналитика</h2><OverviewTech /><h2 className="tech-h">Для заказчика</h2></>}

        <section className="card hero2">
          <div className="hero2-nums">
            {reg && (
              <div><small>Регион сценария</small>
                <select className="field" value={reg.rk} onChange={(e) => set({ selRk: +e.target.value })} aria-label="Регион сценария">
                  {[...all].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map((r) => <option key={r.rk} value={r.rk}>{r.name}</option>)}
                </select>
              </div>
            )}
            <div><small>{M[0].toUpperCase() + M.slice(1)} к тому же месяцу прошлого года</small><b className="big-num">{pp(baseMonth + dMonth)}</b>{diff(dMonth)}</div>
            <div><small>{target - 11 < 12 ? 'С января 2024 года' : 'За 12 месяцев'}</small><b>{pp(baseYear + dYear)}</b>{diff(dYear)}</div>
            <div><small>{target - 11 < 12 ? 'Рынок с января 2024 года' : 'Рынок за 12 месяцев'}</small><b>{bn(market + dMarket)}</b>{diff(dMarket, true)}</div>
            {past
              ? <div><small>Точность</small><b>факт</b><small>месяц прошёл</small></div>
              : <div><small>Средняя ошибка <Info tip={er.measured ? 'WAPE — ошибка в процентах от фактических трат; проверка на истории 2023—2024 годов. В отдельном месяце ошибка может быть выше средней.' : 'После года прогнозируем по предыдущим прогнозам. Ошибку оцениваем по тому, как она росла со сроком прогноза.'} /></small><b style={{ color: tone(er.w) }}>{fmt1(er.w * 100)} %</b><small>{er.measured ? 'на истории' : 'оценка'}</small></div>}
          </div>
          <div className="hero2-chart">
            <LineChart n={60} height={230}
              cursor={{ t: target, min: 12, max: 59, onChange: setTarget }}
              // Полоса — 90 % интервал строгого прогноза (конформный, по категории и шагу); средняя ошибка показана отдельно числом.
              band={{ from: FIRST_FC, color: 'var(--accent)', lo: base.slice(FIRST_FC).map((v, i) => (iv[i] !== undefined ? v / (1 + iv[i]) : v * (1 - errs[i]))), hi: base.slice(FIRST_FC).map((v, i) => v * (1 + (iv[i] ?? errs[i]))) }}
              lines={[
                // Ручка садится на первую линию: сценарий, если он есть, иначе прогноз — с последней точки факта.
                ...(on ? [{ key: 's', name: scnName, color: 'var(--blue)', v: scnS.slice(FIRST_FC - 1), from: FIRST_FC - 1, width: 2.4 }] : []),
                { key: 'p', name: on ? 'Без сценария' : 'Прогноз', color: 'var(--accent)', v: base.slice(FIRST_FC - 1), from: FIRST_FC - 1, dash: true, width: 2 },
                { key: 'f', name: 'Факт', color: 'var(--text)', v: base.slice(0, FIRST_FC), width: 2.4 },
              ]} />
            <div className="legend small">
              <span><span className="dot" style={{ background: 'var(--text)' }} />факт</span>
              <span><span className="dot" style={{ background: 'var(--accent)' }} />прогноз и интервал 90 % <Info tip={`Интервал по ошибкам прошлых прогнозов для категории и срока. Доля фактических значений внутри него на истории 2024 года, шаги 1—6: ${(META.release?.coverage90_by_step ?? []).map((c) => Math.round(c * 100)).join(' / ')} %. После десятого месяца расширяем его как √(h/10); это оценка.`} /></span>
              {on && <span><span className="dot" style={{ background: 'var(--blue)' }} />сценарий: {scnName}{reg ? `, ${reg.name}` : ''} <button className="link" onClick={() => set({ scn: { key: 'base', f: NONE, scope: 'country' } })}>убрать</button></span>}
              <span>₽ на жителя в месяц · тяните пунктир, чтобы сменить месяц</span>
            </div>
            {on && (
              <div className="scn-ev">
                {idle && <span className="tag" data-tip="Сдвиньте пунктир: сценарий влияет на другие месяцы">на {M} сценарий не влияет</span>}
                <span className={`tag ${weak || meas ? '' : 'ok'}`}>{meas ? 'меняется измерение' : weak ? 'связь не подтверждена' : `за ${2025 + Y} год ${signed(ye.e, fmt2)} % ± ${fmt2(1.96 * ye.sd)} п. п.`}</span>
                {ev.map((x) => <span key={x.name} className={`tag wrap ${x.proven ? 'ok' : x.grey || x.measure ? '' : 'warn'}`} data-tip={x.note}>{x.name}: {x.measure ? 'экспертно, измерение' : x.grey ? 'экспертно' : x.proven ? 'по данным 2024 года' : 'не подтверждено'}</span>)}
              </div>
            )}
          </div>
        </section>

        <div className="grid g2">
          <Card title="Рост по категориям" sub={on ? 'Рост за 12 месяцев по выбранный месяц; черта — без сценария' : 'Рост за 12 месяцев по выбранный месяц'}>
            <GrowthBars rows={byCat.map((x) => ({ name: x.name, v: x.g + x.e, base: on ? x.g : undefined, color: catColor(x.c), on: x.c === cat, onClick: () => set({ cat: x.c }) }))} />
          </Card>
          <Card title={on ? 'Где влияние сильнее' : 'Куда расширяться'} sub={on ? `Изменение спроса за ${2025 + Y} год по регионам` : undefined} extra={<button className="btn ghost" onClick={() => go('reg')}>На карте</button>}>
            <div style={{ height: 210, position: 'relative' }} className="mapwrap mini-map">
              <MapRussia dots={dots} color={on ? (v) => (v < 0 ? `color-mix(in srgb, var(--warn) ${Math.round(25 + (75 * -v) / hitMx)}%, var(--map-land))` : `color-mix(in srgb, var(--ok) ${Math.round(25 + (75 * v) / hitMx)}%, var(--map-land))`) : (v) => REC_COLOR[RECS[v]]} onPick={(m) => openReg(m.rk)} pad={6} mini />
            </div>
            {!on && <RecBar counts={RECS.map((r) => all.filter((x) => x.rec === r).length)} role={role} />}
            {on && <div className="top3">
              {hit.map(({ r, rub }) => <button key={r.rk} onClick={() => openReg(r.rk)}><span>{r.name} <small>{signed(hitE.get(r.rk) ?? 0, fmt2)} %</small></span><b className={rub < 0 ? 'bad' : 'good'}>{rub >= 0 ? '+' : '−'}{bn(Math.abs(rub))}</b></button>)}
            </div>}
          </Card>
          <Card title="Что будет, если…" sub={`${2025 + Y} год, ${reg ? reg.name : 'по стране'}, изменение спроса в рублях; нажмите сценарии, чтобы их сочетать`}>
            <Tornado rows={scen.map((x) => ({ name: x.p.name, v: x.rub, pct: x.e, weak: x.weak, note: x.flood && !reg ? 'в регионе паводка' : '', on: scnKeys(scn.key).includes(x.p.key), onClick: () => toggle(x.p.key) }))} />
          </Card>
          <Card title="Сдвиги спроса" sub="Сигналы по месяцам, все муниципалитеты" extra={<button className="btn ghost" onClick={() => go('risk')}>Риски</button>}>
            <MonthBars values={months} color="var(--warn)" height={130} />
            <div className="top3">
              {recent.slice(0, 3).map((a, k) => {
                const m = mo(a[0])!
                const up = (a[6] ?? 0) > 0
                return <button key={k} onClick={() => useApp.getState().openMo(a[0])}><span>{m.name} <small>{monthShort(a[2])} · {strengthWord(a[6] ?? 0)} {up ? 'рост' : 'спад'}</small></span><b className={up ? 'good' : 'bad'}>{a[6] === null ? '—' : pp(a[6])}</b></button>
              })}
            </div>
          </Card>
        </div>

        {mode === 'pro' && <SensCard cat={cat} />}

        <Card title="Средняя ошибка прогноза по месяцам" sub={`Ошибка в процентах на каждый месяц вперёд; на три месяца — ${fmt1(ens.WAPE)} %, в ${fmt1(pro.WAPE / ens.WAPE)} раза точнее базовой модели. После 2025 года ошибку оцениваем`}
          extra={<button className="btn ghost" onClick={() => { set({ aboutPage: 'trust' }); go('about') }}>Подробнее</button>}>
          <div className="acc-strip">
            {[2025, 2026, 2027].map((y, yi) => (
              <div key={y} className="acc-year">
                <small>{y}</small>
                <div>
                  {Array.from({ length: 12 }, (_, mi) => {
                    const t = FIRST_FC + yi * 12 + mi, w = errs[t - FIRST_FC]
                    return <button key={mi} className={`acc-cell${t === target ? ' on' : ''}${yi > 0 ? ' est' : ''}`} style={{ '--c': tone(w) } as React.CSSProperties}
                      data-tip={`${monthIn(t)}: средняя ошибка ${fmt1(w * 100)} % — ${yi > 0 ? 'оценка' : 'на истории'}`} onClick={() => setTarget(t)} />
                  })}
                </div>
              </div>
            ))}
          </div>
        </Card>
        <p className="small">Строгий прогноз&nbsp;— медиана четырёх моделей&nbsp;— от&nbsp;декабря 2024 года; рынок — траты на жителя, умноженные на население. Данные есть по {fmt0(all.reduce((s, r) => s + r.coverage * r.pop, 0) / Math.max(1, all.reduce((s, r) => s + r.pop, 0)) * 100)} % жителей.</p>
      </div>
    </div>
  )
}

function GrowthBars({ rows }: { rows: { name: string; v: number; base?: number; color: string; on: boolean; onClick: () => void }[] }) {
  const sorted = [...rows].sort((a, b) => b.v - a.v)
  const mx = Math.max(...rows.map((r) => Math.max(Math.abs(r.v), Math.abs(r.base ?? 0))), 0.01)
  return (
    <div className="gbars">
      {sorted.map((r) => (
        <button key={r.name} className={r.on ? 'on' : ''} onClick={r.onClick}>
          <span>{r.name}</span>
          <i><em style={{ width: `${(100 * Math.abs(r.v)) / mx}%`, background: r.color }} />{r.base !== undefined && <s className="base" style={{ left: `${(100 * Math.abs(r.base)) / mx}%` }} data-tip={`Без сценария ${pp(r.base)}`} />}</i>
          <b className={r.v < 0 ? 'bad' : ''} data-tip={r.base !== undefined ? `Без сценария ${pp(r.base)}` : undefined}>{pp(r.v)}</b>
        </button>
      ))}
    </div>
  )
}

function RecBar({ counts, role }: { counts: number[]; role: keyof typeof REC_NAME }) {
  return (
    <div className="recbar">
      <div>{counts.map((c, i) => c ? <i key={i} style={{ flex: c, background: REC_COLOR[RECS[i]] }} data-tip={`${REC_NAME[role][RECS[i]]}: ${c}`} /> : null)}</div>
      <div className="legend small nowrap">{counts.map((c, i) => <span key={i}><span className="dot" style={{ background: REC_COLOR[RECS[i]] }} />{REC_NAME[role][RECS[i]]} · {c}</span>)}</div>
    </div>
  )
}

/** «Торнадо»: каждый сценарий — столбик от нуля влево (минус) или вправо (плюс); недоказанное — серым. */
function Tornado({ rows }: { rows: { name: string; v: number; pct: number; weak: boolean; note: string; on?: boolean; onClick: () => void }[] }) {
  const mx = Math.max(...rows.map((r) => Math.abs(r.v)), 1)
  return (
    <div className="tornado">
      {rows.map((r) => {
        const w = (Math.abs(r.v) / mx) * 50
        const c = r.weak ? 'var(--text-3)' : r.v < 0 ? 'var(--warn)' : 'var(--ok)'
        return (
          <button key={r.name} onClick={r.onClick} className={r.on ? 'on' : ''} data-tip={r.weak ? `Оценка ${fmt1(r.pct)} %; интервал включает ноль` : `${fmt1(r.pct)} % к прогнозу${r.note ? ', ' + r.note : ''}`}>
            <span className="t-name">{r.name}</span>
            <span className="t-bar">
              <i style={{ left: r.v < 0 ? `${50 - w}%` : '50%', width: `${w}%`, background: c, opacity: r.weak ? 0.45 : 0.85 }} className={r.weak ? 'weak' : ''} />
              <em />
            </span>
            <b style={{ color: r.weak ? 'var(--text-3)' : c }}>{r.note ? `${fmt1(r.pct)} %` : r.weak ? 'не доказано' : `${r.v >= 0 ? '+' : '−'}${bn(Math.abs(r.v))}`}</b>
          </button>
        )
      })}
    </div>
  )
}
