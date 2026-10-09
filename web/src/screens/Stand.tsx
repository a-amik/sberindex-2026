import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { LineChart, useWidth, type Line, type Pin } from '../components/charts'
import { I } from '../components/icons'
import { Card, Info, Row, Seg, Table, Wait } from '../components/ui'
import { MODEL, MODELS } from '../data/models'
import { ALARMS, CAT_KEYS, META, mo, MOS, monthLong, periodIdx, sample, thr, useShard, type SampleRow, type Shard } from '../data/real'
import { fmt0, fmt1, fmt2, mean, pct, signed } from '../lib/util'
import { alarmsOf, DET_INFO, evaluate, injectShock, KIND_NAME, METHODS, runOnline, type Kind, type Method, type Shock } from '../model/sbiDetect'
import { useApp } from '../store'

export type Mode = 'replay' | 'inject' | 'mass' | 'scenario'
// Стенд открывается на территории, где тревога совпала с новостью о самой МО.
const pickDefault = () => ALARMS.find((a) => a[1] === 0 && a[4])?.[0] ?? MOS[0].id

/** Испытание из «Что если» у аналитика: территория, категория и сам режим стенда. */
export function StandMode({ mode }: { mode: Mode }) {
  const [id, setId] = useState(pickDefault)
  const m = mo(id)!
  const data = useShard(m.rk)
  return (
    <>
      {mode !== 'mass' && <div className="page-tools"><Picker value={id} onChange={setId} /></div>}
      {mode === 'mass' ? <Mass /> : !data ? <Card title={m.name}><Wait label={`Загружаем ${m.region}…`} /></Card>
        : mode === 'replay' ? <Replay id={id} data={data} /> : mode === 'inject' ? <InjectOne key={id} id={id} data={data} /> : <Scenario id={id} data={data} />}
    </>
  )
}

function Picker({ value, onChange }: { value: number; onChange: (id: number) => void }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const cur = mo(value)!
  const found = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (s ? MOS.filter((m) => m.name.toLowerCase().includes(s) || m.region.toLowerCase().includes(s)) : [...MOS].sort((a, b) => b.pop - a.pop)).slice(0, 30)
  }, [q])
  return (
    <div style={{ position: 'relative', width: 340, maxWidth: '100%' }}>
      <input className="field" placeholder={`${cur.name}, ${cur.region}`} value={q} aria-label="Территория"
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} onChange={(e) => { setQ(e.target.value); setOpen(true) }} />
      {open && (
        <div className="menu sc" style={{ left: 0, right: 0, maxHeight: 300 }}>
          {found.map((m) => <button key={m.id} onMouseDown={() => { onChange(m.id); setQ('') }}>{m.name}<span className="small" style={{ marginLeft: 'auto' }}>{m.region}</span></button>)}
        </div>
      )}
    </div>
  )
}

function ModelChips() {
  const { shown, toggleModel } = useApp()
  return <Row>{MODELS.map((m) => <button key={m.key} className="chip" aria-pressed={shown.includes(m.key)} onClick={() => toggleModel(m.key)}><i style={{ background: m.color }} />{m.short}</button>)}</Row>
}

const NOSERIES = <p className="muted">Ряд неполный, модели не проверяли. Выберите другую категорию или территорию.</p>

