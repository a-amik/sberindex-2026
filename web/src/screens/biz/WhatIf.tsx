import { useDeferredValue, useEffect, useState } from 'react'
import { LineChart } from '../../components/charts'
import { Card, Info, Seg, Table, Wait } from '../../components/ui'
import { ScenarioKnobs, Slider } from '../../components/ScenarioKnobs'
import { BIZ_CAT, bn, regionStats } from '../../data/biz'
import { FIRST_FC, META, MOS, monthShort, ser60, useShard } from '../../data/real'
import { ALL_PRESETS, combine, evidence, geoCountry, geoMo, geoRegion, LINKS, measuresOnly, monthlyEffect, NONE, PRESETS, sig, scnKeys, unproven, WORLD_PRESETS, yearEffect, type Factors, type Geo } from '../../data/whatif'
import { fmt0, fmt1, fmt2, signed } from '../../lib/util'
import { useApp } from '../../store'
import { StandMode } from '../Stand'

const money = (x: number) => `${x >= 0 ? '+' : '−'}${bn(Math.abs(x))}`

/** Испытания аналитика — страница «О проекте»: прогон истории, впрыск шока, массовый прогон, сценарий на МО. */
export const TESTS_NAV: [string, string][] = [['replay', 'Проверка на истории'], ['inject', 'Искусственный сдвиг'], ['mass', 'Проверка на выборке рядов'], ['mo', 'Сценарий для муниципалитета']]
export function TestsBody() {
  const tab = useApp((s) => s.testTab)
  return <StandMode key={tab} mode={(tab === 'mo' ? 'scenario' : tab) as 'scenario' | 'replay' | 'inject' | 'mass'} />
}

/**
 * «Что будет, если…» — блок сводки. Сценарий общий со сводкой (store.scn): график наверху
 * показывает его линией поверх прогноза, здесь — разбор по месяцам, категориям и территориям.
 * Чувствительности оценены на данных; итог — в рублях на жителя и в объёме рынка.
 */
