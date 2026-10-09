import { useEffect, useState } from 'react'
import { Card, Table } from '../components/ui'
import { HOUSING_TEST, loadHousing } from '../data/layers'
import { MOS } from '../data/real'
import { fmt0, fmt2, signed } from '../lib/util'

// «Стройка и спрос» — проверка гипотезы участника: сданное жильё меняет расходы территории
// (scripts/20_housing.py, каталог наш.дом.рф). Показано то, что проверено, и то, что не доказано.
export const HYP_NAV: [string, string][] = [['h-sum', 'Жильё и рост трат'], ['h-dose', 'Объём жилья и рост трат'], ['h-cat', 'По категориям'], ['h-event', 'До и после ввода жилья'], ['h-anch', 'АЗС, офисы, торговые центры'], ['h-lim', 'Ограничения']]

const CAT: Record<string, string> = { 'Все категории': 'Все покупки', 'Продовольствие': 'Продукты', 'Общественное питание': 'Кафе и рестораны', 'Маркетплейсы': 'Маркетплейсы', 'Здоровье': 'Здоровье и аптеки', 'Транспорт': 'Транспорт' }

// Якоря — scripts/21_anchors.py по выгрузке OpenStreetMap: срез плотности и объекты, появившиеся на карте в 2023 году.
type Fit = { cat: string; kind: string; coef: number; se: number; p: number; n: number; with?: number }
type Anchors = { objects: Record<string, number>; new23: Record<string, number>; cross: Fit[]; new: Fit[]; housing_check: { coef: number; se: number; p: number } }
const KIND: Record<string, string> = { fuel: 'АЗС', office: 'Офисные центры', mall: 'Торговые центры' }
// Проверок 36 (3 вида × 6 категорий × 2 разреза): при p < 0,05 две «находки» выпали бы случайно.
// Поправка Бонферрони — порог 0,05 / 36.
const STRICT = 0.05 / 36

