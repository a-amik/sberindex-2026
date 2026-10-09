// Настоящие данные экрана: web/public/data, собирает scripts/export_data.py.
// Справочник, метрики и тревоги приходят при запуске; субъект — файлом
// при первом обращении, пока он едет, область показывает лоадер.
import { useEffect, useState } from 'react'

export type CatKey = 'all' | 'food' | 'health' | 'cafe' | 'transport' | 'market'
export const CAT_KEYS: CatKey[] = ['all', 'food', 'health', 'cafe', 'transport', 'market']
export const CAT_SHORT = ['Все', 'Продукты', 'Здоровье', 'Общепит', 'Транспорт', 'Маркетплейсы']
export const catColor = (c: number) => `var(--c-${CAT_KEYS[c]})`

export interface Row { [k: string]: number | string | null }
export interface Meta {
  periods: string[]; cats: string[]; origins: string[]; shown: string[]; regions: string[]
  byH: { model: string; H: number; MAE: number; WAPE: number; R2: number; n: number }[]
  byCat: { model: string; H: number; category: string; MAE: number; WAPE: number; R2: number }[]
  ensemble: { model: string; H: number; MAE_all: number; MAE_report: number | null }[]
  detect: Row[]
  detectChoice: { lead: string; thresholds: Record<string, number | null> }
  early: Row[]; byMonth: Row[]; major: Row[]
  cases: Record<string, Record<string, unknown>>
  groups: import('../model/sbiDetect').Group[]
  fwdTargets: string[]
  fwdModels: string[]
  sensitivity: Record<string, Record<'rate' | 'workday' | 'heat' | 'heat_other' | 'rain' | 'flood', { coef: number; se?: number; n?: number; series?: string; lag?: number; source?: string }>>
  fwdCheck: { cat: string; target: string; fc_yoy: number; nat_yoy: number | null; series: string }[]
  sources: { external: { name: string; files: number; bytes: number; date: string; url: string }[]; built: { file: string; rows: number; date: string }[]; results: { file: string; date: string; by: string }[]; exported: string }
  /** Средняя ошибка (WAPE) сдаваемой модели на шаг 1…36 по категориям; дальше 12 — оценка, а не измерение. */
  horizonErr: Record<string, number[]>
  /** Полуширина 90 % интервала строгого прогноза вперёд, доля к точке, по категориям и шагам 1…36. */
  interval90?: Record<string, number[]>
  /** Манифест релиза: модель сайта, состав, окно отбора, файлы с хешами, покрытие интервалов. */
  release?: { model_id: string; members: string[]; how: string; force_include: string[]; select_last_target: string; report_from: string; data_last: string; forward_origin: string; forward_targets: string[]; adjustments: string[]; intervals: string; adjustment_tested?: string; coverage90_by_step: number[]; files: Record<string, string> }
  robustness: Record<string, { mae_shock: number; mae_base: number; rise: number; by_month: number[]; by_kind: Record<string, number>; n: number }>
}
export interface Mo { id: number; name: string; full: string; region: string; rk: number; type: string; lat: number | null; lon: number | null; pop: number; urban: number | null; /** По категориям: рост г/г, выигрыш к Prophet, тревога, рост 2025, ошибка, волатильность, тревог, уровень 2024. */
  sum: (number | null)[][] }
/** Тревога: МО, категория, месяц, счёт, новость по МО, новость по субъекту, сила (доля к обычному уровню). */
export type Alarm = [number, number, number, number, number, number, number | null]
/** Новость: месяц, дата, заголовок, типы, МО субъекта, к которым привязана. */
export type News = [number, string, string, string[], number[]]
export interface Shard {
  key: string
  series: Record<string, Record<string, (number | null)[]>>
  region: Record<string, number[]>
  fc: Record<string, Record<string, Record<string, Record<string, number[]>>>>
  band: Record<string, Record<string, [Record<string, number[]>, Record<string, number[]>]>>
  alarms: Alarm[]
  news: News[]
  /** Детекторы по ряду: группа, прыжок соседей и онлайн-счёт пяти детекторов по месяцам. */
  det: Record<string, Record<string, { g: number; nb: number[]; s: Record<import('../model/sbiDetect').Method, number[]> & { chronos?: number[] } }>>
  /** Прогноз на 2025 год от декабря 2024: модель → 12 месяцев; у Chronos-2 ещё :q05 и :q95. */
  fwd: Record<string, Record<string, Record<string, number[]>>>
}

