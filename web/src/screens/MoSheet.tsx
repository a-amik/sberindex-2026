import { useEffect, useMemo, useState } from 'react'
import { LineChart, ScoreStrip, type Line, type Pin } from '../components/charts'
import { I } from '../components/icons'
import { Info, Row, Seg, Table, Wait, useSheetDrag } from '../components/ui'
import { MODELS, MODEL } from '../data/models'
import { META, mo as getMo, monthLong, monthShort, NEWS_TYPE, periodIdx, thr, useShard, type Shard } from '../data/real'
import { fmt0, fmt1, mean, pct } from '../lib/util'
import { DET_INFO, SHOWN, type ShownMethod } from '../model/sbiDetect'
import { useApp } from '../store'

/**
 * Шторка территории: у левого края карты, на телефоне — снизу. Ряд, прогнозы
 * моделей от выбранной точки, коридор Chronos-2, тревоги и новости — настоящие;
 * счёт детектора под графиком — приближение (мокап).
 */
export function MoSheet({ id, onClose }: { id: number; onClose: () => void }) {
  const m = getMo(id)!
  const data = useShard(m.rk)
  const drag = useSheetDrag<HTMLElement>(onClose)
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    addEventListener('keydown', k)
    return () => removeEventListener('keydown', k)
  }, [onClose])
  return (
    <>
      <div className="sheet-scrim" onClick={onClose} />
      <aside ref={drag} className="sheet" role="dialog" aria-label={m.name}>
        <div className="grab" />
        <div className="sheet-h">
          <div className="sheet-t"><h2>{m.name}</h2><p>{m.full !== m.name ? `${m.full}, ` : ''}{m.region}</p></div>
          <button className="icon-btn" aria-label="Закрыть" onClick={onClose}>{I.close}</button>
        </div>
        <div className="sheet-b sc">
          <div className="facts">
            <span className="tag">{m.type}</span>
            {m.pop > 0 && <span className="tag">{fmt0(m.pop)} чел.</span>}
            {m.urban !== null && <span className="tag">горожане {pct(m.urban, 0)}</span>}
          </div>
          {data ? <Body id={id} data={data} /> : <Wait label={`Загружаем ${m.region}…`} />}
        </div>
      </aside>
    </>
  )
}