export function HypBody() {
  const [, tick] = useState(0)
  const [A, setA] = useState<Anchors | null>(null)
  useEffect(() => { fetch('/data/anchors.json').then((r) => r.json()).then(setA).catch(() => null) }, [])
  useEffect(() => { if (!HOUSING_TEST) loadHousing((id) => MOS.find((m) => m.id === id)?.name ?? `Муниципалитет ${id}`).then(() => tick(1)).catch(() => tick(-1)) }, [])
  const T = HOUSING_TEST
  if (!T) return <Card title="Стройка и спрос"><p className="small">Загружаем проверку…</p></Card>
  const all = T.regression.find((r) => r.cat === 'Все категории')!
  const mx = Math.max(...all.dose.map((d) => Math.abs(d[1])))
  const ev = T.event.mean.map((v) => v ?? 0), emx = Math.max(...ev.map(Math.abs), 0.5)
  return (
    <>
      <div className="hero" id="h-sum">
        <h2>Где ввели жильё, траты в следующем году растут быстрее, чем у похожих территорий</h2>
        <p>Каждый квадратный метр введённого жилья на жителя связан с прибавкой к росту трат {signed(all.coef, fmt2)} п. п. (± {fmt2(all.se)}, p = {fmt2(all.p)}). Проверено на {fmt0(all.n)} муниципалитетах: ввод жилья в 2023 году сравниваем с изменением трат в 2024 году в пределах одного региона, с поправкой на размер и долю горожан. p — вероятность получить такую или более сильную связь, если связи нет.</p>
        <p className="small">Использование в прогнозе: для строящихся домов с плановым вводом в 2025—2027 годах прибавка {T.uplift_used ? 'рассчитана для каждого муниципалитета со стройкой' : 'не используется, связь статистически незначима'}. Слой «Строящееся жильё» — в «Регионах».</p>
      </div>
      <Card id="h-dose" title="Как рост трат связан с объёмом жилья" sub="Изменение относительного уровня трат муниципалитета среди похожих территорий за год, п. п., по объёму введённого жилья на жителя">
        <div className="hbars">
          {all.dose.map(([g, v, n]) => (
            <div key={g} data-tip={`Муниципалитетов: ${n}`}><span>{g === 'нет' ? 'жильё не вводили' : `${g} кв. м`}</span><i><em style={{ width: `${(50 * Math.abs(v)) / mx}%`, left: v < 0 ? `${50 - (50 * Math.abs(v)) / mx}%` : '50%', background: v < 0 ? 'var(--warn)' : 'var(--ok)' }} /></i><b>{signed(v, fmt2)}</b></div>
          ))}
        </div>
        <p className="small" style={{ marginTop: 8 }}>После 0,5 кв. м на жителя рост перестаёт ускоряться: новые покупатели появляются по мере заселения.</p>
      </Card>
      <Card id="h-cat" title="По категориям" sub="Связь роста трат с 1 кв. м введённого жилья на жителя; считаем связь статистически значимой при p < 0,05">
        <Table rows={T.regression} sort={['c', -1]} cols={[
          { key: 'n', title: 'Категория', get: (r) => CAT[r.cat] ?? r.cat },
          { key: 'c', title: 'Эффект, п. п.', num: true, get: (r) => r.coef, render: (r) => `${signed(r.coef, fmt2)} ± ${fmt2(r.se)}` },
          { key: 'p', title: 'p', num: true, get: (r) => r.p, render: (r) => fmt2(r.p) },
          { key: 's', title: 'Вывод', get: (r) => r.p, render: (r) => (r.p < 0.05 ? <span className="tag ok">доказано</span> : r.p < 0.1 ? <span className="tag">на грани</span> : <span className="tag warn">не доказано</span>) },
        ]} />
      </Card>
      <Card id="h-event" title="До и после ввода жилья" sub={`${T.event.n} кварталов с крупным вводом жилья (больше 0,5 кв. м на жителя): относительный уровень трат муниципалитета среди похожих территорий, п. п., к месяцу перед сдачей`}>
        <div className="evbars">
          {ev.map((v, i) => (
            <div key={i} data-tip={`${T.event.k[i] > 0 ? '+' : ''}${T.event.k[i]} мес.: ${signed(v, fmt2)} п. п.`}>
              <div><i style={{ top: v >= 0 ? `${50 - (50 * v) / emx}%` : '50%', height: `${(50 * Math.abs(v)) / emx}%`, background: T.event.k[i] < 0 ? 'var(--text-3)' : 'var(--accent)' }} /><s /></div>
              <span>{T.event.k[i] > 0 ? '+' : ''}{T.event.k[i]}</span>
            </div>
          ))}
        </div>
        <p className="small" style={{ marginTop: 8 }}>Серым показаны месяцы до ввода жилья, зелёным — после. После ввода траты выше на 1—2 п. п., а до него они уже снижались — см. ограничения.</p>
      </Card>
      <Card id="h-anch" title="АЗС, офисы, торговые центры: гипотеза не подтвердилась" sub="Проверяем рост трат там, где больше объектов на жителя или где они появились в 2023 году. Поправки те же, что для жилья; дополнительно учитываем ввод жилья и полноту карты">
        {!A ? <p className="small">Загружаем проверку…</p> : (
          <>
            <p className="small" style={{ marginTop: 0 }}>На карте {fmt0(A.objects.fuel)} АЗС, {fmt0(A.objects.office)} офисных и {fmt0(A.objects.mall)} торговых центров; в 2023 году появились {fmt0(A.new23.fuel)}, {fmt0(A.new23.office)} и {fmt0(A.new23.mall)}. В той же выборке связь с жильём по-прежнему статистически значима: {signed(A.housing_check.coef, fmt2)} ± {fmt2(A.housing_check.se)} п. п., p = {fmt2(A.housing_check.p)}.</p>
            <Table rows={A.cross.map((c) => ({ c, n: A.new.find((x) => x.cat === c.cat && x.kind === c.kind)! }))} sort={['p', 1]} cols={[
              { key: 'k', title: 'Объект', get: (r) => KIND[r.c.kind] },
              { key: 'cat', title: 'Категория', get: (r) => CAT[r.c.cat] ?? r.c.cat },
              { key: 'x', title: 'Плотность, п. п.', num: true, get: (r) => r.c.coef, render: (r) => <span data-tip={`p = ${fmt2(r.c.p)}`}>{signed(r.c.coef, fmt2)} ± {fmt2(r.c.se)}</span> },
              { key: 'nw', title: 'Новые в 2023 году, п. п.', num: true, get: (r) => r.n.coef, render: (r) => <span data-tip={`p = ${fmt2(r.n.p)}; муниципалитетов с новыми — ${r.n.with}`}>{signed(r.n.coef, fmt2)} ± {fmt2(r.n.se)}</span> },
              { key: 'p', title: 'Наименьшее p', num: true, get: (r) => Math.min(r.c.p, r.n.p), render: (r) => fmt2(Math.min(r.c.p, r.n.p)) },
              { key: 'v', title: 'Вывод', get: (r) => Math.min(r.c.p, r.n.p), render: (r) => { const p = Math.min(r.c.p, r.n.p); return p < STRICT ? <span className="tag ok">доказано</span> : p < 0.05 ? <span className="tag" data-tip="p ниже 0,05; при 36 проверках такая связь может быть случайной">случайность не исключена</span> : <span className="tag warn">не доказано</span> } },
            ]} />
            <p className="small" style={{ marginBottom: 0 }}>Ни одна связь не проходит строгий порог: при 36 проверках и обычном p &lt; 0,05 две связи можно найти случайно. Ближе всего к порогу новые АЗС в транспорте и общепите. Связь скорее объясняется выручкой станции от топлива и кафе, чем ростом трат вокруг неё. Офисные и торговые центры не связаны с ростом трат. Дату появления объекта определяем по году, когда его нанесли на карту; дата открытия может отличаться.</p>
          </>
        )}
      </Card>
      <Card id="h-lim" title="Ограничения">
        <ul className="small" style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6 }}>
          <li>Часть прибавки возникает при расчёте: новые жители уже тратят в муниципалитете, а численность, на которую делим траты, обновляется с задержкой.</li>
          <li>За 4—6 месяцев до ввода жилья траты таких муниципалитетов снижаются на 0,9—1,7 п. п. Территории со стройкой различались ещё до ввода, поэтому сравнение не доказывает причинную связь.</li>
          <li>Проверка на двух годах данных: 2023 и 2024. Регрессия устойчива к выбросам площади (исключены 0,5 % наибольших значений площади), но не к смене методики каталога.</li>
          <li>Риск недостроя учитываем приблизительно: исключаем проблемные дома, дома с истёкшим сроком ввода относим к плановому году.</li>
        </ul>
      </Card>
    </>
  )
}