export function WhatIfBody({ pro, hidePresets = false }: { pro: boolean; hidePresets?: boolean }) {
  const { cat, role, selRk, set, scn } = useApp()
  const target = useApp((s) => s.target)
  const { list } = regionStats(cat, role, undefined, target)
  const { key: pk, f, scope } = scn
  const setScope = (scope: 'country' | 'region') => set({ scn: { ...useApp.getState().scn, scope } })
  const setPk = (key: string) => set({ scn: { ...useApp.getState().scn, key } })
  const fd = useDeferredValue(f)
  const reg = list.find((r) => r.rk === selRk) ?? null
  const rows = scope === 'region' && reg ? [reg] : list
  // Доли отраслей территории: страна или выбранный субъект; у строк таблицы — свои.
  const geo: Geo = scope === 'region' && reg ? geoRegion(reg.rk) : geoCountry()
  // Год сценария — год месяца, выбранного в календаре: 2025, 2026 или 2027.
  const Y = Math.floor((target - FIRST_FC) / 12), year = 2025 + Y
  const yearSum = (id: number, c: number) => { const v = ser60(id, c); return v ? v.slice(FIRST_FC + 12 * Y, FIRST_FC + 12 * Y + 12).reduce((a, x) => a + x, 0) : 0 }
  const market25 = rows.reduce((s, r) => s + r.mos.reduce((a, x) => a + yearSum(x.m.id, cat) * x.m.pop, 0), 0)
  const pop = rows.reduce((s, r) => s + r.mos.reduce((a, x) => a + x.m.pop, 0), 0)
  const ye = yearEffect(cat, fd, Y, geo)
  const base = market25 / pop, scen = base * (1 + ye.e / 100)
  const ev = evidence(cat, fd)
  const months = monthlyEffect(cat, fd, Y, geo)
  // Паводок бывает в регионе, а не в стране: выбор паводка переводит сценарий на регион.
  const toRegion = () => { setScope('region'); if (selRk === null) set({ selRk: (list.find((r) => r.key === 'оренбургская') ?? list[0]).rk }) }
  const pick = (k: string) => { const p = ALL_PRESETS.find((x) => x.key === k); set({ scn: { ...useApp.getState().scn, key: k, f: p?.f ?? NONE } }); if (p?.f.flood) toRegion() }
  useEffect(() => { if (f.flood && scope === 'country') toRegion() }, [f.flood])
  const weak = unproven(cat, fd)
  const meas = measuresOnly(cat, fd)
  const upd = (p: Partial<Factors>) => { const s = useApp.getState().scn; set({ scn: { ...s, key: 'custom', f: { ...s.f, ...p } } }) }

  const byCat = BIZ_CAT.map((name, c) => {
    const st = regionStats(c, role, undefined, target)
    const rr = scope === 'region' && reg ? st.list.filter((r) => r.rk === reg.rk) : st.list
    const mk = rr.reduce((s, r) => s + r.mos.reduce((a, x) => a + yearSum(x.m.id, c) * x.m.pop, 0), 0)
    const e = yearEffect(c, fd, Y, geo)
    return { name, c, mk, e: e.e, sd: e.sd, rub: (mk * e.e) / 100 }
  })
  // Эффект у каждой строки свой: доли отраслей МО или субъекта, а не общее число на всех.
  const hit = (scope === 'region' && reg ? reg.mos.map((x) => ({ name: x.m.name, v: yearSum(x.m.id, cat) * x.m.pop, g: geoMo(x.m.id) })) : list.map((r) => ({ name: r.name, v: r.mos.reduce((a, x) => a + yearSum(x.m.id, cat) * x.m.pop, 0), g: geoRegion(r.rk) })))
    .map((x) => { const e = yearEffect(cat, fd, Y, x.g).e; return { ...x, e, rub: (x.v * e) / 100 } }).sort((a, b) => Math.abs(b.rub) - Math.abs(a.rub)).slice(0, 8)

  return (
    <>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <Seg value={scope} onChange={setScope} items={[['country', 'Вся страна'], ['region', reg ? reg.name : 'Регион']]} />
          {scope === 'region' && (
            <select className="field" style={{ width: 280 }} value={reg?.rk ?? ''} onChange={(e) => set({ selRk: +e.target.value })} aria-label="Регион">
              {!reg && <option value="">Выберите регион</option>}
              {[...list].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map((r) => <option key={r.rk} value={r.rk}>{r.name}</option>)}
            </select>
          )}
        </div>
        {!hidePresets && (
        <Card title="Сценарий">
          <div className="presets">
            <button className="preset" aria-pressed={pk === 'base'} onClick={() => pick('base')}><b>Без сценария</b><span>Базовый прогноз</span></button>
            {PRESETS.map((p) => <button key={p.key} className="preset" aria-pressed={pk === p.key} onClick={() => pick(p.key)}><b>{p.name}</b><span>{p.text}</span></button>)}
            <button className="preset" aria-pressed={pk === 'custom'} onClick={() => setPk('custom')}><b>Своё сочетание</b><span>Задать факторы вручную</span></button>
          </div>
          <div className="small" style={{ marginTop: 14, marginBottom: 6 }}>Сценарии мировой экономики <Info tip="Сценарии составлены из факторов. Их доли заданы экспертно и доступны для изменения. Серые связи увеличивают неопределённость." /></div>
          <div className="presets">
            {WORLD_PRESETS.map((p) => <button key={p.key} className="preset" aria-pressed={pk === p.key} onClick={() => pick(p.key)}><b>{p.name}</b><span>{p.text}</span></button>)}
          </div>
          {(pk === 'custom' || pro) && (
            <div className="grid g2" style={{ marginTop: 16, gap: 14 }}>
              <Slider label="Ключевая ставка" v={f.rate} min={-3} max={3} step={0.25} unit=" п. п." onChange={(rate) => upd({ rate })} />
              <Slider label="Потепление летом" v={f.heat} min={-4} max={4} step={0.5} unit=" °C" onChange={(heat) => upd({ heat })} />
              <Slider label="Дополнительные выходные" v={f.off} min={0} max={4} step={1} unit=" дн." onChange={(off) => upd({ off })} />
              <Slider label="Месяц" v={f.offAt} min={1} max={12} step={1} unit="" fmtV={(v) => monthShort(23 + v)} onChange={(offAt) => upd({ offAt })} />
              <div><Seg value={f.flood ? 'on' : 'off'} onChange={(v) => upd({ flood: v === 'on' })} items={[['off', 'Без паводка'], ['on', 'Паводок']]} /></div>
              {f.flood && <Slider label="Месяц паводка" v={f.floodAt} min={1} max={11} step={1} unit="" fmtV={(v) => monthShort(23 + v)} onChange={(floodAt) => upd({ floodAt })} />}
              <Slider label="ФОТ обработки к среднему" v={f.fotManuf} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotManuf) => upd({ fotManuf })} />
              <Slider label="ФОТ добычи к среднему" v={f.fotMining} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotMining) => upd({ fotMining })} />
              <Slider label="ФОТ сельского хозяйства к среднему" v={f.fotAgri} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotAgri) => upd({ fotAgri })} />
              <Slider label="ФОТ бюджетного сектора к среднему" v={f.fotBudget} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotBudget) => upd({ fotBudget })} />
              <Slider label="Нефть в рублях" v={f.oil} min={-50} max={50} step={5} unit=" %" onChange={(oil) => upd({ oil })} />
              <Slider label="НДС" v={f.vat} min={-2} max={4} step={1} unit=" п. п." onChange={(vat) => upd({ vat })} />
              <Slider label="Ослабление рубля" v={f.fx} min={-20} max={20} step={5} unit=" %" onChange={(fx) => upd({ fx })} />
              <Slider label="Мобильный интернет отключён" v={f.netOff} min={0} max={15} step={1} unit=" дн./мес." onChange={(netOff) => upd({ netOff })} />
            </div>
          )}
        </Card>
        )}
        <div className="hero">
          <span className="muted">{scope === 'region' && reg ? reg.name : 'Вся страна'} · {BIZ_CAT[cat]} · {year} год</span>
          <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'flex-end', marginTop: 6 }}>
            <div><div className="small">Траты на жителя за год</div><div className="big-num">{fmt0(scen)} ₽</div><div className="muted">без сценария — {fmt0(base)} ₽</div></div>
            <div><div className="small">Изменение</div><div className={`big-num ${weak ? 'muted' : ye.e < -0.05 ? 'bad' : ye.e > 0.05 ? 'good' : ''}`}>{signed(ye.e, fmt2)} %</div><div className="muted">{meas ? 'меняется измерение' : weak ? 'связь не подтверждена' : `± ${fmt2(1.96 * ye.sd)} п. п., 95 %`}</div></div>
            <div><div className="small">Объём рынка</div><div className={`big-num ${weak ? 'muted' : ''}`}>{money((market25 * ye.e) / 100)}</div><div className="muted">из {bn(market25)} за год</div></div>
          </div>
          {ev.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
              {ev.map((x) => <span key={x.name} className={`tag wrap ${x.name === 'Паводок' ? '' : x.proven ? 'ok' : x.grey ? '' : 'warn'}`} data-tip={x.note}>{x.name}: {x.name === 'Паводок' ? 'оценка по паводкам 2024 года' : x.measure ? 'измерение, экспертно' : x.grey ? 'экспертная оценка' : x.proven ? 'по данным 2024 года' : 'связь не подтверждена'}</span>)}
            </div>
          )}
        </div>
        <div className="grid g2">
          <Card title="По месяцам" sub="Изменение спроса, % к прогнозу">
            <EffectBars v={months.map((m) => m.e)} from={FIRST_FC + 12 * Y} />
          </Card>
          <Card title="По категориям" sub="Что изменится в каждой категории за год">
            <Table rows={byCat} sort={['r', 1]} cols={[
              { key: 'n', title: 'Категория', get: (r) => r.name, render: (r) => <span className="nw" style={{ fontWeight: r.c === cat ? 600 : 400 }}>{r.name}</span> },
              { key: 'e', title: 'Изменение', num: true, get: (r) => r.e, render: (r) => <span className={r.e < -0.05 ? 'bad' : r.e > 0.05 ? 'good' : ''}>{signed(r.e, fmt2)} %</span> },
              { key: 'r', title: 'В рублях', num: true, get: (r) => r.rub, render: (r) => <span className="nw">{money(r.rub)}</span> },
            ]} />
          </Card>
        </div>
        {scope === 'region' && reg ? <RegionChart rk={reg.rk} cat={cat} f={fd} Y={Y} /> : null}
        <Card title={scope === 'region' ? 'Влияние по муниципалитетам' : 'Где влияние сильнее'} sub="Изменение спроса за год в рублях: чем больше рынок, тем больше сумма">
          <Table rows={hit} sort={['r', 1]} cols={[
            { key: 'n', title: scope === 'region' ? 'Территория' : 'Регион', get: (r) => r.name },
            { key: 'v', title: 'Рынок 2025', num: true, get: (r) => r.v, render: (r) => <span className="nw">{bn(r.v)}</span> },
            { key: 'r', title: 'Изменение', num: true, get: (r) => r.rub, render: (r) => <span className="nw" data-tip={`${signed(r.e, fmt2)} %`}>{money(r.rub)}</span> },
          ]} />
        </Card>
        {pro && <SensCard cat={cat} />}
        <p className="small">Связи оценены по данным: ставка — ряд РФ за 2018—2026 годы; погода — муниципалитеты за 2023—2024 годы; выходные — ряд РФ; паводок — события 2024 года; доходы отраслей — муниципалитеты за 2024 год; нефть → фонд оплаты труда добычи — ряд РФ с 2018 года. НДС, курс и отключения интернета — экспертные оценки, показаны серым. <Info tip="Метод оценки — «О проекте», «Методика и границы». Интервал серой связи включает ноль." /></p>
    </>
  )
}