/* ── Прогон истории: настоящие прогнозы по точкам ── */
function Replay({ id, data }: { id: number; data: Shard }) {
  const { cat, H, shown } = useApp()
  const y = data.series[id]?.[cat]
  const fc = data.fc[id]?.[cat]
  const origins = META.origins
  const [o, setO] = useState(0)
  const [play, setPlay] = useState(false)
  useEffect(() => {
    if (!play) return
    const t = setInterval(() => setO((x) => (x >= origins.length - 1 ? (setPlay(false), x) : x + 1)), 900)
    return () => clearInterval(t)
  }, [play])
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && setPlay(false)
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [])
  if (!y || !fc) return NOSERIES
  const n = META.periods.length
  const t0 = periodIdx(origins[o])
  const lines: Line[] = [
    { key: 'fact', name: 'Факт', color: 'var(--text)', v: y.slice(0, t0 + 1).map((v) => v ?? NaN), width: 2.4 },
    { key: 'next', name: 'Что было дальше', color: 'var(--text-3)', v: y.slice(t0).map((v) => v ?? NaN), from: t0, dash: true, width: 1.4 },
    ...shown.map((k) => ({ key: k, name: MODEL[k].short, color: MODEL[k].color, v: [y[t0] ?? NaN, ...(fc[MODEL[k].real]?.[origins[o]] ?? [])], from: t0 })),
  ]
  // Счёт на горизонте H: только те прогнозы, чей месяц уже наступил к точке прогона.
  const board = MODELS.map((m) => {
    const e: number[] = []
    for (const org of origins.slice(0, o + 1)) {
      const t = periodIdx(org)
      ;(fc[m.real]?.[org] ?? []).slice(0, H).forEach((v, s) => { if (t + s + 1 <= t0) e.push(Math.abs((y[t + s + 1] ?? NaN) - v)) })
    }
    return { m, mae: e.length ? mean(e) : NaN, n: e.length }
  })
  const real = data.alarms.filter((a) => a[0] === id && a[1] === cat && a[2] <= t0).map((a) => a[2])
  const det = data.det[id]?.[cat]
  // Онлайн-счёт: тревога в месяце t поднята по данным до t, поэтому прогон её видит честно.
  const rows = [
    { name: 'Сигналы', color: 'var(--warn)', at: real },
    ...(det ? METHODS.map((m) => ({ name: DET_INFO[m].short, color: DET_INFO[m].color, at: alarmsOf(det.s[m], thr(m)).filter((t) => t <= t0) })) : []),
  ]
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
      <Card title={`Проверка: ${monthLong(t0)}`} sub={mo(id)!.name} extra={<ModelChips />}>
        <LineChart n={n} lines={lines} origin={t0} shade={[t0, n - 1]} />
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 12 }}>
          <button className="btn" onClick={() => { if (o >= origins.length - 1) setO(0); setPlay((p) => !p) }}>{play ? I.pause : I.play}{play ? 'Пауза' : 'Пуск'}</button>
          <button className="icon-btn" aria-label="В начало" onClick={() => { setPlay(false); setO(0) }}>{I.reset}</button>
          <input type="range" min={0} max={origins.length - 1} value={o} onChange={(e) => { setPlay(false); setO(+e.target.value) }} style={{ flex: 1 }} aria-label="Дата прогноза" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '18px 0 6px' }}><h3 style={{ fontSize: 13, color: 'var(--text-2)', fontWeight: 500 }}>Сигналы к этому месяцу</h3><Info tip="«Сигналы» — основной детектор с фильтром группы. Ниже — детекторы с порогами из detect_choice.json." /></div>
        <Timeline n={n} t={t0} rows={rows} />
      </Card>
      <Card title={`Ошибка, ${H} мес. · ${monthLong(t0)}`} sub="Средняя абсолютная ошибка (MAE) по прошедшим месяцам; модель знала только прошлое">
        {board.some((b) => b.n) ? (
          <Table rows={board} sort={['mae', 1]} cols={[
            { key: 'n', title: 'Модель', get: (r) => r.m.short, render: (r) => <span className="nw"><span className="dot" style={{ background: r.m.color }} />{r.m.short}</span> },
            { key: 'mae', title: 'MAE, ₽', num: true, get: (r) => r.mae, render: (r) => fmt0(r.mae) },
            { key: 'k', title: 'Наблюдений', num: true, get: (r) => r.n },
          ]} />
        ) : <p className="muted">Ошибка появится после первого прогнозируемого месяца: {monthLong(periodIdx(origins[0]) + 1)}.</p>}
      </Card>
    </div>
  )
}

