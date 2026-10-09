// Слои карты (web/scripts/layers.py): точки — порты, аэропорты, добыча, пункты пропуска;
// области — моногорода и приграничье. Включённый слой — и значки, и фильтр МО и регионов.
export interface Layer { key: string; name: string; note: string; source: string; kind: 'point' | 'area'; items: (number | string)[][]; total?: number }
export let LAYERS: Layer[] = []
export let LAYER_MO: Record<string, string[]> = {}
export const loadLayers = () => fetch('/data/layers.json').then((r) => r.json()).then((j) => { LAYERS = j.layers; LAYER_MO = j.mo })

export const LAYER_STYLE: Record<string, { color: string; glyph: string }> = {
  port: { color: '#0091D8', glyph: '⚓' },
  airport: { color: '#7c4dff', glyph: '✈' },
  mine: { color: '#8d6e63', glyph: '⛏' },
  field: { color: '#455a64', glyph: '◆' },
  border_pt: { color: '#dc2626', glyph: '⊕' },
  mono: { color: '#d97706', glyph: '◼' },
  border: { color: '#dc2626', glyph: '▤' },
  housing: { color: '#475569', glyph: '⌂' },
}

/** МО, у которых есть хотя бы один из включённых слоёв. */
export const moHas = (id: number, active: string[]) => (LAYER_MO[id] ?? []).some((k) => active.includes(k))

// Строящееся жильё (scripts/20_housing.py, каталог наш.дом.рф): 11 тыс. домов — значок на МО,
// а не на дом; в подсказке — сколько строят, кто, когда сдача, чем рискует и что даст расходам.
// Файл весит 2 МБ, поэтому грузится по первому включению слоя.
export const HOUSING = 'housing'
export let HOUSING_TEST: { regression: { cat: string; coef: number; se: number; p: number; n: number; dose: [string, number, number][] }[]; event: { n: number; k: number[]; mean: (number | null)[]; se: (number | null)[] }; uplift_used: boolean } | null = null
export let HOUSING_UPLIFT: Record<string, Record<string, number>> = {}
let housingP: Promise<void> | null = null
export const loadHousing = (moName: (id: number) => string) => (housingP ??= fetch('/data/housing.json').then((r) => r.json()).then((j) => {
  HOUSING_TEST = j.test
  HOUSING_UPLIFT = j.uplift
  const by = new Map<number, (string | number | null)[][]>()
  for (const r of j.rows) by.set(r[3], [...(by.get(r[3]) ?? []), r])
  const sq = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1).replace('.', ',')} млн` : `${Math.round(v / 1e3)} тыс.`)
  const items: (number | string)[][] = []
  for (const [mo, rs] of by) {
    const n = (k: number) => rs.reduce((a, r) => a + Number(r[k] ?? 0), 0)
    const risk = (w: string) => rs.filter((r) => r[10] === w).length
    const bad = risk('проблемный'), late = risk('срок сдачи прошёл'), devBad = risk('застройщик с проблемными')
    const up = HOUSING_UPLIFT[mo] ?? {}
    // Крупнейшие комплексы: дома одного ЖК и одного застройщика сведены в строку
    const cx = new Map<string, { r: (string | number | null)[]; n: number; area: number }>()
    for (const r of rs) { const k = `${r[2]}|${r[4]}`; const c = cx.get(k); if (c) { c.n++; c.area += Number(r[8]); if (r[10] !== 'обычный') c.r = r } else cx.set(k, { r, n: 1, area: Number(r[8]) }) }
    const top = [...cx.values()].sort((a, b) => b.area - a.area).slice(0, 4)
    const lon = rs.reduce((a, r) => a + Number(r[0]), 0) / rs.length, lat = rs.reduce((a, r) => a + Number(r[1]), 0) / rs.length
    const tip = [`<b>${moName(mo)}</b>`, `Строится домов: ${rs.length} · ${sq(n(8))} м² · ${n(9).toLocaleString('ru')} кв.`,
      bad || late || devBad ? `<span style="color:var(--warn)">Риск: ${[bad && `проблемных ${bad}`, late && `срок сдачи прошёл у ${late}`, devBad && `застройщик с проблемными у ${devBad}`].filter(Boolean).join(', ')}</span>` : 'Риск: признаков недостроя нет',
      Object.keys(up).length ? `Прибавка к росту расходов: ${Object.entries(up).map(([y, v]) => `${y} — +${v.toFixed(2).replace('.', ',')} п. п.`).join(', ')}` : '',
      ...top.map(({ r, n: k }) => `· ${r[2] ?? 'без названия'}${k > 1 ? ` (${k} дом.)` : ''} — ${r[5] ?? r[4] ?? 'застройщик не указан'}, сдача ${r[6] ? String(r[6]).split('-').reverse().join('.') : 'не указана'}${r[10] !== 'обычный' ? ` (${r[10]}${r[11] ? ': ' + r[11] : ''})` : ''}`),
    ].filter(Boolean).join('<br>')
    items.push([lon, lat, moName(mo), mo, tip, bad ? 2 : late || devBad ? 1 : 0])
  }
  LAYERS = [...LAYERS.filter((l) => l.key !== HOUSING), { key: HOUSING, name: 'Строящееся жильё', note: 'Дома в стройке по каталогу наш.дом.рф; значок — на муниципалитет; красный — есть проблемные дома, жёлтый — срок сдачи прошёл', source: 'наш.дом.рф', kind: 'point', items, total: j.rows.length }]
  for (const mo of by.keys()) LAYER_MO[mo] = [...(LAYER_MO[mo] ?? []).filter((k) => k !== HOUSING), HOUSING]
}))
