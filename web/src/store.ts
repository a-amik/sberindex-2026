import { create } from 'zustand'
import type { Horizon } from './data/calendar'
import type { ModelKey } from './data/models'
import { TH, type Role, type Th } from './data/biz'
import { mo } from './data/real'
import { NONE, type Factors } from './data/whatif'

/** Разделы одни на оба режима; режим меняет язык и число ручек, а не набор разделов. */
export type Screen = 'sum' | 'reg' | 'rank' | 'cats' | 'dyn' | 'risk' | 'about'
export type Mode = 'biz' | 'pro'
export type Theme = 'light' | 'dark'

interface State {
  screen: Screen
  mode: Mode
  role: Role
  /** Субъект, открытый в бизнес-режиме. */
  selRk: number | null
  /** Сценарий сводки: один на график наверху и блок «Что будет, если…»; base — без сценария. */
  scn: { key: string; f: Factors; scope: 'country' | 'region' }
  /** Открытое испытание на странице «Испытания» в «О проекте». */
  testTab: string
  /** Ручки своего сочетания открыты под верхней строкой. */
  knobs: boolean
  /** Открытая страница «О проекте». */
  aboutPage: string
  /** Пороги правил рекомендации — ручки аналитика в «Регионах». */
  th: Th
  /** Выбранный в календаре месяц: индекс на оси 2023-01…2027-12, от 24 (январь 2025) до 59. */
  target: number
  /** Включённые слои карты; они же фильтр МО и регионов. */
  layers: string[]
  setTarget: (t: number) => void
  cat: number
  H: Horizon
  sel: number | null
  theme: Theme
  marks: boolean
  shown: ModelKey[]
  palette: boolean
  /** Счётчик перелётов карты к выбранной территории: растёт, когда её выбрали не на карте. */
  focus: number
  set: (p: Partial<State>) => void
  setMode: (m: Mode) => void
  go: (s: Screen) => void
  openMo: (id: number) => void
  toggleModel: (m: ModelKey) => void
}

const saved = (() => { try { return localStorage.getItem('nl-theme') as Theme | null } catch { return null } })()
const sys: Theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
const read = (k: string) => { try { return localStorage.getItem(k) } catch { return null } }
const savedMode: Mode = read('nl-mode') === 'pro' ? 'pro' : 'biz'
const SCREENS: Screen[] = ['sum', 'reg', 'rank', 'cats', 'dyn', 'risk', 'about']
const fromHash = (): Screen => { const s = location.hash.slice(2).split('/')[0] as Screen; return SCREENS.includes(s) ? s : 'sum' }
// Страница «О проекте» — второй частью адреса: #/about/trust. Неизвестную AboutHub заменит первой.
export const pageFromHash = (): string | null => { const [s, p] = location.hash.slice(2).split('/'); return s === 'about' && p ? p : null }

export const useApp = create<State>((set, get) => ({
  screen: fromHash(),
  mode: savedMode,
  selRk: null,
  scn: { key: 'base', f: NONE, scope: 'country' },
  testTab: 'replay',
  knobs: false,
  aboutPage: pageFromHash() ?? 'deck',
  th: TH,
  target: 26,
  layers: [],
  // Горизонт для таблиц метрик аналитика — ближайший измеренный к выбранному месяцу.
  setTarget: (target) => { const h = target - 23; set({ target, H: h <= 1 ? 1 : h <= 3 ? 3 : h <= 6 ? 6 : 12 }) },
  role: (read('nl-role') as Role | null) ?? 'retail',
  cat: 0,
  H: 3,
  sel: null,
  theme: saved ?? sys,
  marks: true,
  shown: ['prophet', 'panel', 'chronos', 'ensemble'],
  palette: false,
  focus: 0,
  set: (p) => {
    try { if (p.role) localStorage.setItem('nl-role', p.role) } catch { /* без памяти */ }
    set(p)
  },
  // Режим — настройка профиля: переключает набор разделов и запоминается на устройстве.
  setMode: (mode) => {
    try { localStorage.setItem('nl-mode', mode) } catch { /* без памяти */ }
    set({ mode, sel: null })
  },
  go: (screen) => { history.replaceState(null, '', screen === 'about' ? `#/about/${get().aboutPage}` : `#/${screen}`); set({ screen }) },
  // Территорию открывают на карте: шторка у края карты, на телефоне — снизу.
  openMo: (id) => set((s) => {
    // В бизнес-режиме территорию открывают в её регионе, у аналитика — на карте.
    history.replaceState(null, '', '#/reg')
    return { screen: 'reg', selRk: mo(id)?.rk ?? null, sel: s.mode === 'pro' ? id : null, palette: false, focus: s.focus + 1 }
  }),
  toggleModel: (m) => set((s) => ({ shown: s.shown.includes(m) ? s.shown.filter((x) => x !== m) : [...s.shown, m] })),
}))
