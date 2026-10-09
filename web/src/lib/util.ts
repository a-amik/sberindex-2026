// Детерминированный генератор: та же территория — тот же ряд при любой перезагрузке.
export function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function hash(...xs: (number | string)[]) {
  let h = 2166136261
  for (const x of xs) {
    const s = String(x)
    for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
    h = Math.imul(h ^ 124, 16777619)
  }
  return h >>> 0
}

export function gauss(r: () => number) {
  const u = Math.max(1e-9, r())
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r())
}

const nf0 = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1, minimumFractionDigits: 1 })
const nf2 = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2, minimumFractionDigits: 2 })
export const fmt0 = (x: number) => (Number.isFinite(x) ? nf0.format(x) : '—')
export const fmt1 = (x: number) => (Number.isFinite(x) ? nf1.format(x) : '—')
const nf3 = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3, minimumFractionDigits: 3 })
export const fmt3 = (x: number) => (Number.isFinite(x) ? nf3.format(x) : '—')
export const fmt2 = (x: number) => (Number.isFinite(x) ? nf2.format(x) : '—')
export const pct = (x: number, d = 1) => (Number.isFinite(x) ? (d ? nf1 : nf0).format(x * 100) + ' %' : '—')
export const signed = (x: number, f = fmt1) => (Number.isFinite(x) ? (x > 0 ? '+' : x < 0 ? '−' : '') + f(Math.abs(x)) : '—')

export const mean = (a: ArrayLike<number>) => {
  let s = 0, n = 0
  for (let i = 0; i < a.length; i++) if (Number.isFinite(a[i])) { s += a[i]; n++ }
  return n ? s / n : NaN
}
export const median = (a: number[]) => {
  const b = a.filter(Number.isFinite).sort((x, y) => x - y)
  if (!b.length) return NaN
  const m = b.length >> 1
  return b.length % 2 ? b[m] : (b[m - 1] + b[m]) / 2
}
export const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x))
