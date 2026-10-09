// Бизнес-режим: те же данные, сведённые к ответам на вопросы заказчика —
// где растёт спрос, где риск, куда выходить и в каком формате, насколько верить.
import { FIRST_FC, META, MOS, ser60, type Mo } from './real'

export type Role = 'retail' | 'bank' | 'gov' | 'any'
export type Rec = 'own' | 'partner' | 'watch' | 'blind'

/** Названия категорий для заказчика: как их называют в бизнесе, а не в выгрузке. */
export const BIZ_CAT = ['Все покупки', 'Продукты', 'Здоровье и аптеки', 'Кафе и рестораны', 'Транспорт', 'Маркетплейсы']

export const ROLE_NAME: Record<Role, string> = { retail: 'Ритейл и сети', bank: 'Банк', gov: 'Власти региона', any: 'Общий профиль' }
// Названия одни на любой бизнес — розница, банк, общепит, услуги: решение «как заходить», а не формат точки.
// Это список территорий на проверку, а не решение об открытии: аренда, маржа, конкуренты
// и история открытий в данных отсутствуют, финансовый расчёт делается отдельно.
const BIZ_REC: Record<Rec, string> = { own: 'Проверить для своей сети', partner: 'Проверить через партнёра', watch: 'Подождать', blind: 'Мало данных' }
export const REC_NAME: Record<Role, Record<Rec, string>> = {
  retail: BIZ_REC,
  bank: BIZ_REC,
  gov: { own: 'Точка роста', partner: 'Нужна поддержка бизнеса', watch: 'Зона внимания', blind: 'Мало данных' },
  any: BIZ_REC,
}
export const REC_COLOR: Record<Rec, string> = { own: 'var(--ok)', partner: 'var(--blue)', watch: 'var(--shift)', blind: 'var(--text-3)' }
export const ACTION: Record<Role, string> = {
  retail: 'Проверьте продажи и запасы своих точек в районе',
  bank: 'Проверьте поток платежей и просрочку клиентов района',
  gov: 'Проверьте обстановку и обращения жителей',
  any: 'Сравните со своими данными по территории',
}

// Поля сводки ряда в mo.json: рост г/г, выигрыш к Prophet, тревога, рост 2025, WAPE, волатильность, тревог, уровень 2024.
const F = { yoy: 0, gain: 1, alarm: 2, fc25: 3, wape: 4, vol: 5, nal: 6, lvl: 7 } as const
export const field = (m: Mo, c: number, k: keyof typeof F) => m.sum[c][F[k]] as number | null

export interface RegionInfo { key: string; beta: number | null; r2: number | null; riskNews: number; attackNews: number }
let REG: RegionInfo[] = []
export const loadRegions = () => fetch('/data/regions.json').then((r) => r.json()).then((j) => (REG = j))

export interface RegionStat {
  rk: number; key: string; name: string; pop: number; nMo: number
  /** coverage — полнота внутри набора: доля населения МО субъекта из справочника СберИндекса, у которых есть полный ряд;
   *  всего населения субъекта по Росстату в данных нет. market — расходы жителей охваченных МО, не выручка точек. */
  coverage: number; market: number; marketBase: number; growth: number; wape: number; vol: number; alarms: number
  topShare: number; macro: 'strong' | 'weak' | 'none'; riskNews: number
  mos: { m: Mo; market: number; growth: number }[]
  rec: Rec; reasons: string[]
}

const q = (xs: number[], p: number) => { const s = xs.filter(Number.isFinite).sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))] ?? NaN }

/** Пороги правил рекомендации: у бизнеса — по умолчанию, у аналитика — ручки. */
export interface Th { market: number; gap: number; cover: number; vol: number; conc: number }
export const TH: Th = { market: 0.6, gap: -3, cover: 0.6, vol: 0.8, conc: 0.45 }