function Body({ id, data }: { id: number; data: Shard }) {
  const { cat, H, shown, toggleModel } = useApp()
  const y = data.series[id]?.[cat]
  const fc = data.fc[id]?.[cat]
  const band = data.band[id]?.[cat]
  const origins = META.origins
  const [oi, setOi] = useState(Math.max(0, origins.length - H))
  const [method, setMethod] = useState<ShownMethod>(SHOWN.includes(META.detectChoice.lead as ShownMethod) ? META.detectChoice.lead as ShownMethod : 'zscore')
  const origin = origins[Math.min(oi, origins.length - 1)]
  const t0 = periodIdx(origin)
  const n = META.periods.length

  const al = data.alarms.filter((a) => a[0] === id && a[1] === cat)
  const news = data.news.filter((x) => x[4].includes(id))
  const regNews = data.news.filter((x) => !x[4].length)

  const errs = useMemo(() => {
    if (!fc || !y) return []
    return MODELS.map((mm) => {
      const e: number[] = []
      for (const o of origins) {
        const t = periodIdx(o)
        ;(fc[mm.real]?.[o] ?? []).slice(0, H).forEach((v, s) => { const a = y[t + s + 1]; if (a !== null && a !== undefined) e.push(Math.abs(a - v)) })
      }
      return { m: mm, mae: mean(e), wape: (100 * e.reduce((s, x) => s + x, 0)) / origins.reduce((s, o) => s + y.slice(periodIdx(o) + 1, periodIdx(o) + 1 + H).reduce<number>((a, b) => a + (b ?? 0), 0), 0) }
    })
  }, [fc, y, H])

  if (!y) return <p className="muted">Нет данных по этой категории.</p>
  const lines: Line[] = [
    { key: 'fact', name: 'Факт', color: 'var(--text)', v: y.map((v) => v ?? NaN), width: 2.4 },
    ...(fc ? shown.map((k) => ({ key: k, name: MODEL[k].short, color: MODEL[k].color, v: [y[t0] ?? NaN, ...(fc[MODEL[k].real]?.[origin] ?? []).slice(0, H)], from: t0 })) : []),
  ]
  const b = band && shown.includes('chronos') ? { from: t0 + 1, color: 'var(--m-chronos)', lo: (band[0][origin] ?? []).slice(0, H), hi: (band[1][origin] ?? []).slice(0, H) } : undefined
  const pins: Pin[] = [
    ...al.map((a) => ({ t: a[2], kind: 'alarm' as const, color: 'var(--warn)', tip: `<b>Сигнал · ${monthLong(a[2])}</b><br>балл ${fmt1(a[3])}${a[4] ? '<br>есть новость о муниципалитете' : a[5] ? '<br>есть новость по субъекту' : ''}` })),
    ...news.map((x) => ({ t: x[0], kind: 'news' as const, color: 'var(--blue)', tip: `<b>${x[1]}</b><br>${x[2]}` })),
  ]
  const det = data.det[id]?.[cat]
  const best = Math.min(...errs.map((e) => e.mae))

  return (
    <>
      <div>
        <h3>Траты на жителя, ₽ <Info tip="Безналичные траты СберИндекса. Проверка на истории: модель знает только данные до даты прогноза." /></h3>
        <Row>{MODELS.map((mm) => <button key={mm.key} className="chip" aria-pressed={shown.includes(mm.key)} onClick={() => toggleModel(mm.key)}><i style={{ background: mm.color }} />{mm.short}</button>)}</Row>
        <div style={{ marginTop: 10 }}>
          <LineChart n={n} lines={lines} band={b} pins={pins} origin={fc ? t0 : undefined} shade={fc ? [t0, Math.min(n - 1, t0 + H)] : undefined} height={230} />
        </div>
        {fc ? (
          <div className="range" style={{ marginTop: 8 }}>
            <div className="range-top"><span>Дата прогноза</span><b>{monthLong(t0)}</b></div>
            <input type="range" min={0} max={origins.length - 1} value={oi} onChange={(e) => setOi(+e.target.value)} aria-label="Дата прогноза" />
          </div>
        ) : <p className="small">Ряд неполный: модели не проверяли.</p>}
        <div className="legend small" style={{ marginTop: 6 }}>
          <span><span className="dot" style={{ background: 'var(--warn)' }} />сигнал</span>
          <span><span className="dot" style={{ background: 'var(--blue)', borderRadius: 2 }} />новость о муниципалитете</span>
          {b && <span><span className="dot" style={{ background: 'var(--m-chronos)', opacity: 0.35 }} />интервал Chronos-2, 5—95 %</span>}
        </div>
      </div>
      {det && (
        <div>
          <h3>Балл детектора <Info tip={`${DET_INFO[method].note}. Месяц оцениваем по прошлым данным. Пунктир — порог сигнала.${method === META.detectChoice.lead ? ' Основной детектор: сигналы отмечены точками.' : ''}`} /></h3>
          <Seg value={method} onChange={setMethod} items={SHOWN.filter((m) => det.s[m]).map((m) => [m, DET_INFO[m].short])} />
          <div style={{ marginTop: 8 }}><ScoreStrip s={det.s[method] ?? []} thr={thr(method)} n={n} color={DET_INFO[method].color} /></div>
        </div>
      )}
      {fc && (
        <div>
          <h3>Ошибка на {H} мес.</h3>
          <Table rows={errs} sort={['mae', 1]} rowClass={(r) => (r.mae === best ? 'best' : '')} cols={[
            { key: 'n', title: 'Модель', get: (r) => r.m.short, render: (r) => <span className="nw"><span className="dot" style={{ background: r.m.color }} />{r.m.short}</span> },
            { key: 'mae', title: 'MAE, ₽', num: true, get: (r) => r.mae, render: (r) => fmt0(r.mae) },
            { key: 'w', title: 'WAPE', num: true, get: (r) => r.wape, render: (r) => fmt1(r.wape) + ' %' },
          ]} />
        </div>
      )}
      <div>
        <h3>Новости рядом</h3>
        <div className="feed">
          {[...news, ...regNews.slice(-12)].sort((a, b) => b[1].localeCompare(a[1])).slice(0, 10).map((x, k) => (
            <div key={k} className="feed-i" style={{ gridTemplateColumns: '58px minmax(0,1fr)' }}>
              <span className="feed-t">{monthShort(x[0])}</span>
              <span style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13 }}>{x[2]}</div>
                <span style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
                  {x[3].map((t) => <span key={t} className="tag">{NEWS_TYPE[t] ?? t}</span>)}
                  <span className="tag">{x[4].length ? 'о муниципалитете' : 'о субъекте'}</span>
                </span>
              </span>
            </div>
          ))}
          {!news.length && !regNews.length && <p className="small">Размеченных новостей нет</p>}
        </div>
      </div>
    </>
  )
}
