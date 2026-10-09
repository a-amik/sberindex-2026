import { Page, useSections, Slot } from '../components/Shell'
import { useApp } from '../store'
import { I } from '../components/icons'
import { AboutBody, METHOD_NAV } from './About'
import { TRUST_NAV, TrustBody } from './biz/Trust'
import { DETECT_NAV, DetectBody } from './Detect'
import { MODELS_NAV, ModelsBody } from './Models'
import { SOURCES_NAV, SourcesBody } from './Sources'
import { SIGNALS_NAV, SignalsBody } from './Signals'
import { NEWS_NAV, NewsBody } from './NewsEvents'
import { PROTOCOL_NAV, ProtocolBody } from './Protocol'
import { CITY_NAV, CityBody } from './CityDistricts'
import { VALUE_NAV, ValueBody } from './Value'
import { HYP_NAV, HypBody } from './Hypotheses'
import { TESTS_NAV, TestsBody } from './biz/WhatIf'
import { DECK_NAV, DeckBody } from './Deck'
import { AboutHero, heroes } from '../components/AboutHero'

// «О проекте» — как у «Маршрута дня»: отчёты о решении страницами, у каждой свои главы.
// Одинаково в обоих режимах: бизнесу полезно видеть, откуда данные и как проверены модели.
const PAGES: { key: string; title: string; icon: React.ReactNode; nav: [string, string][]; Body: () => React.ReactNode; pro?: boolean }[] = [
  { key: 'deck', title: 'Презентация', icon: I.slides, nav: DECK_NAV, Body: DeckBody },
  { key: 'trust', title: 'Надёжность прогноза', icon: I.shield, nav: TRUST_NAV, Body: TrustBody },
  { key: 'value', title: 'Кому это полезно', icon: I.users, nav: VALUE_NAV, Body: ValueBody },
  { key: 'models', title: 'Модели прогноза', icon: I.models, nav: MODELS_NAV, Body: ModelsBody },
  { key: 'signals', title: 'Внешние данные', icon: I.globe, nav: SIGNALS_NAV, Body: SignalsBody },
  { key: 'city', title: 'Внутри города', icon: I.building, nav: CITY_NAV, Body: CityBody },
  { key: 'detect', title: 'Детекторы шоков', icon: I.detect, nav: DETECT_NAV, Body: DetectBody },
  { key: 'news', title: 'Новости и шоки', icon: I.news, nav: NEWS_NAV, Body: NewsBody },
  { key: 'hyp', title: 'Гипотезы: стройка и якоря', icon: I.bulb, nav: HYP_NAV, Body: HypBody },
  // Испытания — ручки аналитика: главы страницы переключают испытание, а не листают.
  { key: 'tests', title: 'Испытания', icon: I.stand, nav: TESTS_NAV, Body: TestsBody, pro: true },
  { key: 'sources', title: 'Данные и источники', icon: I.database, nav: SOURCES_NAV, Body: SourcesBody },
  { key: 'protocol', title: 'Протокол и воспроизводимость', icon: I.protocol, nav: PROTOCOL_NAV, Body: ProtocolBody },
  { key: 'method', title: 'Методика и границы применимости', icon: I.book, nav: METHOD_NAV, Body: AboutBody },
]

export function AboutHub() {
  const { aboutPage, set, mode } = useApp()
  const pages = PAGES.filter((x) => !x.pro || mode === 'pro')
  const p = pages.find((x) => x.key === aboutPage) ?? pages[0]
  return <Hub key={p.key} p={p} pages={pages} onPage={(k) => { set({ aboutPage: k }); history.pushState(null, '', `#/about/${k}`); document.getElementById('page-main')?.scrollTo({ top: 0 }) }} />
}

function Hub({ p, pages, onPage }: { p: (typeof PAGES)[number]; pages: typeof PAGES; onPage: (k: string) => void }) {
  const [sec, scroll] = useSections(p.nav.map((n) => n[0]))
  const { testTab, set } = useApp()
  const tabs = p.key === 'tests'
  const active = tabs ? testTab : sec
  const go = tabs ? (k: string) => set({ testTab: k }) : scroll
  const hero = heroes()[p.key]
  return (
    <Page nav={p.nav} active={active} onNav={go} pages={pages.map((x) => [x.key, x.title, x.icon])} page={p.key} onPage={onPage}>
      <Slot id="top-slot"><h1 className="top-title">О проекте</h1><div id="top-tools" className="top-tools-slot" /></Slot>
      {hero && <AboutHero h={hero} />}
      <p.Body />
    </Page>
  )
}