/**
 * Сценарий одного региона — в шите карточки, без перехода на сводку. Сценарий локальный:
 * стартует с общего (или с подъёма ставки, если общего нет) и общий фильтр не трогает.
 */
export function RegionScenario({ rk }: { rk: number }) {
  const { cat, role } = useApp()
  const target = useApp((s) => s.target)
  const [st, setSt] = useState(() => {
    const g = useApp.getState().scn
    if (g.key === 'custom') return { key: 'custom', f: g.f }
    const k = scnKeys(g.key)
    return k.length === 1 ? { key: k[0], f: g.f } : k.length ? { key: 'custom', f: combine(k) } : { key: PRESETS[0].key, f: PRESETS[0].f }
  })
  const fd = useDeferredValue(st.f)
  const reg = regionStats(cat, role, undefined, target).list.find((r) => r.rk === rk)
  if (!reg) return null
  const pick = (key: string) => setSt((s) => ({ key, f: key === 'base' ? NONE : key === 'custom' ? s.f : ALL_PRESETS.find((p) => p.key === key)?.f ?? NONE }))
  const upd = (p: Partial<Factors>) => setSt((s) => ({ key: 'custom', f: { ...s.f, ...p } }))
  const geo = geoRegion(rk)
  const Y = Math.floor((target - FIRST_FC) / 12), year = 2025 + Y
  const yearSum = (id: number, c: number) => { const v = ser60(id, c); return v ? v.slice(FIRST_FC + 12 * Y, FIRST_FC + 12 * Y + 12).reduce((a, x) => a + x, 0) : 0 }
  const market = reg.mos.reduce((a, x) => a + yearSum(x.m.id, cat) * x.m.pop, 0)
  const pop = reg.mos.reduce((a, x) => a + x.m.pop, 0)
  const ye = yearEffect(cat, fd, Y, geo)
  const base = market / pop, scen = base * (1 + ye.e / 100)
  const ev = evidence(cat, fd)
  const weak = unproven(cat, fd), meas = measuresOnly(cat, fd)
  const byCat = BIZ_CAT.map((name, c) => {
    const r = regionStats(c, role, undefined, target).list.find((x) => x.rk === rk)
    const mk = r ? r.mos.reduce((a, x) => a + yearSum(x.m.id, c) * x.m.pop, 0) : 0
    const e = yearEffect(c, fd, Y, geo).e
    return { name, c, e, rub: (mk * e) / 100 }
  })
  const hit = reg.mos.map((x) => { const v = yearSum(x.m.id, cat) * x.m.pop, e = yearEffect(cat, fd, Y, geoMo(x.m.id)).e; return { name: x.m.name, v, e, rub: (v * e) / 100 } })
    .sort((a, b) => Math.abs(b.rub) - Math.abs(a.rub)).slice(0, 8)
  return (
    <>
      <div>
        <h3>Сценарий</h3>
        <select className="field" style={{ width: '100%' }} value={st.key} onChange={(e) => pick(e.target.value)} aria-label="Сценарий">
          <option value="base">Базовый прогноз</option>
          <optgroup label="Простые">{PRESETS.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</optgroup>
          <optgroup label="Мировая экономика">{WORLD_PRESETS.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}</optgroup>
          <option value="custom">Своё сочетание…</option>
        </select>
        {st.key === 'custom' && <ScenarioKnobs f={st.f} onChange={upd} one />}
      </div>
      <div className="stats">
        <div className="stat"><small>На жителя за {year} год</small><b>{fmt0(scen)} ₽</b><small>без сценария — {fmt0(base)} ₽</small></div>
        <div className="stat"><small>Изменение <Info tip={meas ? 'Меняется учёт безналичного оборота; спрос может остаться прежним' : weak ? 'Связь не подтверждена: интервал включает ноль' : `± ${fmt2(1.96 * ye.sd)} п. п., 95 %`} /></small><b className={weak ? 'muted' : ye.e < -0.05 ? 'bad' : ye.e > 0.05 ? 'good' : ''}>{signed(ye.e, fmt2)} %</b></div>
        <div className="stat" style={{ gridColumn: '1 / -1' }}><small>Объём рынка</small><b className={weak ? 'muted' : ''}>{money((market * ye.e) / 100)}</b><small>из {bn(market)} за год</small></div>
      </div>
      {ev.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {ev.map((x) => <span key={x.name} className={`tag ${x.name === 'Паводок' ? '' : x.proven ? 'ok' : x.grey ? '' : 'warn'}`} data-tip={x.note}>{x.name}: {x.name === 'Паводок' ? 'паводки 2024 года' : x.measure ? 'меняет измерение' : x.grey ? 'экспертно' : x.proven ? 'по данным' : 'не подтверждено'}</span>)}
        </div>
      )}
      <div><h3>По месяцам, % к прогнозу</h3><EffectBars v={monthlyEffect(cat, fd, Y, geo).map((m) => m.e)} from={FIRST_FC + 12 * Y} /></div>
      <RegionChart rk={rk} cat={cat} f={fd} Y={Y} />
      <div>
        <h3>По категориям</h3>
        <Table rows={byCat} sort={['r', 1]} cols={[
          { key: 'n', title: 'Категория', get: (r) => r.name, render: (r) => <span className="nw" style={{ fontWeight: r.c === cat ? 600 : 400 }}>{r.name}</span> },
          { key: 'e', title: 'Изменение', num: true, get: (r) => r.e, render: (r) => <span className={r.e < -0.05 ? 'bad' : r.e > 0.05 ? 'good' : ''}>{signed(r.e, fmt2)} %</span> },
          { key: 'r', title: 'В рублях', num: true, get: (r) => r.rub, render: (r) => <span className="nw">{money(r.rub)}</span> },
        ]} />
      </div>
      <div>
        <h3>Где влияние сильнее</h3>
        <Table rows={hit} sort={['r', -1]} cols={[
          { key: 'n', title: 'Территория', get: (r) => r.name, render: (r) => <span className="ell" style={{ maxWidth: 150 }}>{r.name}</span> },
          { key: 'v', title: 'Рынок', num: true, get: (r) => r.v, render: (r) => <span className="nw">{bn(r.v)}</span> },
          { key: 'r', title: 'Изменение', num: true, get: (r) => r.rub, render: (r) => <span className="nw" data-tip={`${signed(r.e, fmt2)} %`}>{money(r.rub)}</span> },
        ]} />
      </div>
    </>
  )
}

