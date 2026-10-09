import { useState } from 'react'
import { Bars, LineChart } from '../components/charts'
import { Card, CatChips, Seg, Table } from '../components/ui'
import { HORIZONS, type Horizon } from '../data/calendar'
import { MODELS, modelLabel } from '../data/models'
import { CAT_SHORT, catColor, META } from '../data/real'
import { fmt0, fmt1, fmt2, pct } from '../lib/util'
import { useApp } from '../store'
import { metric } from './Overview'

type M = 'MAE' | 'WAPE' | 'R2'
const fmtM = (m: M) => (v: number) => (m === 'MAE' ? fmt0(v) : m === 'WAPE' ? fmt1(v) + ' %' : fmt2(v))
const NAV: [string, string][] = [['vs', 'Сравнение с Prophet'], ['h', 'По срокам прогноза'], ['cat', 'По категориям'], ['ens', 'Выбор моделей ансамбля'], ['all', 'Все модели'], ['fwd', 'Прогноз на 2025 год']]

export const MODELS_NAV = NAV

export function ModelsBody() {
  const { H, set } = useApp()
  const [m, setM] = useState<M>('MAE')
  const vals = MODELS.map((x) => metric(x.real, H)[m])
  const best = m === 'R2' ? Math.max(...vals) : Math.min(...vals)
  const gain = (real: string, h: number) => 1 - metric(real, h).MAE / metric('prophet_default', h).MAE
  const all = META.byH.filter((r) => r.H === H)
  const [fc, setFc] = useState(0)
  const chk = META.fwdCheck.filter((r) => r.cat === META.cats[fc])
  const chkMae = (c: string) => { const r = META.fwdCheck.filter((x) => x.cat === c && x.nat_yoy !== null); return r.reduce((a, x) => a + Math.abs(x.fc_yoy - x.nat_yoy!), 0) / r.length }

  return (
    <>
      <div className="page-tools"><Seg label="Горизонт" value={H} onChange={(v: Horizon) => set({ H: v })} items={HORIZONS.map((h) => [h, `${h} мес.`])} /></div>
      <Card id="vs" title={`Сравнение с Prophet, ${H} мес.`} sub="12 096 полных рядов: 2 016 муниципалитетов × 6 категорий; ошибка на горизонте — средняя по шагам 1…H"
        extra={<Seg value={m} onChange={setM} items={[['MAE', 'MAE'], ['WAPE', 'WAPE'], ['R2', 'R²']]} />}>
        <Bars fmt={fmtM(m)} ref0={metric('prophet_default', H)[m]} refName="Prophet, базовая модель"
          rows={MODELS.map((x) => ({ name: x.name, v: metric(x.real, H)[m], color: x.color, best: metric(x.real, H)[m] === best }))} />
        <p className="small" style={{ marginTop: 10 }}>{m === 'R2' ? 'Выше — лучше' : 'Ниже — лучше'}; пунктир обозначает Prophet. MAE — средняя абсолютная ошибка, WAPE — ошибка в процентах от фактических трат, R² — доля разброса, которую объясняет модель.</p>
      </Card>
      <Card id="h" title="Ошибка по срокам прогноза" sub={`Средняя абсолютная ошибка, ₽ на жителя; последняя колонка — снижение ошибки по сравнению с Prophet на ${H} мес.`}>
        <Table rows={MODELS} sort={['g', -1]} rowClass={(x) => (x.key === 'strict' ? 'best' : '')} cols={[
          { key: 'n', title: 'Модель', get: (x) => x.name, render: (x) => <span className="nw"><span className="dot" style={{ background: x.color }} />{x.name}</span> },
          { key: 'k', title: 'Класс', get: (x) => x.kind },
          ...HORIZONS.map((h) => ({ key: `h${h}`, title: `${h} мес.`, num: true, get: (x: (typeof MODELS)[number]) => metric(x.real, h).MAE, render: (x: (typeof MODELS)[number]) => fmt0(metric(x.real, h).MAE) })),
          { key: 'g', title: 'К Prophet', num: true, get: (x) => gain(x.real, H), render: (x) => { const g = gain(x.real, H); return <span className={g > 0.001 ? 'good' : ''}>{g > 0.001 ? '−' : ''}{pct(Math.abs(g), 0)}</span> } },
        ]} />
      </Card>
      <Card id="cat" title={`По категориям, ${H} мес.`} sub="Средняя абсолютная ошибка, ₽ на жителя; в каждой строке выделена модель с наименьшей ошибкой">
        <Table rows={META.cats.map((c, i) => ({ c, i }))} sort={['c', 1]} cols={[
          { key: 'c', title: 'Категория', get: (r) => r.i, render: (r) => <span className="nw"><span className="dot" style={{ background: catColor(r.i) }} />{CAT_SHORT[r.i]}</span> },
          ...MODELS.map((x) => ({
            key: x.key, title: x.short, num: true,
            get: (r: { c: string }) => META.byCat.find((b) => b.model === x.real && b.H === H && b.category === r.c)?.MAE ?? NaN,
            render: (r: { c: string }) => {
              const v = META.byCat.find((b) => b.model === x.real && b.H === H && b.category === r.c)?.MAE ?? NaN
              const b = Math.min(...MODELS.map((y) => META.byCat.find((q) => q.model === y.real && q.H === H && q.category === r.c)?.MAE ?? Infinity))
              return <span style={{ fontWeight: v === b ? 600 : 400, color: v === b ? 'var(--accent-press)' : undefined }}>{fmt0(v)}</span>
            },
          })),
        ]} />
      </Card>
      <Card id="ens" title="Как выбирали модели ансамбля" sub="Кандидаты ансамбля и Prophet: средняя абсолютная ошибка на всех рядах и на итоговой выборке">
        <Table rows={META.ensemble.filter((r) => r.H === H)} sort={['a', 1]} cols={[
          { key: 'n', title: 'Модель', get: (r) => modelLabel(r.model)[0] },
          { key: 'a', title: 'MAE, все ряды', num: true, get: (r) => r.MAE_all, render: (r) => fmt0(r.MAE_all) },
          { key: 'r', title: 'MAE, итоговая выборка', num: true, get: (r) => r.MAE_report ?? NaN, render: (r) => (r.MAE_report === null ? '—' : fmt0(r.MAE_report)) },
        ]} />
      </Card>
      <Card id="all" title={`Все модели, ${H} мес.`} sub={`${all.length} моделей проверены на истории; выделены модели, которые видны на графиках территории`}>
        <Table rows={all} sort={['mae', 1]} rowClass={(r) => (MODELS.some((x) => x.real === r.model) ? 'best' : '')} cols={[
          { key: 'n', title: 'Модель', get: (r) => modelLabel(r.model)[0], render: (r) => <span data-tip={r.model}>{modelLabel(r.model)[0]}</span> },
          { key: 'k', title: 'Класс', get: (r) => modelLabel(r.model)[1] },
          { key: 'mae', title: 'MAE', num: true, get: (r) => r.MAE, render: (r) => fmt0(r.MAE) },
          { key: 'w', title: 'WAPE', num: true, get: (r) => r.WAPE, render: (r) => fmt2(r.WAPE) + ' %' },
          { key: 'r2', title: 'R²', num: true, get: (r) => r.R2, render: (r) => fmt2(r.R2) },
          { key: 'g', title: 'К Prophet', num: true, get: (r) => 1 - r.MAE / metric('prophet_default', H).MAE, render: (r) => { const g = 1 - r.MAE / metric('prophet_default', H).MAE; return <span className={g > 0 ? 'good' : g < 0 ? 'bad' : ''}>{g > 0 ? '−' : g < 0 ? '+' : ''}{pct(Math.abs(g), 0)}</span> } },
        ]} />
        <button className="btn ghost" style={{ marginTop: 12 }} onClick={() => useApp.getState().go('reg')}>Смотреть прогнозы на карте</button>
      </Card>
      <Card id="fwd" title="Прогноз на 2025 год и сверка с РФ" sub="Прогноз ансамбля из декабря 2024 года на 12 месяцев. Данных по муниципалитетам за 2025 год ещё нет; сравниваем с недельным рядом СберИндекса по стране — годовой рост, %"
        extra={<CatChips value={fc} onChange={setFc} />}>
        <LineChart n={12} x0={24} height={220} yFmt={fmt0} lines={[
          { key: 'f', name: 'Прогноз ансамбля', color: 'var(--m-ensemble)', v: chk.map((r) => r.fc_yoy) },
          { key: 'n', name: `РФ, ${chk[0]?.series.trim() ?? ''}`, color: 'var(--text-2)', v: chk.map((r) => r.nat_yoy ?? NaN), dash: true },
        ]} />
        <div style={{ height: 12 }} />
        <Table rows={META.cats.map((c, i) => ({ c, i }))} sort={['m', 1]} cols={[
          { key: 'c', title: 'Категория', get: (r) => r.i, render: (r) => <span className="nw"><span className="dot" style={{ background: catColor(r.i) }} />{CAT_SHORT[r.i]}</span> },
          { key: 's', title: 'Ряд РФ', get: (r) => META.fwdCheck.find((x) => x.cat === r.c)?.series.trim() ?? '' },
          { key: 'm', title: 'Расхождение, п. п.', num: true, tip: 'Средняя разница годового роста за 12 месяцев между прогнозом и рядом РФ', get: (r) => chkMae(r.c), render: (r) => fmt1(chkMae(r.c)) },
        ]} />
        <p className="small" style={{ marginTop: 8 }}>Ряд РФ шире набора муниципалитетов, поэтому расхождение помогает оценить прогноз, но не даёт строго измерить ошибку.</p>
      </Card>
    </>
  )
}
