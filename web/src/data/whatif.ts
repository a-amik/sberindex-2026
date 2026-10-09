// «Что будет, если…»: сценарий ложится поверх прогноза по чувствительностям, оценённым
// на данных (scripts/18_sensitivity.py — ставка, погода, выходные, паводок; scripts/38 —
// доходы по отраслям; scripts/40 — нефть → ФОТ добычи). Один движок на бизнес-режим и стенд.
// Ручки двух уровней: первичные (один драйвер) и составные пресеты из первичных.
// Звено без оценки на данных считается серым: его эффект показывается с ошибкой,
// у которой ноль внутри 95 % интервала, — число есть, вывода нет (ZADANIE 6.8).
import { INDUSTRY, META } from './real'

export interface Factors {
  rate: number; heat: number; off: number; offAt: number; flood: boolean; floodAt: number
  /** Рост ФОТ отрасли к среднему по экономике, п. п. за год: обработка, добыча, сельское хозяйство, бюджетный сектор. */
  fotManuf: number; fotMining: number; fotAgri: number; fotBudget: number
  /** Цена нефти в рублях, % к базовому году; действует на ФОТ добычи с лагом полгода. */
  oil: number
  /** НДС, п. п.; курс, % ослабления рубля; отключения мобильного интернета, дней в месяц. */
  vat: number; fx: number; netOff: number
}
export const NONE: Factors = { rate: 0, heat: 0, off: 0, offAt: 5, flood: false, floodAt: 4, fotManuf: 0, fotMining: 0, fotAgri: 0, fotBudget: 0, oil: 0, vat: 0, fx: 0, netOff: 0 }

/** Доли занятости территории: обработка, добыча, сельское хозяйство, бюджетный сектор (public/data/industry.json). */
export type Geo = [number, number, number, number]
export const geoCountry = (): Geo => (INDUSTRY?.country as Geo) ?? [0.16, 0.02, 0.03, 0.4]
export const geoRegion = (rk: number): Geo => (INDUSTRY?.regions[rk] as Geo) ?? geoCountry()
export const geoMo = (id: number): Geo => (INDUSTRY?.mo[id] as Geo) ?? geoCountry()

/** Коэффициенты звеньев, не зависящие от категории. Источник и статус — у каждого. */
export const LINKS = {
  /** п. п. годового роста расходов на 1 п. п. ожидаемого роста доходов (Σ доля × относительный рост ФОТ), внутри субъекта и типа; scripts/38 --within. */
  income: { coef: 0.29, se: 0.042, n: 2016, note: 'муниципалитеты за 2024 год, сравнение внутри субъекта и типа' },
  /** то же, только обрабатывающие производства — единственная отрасль с собственной значимой оценкой. */
  manuf: { coef: 0.59, se: 0.095, note: 'муниципалитеты за 2024 год; фонд оплаты труда обработки +5,7 % к среднему' },
  /** Δ12 log ФОТ добычи на Δ12 log рублёвой цены Brent, лаг 6 мес.; scripts/40. */
  oilToMining: { coef: 0.079, se: 0.024, lag: 6, note: 'ряд РФ 2018—2026, ошибки с учётом связи наблюдений (Ньюи—Уэст); без ковида и 2022 года t = 1,7' },
  /** Экспертные, серые: номинальный эффект НДС, курса и отключений интернета. */
  vat: { coef: 0.5, note: 'экспертная оценка: половина ставки переходит в цену при падении объёма; по 2023—2026 годам перенос индекса потребительских цен не оценён' },
  fx: { coef: 0.2, note: 'экспертная оценка по доле импорта маркетплейсов и транспорта; на данных не проверена' },
  netOff: { coef: -0.3, note: 'экспертная оценка: % безналичного оборота на день отключения; в рядах России за 2025 год региональный эффект не виден' },
} as const