export let META: Meta
/** Доли отраслей для сценариев: страна, субъект по rk, МО по id (web/scripts/export_industry.py). */
/** Профиль людей: сальдо внутренней миграции 2023 на 1 000, доля 65+, доля 15—34 — страна, субъект по rk, МО по id (web/scripts/export_people.py). */
export let PEOPLE: { keys: string[]; country: (number | null)[]; regions: Record<number, (number | null)[]>; mo: Record<number, (number | null)[]> } | null = null
export let INDUSTRY: { groups: string[]; country: number[]; regions: Record<number, number[]>; mo: Record<number, number[]>; moSource: Record<number, string> } | null = null
export let MOS: Mo[] = []
export let ALARMS: Alarm[] = []
const byId = new Map<number, Mo>()
export const mo = (id: number) => byId.get(id)

/** Ряды для календаря: 2023-01…2027-12 — два года факта и три года прогноза ансамбля. */
export const SERIES60 = new Map<string, number[]>()
export const ser60 = (id: number, c: number) => SERIES60.get(`${id}:${c}`)
/** Индекс месяца на оси 2023-01…2027-12: 24 — январь 2025, первый месяц прогноза. */
export const FIRST_FC = 24

export async function boot() {
  // meta, mo, alarms, months обязательны: без любого из них экран пуст, и честнее сказать об этом,
  // чем молча падать внутри Promise.all. industry и people — необязательные слои.
  const need = new Set(['meta', 'mo', 'alarms', 'months'])
  const [m, list, al, mon, ind, ppl] = await Promise.all(['meta', 'mo', 'alarms', 'months', 'industry', 'people'].map((f) =>
    fetch(`/data/${f}.json`).then((r) => {
      if (!r.ok) { if (need.has(f)) throw new Error(`не загрузился файл данных ${f}.json (${r.status})`); return null }
      return r.json().catch(() => { if (need.has(f)) throw new Error(`файл данных ${f}.json повреждён`); return null })
    }, (err) => { if (need.has(f)) throw new Error(`нет связи с сервером данных (${f}.json): ${err.message}`); return null })))
  INDUSTRY = ind
  PEOPLE = ppl
  for (const [id, c, v] of mon as [number, number, number[]][]) SERIES60.set(`${id}:${c}`, v)
  META = m
  MOS = (list.rows as unknown[][]).map((r) => Object.fromEntries((list.cols as string[]).map((c, i) => [c, r[i]])) as unknown as Mo)
  for (const x of MOS) byId.set(x.id, x)
  ALARMS = al
}

/** Имя субъекта по ключу из results: «оренбургская» → «Оренбургская область». */
/** Порог детектора из results/metrics/detect_choice.json. */
export const thr = (m: string) => META.detectChoice.thresholds[m] ?? Infinity

export const regionName = (key: string) => MOS.find((m) => META.regions[m.rk] === key)?.region ?? key
const MN = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const MNF = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
// Ось начинается с января 2023 года; индексы за концом истории — будущие месяцы стенда.
export const monthShort = (i: number) => `${MN[i % 12]} ${23 + Math.floor(i / 12)}`
export const monthLong = (i: number) => `${MNF[i % 12]} ${2023 + Math.floor(i / 12)}`
const MNP = ['январе', 'феврале', 'марте', 'апреле', 'мае', 'июне', 'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре']
/** «в ноябре 2024»: месяц в предложном падеже. */
export const monthIn = (i: number) => `${MNP[i % 12]} ${2023 + Math.floor(i / 12)} года`
export const periodIdx = (p: string) => META.periods.indexOf(p)

const shards = new Map<number, Promise<Shard>>()
export function shard(rk: number) {
  // Неудачная загрузка не остаётся в кэше: следующий запрос того же субъекта повторит её.
  if (!shards.has(rk)) shards.set(rk, fetch(`/data/reg/${rk}.json`).then((r) => { if (!r.ok) throw new Error(`reg/${rk}.json ${r.status}`); return r.json() as Promise<Shard> }).catch((e) => { shards.delete(rk); throw e }))
  return shards.get(rk)!
}
export function useShard(rk: number | undefined) {
  const [st, setSt] = useState<{ rk?: number; data?: Shard; error?: string }>({})
  useEffect(() => {
    if (rk === undefined || rk < 0) return
    let live = true
    shard(rk).then((data) => live && setSt({ rk, data }), (e: Error) => live && setSt({ rk, error: e.message }))
    return () => { live = false }
  }, [rk])
  return st.rk === rk ? st.data : undefined
}

export type SampleRow = [number, number, number[], number[], number, number[]]
let SAMPLE: Promise<SampleRow[]> | null = null
export const sample = () => (SAMPLE ??= fetch('/data/sample.json').then((r) => r.json()))

export const NEWS_TYPE: Record<string, string> = {
  attack: 'Атака', disaster: 'Стихия', emergency: 'ЧС', fire: 'Пожар', flood: 'Паводок', layoff: 'Увольнения',
  macro: 'Макро', payments: 'Платежи', plant: 'Предприятие', transport: 'Транспорт',
}