function Timeline({ n, t, rows }: { n: number; t: number; rows: { name: string; color: string; at: number[] }[] }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const pad = 70, w = W - pad - 12, rh = 22
  const x = (i: number) => pad + (w * i) / (n - 1)
  return (
    <div ref={ref}>
      <svg className="chart" width={W} height={rows.length * rh + 4}>
        <rect x={x(t)} y={0} width={Math.max(0, W - 12 - x(t))} height={rows.length * rh} fill="var(--hover)" />
        {rows.map((r, k) => (
          <g key={r.name} transform={`translate(0 ${k * rh + rh / 2})`}>
            <text x={pad - 8} y={4} textAnchor="end">{r.name}</text>
            <line className="grid-l" x1={pad} x2={W - 12} />
            {r.at.map((a) => <circle key={a} cx={x(a)} r={5} fill={r.color} data-tip={`${r.name}: ${monthLong(a)}`} />)}
          </g>
        ))}
      </svg>
    </div>
  )
}

/* ── Впрыск шока в настоящий ряд: детекторы — перенос detect.py ── */
function InjectOne({ id, data }: { id: number; data: Shard }) {
  const { cat } = useApp()
  const y = data.series[id]?.[cat]
  const det = data.det[id]?.[cat]
  const [tau, setTau] = useState(15)
  const [kind, setKind] = useState<Kind>('step')
  const [size, setSize] = useState(-20)
  const n = META.periods.length
  const sh: Shock = { tau, kind, size: size / 100 }
  const yy = useMemo(() => (y && det ? injectShock(y as number[], sh) : null), [y, det, tau, kind, size])
  if (!y || !det || !yy) return NOSERIES
  const g = META.groups[det.g]
  const lines: Line[] = [
    { key: 'base', name: 'Без сдвига', color: 'var(--text-3)', v: y as number[], dash: true, width: 1.4 },
    { key: 'shock', name: 'Со сдвигом', color: `var(--c-${CAT_KEYS[cat]})`, v: yy, width: 2.4 },
  ]
  const pins: Pin[] = [{ t: tau, kind: 'shock', color: 'var(--shift)', tip: `<b>Искусственный сдвиг</b><br>${KIND_NAME[kind]}, ${signed(size, fmt0)} %` }]
  const rows = METHODS.map((m) => {
    const a = alarmsOf(runOnline(m, yy, g, det.nb), thr(m), 6)
    const hit = a.find((t) => t >= tau && t <= tau + 2)
    return { m, hit, delay: hit === undefined ? NaN : hit - tau, fa: a.filter((t) => t < tau || t > tau + 2).length, before: alarmsOf(det.s[m], thr(m), 6).length }
  })
  // Как модели переживают шок — не по этому ряду, а по всем: бэктест на панели с шоками (шаг 19).
  const react = MODELS.filter((m) => META.robustness[m.real]).map((m) => ({ m, r: META.robustness[m.real] }))
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
      <Card title={`Искусственный сдвиг: ${mo(id)!.name}`} sub="Сдвиг как в сравнительном тесте: резкая ступень, плавное изменение за три месяца или всплеск на месяц">
        <LineChart n={n} lines={lines} pins={pins} />
        <div className="grid g2" style={{ marginTop: 14, alignItems: 'end' }}>
          <div className="range"><div className="range-top"><span>Месяц</span><b>{monthLong(tau)}</b></div>
            <input type="range" min={6} max={21} value={tau} onChange={(e) => setTau(+e.target.value)} aria-label="Месяц искусственного сдвига" /></div>
          <div className="range"><div className="range-top"><span>Размер</span><b>{signed(size, fmt0)} %</b></div>
            <input type="range" min={-30} max={30} step={10} value={size} onChange={(e) => setSize(+e.target.value || 10)} aria-label="Размер искусственного сдвига" /></div>
        </div>
        <div style={{ marginTop: 12 }}><Seg value={kind} onChange={setKind} items={[['step', 'Ступень'], ['ramp', 'Плавный сдвиг'], ['spike', 'Всплеск']]} /></div>
      </Card>
      <div className="grid g2">
        <Card title="Детекторы" sub="Формулы и пороги из results; проверяем месяц сдвига и два следующих">
          <Table rows={rows} sort={['dl', 1]} cols={[
            { key: 'n', title: 'Детектор', get: (r) => DET_INFO[r.m].short, render: (r) => <span className="nw" data-tip={DET_INFO[r.m].note}><span className="dot" style={{ background: DET_INFO[r.m].color }} />{DET_INFO[r.m].short}</span> },
            { key: 'dl', title: 'Сигнал', num: true, get: (r) => r.delay, render: (r) => (r.hit === undefined ? <span className="tag warn">нет</span> : <span className="tag ok">{r.delay ? `+${r.delay} мес.` : 'сразу'}</span>) },
            { key: 'fa', title: 'Лишних', num: true, tip: 'Сигналы вне периода сдвига; в скобках — число без сдвига', get: (r) => r.fa, render: (r) => `${r.fa} (${r.before})` },
          ]} />
        </Card>
        <Card title="Ошибка после сдвига" sub={`Искусственные сдвиги в 30 % рядов, повторная проверка на истории; ошибка на шаг вперёд за полгода после сдвига к той же дате прогноза без сдвига. Колонка «${KIND_NAME[kind]}» — выбранный вид`}>
          <Table rows={react} sort={['a', 1]} cols={[
            { key: 'n', title: 'Модель', get: (r) => r.m.short, render: (r) => <span className="nw"><span className="dot" style={{ background: r.m.color }} />{r.m.short}</span> },
            { key: 'a', title: 'Ошибка после сдвига, ₽', num: true, tip: 'Ошибка на шаг вперёд за полгода после сдвига, ₽ на жителя', get: (r) => r.r.mae_shock, render: (r) => fmt0(r.r.mae_shock) },
            { key: 'r', title: 'Рост ошибки', num: true, tip: 'К той же дате прогноза без сдвига. Чем выше исходная ошибка, тем меньше её рост в процентах', get: (r) => r.r.rise, render: (r) => `${signed(r.r.rise * 100, fmt0)} %` },
            { key: 'k', title: KIND_NAME[kind], num: true, get: (r) => r.r.by_kind[kind] ?? NaN, render: (r) => `${signed((r.r.by_kind[kind] ?? NaN) * 100, fmt0)} %` },
            { key: 'b', title: 'Через полгода', num: true, tip: 'Рост ошибки на шестой месяц после сдвига', get: (r) => r.r.by_month[5], render: (r) => `${signed(r.r.by_month[5] * 100, fmt0)} %` },
          ]} />
        </Card>
      </div>
    </div>
  )
}