/** Регион помесячно: прогноз ансамбля и сценарий, рубли на жителя. */
function RegionChart({ rk, cat, f, Y }: { rk: number; cat: number; f: Factors; Y: number }) {
  const data = useShard(rk)
  const months = monthlyEffect(cat, f, Y)
  if (!data) return <Card title="Помесячно"><Wait label="Загружаем регион…" /></Card>
  const ms = MOS.filter((m) => m.rk === rk)
  const n = META.periods.length
  const agg = (pick: (id: number) => (number | null)[] | undefined, len: number) => {
    const out = new Array(len).fill(0), w = new Array(len).fill(0)
    for (const m of ms) {
      const v = pick(m.id)
      if (!v || !m.pop) continue
      v.forEach((x, i) => { if (x !== null && Number.isFinite(x)) { out[i] += x * m.pop; w[i] += m.pop } })
    }
    return out.map((x, i) => (w[i] ? x / w[i] : NaN))
  }
  const fact = agg((id) => data.series[id]?.[cat], n)
  const H = 36
  const base = agg((id) => data.fwd?.[id]?.[cat]?.ensemble, H)
  // Сценарий ложится на год выбранного месяца; остальные годы — прогноз без изменений.
  const scen = base.map((v, i) => (i >= 12 * Y && i < 12 * Y + 12 ? v * (1 + months[i - 12 * Y].e / 100) : v))
  return (
    <Card title="Помесячно, ₽ на жителя" sub={`Факт 2023—2024 годов, прогноз до 2027 года, сценарий — на ${2025 + Y} год`}>
      <LineChart n={n + H} origin={n - 1} shade={[n + 12 * Y, n + 12 * Y + 11]} lines={[
        { key: 'f', name: 'Факт', color: 'var(--text)', v: fact, width: 2.4 },
        { key: 'b', name: 'Прогноз', color: 'var(--text-3)', v: [fact[n - 1], ...base], from: n - 1, dash: true, width: 1.6 },
        { key: 's', name: 'Сценарий', color: 'var(--accent)', v: [fact[n - 1], ...scen], from: n - 1, width: 2.4 },
      ]} />
    </Card>
  )
}