/** Сводка по субъектам для категории: объём рынка, рост, надёжность, риски — и рекомендация. */
const cache = new Map<string, { list: RegionStat[]; national: number; month: number }>()
export function regionStats(cat: number, role: Role, th: Th = TH, T = FIRST_FC + 11) {
  const ck = `${cat}:${role}:${JSON.stringify(th)}:${T}`
  // Ошибка растёт с горизонтом: надёжность региона пересчитывается на выбранный месяц.
  const errC = META.horizonErr[META.cats[cat]] ?? META.horizonErr['Все']
  // Прошлый месяц — факт: ошибка как у ближайшего месяца прогноза, рекомендации не ломаются.
  const errK = errC[Math.max(0, T - FIRST_FC)] / errC[2]
  if (cache.has(ck)) return cache.get(ck)!
  const by = new Map<number, Mo[]>()
  for (const m of MOS) { if (m.rk < 0) continue; by.set(m.rk, [...(by.get(m.rk) ?? []), m]) }
  const raw: RegionStat[] = []
  let natM = 0, natG = 0, natA = 0, natB = 0
  for (const [rk, ms] of by) {
    let pop = 0, cov = 0, market = 0, marketBase = 0, g = 0, w = 0, wv = 0, v = 0, al = 0
    const mos: RegionStat['mos'] = []
    for (const m of ms) {
      pop += m.pop
      // Рынок и рост — за 12 месяцев до выбранного месяца против 12 месяцев годом раньше.
      const sv = ser60(m.id, cat)
      const wp0 = field(m, cat, 'wape'), vo = field(m, cat, 'vol')
      const wp = wp0 === null ? null : wp0 * errK
      al += field(m, cat, 'nal') ?? 0
      if (!sv || !m.pop) continue
      let a = 0, b = 0
      // Ряд начинается в январе 2023 года: для месяцев 2024 года окно короче двенадцати месяцев.
      for (let i = Math.max(12, T - 11); i <= T; i++) { a += sv[i]; b += sv[i - 12] }
      natA += sv[T] * m.pop; natB += sv[T - 12] * m.pop
      const lvl = a, fc = a / b - 1
      cov += m.pop
      const mk = lvl * m.pop
      // Рост субъекта — отношение сумм расходов, а не среднее темпов МО с весом текущего рынка.
      market += mk; marketBase += b * m.pop; g += mk * fc
      if (wp !== null) { w += mk * wp; wv += mk }
      if (vo !== null) v += mk * vo
      mos.push({ m, market: mk, growth: fc })
    }
    mos.sort((a, b) => b.market - a.market)
    const info = REG.find((r) => r.key === META.regions[rk])
    const macro = info?.beta == null ? 'none' : info.r2! > 0.3 && info.beta > 0.8 ? 'strong' : info.r2! > 0.3 ? 'weak' : 'none'
    raw.push({
      rk, key: META.regions[rk], name: ms[0].region, pop, nMo: ms.length, coverage: pop ? cov / pop : 0,
      market, marketBase, growth: marketBase ? market / marketBase - 1 : NaN, wape: wv ? w / wv : NaN, vol: market ? v / market : NaN, alarms: al,
      // Город федерального значения — один рынок, а не сто районов: его плотность — весь рынок.
      topShare: ms.every((m) => m.type.startsWith('внутригородская')) ? 1 : market ? mos.slice(0, 3).reduce((s, x) => s + x.market, 0) / market : 0,
      macro, riskNews: info?.riskNews ?? 0, mos, rec: 'partner', reasons: [],
    })
    natM += market; natG += marketBase
  }
  const national = natM / natG - 1
  const mQ = q(raw.map((r) => r.market), th.market), wQ = q(raw.map((r) => r.wape), 0.75), vQ = q(raw.map((r) => r.vol), th.vol), nQ = q(raw.map((r) => r.riskNews), 0.85)
  for (const r of raw) {
    const why: string[] = []
    const gD = (r.growth - national) * 100
    if (r.coverage < th.cover || r.mos.length < 2) {
      r.rec = 'blind'
      why.push(`полные ряды охватывают ${Math.round(r.coverage * 100)} % жителей субъекта в наборе`)
    } else if (gD < th.gap || r.vol > vQ) {
      r.rec = 'watch'
      if (gD < th.gap) why.push(`спрос растёт медленнее страны на ${fmtPp(-gD)}`)
      if (r.vol > vQ) why.push(`разброс трат выше, чем в ${Math.round(th.vol * 100)} % регионов`)
    } else if (r.market >= mQ && r.wape <= wQ && r.topShare >= th.conc) {
      r.rec = 'own'
      why.push('крупный рынок', r.topShare === 1 ? 'единый городской рынок; проверьте для своей сети, окупаемость считайте отдельно' : `${Math.round(r.topShare * 100)} % рынка — в трёх крупнейших муниципалитетах; проверьте для своих точек`)
      if (gD >= 0) why.push(`спрос растёт быстрее страны на ${fmtPp(gD)}`)
    } else {
      r.rec = 'partner'
      if (r.market < mQ) why.push('рынок средний или небольшой')
      if (r.topShare < th.conc) why.push('спрос распределён по муниципалитетам; через партнёров охват дешевле')
      if (r.wape > wQ) why.push('ошибка прогноза выше; риск лучше разделить')
    }
    if (r.riskNews > nQ) why.push('много новостей о ЧС и бедствиях')
    if (r.macro === 'strong') why.push('динамика близка к стране')
    r.reasons = why
  }
  const res = { list: raw.sort((a, b) => b.market - a.market), national, month: natA / natB - 1 }
  cache.set(ck, res)
  return res
}

