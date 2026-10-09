import { useMemo, useState } from 'react'
import { MonthBars } from '../components/charts'
import { Card, Seg, Table } from '../components/ui'
import { ALARMS, META, mo, monthShort, regionName } from '../data/real'
import { fmt0, fmt1, fmt2 } from '../lib/util'
import { useApp } from '../store'

export const SHOCKS_NAV: [string, string][] = [['feed', 'Лента сигналов'], ['months', 'По месяцам'], ['major', 'Крупные события'], ['cases', 'Разобранные случаи']]

export function ShocksBody() {
  const { cat, openMo } = useApp()
  const [f, setF] = useState<'all' | 'mo' | 'reg' | 'none'>('all')
  const [more, setMore] = useState(30)
  const rows = useMemo(() => ALARMS.filter((a) => a[1] === cat).filter((a) => (f === 'all' ? true : f === 'mo' ? a[4] : f === 'reg' ? a[5] && !a[4] : !a[4] && !a[5])).map((a) => ({ a, m: mo(a[0])! })), [cat, f])
  const all = ALARMS.filter((a) => a[1] === cat)
  const share = all.length ? all.filter((a) => a[4] || a[5]).length / all.length : 0
  const byCat = Array.from({ length: META.periods.length }, (_, t) => all.filter((a) => a[2] === t).length)
  const cases = META.cases as Record<string, Record<string, unknown>>
  const apr = cases.april_2023 as { by_category_district_pct: Record<string, number>; alarm_share_district_pct: number; alarm_share_city_pct: number }
  const fl = cases.floods_2024 as { series_flood_regions: number; alarm_any_pct: Record<string, number>; shift_pct_by_category: Record<string, { flood: number; rest: number }> }

  return (
    <>
      <Card id="feed" title="Лента сигналов" sub={`${fmt0(all.length)} сигналов за два года; у ${fmt0(share * 100)} % рядом есть новость по муниципалитетам или субъекту`}
        extra={<Seg value={f} onChange={(v) => { setF(v); setMore(30) }} items={[['all', 'Все'], ['mo', 'Новость о муниципалитете'], ['reg', 'О субъекте'], ['none', 'Без новости']]} />}>
        <Table rows={rows} limit={more} sort={['t', -1]} onRow={(r) => openMo(r.a[0])} cols={[
          { key: 't', title: 'Месяц', get: (r) => r.a[2], render: (r) => monthShort(r.a[2]) },
          { key: 'mo', title: 'Территория', get: (r) => r.m.name, render: (r) => <span className="ell" style={{ maxWidth: 220 }}>{r.m.name}</span> },
          { key: 'reg', title: 'Субъект', get: (r) => r.m.region, render: (r) => <span className="ell" style={{ maxWidth: 220 }} data-tip={r.m.region}>{r.m.region}</span> },
          { key: 's', title: 'Счёт', num: true, tip: 'Робастный z‑счёт: отклонение месяца в единицах разброса своей истории', get: (r) => r.a[3], render: (r) => <span className={r.a[3] < 0 ? 'bad' : 'good'}>{fmt2(r.a[3])}</span> },
          { key: 'n', title: 'Новость', get: (r) => r.a[4] * 2 + r.a[5], render: (r) => (r.a[4] ? <span className="tag ok">о МО</span> : r.a[5] ? <span className="tag">о субъекте</span> : <span className="small">—</span>) },
        ]} />
        {rows.length > more && <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}><button className="btn ghost" onClick={() => setMore((m) => m + 30)}>Показать ещё</button><span className="small">{fmt0(more)} из {fmt0(rows.length)}</span></div>}
      </Card>
      <Card id="months" title="Сигналы по месяцам" sub="Выбранная категория, все муниципалитеты">
        <MonthBars values={byCat} color="var(--warn)" />
      </Card>
      <Card id="major" title="Крупные события" sub="Субъект и месяц с наибольшим числом новостей о бедствиях; сдвиг расходов — % к ожиданию">
        <Table rows={META.major} sort={['d', -1]} cols={[
          { key: 'r', title: 'Субъект', get: (r) => String(r.region_key), render: (r) => regionName(String(r.region_key)) },
          { key: 'p', title: 'Месяц', get: (r) => String(r.period), render: (r) => monthShort(META.periods.indexOf(String(r.period))) },
          { key: 'd', title: 'Новостей', num: true, get: (r) => Number(r.disaster_news) },
          { key: 'b', title: 'Сигналов до', num: true, get: (r) => Number(r.alarms_3m_before) },
          { key: 'a', title: 'после', num: true, get: (r) => Number(r.alarms_3m_after) },
          ...['Здоровье', 'Общественное питание', 'Транспорт'].map((c) => ({ key: c, title: c === 'Общественное питание' ? 'Общепит' : c, num: true, get: (r: Record<string, unknown>) => Number(r[c]), render: (r: Record<string, unknown>) => <span className={Number(r[c]) < -2 ? 'bad' : ''}>{fmt1(Number(r[c]))} %</span> })),
        ]} />
      </Card>
      <Card id="cases" title="Разобранные случаи">
        <div className="grid g2">
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 6 }}>Апрель 2023: провал в районах</h3>
            <p className="muted" style={{ fontSize: 13, marginBottom: 10 }}>Сигналы в районах — {fmt1(apr.alarm_share_district_pct)} % рядов против {fmt1(apr.alarm_share_city_pct)} % в городах. В общероссийском ряду провала нет: сдвиг локальный.</p>
            <Table rows={Object.entries(apr.by_category_district_pct)} sort={['v', -1]} cols={[
              { key: 'c', title: 'Категория', get: (r) => r[0] },
              { key: 'v', title: 'Сигналов, %', num: true, get: (r) => r[1], render: (r) => fmt1(r[1]) },
            ]} />
          </div>
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 6 }}>Паводки 2024 года</h3>
            <p className="muted" style={{ fontSize: 13, marginBottom: 10 }}>{fmt0(fl.series_flood_regions)} рядов в субъектах паводка. Сигналов после — {fmt1(fl.alarm_any_pct.flood_after)} %, до — {fmt1(fl.alarm_any_pct.flood_before)} %; в остальных субъектах {fmt1(fl.alarm_any_pct.rest_after)} %.</p>
            <Table rows={Object.entries(fl.shift_pct_by_category)} sort={['f', 1]} cols={[
              { key: 'c', title: 'Категория', get: (r) => r[0] },
              { key: 'f', title: 'Паводок', num: true, get: (r) => r[1].flood, render: (r) => <span className={r[1].flood < -1 ? 'bad' : ''}>{fmt1(r[1].flood)} %</span> },
              { key: 'r', title: 'Остальные', num: true, get: (r) => r[1].rest, render: (r) => `${fmt1(r[1].rest)} %` },
            ]} />
          </div>
        </div>
      </Card>
    </>
  )
}