function EffectBars({ v, from }: { v: number[]; from: number }) {
  const mx = Math.max(0.2, ...v.map(Math.abs))
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${v.length}, minmax(0, 1fr))`, gap: 4, height: 160, alignItems: 'stretch' }}>
      {v.map((x, i) => (
        <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }} data-tip={`${monthShort(from + i)}: ${signed(x, fmt2)} %`}>
          <div style={{ flex: 1, width: '100%', position: 'relative' }}>
            <div style={{ position: 'absolute', left: '15%', right: '15%', borderRadius: 3, background: x < 0 ? 'var(--warn)' : 'var(--ok)', opacity: x ? 0.85 : 0,
              top: x >= 0 ? `${50 - (50 * x) / mx}%` : '50%', height: `${(50 * Math.abs(x)) / mx}%` }} />
            <div style={{ position: 'absolute', left: 0, right: 0, top: '50%', borderTop: '1px solid var(--line-2)' }} />
          </div>
          <span className="small" style={{ fontSize: 10.5 }}>{monthShort(from + i).split(' ')[0]}</span>
        </div>
      ))}
    </div>
  )
}


/** Коэффициенты сценария с ошибками — ручки и цифры аналитика. */
export function SensCard({ cat }: { cat: number }) {
  const S = META.sensitivity[META.cats[cat]]
  const rows: [string, string, number, number | undefined, string][] = [
    ['Ставка', 'п. п. годового реального роста на 1 п. п. изменения за год', S.rate.coef, S.rate.se, `лаг ${S.rate.lag} мес., ряд РФ «${S.rate.series}», n = ${S.rate.n}`],
    ['Жара летом', '% на 1 °C, июнь—август', S.heat.coef, S.heat.se, `панель муниципалитетов, кластеры по субъектам, n = ${S.heat.n}`],
    ['Рабочий день', '% месячных трат на день', S.workday.coef, S.workday.se, `ряд РФ, n = ${S.workday.n}`],
    ['Осадки', '% на 1 мм/сут', S.rain.coef, S.rain.se, 'панель муниципалитетов'],
    ['Паводок', '% в месяц паводка', S.flood.coef, undefined, 'события 2024 года: пострадавшие субъекты и остальные'],
    ['Доходы по отраслям', 'п. п. годового роста на 1 п. п. ожидаемого роста доходов', LINKS.income.coef, LINKS.income.se, LINKS.income.note],
    ['Обработка', 'то же, доля обработки × её относительный рост ФОТ', LINKS.manuf.coef, LINKS.manuf.se, LINKS.manuf.note],
    ['Нефть → зарплатный фонд добычи', 'Δ log фонда оплаты труда на Δ log рублёвой цены, задержка 6 мес.', LINKS.oilToMining.coef, LINKS.oilToMining.se, LINKS.oilToMining.note],
    ['НДС', 'п. п. номинального роста на 1 п. п. ставки', LINKS.vat.coef, undefined, LINKS.vat.note],
    ['Курс', '% номинального роста на 1 % ослабления, × доля импорта категории', LINKS.fx.coef, undefined, LINKS.fx.note],
    ['Интернет', '% оборота на день отключения', LINKS.netOff.coef, undefined, LINKS.netOff.note],
  ]
  return (
    <Card title="Коэффициенты сценария" sub="Расчёты scripts/18, 38, 40: ошибки с учётом связи наблюдений для рядов РФ, с группировкой — для панели; у экспертных оценок ошибка не рассчитана">
      <Table rows={rows} sort={['n', 1]} cols={[
        { key: 'n', title: 'Фактор', get: (r) => r[0], render: (r) => <span className="nw" data-tip={r[4]}>{r[0]}</span> },
        { key: 'u', title: 'Единица', get: (r) => r[1] },
        { key: 'c', title: 'Оценка', num: true, get: (r) => r[2], render: (r) => `${signed(r[2], fmt2)}${r[3] !== undefined ? ` ± ${fmt2(r[3])}` : ''}` },
        { key: 't', title: 't', num: true, get: (r) => (r[3] ? r[2] / r[3] : NaN), render: (r) => (r[3] ? fmt1(r[2] / r[3]) : '—') },
        { key: 's', title: 'Связь подтверждена', get: (r) => r[0], render: (r) => (r[3] === undefined ? <span className="tag">{r[0] === 'Паводок' ? 'случай' : 'экспертно'}</span> : sig(r[2], r[3]) ? <span className="tag ok">да</span> : <span className="tag warn">нет</span>) },
      ]} />
    </Card>
  )
}
