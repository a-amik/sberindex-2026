// Контур России для карты: берём из world-atlas (Natural Earth 1:50m) и кладём
// в public/data, чтобы образ работал без интернета.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { feature } from 'topojson-client'

const out = new URL('../public/data/russia.json', import.meta.url)
if (!existsSync(out)) {
  const topo = JSON.parse(readFileSync(new URL('../node_modules/world-atlas/countries-50m.json', import.meta.url)))
  const all = feature(topo, topo.objects.countries)
  const ru = all.features.find((f) => f.id === '643')
  // Координаты до 0,01°: точнее карте такого масштаба не нужно.
  const round = (c) => (typeof c[0] === 'number' ? [Math.round(c[0] * 100) / 100, Math.round(c[1] * 100) / 100] : c.map(round))
  ru.geometry.coordinates = round(ru.geometry.coordinates)
  writeFileSync(out, JSON.stringify({ type: 'Feature', properties: {}, geometry: ru.geometry }))
}
