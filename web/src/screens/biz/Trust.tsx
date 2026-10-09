import { useEffect, useState } from 'react'
import { LineChart } from '../../components/charts'
import { Card, CatChips, Info, Table } from '../../components/ui'
import { HORIZONS } from '../../data/calendar'
import { BIZ_CAT, regionStats, reliability } from '../../data/biz'
import { META, MOS } from '../../data/real'
import { fmt0, fmt1 } from '../../lib/util'
import { useApp } from '../../store'
import { metric } from '../Overview'

export const TRUST_NAV: [string, string][] = [['tr-h', 'По срокам прогноза'], ['tr-25', 'Проверка на данных 2025 года'], ['tr-two', 'Два ряда по России'], ['tr-ev', 'События 2025—2026'], ['tr-blind', 'Слепые зоны'], ['tr-weak', 'Где ошибка выше']]

/** Сверка с фактом 2025—2026 по двум рядам России и реальные события (public/data/check2025.json, scripts/33—35). */
export interface Check2025 {
  byCat: Record<string, { targets: string[]; fc: number[]; weekly: number[]; monthly: (number | null)[] }>
  models: { model: string; mae25w: number | null; mae26w: number | null; mae25m: number | null }[]
  rules: { cat: string; rule: string; year: number; maeM: number; maeW: number; biasM: number }[]
  events: { id: string; type: string; start: string; sign: number | null; confidence: string; note: string; source: string; first: string | null; delay: number | null; caught: boolean; series: string | null }[]
  alarms: { series: number; months: number; cells: number; share: number; byMonth: Record<string, number> }
}
let CHECK: Promise<Check2025 | null> | null = null
export const check2025 = () => (CHECK ??= fetch('/data/check2025.json').then((r) => (r.ok ? r.json() : null)).catch(() => null))
const MONTH_RU = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const ym = (p: string) => `${MONTH_RU[+p.slice(5, 7) - 1]} ${p.slice(2, 4)}`
const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1)
const MODEL_RU: Record<string, string> = { 'ансамбль': 'Ансамбль — наш прогноз', 'панельная база': 'Панельная модель', 'сезонная наивная с ростом': 'Прошлогодние траты с поправкой на рост', 'ансамбль + рост из недельного ряда (все шаги)': 'Ансамбль, темп из недельного ряда', 'ансамбль + рост из недельного ряда (шаги 4+)': 'Ансамбль, темп из недельного ряда с 4-го шага' }


