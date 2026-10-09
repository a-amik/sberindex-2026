import { Bars, LineChart } from '../components/charts'
import { Card, Table } from '../components/ui'
import { META } from '../data/real'
import { fmt0, fmt1, fmt2, pct } from '../lib/util'

const NAME: Record<string, string> = {
  zero: 'Без детектора', zscore: 'Устойчивая z‑оценка', panel: 'Сравнение с соседями', cusum: 'CUSUM', bocpd: 'BOCPD', forecast: 'Ошибка прогноза', chronos: 'Интервал Chronos‑2',
  'chronos+valve': 'Chronos‑2 с клапаном', 'chronos&zscore': 'Chronos‑2 и z‑оценка', 'chronos|zscore': 'Chronos‑2 или z‑оценка',
  'zscore+valve': 'z‑оценка с клапаном', 'zscore&bocpd': 'z‑оценка и BOCPD', 'zscore|bocpd': 'z‑оценка или BOCPD',
}
const COLOR: Record<string, string> = { zscore: 'var(--m-ensemble)', cusum: 'var(--m-snaive)', bocpd: 'var(--m-prophet)', panel: 'var(--m-panel)', forecast: 'var(--m-lgbm)', chronos: 'var(--m-chronos)' }
export const detName = (m: string) => NAME[m] ?? m.replace('chronos+pelt', 'Chronos‑2 + PELT').replace('zscore+pelt', 'z‑оценка + PELT').replace('pen=', 'штраф ')
const NAV: [string, string][] = [['sum', 'Сводка'], ['kind', 'По виду сдвига'], ['size', 'По размеру сдвига'], ['early', 'Раннее предупреждение']]
type R = Record<string, number | string | null>
const n = (r: R, k: string) => Number(r[k])

export const DETECT_NAV = NAV

export function DetectBody() {
  const lead = META.detectChoice.lead
  const rows = META.detect.filter((r) => r.method !== 'zero')
  const base = ['chronos', 'zscore', 'cusum', 'bocpd', 'panel', 'forecast']
  const bestF1 = Math.max(...rows.map((r) => n(r, 'f1')))
  const early = META.early
  const name = (r: R) => <span className="nw" data-tip={String(r.method)}>{COLOR[String(r.method)] && <span className="dot" style={{ background: COLOR[String(r.method)] }} />}{detName(String(r.method))}{r.method === lead && <span className="tag ok" style={{ marginLeft: 8 }}>основной</span>}</span>

  return (
    <>
      <Card id="sum" title="Сравнение детекторов по F1" sub="F1 объединяет долю найденных сдвигов и долю верных сигналов. Искусственный сдвиг в реальном ряду считаем найденным, если сигнал появился в его месяц или два следующих">
        <Bars fmt={fmt2} rows={base.map((m) => { const r = rows.find((x) => x.method === m)!; return { name: detName(m), v: n(r, 'f1'), color: COLOR[m], best: m === lead } })} />
        <div style={{ height: 16 }} />
        <Table rows={rows} sort={['f1', -1]} rowClass={(r) => (n(r, 'f1') === bestF1 ? 'best' : '')} cols={[
          { key: 'm', title: 'Детектор', get: (r) => detName(String(r.method)), render: name },
          { key: 'rec', title: 'Найденные сдвиги', num: true, get: (r) => n(r, 'recall'), render: (r) => pct(n(r, 'recall'), 0) },
          { key: 'prec', title: 'Верные сигналы', num: true, get: (r) => n(r, 'precision'), render: (r) => pct(n(r, 'precision'), 0) },
          { key: 'f1', title: 'F1', num: true, get: (r) => n(r, 'f1'), render: (r) => fmt2(n(r, 'f1')) },
          { key: 'fa', title: 'Ложных на 100', num: true, tip: 'Ложные сигналы на 100 рядов за месяц', get: (r) => n(r, 'fa_per_100'), render: (r) => fmt1(n(r, 'fa_per_100')) },
          { key: 'dl', title: 'Задержка', num: true, tip: 'Средняя задержка сигнала, месяцев', get: (r) => n(r, 'delay_mean'), render: (r) => fmt2(n(r, 'delay_mean')) },
          { key: 'x', title: 'Лучше случайных, раз', num: true, tip: 'Во сколько раз лучше случайных сигналов той же частоты', get: (r) => n(r, 'recall_over_random'), render: (r) => `× ${fmt1(n(r, 'recall_over_random'))}` },
        ]} />
      </Card>
      <Card id="kind" title="По виду сдвига" sub="Доля найденных сдвигов: ступень — резкое изменение уровня, всплеск — краткий скачок, плавный сдвиг — постепенное изменение">
        <Table rows={rows} sort={['step', -1]} cols={[
          { key: 'm', title: 'Детектор', get: (r) => detName(String(r.method)), render: name },
          ...[['step', 'Ступень'], ['spike', 'Всплеск'], ['ramp', 'Плавный сдвиг']].map(([k, t]) => ({ key: k, title: t, num: true, get: (r: R) => n(r, `recall_${k}`), render: (r: R) => pct(n(r, `recall_${k}`), 0) })),
        ]} />
      </Card>
      <Card id="size" title="По размеру сдвига" sub="Доля найденных искусственных сдвигов размером 10, 20 и 30 % уровня ряда">
        <Table rows={rows} sort={['s3', -1]} cols={[
          { key: 'm', title: 'Детектор', get: (r) => detName(String(r.method)), render: name },
          ...[['0.1', '10 %'], ['0.2', '20 %'], ['0.3', '30 %']].map(([k, t], i) => ({ key: `s${i + 1}`, title: t, num: true, get: (r: R) => n(r, `recall_size_${k}`), render: (r: R) => pct(n(r, `recall_size_${k}`), 0) })),
        ]} />
      </Card>
      <Card id="early" title="Раннее предупреждение, AUC" sub="AUC показывает, насколько модель за месяц до шока различает ряды с будущим шоком и без него; 0,5 — случайное угадывание">
        <LineChart n={early.length} x0={12} height={220} yFmt={fmt2} lines={[
          { key: 'm', name: 'Модель', color: 'var(--m-ensemble)', v: early.map((r) => n(r, 'auc_model')) },
          { key: 'r', name: 'Правило', color: 'var(--m-prophet)', v: early.map((r) => n(r, 'auc_rule')), dash: true },
        ]} />
        <p className="small" style={{ marginTop: 8 }}>Шоков за год: {fmt0(early.reduce((s, r) => s + n(r, 'positives'), 0))}. Пунктир — простое правило без модели.</p>
      </Card>
    </>
  )
}