/* ── Массовый прогон: выборка настоящих рядов, шоки как в detect.inject ── */
const KS = [0.6, 0.7, 0.8, 0.9, 1, 1.1, 1.25, 1.4, 1.6, 1.8]
function Mass() {
  const [raw, setRaw] = useState<SampleRow[] | null>(null)
  const [k, setK] = useState(1)
  const kd = useDeferredValue(k)
  useEffect(() => { sample().then(setRaw) }, [])
  // Счёт каждого ряда считается один раз; порог двигается без пересчёта детекторов.
  const set = useMemo(() => {
    if (!raw) return null
    let seed = 2
    const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646
    const kinds: Kind[] = ['step', 'ramp', 'spike']
    return raw.map(([, , y, , g, nb]) => {
      const shock: Shock | null = rnd() < 0.3 ? { tau: 6 + Math.floor(rnd() * 16), kind: kinds[Math.floor(rnd() * 3)], size: [0.1, 0.2, 0.3][Math.floor(rnd() * 3)] * (rnd() < 0.5 ? -1 : 1) } : null
      const yy = shock ? injectShock(y, shock) : y
      return { shock, T: y.length, s: Object.fromEntries(METHODS.map((m) => [m, runOnline(m, yy, META.groups[g], nb)])) as Record<Method, number[]> }
    })
  }, [raw])
  const thrAt = (m: Method, x: number) => (m === 'bocpd' ? Math.min(0.999, 1 - (1 - thr(m)) / x) : thr(m) * x)
  const ev = (m: Method, x: number) => evaluate(set!.map((r) => ({ shock: r.shock, T: r.T, alarms: alarmsOf(r.s[m], thrAt(m, x)) })))
  const rows = useMemo(() => (set ? METHODS.map((m) => ({ m, b: ev(m, kd) })) : []), [kd, set])
  const curves = useMemo(() => (set ? METHODS.map((m) => ({ m, pts: KS.map((x) => ev(m, x)) })) : []), [set])
  if (!set) return <Card title="Проверка на выборке"><Wait label="Загружаем выборку рядов…" /></Card>
  return (
    <Card title="Проверка на выборке" sub={`${fmt0(set.length)} реальных рядов, в ${fmt0(set.filter((x) => x.shock).length)} внесён искусственный сдвиг; детекторы, пороги и оценка как в сравнительном тесте, без фильтра группы`}>
      <div className="range" style={{ maxWidth: 420, marginBottom: 14 }}>
        <div className="range-top"><span>Порог <Info tip="Множитель порогов из detect_choice.json. При повышении порога меньше ложных сигналов и найденных сдвигов." /></span><b>× {fmt2(k)}</b></div>
        <input type="range" min={0.6} max={1.8} step={0.05} value={k} onChange={(e) => setK(+e.target.value)} aria-label="Множитель порога" />
      </div>
      <div style={{ maxWidth: 620 }}><PR curves={curves} cur={rows} /></div>
      <Table rows={rows} sort={['f1', -1]} cols={[
        { key: 'n', title: 'Детектор', get: (r) => DET_INFO[r.m].short, render: (r) => <span className="nw"><span className="dot" style={{ background: DET_INFO[r.m].color }} />{DET_INFO[r.m].name}</span> },
        { key: 'rec', title: 'Найденные сдвиги', num: true, get: (r) => r.b.recall, render: (r) => pct(r.b.recall, 0) },
        { key: 'prec', title: 'Верные сигналы', num: true, get: (r) => r.b.precision, render: (r) => pct(r.b.precision, 0) },
        { key: 'f1', title: 'F1', num: true, get: (r) => r.b.f1, render: (r) => fmt2(r.b.f1) },
        { key: 'fa', title: 'Ложных на 100', num: true, get: (r) => r.b.fa100, render: (r) => fmt1(r.b.fa100) },
        { key: 'dl', title: 'Задержка', num: true, get: (r) => r.b.delay, render: (r) => fmt2(r.b.delay) },
      ]} />
    </Card>
  )
}

