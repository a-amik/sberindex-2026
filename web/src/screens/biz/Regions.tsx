import { TITLES } from '../../components/Shell'
import { useEffect, useMemo, useRef, useState } from 'react'
import { I } from '../../components/icons'
import { diverging, MapRussia } from '../../components/MapRussia'
import { CatHeat, Quadrant } from '../../components/RegionViews'
import { MarketTree, RankLanes, RatingBars, RegionProfile, ScenarioFan, SmallMultiples } from '../../components/RegionViews2'
import { usePhone } from '../../components/Shell'
import { Info, Row, Seg, Table, useSheetDrag } from '../../components/ui'
import { BIZ_CAT, bn, REC_COLOR, REC_NAME, regionStats, reliability, strengthWord, TH, type Rec, type RegionStat, type Th } from '../../data/biz'
import { ALARMS, META, MOS, monthShort, PEOPLE } from '../../data/real'
import { fmt0, fmt1, fmt2, median, pct } from '../../lib/util'
import { MoSheet } from '../MoSheet'
import { useApp } from '../../store'
import { RegionScenario } from './WhatIf'
import { HOUSING, LAYER_STYLE, LAYERS, loadHousing, moHas } from '../../data/layers'

const pp = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${fmt1(Math.abs(x * 100))} %`
const RECS: Rec[] = ['own', 'partner', 'watch', 'blind']

/**
 * Регионы: куда выходить и в каком формате. Слева список субъектов с рекомендацией,
 * справа карта, где точки МО окрашены рекомендацией своего региона; карточка региона —
 * шторкой у края карты, на телефоне снизу.
 */
export function Regions() {
  const { cat, role, selRk, set, focus, mode, th, sel: selMo, layers } = useApp()
  const pro = mode === 'pro'
  const phone = usePhone()
  const target = useApp((s) => s.target)
  const { list, national } = regionStats(cat, role, pro ? th : TH, target)
  const [metric, setMetric] = useState<'rec' | 'yoy' | 'gain' | 'alarm' | 'mig' | 'old'>('rec')
  // Вид справа задаёт раздел левой колонки; внутри трёх разделов — переключатель из двух видов.
  const screen = useApp((s) => s.screen)
  const GROUP: Record<string, [string, string][]> = { rank: [['bars', 'Список'], ['quad', 'Рост и рынок']], cats: [['heat', 'По категориям'], ['tree', 'Доли рынка']], dyn: [['ranks', 'Смена мест'], ['grid', 'Ряды по месяцам']] }
  const sub = GROUP[screen] ?? null
  const [pick, setPick] = useState<Record<string, string>>({})
  const view = (sub ? pick[screen] ?? sub[0][0] : 'map') as 'map' | 'bars' | 'quad' | 'heat' | 'tree' | 'ranks' | 'grid'
  const setView = (v: string) => setPick((p) => ({ ...p, [screen]: v }))
  const med = useMemo(() => median(MOS.map((m) => m.sum[cat][0] ?? NaN)), [cat])
  const [only, setOnly] = useState<Rec | 'all'>('all')
  // Включённые слои — фильтр: на карте МО без них притушены, в списке — только регионы, где они есть.
  const keep = useMemo(() => (layers.length ? new Set(MOS.filter((m) => moHas(m.id, layers)).map((m) => m.id)) : null), [layers])
  const regHas = useMemo(() => (keep ? new Set(MOS.filter((m) => keep.has(m.id)).map((m) => m.rk)) : null), [keep])
  const rows = useMemo(() => list.filter((r) => (only === 'all' || r.rec === only) && (!regHas || regHas.has(r.rk))), [list, only, regHas])
  const marks = useMemo(() => LAYERS.filter((l) => l.kind === 'point' && layers.includes(l.key)).flatMap((l) => l.items.map((it) => ({
    lon: +it[0], lat: +it[1], name: String(it[2]), glyph: LAYER_STYLE[l.key].glyph,
    color: l.key === HOUSING ? ['#475569', '#d97706', '#dc2626'][+it[5]] : LAYER_STYLE[l.key].color,
    tip: typeof it[4] === 'string' ? it[4] : `<b>${it[2]}</b><br>${l.name}${MOS.find((m) => m.id === +it[3]) ? ' · ' + MOS.find((m) => m.id === +it[3])!.name : ''}`,
  }))), [layers])
  const recOf = useMemo(() => new Map(list.map((r) => [r.rk, r.rec])), [list])
  // У аналитика карта красится и другими показателями: рост г/г к медиане, выигрыш над Prophet, тревоги.
  const dots = useMemo(() => MOS.map((m) => {
    const rec = recOf.get(m.rk) ?? 'blind'
    if (metric === 'rec') return { mo: m, v: RECS.indexOf(rec), tip: `<b>${m.region}</b><br>${REC_NAME[role][rec]}<br>${m.name}` }
    // Люди: приток — сальдо внутренней миграции на 1 000 жителей; возраст — доля 65+ к стране. Свойство территории, поэтому раскраска, а не значки.
    if (metric === 'mig' || metric === 'old') {
      const pp0 = PEOPLE?.mo[m.id], c0 = PEOPLE?.country
      const raw = pp0 ? (metric === 'mig' ? pp0[0] : pp0[1]) : null
      if (raw === null || raw === undefined || !c0) return { mo: m, v: NaN, tip: `<b>${m.name}</b><br>${m.region}<br>нет данных` }
      const v = metric === 'mig' ? raw : raw - (c0[1] ?? 0)
      return { mo: m, v, tip: `<b>${m.name}</b><br>${m.region}<br>${metric === 'mig' ? `Приток людей ${raw > 0 ? '+' : raw < 0 ? '−' : ''}${fmt1(Math.abs(raw))} на 1 000 жителей` : `Жители 65+: ${fmt0(raw * 100)} % (${v > 0 ? '+' : '−'}${fmt1(Math.abs(v) * 100)} п. п. к стране)`}` }
    }
    const k = metric === 'yoy' ? 0 : metric === 'gain' ? 1 : 2
    const raw = m.sum[cat][k] ?? NaN
    const v = metric === 'yoy' ? raw - med : raw
    return { mo: m, v, tip: `<b>${m.name}</b><br>${m.region}<br>${metric === 'yoy' ? `Рост за год ${pct(raw)}` : metric === 'gain' ? `Средняя ошибка ансамбля ниже, чем у Prophet, на ${pct(raw, 0)}` : raw ? `Сигнал, балл ${fmt1(raw)}` : 'Сигналов нет'}` }
  }), [recOf, role, metric, cat, med])
  const color = metric === 'rec' ? (v: number) => REC_COLOR[RECS[v]] : metric === 'alarm' ? (v: number) => (v ? 'var(--warn)' : 'color-mix(in srgb, var(--text-3) 40%, transparent)') : metric === 'mig' ? diverging(10) : metric === 'old' ? ((f) => (v: number) => f(-v))(diverging(0.06)) : diverging(metric === 'yoy' ? 0.15 : 0.5)
  const sel = list.find((r) => r.rk === selRk) ?? null
  // Точка, к которой летит карта: крупнейшая МО выбранного региона.
  const anchor = sel?.mos[0]?.m.id ?? null

  return (
    <div className="mapscreen">
      <aside className="col">
        <div className="col-h">
          <h1 className="page-h">{TITLES[screen]}</h1>
          {/* Поиск территории — в шапке; здесь переключатель видов раздела. */}
          {sub && <div className="col-seg"><Seg value={view} onChange={setView} items={sub} /></div>}
          <Row>
            <button className="chip" aria-pressed={only === 'all'} onClick={() => setOnly('all')}>Все</button>
            {RECS.map((r) => <button key={r} className="chip" aria-pressed={only === r} onClick={() => setOnly(r)}><i style={{ background: REC_COLOR[r] }} />{REC_NAME[role][r]} · {list.filter((x) => x.rec === r).length}</button>)}
          </Row>
          <span className="small">Рост за 12 мес. по {monthShort(target)}: по стране {pp(national)} · по объёму рынка</span>
          {pro && <Thresholds />}
        </div>
        <div className="col-list sc">
          {rows.map((r) => (
            <button key={r.rk} className={`reg-row${selRk === r.rk ? ' on' : ''}`} onClick={() => set({ selRk: r.rk, focus: focus + 1 })}>
              <b>{r.name}</b><span className="rec-dot" style={{ background: REC_COLOR[r.rec] }} data-tip={REC_NAME[role][r.rec]} />
              <span>{r.market ? bn(r.market) : '—'} за 12 мес.{pro && ` · ошибка ${fmt1(r.wape * 100)} % · разброс ${fmt1(r.vol)} · данные ${fmt0(r.coverage * 100)} %`}</span><span className={r.growth >= national ? 'good' : ''} style={{ textAlign: 'right' }}>{Number.isFinite(r.growth) ? pp(r.growth) : '—'}</span>
            </button>
          ))}
        </div>
      </aside>
      <div className="mapwrap">
        {view === 'map' ? <MapRussia dots={dots} color={color} marks={marks} keep={keep} selected={pro && selMo !== null ? selMo : anchor} focus={focus} inset={(sel || (pro && selMo !== null)) && !phone ? 440 : 0}
          onPick={(m) => set(pro ? { selRk: m.rk, sel: m.id } : { selRk: m.rk })} pad={phone ? 8 : 28} tools={<LayersButton />} />
          : view === 'bars' ? <RatingBars list={list} national={national} role={role} onPick={(rk) => set({ selRk: rk })} />
          : view === 'quad' ? <Quadrant list={list} national={national} role={role} onPick={(rk) => set({ selRk: rk })} />
          : view === 'ranks' ? <RankLanes list={list} onPick={(rk) => set({ selRk: rk })} />
          : view === 'grid' ? <SmallMultiples list={list} onPick={(rk) => set({ selRk: rk })} />
          : view === 'tree' ? <MarketTree list={list} national={national} onPick={(rk) => set({ selRk: rk })} />
          : <CatHeat role={role} onPick={(rk) => set({ selRk: rk })} />}
        <div className="map-float" style={{ left: (sel || (pro && selMo !== null)) && !phone ? 'calc(var(--sheet) + 12px)' : 12, top: 12, flexWrap: 'wrap' }}>
          {view === 'map' && <Seg value={metric} onChange={setMetric} items={pro ? [['rec', 'Рекомендация'], ['yoy', 'Рост за год'], ['gain', 'К Prophet'], ['alarm', 'Сигналы'], ['mig', 'Приток людей'], ['old', 'Жители 65+']] : [['rec', 'Рекомендация'], ['mig', 'Приток людей'], ['old', 'Жители 65+']]} />}
        </div>
        {view === 'map' && <div className="map-float" style={{ left: sel && !phone ? 'calc(var(--sheet) + 12px)' : 12, bottom: 12 }}>
          <div className="map-legend">{metric !== 'rec' ? (metric === 'alarm' ? 'Сигнал за 3 месяца' : metric === 'yoy' ? '−15 … +15 п. п. к медиане' : metric === 'mig' ? 'Отток −10 … приток +10 на 1 000 жителей за последний год' : metric === 'old' ? 'Жители 65+: доля ниже … выше доли по стране на 6 п. п.' : '−50 … +50 % к Prophet') : RECS.map((r) => <span key={r} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><span className="dot" style={{ background: REC_COLOR[r], margin: 0 }} />{REC_NAME[role][r]}</span>)}</div>
        </div>}
        {pro && selMo !== null ? <MoSheet id={selMo} onClose={() => set({ sel: null })} />
          : sel && <RegionSheet r={sel} national={national} onClose={() => set({ selRk: null })} />}
      </div>
    </div>
  )
}

function RegionSheet({ r, national, onClose }: { r: RegionStat; national: number; onClose: () => void }) {
  const { cat, role, mode } = useApp()
  // Сценарий региона открывается в этом же шите, вместо карточки; другой регион — снова карточка.
  const [what, setWhat] = useState(false)
  const drag = useSheetDrag<HTMLElement>(onClose)
  useEffect(() => setWhat(false), [r.rk])
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && (what ? setWhat(false) : onClose())
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [onClose, what])
  const rel = reliability(r.wape)
  const T = META.periods.length
  const ids = new Set(r.mos.map((x) => x.m.id).concat(MOS.filter((m) => m.rk === r.rk).map((m) => m.id)))
  const sig = ALARMS.filter((a) => a[1] === cat && ids.has(a[0]) && a[2] >= T - 6).sort((a, b) => b[2] - a[2])
  const local = r.riskNews > 20 || r.vol > 4 ? 'повышенный' : r.riskNews > 5 ? 'умеренный' : 'низкий'
  const macro = { strong: 'повторяет страну', weak: 'слабая связь', none: 'связь не найдена' }[r.macro]
  return (
    <>
      <div className="sheet-scrim" onClick={onClose} />
      <aside ref={drag} className="sheet" role="dialog" aria-label={r.name}>
        <div className="grab" />
        <div className="sheet-h">
          {what && <button className="icon-btn" aria-label="К карточке региона" data-tip="К карточке региона" onClick={() => setWhat(false)}>{I.back}</button>}
          <div className="sheet-t"><h2>{what ? 'Что будет, если…' : r.name}</h2><p>{what ? `${r.name} · ${BIZ_CAT[cat]}` : `${BIZ_CAT[cat]} · ${r.nMo} МО · ${fmt0(r.pop)} жителей`}</p></div>
          <button className="icon-btn" aria-label="Закрыть" onClick={onClose}>{I.close}</button>
        </div>
        {what ? <div className="sheet-b sc" key="scn"><RegionScenario rk={r.rk} /></div> : <div className="sheet-b sc">
          <div>
            <span className="rec" style={{ '--c': REC_COLOR[r.rec], height: 30, fontSize: 14 } as React.CSSProperties}>{REC_NAME[role][r.rec]}</span>
            <ul className="why" style={{ marginTop: 10 }}>{r.reasons.map((w) => <li key={w}>{w[0].toUpperCase() + w.slice(1)}</li>)}</ul>
          </div>
          <div className="stats">
            <div className="stat"><small>Рынок за 12 мес.</small><b>{r.market ? bn(r.market) : '—'}</b></div>
            <div className="stat"><small>Рост за 12 мес.</small><b className={r.growth >= national ? 'good' : ''}>{Number.isFinite(r.growth) ? pp(r.growth) : '—'}</b></div>
            <div className="stat"><small>Надёжность прогноза <Info tip="Средняя ошибка на три месяца по муниципалитетам региона с учётом объёма рынка." /></small><b style={{ color: rel.tone }}>{rel.word}</b></div>
            <div className="stat"><small>Охват данными</small><b>{Math.round(r.coverage * 100)} % жителей</b></div>
            <div className="stat"><small>Локальный риск <Info tip="Новости о ЧС, бедствиях и пожарах за 2023—2024 годы и разброс трат." /></small><b>{local}</b></div>
            <div className="stat"><small>Макрориск <Info tip="Насколько рост трат региона повторял рост по стране в 2024 году." /></small><b style={{ fontSize: 14 }}>{macro}</b></div>
          </div>
          <ScenarioFan rk={r.rk} />
          <RegionProfile rk={r.rk} role={role} />
          <PeopleBlock rk={r.rk} />
          {mode === 'pro' && (
            <div>
              <h3>Показатели рекомендации</h3>
              <Table rows={[
                ['Рынок, ₽ в год', bn(r.market)], ['Рост 2025, к стране', `${pp(r.growth)} / ${pp(national)}`], ['WAPE ансамбля, 3 мес.', `${fmt1(r.wape * 100)} %`],
                ['Разброс, σ сигнала', fmt1(r.vol)], ['Охват данными', `${fmt0(r.coverage * 100)} %`], ['Доля трёх крупнейших муниципалитетов', `${fmt0(r.topShare * 100)} %`],
                ['Новости ЧС, 2023—2024', String(r.riskNews)], ['Связь со страной', { strong: 'сильная', weak: 'слабая', none: 'не выявлена' }[r.macro]],
              ]} cols={[{ key: 'k', title: 'Показатель', get: (x) => x[0] }, { key: 'v', title: 'Значение', num: true, get: (x) => x[1] }]} />
            </div>
          )}
          <div>
            <h3>Крупнейшие рынки</h3>
            <Table rows={r.mos.slice(0, 8)} sort={['m', -1]} onRow={(x) => useApp.getState().openMo(x.m.id)} cols={[
              { key: 'n', title: 'Территория', get: (x) => x.m.name, render: (x) => <span className="ell" style={{ maxWidth: 170 }}>{x.m.name}</span> },
              { key: 'm', title: 'Доля рынка', num: true, get: (x) => x.market, render: (x) => `${fmt0((100 * x.market) / r.market)} %` },
              { key: 'g', title: 'Рост', num: true, get: (x) => x.growth, render: (x) => <span className={x.growth >= national ? 'good' : ''}>{pp(x.growth)}</span> },
            ]} />
          </div>
          <div>
            <h3>Сигналы за полгода</h3>
            <div className="feed">
              {sig.slice(0, 6).map((a, k) => {
                const m = MOS.find((x) => x.id === a[0])!
                return <div key={k} className="feed-i" style={{ gridTemplateColumns: '52px minmax(0,1fr) auto' }}><span className="feed-t">{monthShort(a[2])}</span><span className="feed-n">{m.name}</span><span className={`tag ${(a[6] ?? 0) > 0 ? 'ok' : 'warn'}`}>{strengthWord(a[6] ?? 0)} {(a[6] ?? 0) > 0 ? 'рост' : 'спад'}</span></div>
              })}
              {!sig.length && <p className="small">Сигналов нет</p>}
            </div>
          </div>
          <button className="btn" onClick={() => setWhat(true)}>Сценарий региона…</button>
        </div>}
      </aside>
    </>
  )
}

/** Пороги правил рекомендации — ручки аналитика; бизнес видит рекомендации по умолчанию. */
function Thresholds() {
  const { th, set } = useApp()
  const upd = (p: Partial<Th>) => set({ th: { ...th, ...p } })
  const S = (label: string, k: keyof Th, min: number, max: number, step: number, f: (v: number) => string, tip: string) => (
    <div className="range" data-tip={tip}>
      <div className="range-top"><span>{label}</span><b>{f(th[k])}</b></div>
      <input type="range" min={min} max={max} step={step} value={th[k]} onChange={(e) => upd({ [k]: +e.target.value })} aria-label={label} />
    </div>
  )
  return (
    <details className="th">
      <summary>Пороги рекомендаций…</summary>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
        {S('Крупный рынок', 'market', 0.3, 0.9, 0.05, fmt2, '«Проверить для своей сети» — только там, где рынок больше, чем у этой доли регионов')}
        {S('Отставание, п. п.', 'gap', -8, 0, 0.5, fmt1, 'Рост ниже страны на этот порог — рекомендуем повременить')}
        {S('Минимальный охват', 'cover', 0.3, 0.95, 0.05, fmt2, 'Охват ниже порога — рекомендация «мало данных»')}
        {S('Разброс трат', 'vol', 0.5, 0.98, 0.02, fmt2, 'Разброс выше, чем у этой доли регионов, — рекомендуем повременить')}
        {S('Доля трёх муниципалитетов', 'conc', 0.2, 0.9, 0.05, fmt2, 'Доля рынка в трёх крупнейших муниципалитетах для своего присутствия')}
        <button className="btn ghost" onClick={() => set({ th: TH })}>Сбросить</button>
      </div>
    </details>
  )
}

/** Слои карты — кнопкой на карте, как у картографических сервисов: список с галочками, число объектов, источник в подсказке. */
function LayersButton() {
  const { layers, set } = useApp()
  const [open, setOpen] = useState(false)
  const [wait, setWait] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const off = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', off)
    addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', off); removeEventListener('keydown', esc) }
  }, [open])
  const toggle = async (k: string) => {
    if (layers.includes(k)) return set({ layers: layers.filter((x) => x !== k) })
    if (k === HOUSING) { setWait(true); await loadHousing((id) => MOS.find((m) => m.id === id)?.name ?? `Муниципалитет ${id}`).catch(() => null); setWait(false) }
    set({ layers: [...useApp.getState().layers, k] })
  }
  if (!LAYERS.length) return null
  const all = LAYERS.some((l) => l.key === HOUSING) ? [...LAYERS].sort((a) => (a.key === HOUSING ? -1 : 0)) : [{ key: HOUSING, name: 'Строящееся жильё', note: 'Строящиеся дома из наш.дом.рф: застройщик, срок ввода, риск недостроя', source: 'наш.дом.рф', items: [] as unknown[][], total: undefined as number | undefined }, ...LAYERS]
  const n = (l: (typeof all)[number]) => (l.key === HOUSING && wait ? '…' : (l.total ?? l.items.length) ? (l.total ?? l.items.length).toLocaleString('ru') : '')
  return (
    <div className="menu-wrap map-layers" ref={ref}>
      <button className={`icon-btn${layers.length ? ' on' : ''}`} aria-label="Слои карты" aria-expanded={open} aria-haspopup="menu" data-tip={layers.length ? `<b>Слои</b><br>Включено: ${layers.length}` : '<b>Слои</b><br>Стройка, порты, добыча и другие объекты на карте'} onClick={() => setOpen((o) => !o)}>
        <svg className="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3.5l9 4.5-9 4.5L3 8z" /><path d="M3 12.5l9 4.5 9-4.5" /><path d="M3 16.5l9 4.5 9-4.5" /></svg>
      </button>
      {open && (
        <div className="menu" role="menu">
          <small className="menu-h">Слои карты</small>
          {all.map((l) => (
            <button key={l.key} role="menuitemcheckbox" aria-checked={layers.includes(l.key)} onClick={() => toggle(l.key)} data-tip={`<b>${l.name}</b><br>${l.note}<br>Источник: ${l.source}`}>
              {layers.includes(l.key) ? I.check : <span className="i" />}<i className="dot" style={{ background: LAYER_STYLE[l.key].color, margin: 0 }} />{(() => { const t = l.name.replace('Добыча: ', ''); return t.charAt(0).toUpperCase() + t.slice(1) })()}<span className="small" style={{ marginLeft: 'auto', paddingLeft: 12 }}>{n(l)}</span>
            </button>
          ))}
          <hr />
          {layers.length < all.length && <button onClick={async () => { if (!LAYERS.some((l) => l.key === HOUSING)) { setWait(true); await loadHousing((id) => MOS.find((m) => m.id === id)?.name ?? `Муниципалитет ${id}`).catch(() => null); setWait(false) } set({ layers: all.map((l) => l.key) }) }}><span className="i" />Включить все</button>}
          {layers.length > 0 && <button onClick={() => { set({ layers: [] }); setOpen(false) }}><span className="i" />Сбросить слои</button>}
        </div>
      )}
    </div>
  )
}


/** Люди региона против страны: миграция прошлого года двигает рост следующего (dev 41), возраст — слабее и через неё. Чего нет в данных — прочерк. */
function PeopleBlock({ rk }: { rk: number }) {
  const p = PEOPLE?.regions[rk], c = PEOPLE?.country
  if (!p || !c || p.every((x) => x === null)) return null
  const sg = (x: number) => (x > 0 ? '+' : x < 0 ? '−' : '')
  const d = (a: number | null, b: number | null, f: (x: number) => string, unit = '') => { if (a === null || b === null) return null; const x = a - b; return <small className={x > 0 ? 'good' : x < 0 ? 'bad' : ''}>{sg(x)}{f(Math.abs(x))}{unit} к стране</small> }
  return (
    <div>
      <h3>Население <Info tip="Сальдо внутренней миграции за 2023 год, у части субъектов — 2020—2022, на 1 000 жителей; возраст на 01.01.2023, Росстат. В данных за 2024 год приток прошлого года связан с ростом трат и рынка в следующем: одно стандартное отклонение сальдо — около +0,4 п. п. роста. Связь с возрастом частично объясняется переездом молодых." /></h3>
      <div className="stats">
        <div className="stat"><small>Приток людей, на 1 000 <Info tip="Приехавшие минус уехавшие внутри России, на 1 000 жителей." /></small><b className={p[0] === null ? '' : p[0] > 0 ? 'good' : p[0] < 0 ? 'bad' : ''}>{p[0] === null ? '—' : `${sg(p[0])}${fmt1(Math.abs(p[0]))}`}</b>{d(p[0], c[0], fmt1)}</div>
        <div className="stat"><small>Жители 65+</small><b>{p[1] === null ? '—' : `${fmt0(p[1] * 100)} %`}</b>{d(p[1] === null ? null : p[1] * 100, c[1] === null ? null : c[1] * 100, fmt1, ' п. п.')}</div>
        <div className="stat"><small>Жители 15—34</small><b>{p[2] === null ? '—' : `${fmt0(p[2] * 100)} %`}</b>{d(p[2] === null ? null : p[2] * 100, c[2] === null ? null : c[2] * 100, fmt1, ' п. п.')}</div>
      </div>
    </div>
  )
}