const fmtPp = (x: number) => `${x.toFixed(1).replace('.', ',')} п. п.`
const nf1 = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1, minimumFractionDigits: 1 })
export const bn = (x: number) => (x >= 1e12 ? `${nf1.format(x / 1e12)} трлн ₽` : x >= 1e9 ? `${nf1.format(x / 1e9)} млрд ₽` : `${Math.round(x / 1e6).toLocaleString('ru-RU')} млн ₽`)

/** Надёжность словами по ошибке прогноза. */
export function reliability(wape: number) {
  if (!Number.isFinite(wape)) return { word: 'нет оценки', tone: 'var(--text-3)' }
  if (wape < 0.05) return { word: 'высокая', tone: 'var(--ok)' }
  if (wape < 0.09) return { word: 'средняя', tone: 'var(--shift)' }
  return { word: 'низкая', tone: 'var(--warn)' }
}

/** Сила сдвига словами. */
export const strengthWord = (p: number) => (Math.abs(p) >= 0.25 ? 'резкий' : Math.abs(p) >= 0.12 ? 'заметный' : 'умеренный')

/** Ожидаемая ошибка прогноза на месяц T для категории и то, измерена она или оценена. */
export function errAt(cat: number, T: number) {
  const e = META.horizonErr[META.cats[cat]] ?? META.horizonErr['Все']
  const h = T - FIRST_FC + 1
  // До января 2025 года — факт: ошибки нет.
  if (h < 1) return { w: 0, h, measured: true, fact: true }
  return { w: e[h - 1], h, measured: h <= 12, fact: false }
}

/** Расходы на жителя по стране, 2023-01…2027-12: средняя по МО, взвешенная населением. */
const natCache = new Map<number, number[]>()
export function nationalSeries(cat: number) {
  if (natCache.has(cat)) return natCache.get(cat)!
  const out = new Array(60).fill(0), w = new Array(60).fill(0)
  for (const m of MOS) {
    const v = ser60(m.id, cat)
    if (!v || !m.pop) continue
    for (let i = 0; i < 60; i++) { out[i] += v[i] * m.pop; w[i] += m.pop }
  }
  const res = out.map((x, i) => x / w[i])
  natCache.set(cat, res)
  return res
}

/** Ряд региона, ₽ на жителя, 2023-01…2027-12: средняя по его МО, взвешенная населением, — как ряд страны. */
const regCache = new Map<string, number[]>()
export function regionSeries(cat: number, rk: number) {
  const k = `${cat}:${rk}`
  if (regCache.has(k)) return regCache.get(k)!
  const out = new Array(60).fill(0), w = new Array(60).fill(0)
  for (const m of MOS) {
    if (m.rk !== rk || !m.pop) continue
    const v = ser60(m.id, cat)
    if (!v) continue
    for (let i = 0; i < 60; i++) if (Number.isFinite(v[i])) { out[i] += v[i] * m.pop; w[i] += m.pop }
  }
  const res = out.map((x, i) => (w[i] ? x / w[i] : NaN))
  regCache.set(k, res)
  return res
}