export interface Preset { key: string; name: string; text: string; f: Factors; world?: boolean }
export const PRESETS: Preset[] = [
  { key: 'rate', name: 'Ставка +2 п. п.', text: 'Кредиты дороже, сбережения выгоднее', f: { ...NONE, rate: 2 } },
  { key: 'cut', name: 'Ставка −2 п. п.', text: 'Кредиты дешевле', f: { ...NONE, rate: -2 } },
  { key: 'heat', name: 'Жаркое лето, +3 °C', text: 'Июнь—август теплее обычного', f: { ...NONE, heat: 3 } },
  { key: 'cold', name: 'Холодное лето, −3 °C', text: 'Июнь—август холоднее обычного', f: { ...NONE, heat: -3 } },
  { key: 'may', name: 'Длинные майские, +3 дня', text: 'Три дополнительных выходных в мае', f: { ...NONE, off: 3, offAt: 5 } },
  { key: 'flood', name: 'Паводок весной', text: 'Апрель, как при паводках 2024 года; один регион', f: { ...NONE, flood: true, floodAt: 4 } },
]
/** Составные сценарии: мировой сюжет, собранный из первичных ручек с записанными долями. Доли экспертные и видны в ручках. */
export const WORLD_PRESETS: Preset[] = [
  { key: 'w-recession', name: 'Мировая рецессия', text: 'Нефть в рублях −30 %; рост фонда оплаты труда обработки и добычи −3 п. п. каждой, ставка −1 п. п.', world: true, f: { ...NONE, oil: -30, fotMining: -3, fotManuf: -3, rate: -1 } },
  { key: 'w-china', name: 'Китай замедляется', text: 'Цены угля и металлов падают: добыча −2 п. п., обработка −1 п. п.; нефть −10 %', world: true, f: { ...NONE, oil: -10, fotMining: -2, fotManuf: -1 } },
  { key: 'w-sanctions', name: 'Снятие части санкций', text: 'Рубль укрепляется на 10 %, импорт дешевеет; оборонный рост обработки ниже на 2 п. п.', world: true, f: { ...NONE, fx: -10, fotManuf: -2 } },
  { key: 'w-escalation', name: 'Эскалация', text: 'Оборонная обработка +3 п. п., бюджетный сектор +2 п. п., ставка +1 п. п., рубль −10 %', world: true, f: { ...NONE, fotManuf: 3, fotBudget: 2, rate: 1, fx: 10 } },
  { key: 'w-harvest', name: 'Неурожай', text: 'Фонд оплаты труда сельского хозяйства −4 п. п.; пошлина ограничивает связь мировой цены пшеницы с зарплатами', world: true, f: { ...NONE, fotAgri: -4 } },
  { key: 'w-tight', name: 'Жёсткая политика дольше', text: 'Ставка +2 п. п. к базовому сценарию на весь год', world: true, f: { ...NONE, rate: 2 } },
  { key: 'w-tax', name: 'Налоговый манёвр', text: 'НДС +2 п. п.: цены растут, объём покупок падает', world: true, f: { ...NONE, vat: 2 } },
  { key: 'w-offline', name: 'Интернет отключают', text: 'Мобильный интернет недоступен 5 дней в месяц: безналичный оборот падает, спрос может остаться прежним', world: true, f: { ...NONE, netOff: 5 } },
]
export const ALL_PRESETS = [...PRESETS, ...WORLD_PRESETS]

export const sig = (c: number, se?: number) => se === undefined || Math.abs(c) > 1.96 * se
/** Серое звено: эффект есть, но ошибка такова, что ноль внутри 95 % интервала. */
const grey = (e: number): [number, number] => [e, Math.abs(e) / 1.96 + 1e-9]

/** Чем сценарий бьёт по категории через цены и курс: индекс категории → доля. Маркетплейсы и транспорт — импорт. */
const FX_SHARE = [0.1, 0.05, 0.1, 0.05, 0.3, 0.6]
const VAT_SHARE = [1, 1, 0.8, 1, 1, 1]

/** Эффект по месяцам года прогноза (0 — 2025, 1 — 2026, 2 — 2027), % к прогнозу, и его ошибка. geo — доли отраслей территории. */
export function monthlyEffect(cat: number, f: Factors, year = 0, geo: Geo = geoCountry()) {
  const S = META.sensitivity[META.cats[cat]]
  const months = META.fwdTargets.slice(year * 12, year * 12 + 12).map((p) => +p.slice(5, 7))
  const [sManuf, sMining, sAgri, sBudget] = geo
  // Доходы по отраслям: годовой эффект, ровно по месяцам года. Обработка — своим наклоном, остальные — общим и серыми.
  const manuf: [number, number] = [LINKS.manuf.coef * sManuf * f.fotManuf, LINKS.manuf.se * sManuf * Math.abs(f.fotManuf)]
  const mining = grey(LINKS.income.coef * sMining * f.fotMining)
  const agri = grey(LINKS.income.coef * sAgri * f.fotAgri)
  const budget = grey(LINKS.income.coef * sBudget * f.fotBudget)
  const vat = grey(LINKS.vat.coef * VAT_SHARE[cat] * f.vat)
  const fx = grey(LINKS.fx.coef * FX_SHARE[cat] * f.fx)
  const net = grey(LINKS.netOff.coef * f.netOff)
  return months.map((mm, i) => {
    // Ставка копится от начала прогноза; праздники и паводок — в своём месяце выбранного года.
    const h = year * 12 + i + 1, hy = i + 1
    const ramp = Math.min(1, Math.max(0, (h - (S.rate.lag ?? 6)) / 12))
    // Нефть: через полгода поднимает рост ФОТ добычи, дальше — как ручка добычи, второе звено серое.
    const oilRamp = Math.min(1, Math.max(0, (h - LINKS.oilToMining.lag) / 6))
    const oil = grey(LINKS.income.coef * sMining * LINKS.oilToMining.coef * f.oil * oilRamp)
    const parts: [number, number][] = [
      [S.rate.coef * f.rate * ramp, (S.rate.se ?? 0) * f.rate * ramp],
      [mm >= 6 && mm <= 8 ? S.heat.coef * f.heat : 0, mm >= 6 && mm <= 8 ? (S.heat.se ?? 0) * f.heat : 0],
      [hy === f.offAt ? -S.workday.coef * f.off : 0, hy === f.offAt ? (S.workday.se ?? 0) * f.off : 0],
      [f.flood && hy >= f.floodAt && hy <= f.floodAt + 1 ? S.flood.coef * (hy === f.floodAt ? 1 : 0.5) : 0, 0],
      manuf, mining, agri, budget, oil, vat, fx, net,
    ]
    return { e: parts.reduce((a, p) => a + p[0], 0), sd: Math.sqrt(parts.reduce((a, p) => a + p[1] ** 2, 0)) }
  })
}

