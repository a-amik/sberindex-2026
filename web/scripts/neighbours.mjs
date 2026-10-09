// Соседи России для карты — грубо (Natural Earth 1:110m): только чтобы читалось, где граница.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { feature } from 'topojson-client'

const out = new URL('../public/data/neighbours.json', import.meta.url)
if (!existsSync(out)) {
  const topo = JSON.parse(readFileSync(new URL('../node_modules/world-atlas/countries-50m.json', import.meta.url)))
  const NAMES = { 578: 'Норвегия', 246: 'Финляндия', 752: 'Швеция', 233: 'Эстония', 428: 'Латвия', 440: 'Литва', 616: 'Польша', 112: 'Беларусь', 804: 'Украина',
    268: 'Грузия', '031': 'Азербайджан', '051': 'Армения', 398: 'Казахстан', 156: 'Китай', 496: 'Монголия', 408: 'КНДР', 410: 'Корея', 392: 'Япония',
    860: 'Узбекистан', 417: 'Киргизия', 795: 'Туркмения', 762: 'Таджикистан', 792: 'Турция', 364: 'Иран', 498: 'Молдавия', 642: 'Румыния', 840: 'США' }
  const all = feature(topo, topo.objects.countries).features.filter((f) => NAMES[f.id] && f.id !== '840')
  const round = (c) => (typeof c[0] === 'number' ? [Math.round(c[0] * 20) / 20, Math.round(c[1] * 20) / 20] : c.map(round))
  writeFileSync(out, JSON.stringify({ type: 'FeatureCollection', features: all.map((f) => ({ type: 'Feature', properties: { name: NAMES[f.id] }, geometry: { type: f.geometry.type, coordinates: round(f.geometry.coordinates) } })) }))
}
