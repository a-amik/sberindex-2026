import { useMemo, useState } from 'react'
import { Card, Seg } from '../../components/ui'
import { ACTION, BIZ_CAT, regionStats, strengthWord } from '../../data/biz'
import { ALARMS, META, mo, monthIn } from '../../data/real'
import { fmt0, fmt1 } from '../../lib/util'
import { useApp } from '../../store'
import { ShocksBody } from '../Shocks'

const pp = (x: number) => `${x > 0 ? '+' : '−'}${fmt1(Math.abs(x * 100))} %`

/** Сигналы словами: где спрос резко ушёл от обычного, насколько, с новостью ли, что сделать. */
// Склонение по числу: 1 просадка, 2 просадки, 5 просадок.
const plural = (n: number, f: [string, string, string]) => {
  const a = n % 100, b = n % 10
  return a > 10 && a < 20 ? f[2] : b === 1 ? f[0] : b > 1 && b < 5 ? f[1] : f[2]
}

export function Risks() {
  const { cat, role, openMo, mode } = useApp()
  const [span, setSpan] = useState<3 | 6 | 12>(6)
  const [dir, setDir] = useState<'all' | 'down' | 'up'>('down')
  const T = META.periods.length
  const rows = useMemo(() => ALARMS.filter((a) => a[1] === cat && a[2] >= T - span && a[6] !== null && (dir === 'all' || (dir === 'down' ? a[6]! < 0 : a[6]! > 0)))
    .sort((a, b) => b[2] - a[2] || Math.abs(b[6]!) - Math.abs(a[6]!)), [cat, span, dir])
  const regions = new Map<string, number>()
  for (const a of rows) { const r = mo(a[0])!.region; regions.set(r, (regions.get(r) ?? 0) + 1) }
  const top = [...regions].sort((a, b) => b[1] - a[1]).slice(0, 5)
  const withNews = rows.filter((a) => a[4] || a[5]).length
  const target = useApp((s) => s.target)
  const { list } = regionStats(cat, role, undefined, target)

  return (
    <div className="page-main sc" style={{ flex: 1 }}>
      <div className="page-in" style={{ maxWidth: 1040 }}>
        <h1 className="page-h">Риски</h1>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Seg value={dir} onChange={setDir} items={[['down', 'Просадки'], ['up', 'Всплески'], ['all', 'Все']]} />
          <Seg value={span} onChange={setSpan} items={[[3, '3 месяца'], [6, 'Полгода'], [12, 'Год']]} />
        </div>
        <div className="hero">
          <h2>{rows.length ? `${rows.length} ${plural(rows.length, dir === 'up' ? ['всплеск', 'всплеска', 'всплесков'] : dir === 'down' ? ['просадка', 'просадки', 'просадок'] : ['резкий сдвиг', 'резких сдвига', 'резких сдвигов'])} спроса в категории «${BIZ_CAT[cat]}» за ${span === 12 ? 'год' : span === 6 ? 'полгода' : 'три месяца'}` : 'Сигналов о сдвигах нет'}</h2>
          {rows.length > 0 && <p>Для {fmt0((100 * withNews) / rows.length)} % сигналов есть новость о событии в муниципалитете или регионе. Больше всего сигналов в регионах: {top.map(([r, n]) => `${r} (${n})`).join(', ')}.</p>}
        </div>
        {mode === 'pro' ? <ShocksBody /> : <Card title="Сигналы" sub="Изменение месячных трат к обычному уровню с учётом похожих муниципалитетов">
          <div className="feed">
            {rows.slice(0, 60).map((a, k) => {
              const m = mo(a[0])!
              const up = a[6]! > 0
              const reg = list.find((r) => r.rk === m.rk)
              return (
                <button key={k} className="feed-i" style={{ gridTemplateColumns: 'minmax(0,1fr) auto', alignItems: 'start', padding: '12px 2px' }} onClick={() => openMo(a[0])}>
                  <span style={{ minWidth: 0 }}>
                    <div className="say"><b>{m.name}</b>, {m.region}: {strengthWord(a[6]!)} {up ? 'рост' : 'спад'} трат в {monthIn(a[2])}</div>
                    <div className="feed-s" style={{ marginTop: 3 }}>
                      {a[4] ? 'Есть новость по муниципалитету. ' : a[5] ? 'Есть новость по региону. ' : 'Новостей нет; проверьте причину. '}
                      {!up ? ACTION[role] + '.' : 'Проверьте, не разовый ли это всплеск: праздник, событие, открытие.'}
                      {reg && reg.rec === 'blind' ? ' Мало данных по региону.' : ''}
                    </div>
                  </span>
                  <span className={`tag ${up ? 'ok' : 'warn'}`} style={{ marginTop: 2 }}>{pp(a[6]!)}</span>
                </button>
              )
            })}
            {rows.length > 60 && <p className="small" style={{ padding: 10 }}>Показаны 60 последних из {rows.length}</p>}
          </div>
        </Card>}
      </div>
    </div>
  )
}