/** Насколько верить прогнозу: точность простыми словами, проверка на 2025 годе, слепые зоны. */
export function TrustBody() {
  const { cat, role, set, go } = useApp()
  const [ck, setCk] = useState(0)
  const [chk25, setChk25] = useState<Check2025 | null>(null)
  useEffect(() => { check2025().then(setChk25) }, [])
  const target = useApp((s) => s.target)
  const { list } = regionStats(cat, role, undefined, target)
  const blind = list.filter((r) => r.rec === 'blind')
  const noData = MOS.filter((m) => m.sum[cat][3] === null).length
  const weak = [...list].filter((r) => r.rec !== 'blind' && Number.isFinite(r.wape)).sort((a, b) => b.wape - a.wape).slice(0, 8)
  const chk = META.fwdCheck.filter((r) => r.cat === META.cats[ck])
  const gap = (c: string) => { const r = META.fwdCheck.filter((x) => x.cat === c && x.nat_yoy !== null); return r.reduce((a, x) => a + Math.abs(x.fc_yoy - x.nat_yoy!), 0) / r.length }

  return (
    <>
        <Card id="tr-h" title="Ошибка по срокам прогноза" sub="Средняя ошибка прогноза в зависимости от того, на сколько месяцев вперёд он сделан">
          <div className="grid g4">
            {HORIZONS.map((h) => {
              const w = metric('ensemble', h).WAPE / 100
              const r = reliability(w)
              return <div key={h} className="stat"><small>{h === 1 ? 'На месяц' : `На ${h} мес.`}</small><b>{fmt1(w * 100)} %</b><span style={{ color: r.tone, fontSize: 13 }}>надёжность {r.word}</span></div>
            })}
          </div>
        </Card>
        <Card id="tr-25" title="Проверка на данных 2025 года" sub="Данных по муниципалитетам за 2025 год ещё нет; сравниваем прогноз с общероссийским рядом СберИндекса — годовой рост, %" extra={<CatChips value={ck} onChange={setCk} />}>
          <LineChart n={12} x0={24} height={200} yFmt={fmt0} lines={[
            { key: 'f', name: 'Наш прогноз', color: 'var(--m-ensemble)', v: chk.map((r) => r.fc_yoy) },
            { key: 'n', name: 'Факт по стране', color: 'var(--text-2)', v: chk.map((r) => r.nat_yoy ?? NaN), dash: true },
          ]} />
          <Table rows={META.cats.map((c, i) => ({ c, i }))} sort={['g', 1]} cols={[
            { key: 'n', title: 'Категория', get: (r) => BIZ_CAT[r.i] },
            { key: 'g', title: 'Расхождение с фактом', num: true, get: (r) => gap(r.c), render: (r) => `${fmt1(gap(r.c))} п. п.` },
            { key: 'w', title: 'Вывод', get: (r) => gap(r.c), render: (r) => (gap(r.c) < 5 ? <span className="tag ok">совпадает</span> : gap(r.c) < 8 ? <span className="tag">близко</span> : <span className="tag warn">расходится</span>) },
          ]} />
        </Card>
        <Card id="tr-two" title="Два ряда по России расходятся" sub="Рост к тому же месяцу 2024 года, %: прогноз по муниципалитетам объединяем с учётом населения и сравниваем с месячным и недельным рядами СберИндекса; 2026 год — за два года" extra={<CatChips value={ck} onChange={setCk} />}>
          {chk25 ? (() => {
            const d = chk25.byCat[META.cats[ck]]
            if (!d) return <p className="small">Для этой категории нет данных для сравнения.</p>
            return (
              <>
                <LineChart n={d.targets.length} x0={24} height={200} yFmt={fmt0} lines={[
                  { key: 'f', name: 'Наш прогноз', color: 'var(--m-ensemble)', v: d.fc },
                  { key: 'm', name: 'Месячный ряд', color: 'var(--text)', v: d.monthly.map((x) => x ?? NaN), dash: true },
                  { key: 'w', name: 'Недельный ряд', color: 'var(--text-3)', v: d.weekly, dash: true },
                ]} />
                <p className="small" style={{ marginTop: 8 }}>С июля 2025 года месячный ряд показывает рост 12—15 %, недельный — 6—9 %; в 2024 году они совпадали. В месячном ряду общепита с января 2025 года виден скачок из-за изменения методики. Нужно уточнить у организаторов, какому ряду соответствует муниципальный набор. <Info tip="Модели сохраняют темп конца 2024 года и не учитывают замедление: ошибка общей динамики группы растёт со сроком прогноза." /></p>
                <Table rows={chk25.models} sort={['a', 1]} cols={[
                  { key: 'n', title: 'Модель', get: (r) => r.model, render: (r) => MODEL_RU[r.model] ?? r.model },
                  { key: 'a', title: '2025, к месячному', num: true, get: (r) => r.mae25m ?? 99, render: (r) => (r.mae25m === null ? '—' : `${fmt1(r.mae25m)} п. п.`) },
                  { key: 'b', title: '2025, к недельному', num: true, get: (r) => r.mae25w ?? 99, render: (r) => (r.mae25w === null ? '—' : `${fmt1(r.mae25w)} п. п.`) },
                  { key: 'c', title: '2026, к недельному', num: true, get: (r) => r.mae26w ?? 99, render: (r) => (r.mae26w === null ? '—' : `${fmt1(r.mae26w)} п. п.`) },
                ]} />
                <p className="small" style={{ marginTop: 8 }}>Сравнили три заранее заданных правила прогноза общей динамики группы с теми же фактическими данными, без настройки по ним: «перенос темпа» ошибается на {fmt1(chk25.rules.find((r) => r.cat === 'Всего' && r.rule === 'перенос темпа' && r.year === 2025)?.maeM ?? NaN)} п. п. за 2025 год, макромодель со ставкой — на {fmt1(chk25.rules.find((r) => r.cat === 'Всего' && r.rule === 'макромодель' && r.year === 2025)?.maeM ?? NaN)} п. п. Эта модель предсказала ускорение. Прежнее правило прогноза общей динамики группы сохранили.</p>
              </>
            )
          })() : <p className="small">Загружаем сверку…</p>}
        </Card>
        <Card id="tr-ev" title="Какие события 2025—2026 нашёл детектор" sub={chk25 ? `Сигналы: ${fmt1(chk25.alarms.share)} на 100 рядов за месяц; проверка на ${chk25.alarms.series} рядах России и отраслей; событие найдено, если сигнал пришёл не позже чем через два месяца` : 'Реестр событий с источниками'}>
          {chk25 ? (
            <>
              <Table rows={chk25.events} sort={['s', 1]} cols={[
                { key: 'n', title: 'Событие', get: (r) => r.id, render: (r) => <span data-tip={`${r.note}${r.source ? ` · ${r.source}` : ''}`}>{cap(r.id)}</span> },
                { key: 's', title: 'Начало', get: (r) => r.start, render: (r) => ym(r.start) },
                { key: 'f', title: 'Первый сигнал', get: (r) => r.first ?? 'я', render: (r) => (r.first ? <span data-tip={r.series ?? ''}>{ym(r.first)}</span> : '—') },
                { key: 'd', title: 'Задержка', num: true, get: (r) => r.delay ?? 99, render: (r) => (r.delay === null ? '—' : `${r.delay} мес.`) },
                { key: 'c', title: 'Итог', get: (r) => (r.caught ? 0 : 1), render: (r) => (r.caught ? <span className="tag ok">найдено</span> : r.type.startsWith('measurement') ? <span className="tag" data-tip="Региональный эффект не виден в общем ряду России">по стране не видно</span> : <span className="tag warn">пропущено</span>) },
              ]} />
              <p className="small" style={{ marginTop: 8 }}>Детектор нашёл {chk25.events.filter((e) => e.caught).length} из {chk25.events.length} событий: оба этапа изменения НДС, укрепление рубля, начало снижения ставки, утильсбор и скачок из-за методики. Отключения мобильного интернета и топливный кризис не видны в общероссийских рядах. Эти региональные эффекты сервис показывает на карте.</p>
            </>
          ) : <p className="small">Загружаем события…</p>}
        </Card>
        <div className="grid g2">
          <Card id="tr-blind" title="Слепые зоны" sub={`Регионы, где полные данные есть меньше чем у 60 % жителей; всего муниципалитетов без полного ряда — ${noData}`}>
            <Table rows={blind} sort={['c', 1]} onRow={(r) => { set({ selRk: r.rk }); go('reg') }} cols={[
              { key: 'n', title: 'Регион', get: (r) => r.name },
              { key: 'c', title: 'Охват данными', num: true, get: (r) => r.coverage, render: (r) => `${fmt0(r.coverage * 100)} % жителей` },
            ]} />
            {!blind.length && <p className="small">Слепых зон нет</p>}
          </Card>
          <Card id="tr-weak" title="Где ошибка прогноза выше" sub="Регионы с наибольшей ошибкой прогноза на три месяца">
            <Table rows={weak} sort={['w', -1]} onRow={(r) => { set({ selRk: r.rk }); go('reg') }} cols={[
              { key: 'n', title: 'Регион', get: (r) => r.name },
              { key: 'w', title: 'Ошибка', num: true, get: (r) => r.wape, render: (r) => `${fmt1(r.wape * 100)} %` },
              { key: 'r', title: 'Надёжность', get: (r) => r.wape, render: (r) => <span style={{ color: reliability(r.wape).tone }}>{reliability(r.wape).word}</span> },
            ]} />
          </Card>
        </div>
        <p className="small">Подробности о моделях, метриках и детекторах — на соседних страницах раздела «О проекте».</p>
    </>
  )
}
