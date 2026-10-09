import { MonthBars } from '../components/charts'
import { Card, Info } from '../components/ui'
import { HORIZONS } from '../data/calendar'
import { ALARMS, CAT_SHORT, catColor, META, mo, monthShort, regionName } from '../data/real'
import { fmt0, fmt1, fmt2, fmt3, pct } from '../lib/util'
import { useApp } from '../store'

export const metric = (model: string, H: number) => META.byH.find((r) => r.model === model && r.H === H)!
export const detRow = (method: string) => META.detect.find((r) => r.method === method)!

/** Технический слой «Сводки»: метрики моделей и детектора, тревоги по месяцам. */
export function OverviewTech() {
  const { H, openMo } = useApp()
  const ens = metric('ensemble', H), pro = metric('prophet_default', H)
  const lead = META.detectChoice.lead
  const det = detRow(lead)
  const months = META.byMonth.map((r) => Number(r.alarms_after_valve))
  const last = months[months.length - 1], prev = months[months.length - 2]
  const fresh = [...ALARMS].sort((a, b) => b[2] - a[2] || Math.abs(b[3]) - Math.abs(a[3])).slice(0, 8)
  const major = META.major.slice(0, 6)

  return (
    <>
        <div className="grid g4">
          <div className="kpi">
            <span className="kpi-l">Ошибка ансамбля, {H} мес. <Info tip="Средняя абсолютная ошибка (MAE), рубли на жителя: 2 016 муниципалитетов × 6 категорий; даты прогноза 2023-12…2024-11." /></span>
            <span className="kpi-v">{fmt0(ens.MAE)}<small>₽</small></span>
            <span className="kpi-d">Prophet — {fmt0(pro.MAE)} ₽, <b className="good">−{pct(1 - ens.MAE / pro.MAE, 0)}</b></span>
          </div>
          <div className="kpi">
            <span className="kpi-l">R² ансамбля</span>
            <span className="kpi-v">{fmt3(ens.R2)}</span>
            <span className="kpi-d">WAPE {fmt2(ens.WAPE)} %, у Prophet {fmt2(pro.WAPE)} %</span>
          </div>
          <div className="kpi">
            <span className="kpi-l">Найденные сдвиги <Info tip="Доля искусственных сдвигов, найденных в реальных рядах в месяц сдвига или два следующих." /></span>
            <span className="kpi-v">{pct(Number(det.recall), 0)}</span>
            <span className="kpi-d">верных сигналов на искусственных сдвигах {pct(Number(det.precision), 0)}, ложных сигналов {fmt1(Number(det.fa_per_100))} на 100 рядов за месяц</span>
          </div>
          <div className="kpi">
            <span className="kpi-l">Сигналы, {monthShort(months.length - 1)}</span>
            <span className="kpi-v">{fmt0(last)}</span>
            <span className="kpi-d">месяцем раньше — {fmt0(prev)}</span>
          </div>
        </div>
        <div className="grid g2">
          <Card title="Ошибка ансамбля ниже, чем у Prophet" sub="Средняя абсолютная ошибка на жителя по срокам прогноза">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {HORIZONS.map((h) => {
                const a = metric('ensemble', h).MAE, b = metric('prophet_default', h).MAE
                const mx = Math.max(...HORIZONS.map((x) => metric('prophet_default', x).MAE))
                return (
                  <div key={h} style={{ display: 'grid', gridTemplateColumns: '56px minmax(0,1fr) 52px', gap: 10, alignItems: 'center', opacity: h === H ? 1 : 0.75 }}>
                    <span style={{ fontWeight: h === H ? 600 : 400 }}>{h} мес.</span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ height: 8, borderRadius: 4, width: `${(100 * a) / mx}%`, background: 'var(--m-ensemble)' }} data-tip={`Ансамбль: ${fmt0(a)} ₽`} />
                      <div style={{ height: 8, borderRadius: 4, width: `${(100 * b) / mx}%`, background: 'var(--m-prophet)' }} data-tip={`Prophet: ${fmt0(b)} ₽`} />
                    </div>
                    <b className="good" style={{ textAlign: 'right' }}>−{pct(1 - a / b, 0)}</b>
                  </div>
                )
              })}
              <div className="legend small"><span><span className="dot" style={{ background: 'var(--m-ensemble)' }} />Ансамбль</span><span><span className="dot" style={{ background: 'var(--m-prophet)' }} />Prophet</span></div>
            </div>
          </Card>
          <Card title="Сигналы по месяцам" sub="Сигналы основного детектора по всем рядам после фильтрации">
            <MonthBars values={months} color="var(--warn)" />
          </Card>
          <Card title="Последние сигналы" extra={<button className="btn ghost" onClick={() => useApp.getState().go('risk')}>Все сигналы</button>}>
            <div className="feed">
              {fresh.map((a, k) => {
                const m = mo(a[0])
                return (
                  <button key={k} className="feed-i" onClick={() => openMo(a[0])}>
                    <span className="feed-t">{monthShort(a[2])}</span>
                    <span style={{ minWidth: 0 }}><div className="feed-n">{m?.name}</div><div className="feed-s"><span className="dot" style={{ background: catColor(a[1]), width: 7, height: 7, marginRight: 6 }} />{CAT_SHORT[a[1]]} · {m?.region}</div></span>
                    <span className={`tag ${a[3] < 0 ? 'warn' : 'ok'}`}>{a[3] < 0 ? 'спад' : 'рост'}</span>
                  </button>
                )
              })}
            </div>
          </Card>
          <Card title="Крупные события" sub="Субъекты с наибольшим числом новостей о бедствиях; изменение трат в процентах к ожидаемому уровню">
            <div className="feed">
              {major.map((r, k) => (
                <div key={k} className="feed-i" style={{ gridTemplateColumns: '58px minmax(0,1fr) auto' }}>
                  <span className="feed-t">{monthShort(META.periods.indexOf(String(r.period)))}</span>
                  <span style={{ minWidth: 0 }}><div className="feed-n">{regionName(String(r.region_key))}</div><div className="feed-s">{fmt0(Number(r.disaster_news))} новостей · сигналов до {fmt0(Number(r.alarms_3m_before))}, после {fmt0(Number(r.alarms_3m_after))}</div></span>
                  <span className={`tag ${Number(r['Здоровье']) < 0 ? 'warn' : ''}`} data-tip="Здоровье, % к ожиданию">{fmt1(Number(r['Здоровье']))} %</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
    </>
  )
}