/** Годовой эффект: среднее помесячных, % к прогнозу года, с ошибкой.
 *  Коэффициент каждого звена один на все месяцы года, поэтому ошибки месяцев
 *  складываются как полностью зависимые: sd года — среднее sd месяцев, а не
 *  корень из суммы квадратов. До 07.10.2026 годовой интервал был в √12 раз уже,
 *  и серое звено с нулём внутри месячного интервала за год выглядело доказанным. */
export function yearEffect(cat: number, f: Factors, year = 0, geo: Geo = geoCountry()) {
  const m = monthlyEffect(cat, f, year, geo)
  return { e: m.reduce((a, x) => a + x.e, 0) / 12, sd: m.reduce((a, x) => a + x.sd, 0) / 12 }
}

export interface Evidence { name: string; proven: boolean; note: string; grey?: boolean; measure?: boolean }
/** Какие факторы сценария доказаны данными, какие нет, а какие — экспертные (серые). */
export function evidence(cat: number, f: Factors): Evidence[] {
  const S = META.sensitivity[META.cats[cat]]
  const out: Evidence[] = []
  if (f.rate) out.push({ name: 'Ставка', proven: sig(S.rate.coef, S.rate.se), note: 'по ряду РФ за 2018—2026 годы' })
  if (f.heat) out.push({ name: 'Погода', proven: sig(S.heat.coef, S.heat.se), note: 'по муниципалитетам за 2023—2024 годы' })
  if (f.off) out.push({ name: 'Выходные', proven: sig(S.workday.coef, S.workday.se), note: 'по ряду РФ за 2022—2025 годы' })
  if (f.flood) out.push({ name: 'Паводок', proven: true, note: 'по паводкам 2024 года' })
  if (f.fotManuf) out.push({ name: 'Обработка', proven: true, note: LINKS.manuf.note })
  if (f.fotMining) out.push({ name: 'Добыча', proven: false, grey: true, note: 'по общему коэффициенту доходов; у добычи в 2024 году нет разброса, отдельной оценки нет' })
  if (f.fotAgri) out.push({ name: 'Сельское хозяйство', proven: false, grey: true, note: 'по общему коэффициенту; внутри субъекта связь не подтверждена' })
  if (f.fotBudget) out.push({ name: 'Бюджетный сектор', proven: false, grey: true, note: 'по общему коэффициенту доходов; отдельной оценки нет' })
  if (f.oil) out.push({ name: 'Нефть', proven: false, grey: true, note: `связь нефти с фондом оплаты труда добычи оценена (${LINKS.oilToMining.note}); связь этого фонда с тратами не подтверждена` })
  if (f.vat) out.push({ name: 'НДС', proven: false, grey: true, note: LINKS.vat.note })
  if (f.fx) out.push({ name: 'Курс', proven: false, grey: true, note: LINKS.fx.note })
  if (f.netOff) out.push({ name: 'Интернет', proven: false, grey: true, measure: true, note: LINKS.netOff.note })
  return out
}

/** Все ли факторы сценария не доказаны данными: тогда число — оценка, а не вывод. */
export const unproven = (cat: number, f: Factors) => { const e = evidence(cat, f); return e.length > 0 && e.every((x) => !x.proven) }
/** Сценарий меняет измерение (безналичный канал), а не спрос. */
export const measuresOnly = (cat: number, f: Factors) => { const e = evidence(cat, f); return e.length > 0 && e.every((x) => x.measure) }

/** Ключ сценария в store — набор ключей пресетов через «+», «base» — без сценария, «custom» — ручки. */
export const scnKeys = (key: string): string[] => (key === 'base' || key === 'custom' || !key ? [] : key.split('+'))
/** Сочетание пресетов: числовые факторы складываются, паводок — «или», месяцы берутся у того, кто их задал. */
export function combine(keys: string[]): Factors {
  const out: Factors = { ...NONE }
  for (const k of keys) {
    const p = ALL_PRESETS.find((x) => x.key === k)
    if (!p) continue
    for (const n of ['rate', 'heat', 'off', 'fotManuf', 'fotMining', 'fotAgri', 'fotBudget', 'oil', 'vat', 'fx', 'netOff'] as const) out[n] += p.f[n]
    if (p.f.off) out.offAt = p.f.offAt
    if (p.f.flood) { out.flood = true; out.floodAt = p.f.floodAt }
  }
  return out
}
/** Имя сценария для подписей: пресеты через « + », своё сочетание — так и зовётся. */
export const scnLabel = (key: string) => (key === 'custom' ? 'Своё сочетание' : scnKeys(key).map((k) => ALL_PRESETS.find((p) => p.key === k)?.name ?? k).join(' + '))