function PR({ curves, cur }: { curves: { m: Method; pts: { recall: number; precision: number }[] }[]; cur: { m: Method; b: { recall: number; precision: number } }[] }) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const H = Math.min(300, W * 0.7), p = { l: 44, r: 10, t: 10, b: 34 }
  const x = (v: number) => p.l + (W - p.l - p.r) * v
  const y = (v: number) => p.t + (H - p.t - p.b) * (1 - v)
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  return (
    <div ref={ref} style={{ marginBottom: 12 }}>
      <svg className="chart" width={W} height={H}>
        {ticks.map((t) => <g key={t}><line className="grid-l" x1={p.l} x2={W - p.r} y1={y(t)} y2={y(t)} /><text x={p.l - 6} y={y(t) + 4} textAnchor="end">{pct(t, 0)}</text><text x={x(t)} y={H - 16} textAnchor="middle">{pct(t, 0)}</text></g>)}
        <text x={(W + p.l) / 2} y={H - 2} textAnchor="middle">найденные сдвиги</text>
        <text x={12} y={(H - p.b) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(H - p.b) / 2})`}>верные сигналы</text>
        {curves.map(({ m, pts }) => <path key={m} d={pts.filter((q) => Number.isFinite(q.precision) && Number.isFinite(q.recall)).map((q, i) => `${i ? 'L' : 'M'}${x(q.recall)},${y(q.precision)}`).join('')} fill="none" stroke={DET_INFO[m].color} strokeWidth={2} opacity={0.85} />)}
        {cur.map(({ m, b }) => Number.isFinite(b.precision) && <circle key={m} cx={x(b.recall)} cy={y(b.precision)} r={6} fill={DET_INFO[m].color} stroke="var(--surface)" strokeWidth={2} data-tip={`${DET_INFO[m].name}: найденные сдвиги ${pct(b.recall, 0)}, верные сигналы ${pct(b.precision, 0)}`} />)}
      </svg>
    </div>
  )
}

/* ── Сценарии: настоящий прогноз на 2025 год и оценённые чувствительности ── */
interface Factors { rate: number; heat: number; off: number; offAt: number; flood: boolean; floodAt: number }
const sig = (c: number, se?: number) => se === undefined || Math.abs(c) > 1.96 * se

function Scenario({ id, data }: { id: number; data: Shard }) {
  const { cat, shown } = useApp()
  const y = data.series[id]?.[cat]
  const fw = data.fwd?.[id]?.[cat]
  const [f, setF] = useState<Factors>({ rate: 2, heat: 0, off: 0, offAt: 5, flood: true, floodAt: 4 })
  const fd = useDeferredValue(f)
  const n = META.periods.length
  if (!y || !fw) return NOSERIES
  const S = META.sensitivity[META.cats[cat]]
  const t = n - 1
  // Сценарий по моделям — на 2025 год: у Prophet и наивной модели прогноз только на год.
  const months = META.fwdTargets.slice(0, 12).map((p) => +p.slice(5, 7))
  // Эффект по месяцам, % к прогнозу, и его дисперсия — из стандартных ошибок оценок.
  const eff = months.map((mm, i) => {
    const h = i + 1
    const ramp = Math.min(1, Math.max(0, (h - (S.rate.lag ?? 6)) / 12))
    const parts: [number, number][] = [
      [S.rate.coef * fd.rate * ramp, (S.rate.se ?? 0) * fd.rate * ramp],
      [mm >= 6 && mm <= 8 ? S.heat.coef * fd.heat : 0, mm >= 6 && mm <= 8 ? (S.heat.se ?? 0) * fd.heat : 0],
      [h === fd.offAt ? -S.workday.coef * fd.off : 0, h === fd.offAt ? (S.workday.se ?? 0) * fd.off : 0],
      [fd.flood && h >= fd.floodAt && h <= fd.floodAt + 1 ? S.flood.coef * (h === fd.floodAt ? 1 : 0.5) : 0, 0],
    ]
    return { e: parts.reduce((a, p) => a + p[0], 0), sd: Math.sqrt(parts.reduce((a, p) => a + p[1] ** 2, 0)) }
  })
  const avail = MODELS.filter((m) => fw[m.real])
  const rows = avail.map((m) => {
    const base = fw[m.real].slice(0, 12)
    const sc = base.map((v, i) => v * (1 + eff[i].e / 100))
    return { m, base, sc, total: sc.reduce((a, v) => a + v, 0), d: sc.reduce((a, v) => a + v, 0) / base.reduce((a, v) => a + v, 0) - 1 }
  })
  const ens = rows.find((r) => r.m.key === 'ensemble')
  const yy = y as number[]
  const lines: Line[] = [
    { key: 'fact', name: 'Факт', color: 'var(--text)', v: yy, width: 2.4 },
    ...rows.filter((r) => shown.includes(r.m.key)).map((r) => ({ key: r.m.key, name: r.m.short, color: r.m.color, v: [yy[t], ...r.sc], from: t })),
    ...(ens ? [{ key: 'base', name: 'Ансамбль без сценария', color: 'var(--text-3)', v: [yy[t], ...ens.base], from: t, dash: true, width: 1.4 }] : []),
  ]
  const band = ens ? { from: t + 1, color: 'var(--m-ensemble)', lo: ens.sc.map((v, i) => v * (1 - (1.96 * eff[i].sd) / 100)), hi: ens.sc.map((v, i) => v * (1 + (1.96 * eff[i].sd) / 100)) } : undefined
  const upd = (p: Partial<Factors>) => setF((x) => ({ ...x, ...p }))
  const fx: { k: string; name: string; unit: string; coef: number; se?: number; note: string }[] = [
    { k: 'rate', name: 'Ключевая ставка', unit: 'п. п. роста за год на 1 п. п.', coef: S.rate.coef, se: S.rate.se, note: `Ряд РФ «${S.rate.series}», реальный прирост, задержка ${S.rate.lag} мес., ${S.rate.n} мес.` },
    { k: 'heat', name: 'Жара летом', unit: '% на 1 °C', coef: S.heat.coef, se: S.heat.se, note: 'Муниципалитеты: связь относительного уровня трат с температурой выше нормы, июнь—август' },
    { k: 'workday', name: 'Рабочий день', unit: '% на день', coef: S.workday.coef, se: S.workday.se, note: `Ряд РФ «${S.workday.series}», связь месячного прироста с числом рабочих дней` },
    { k: 'flood', name: 'Паводок', unit: '%', coef: S.flood.coef, note: 'События 2024 года: пострадавшие субъекты и остальные' },
  ]
  return (
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
      <Card title={`Сценарий на 2025 год: ${mo(id)!.name}`} sub="Прогнозы из декабря 2024 года с учётом сценария; интервал 95 % для его эффекта" extra={<ModelChips />}>
        <LineChart n={n + 12} lines={lines} band={band} origin={t} shade={[t, n + 11]} pins={fd.flood ? [{ t: t + fd.floodAt, kind: 'news', color: 'var(--blue)', tip: `<b>Паводок</b><br>${monthLong(t + fd.floodAt)}` }] : []} />
        <div className="grid g2" style={{ marginTop: 14, gap: 14 }}>
          <Slider label="Ключевая ставка" v={f.rate} min={-3} max={3} step={0.25} unit=" п. п." onChange={(rate) => upd({ rate })} />
          <Slider label="Жара летом" v={f.heat} min={-4} max={4} step={0.5} unit=" °C" onChange={(heat) => upd({ heat })} />
          <Slider label="Дополнительные выходные" v={f.off} min={0} max={4} step={1} unit=" дн." onChange={(off) => upd({ off })} />
          <Slider label="Месяц выходных" v={f.offAt} min={1} max={12} step={1} unit="" onChange={(offAt) => upd({ offAt })} />
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
          <Seg value={f.flood ? 'on' : 'off'} onChange={(v) => upd({ flood: v === 'on' })} items={[['off', 'Без паводка'], ['on', 'Паводок']]} />
          {f.flood && <div style={{ flex: 1, minWidth: 220 }}><Slider label="Месяц паводка" v={f.floodAt} min={1} max={11} step={1} unit="" onChange={(floodAt) => upd({ floodAt })} /></div>}
        </div>
      </Card>
      <div className="grid g2">
        <Card title="Связи факторов" sub={`${META.cats[cat]}: оценки по данным`}>
          <Table rows={fx} sort={['n', 1]} cols={[
            { key: 'n', title: 'Фактор', get: (r) => r.name, render: (r) => <span className="nw" data-tip={r.note}>{r.name}</span> },
            { key: 'c', title: 'Эффект', num: true, get: (r) => r.coef, render: (r) => <span data-tip={r.unit}>{signed(r.coef, fmt2)}{r.se !== undefined ? ` ± ${fmt2(r.se)}` : ''}</span> },
            { key: 's', title: 'Связь подтверждена', get: (r) => (sig(r.coef, r.se) ? 1 : 0), render: (r) => (r.se === undefined ? <span className="tag">случай</span> : sig(r.coef, r.se) ? <span className="tag ok">да</span> : <span className="tag warn" data-tip="Интервал 95-процентный включает ноль: связь не подтверждена">нет</span>) },
          ]} />
        </Card>
        <Card title="Итог за 2025 год" sub="Траты на жителя за 12 месяцев со сценарием">
          <Table rows={rows} sort={['t', 1]} cols={[
            { key: 'n', title: 'Модель', get: (r) => r.m.short, render: (r) => <span className="nw"><span className="dot" style={{ background: r.m.color }} />{r.m.short}</span> },
            { key: 't', title: 'Сумма, ₽', num: true, get: (r) => r.total, render: (r) => fmt0(r.total) },
            { key: 'd', title: 'Сценарий', num: true, get: (r) => r.d, render: (r) => `${signed(r.d * 100, fmt1)} %` },
          ]} />
        </Card>
      </div>
    </div>
  )
}

function Slider({ label, v, min, max, step, unit, onChange }: { label: string; v: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void }) {
  const fmt = Number.isInteger(v) ? fmt0 : step < 0.5 ? fmt2 : fmt1
  return (
    <div className="range">
      <div className="range-top"><span>{label}</span><b>{(min < 0 ? (x: number) => signed(x, fmt) : fmt)(v)}{unit}</b></div>
      <input type="range" min={min} max={max} step={step} value={v} onChange={(e) => onChange(+e.target.value)} aria-label={label} />
    </div>
  )
}
