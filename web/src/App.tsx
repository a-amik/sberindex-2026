import { useEffect, type ReactNode } from 'react'
import { CatMenu, FilterBar, Palette, PhoneNav, Rail, ScenarioMenu, TopBar, usePhone } from './components/Shell'
import { MonthPicker } from './components/MonthPicker'
import { TipLayer } from './components/ui'
import { AboutHub } from './screens/AboutHub'
import { Regions } from './screens/biz/Regions'
import { Risks } from './screens/biz/Risks'
import { Summary } from './screens/biz/Summary'
import { pageFromHash, useApp, type Screen } from './store'

// Карта, рейтинг, категории и динамика — один экран регионов с разным видом справа.
const SCREENS: Record<Screen, () => ReactNode> = { sum: Summary, reg: Regions, rank: Regions, cats: Regions, dyn: Regions, risk: Risks, about: AboutHub }

export default function App() {
  const { screen, theme, marks, set } = useApp()
  const phone = usePhone()
  const View = SCREENS[screen] ?? Summary
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('nl-theme', theme) } catch { /* без памяти темы */ }
  }, [theme])
  useEffect(() => {
    const f = () => { const s = location.hash.slice(2).split('/')[0] as Screen; const pg = pageFromHash(); if (pg) set({ aboutPage: pg }); if (s in SCREENS) set({ screen: s }); else if ((s as string) === 'whatif') set({ screen: 'sum' }) }
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [set])
  // Месяц прогноза — календарь в шапке, у обоих режимов: каждый месяц окрашен точностью.
  // Месяц, покупки и сценарий — одна группа кнопок; в «О проекте» у страниц свои выключатели.
  const horizon = screen !== 'about' && <div className="top-flt"><MonthPicker /><CatMenu /><ScenarioMenu /></div>
  // У «О проекте» фильтров нет: в полосу шапки страница кладёт свой заголовок и ручки (Slot).
  const head = screen === 'about' ? <div id="top-slot" className="top-slot" /> : horizon
  return (
    <div className={`app${marks ? '' : ' marks-off'}`}>
      <Rail />
      <div className="main">
        <TopBar phone={phone}>{head}</TopBar>
        {phone && horizon && <div className="top-flt-row">{horizon}</div>}
        <FilterBar />
        <div className="body"><View /></div>
      </div>
      <PhoneNav />
      <Palette />
      <TipLayer />
    </div>
  )
}
