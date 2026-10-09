// Детекторы src/sbi/detect.py, перенесённые один в один: стенд пересчитывает ими
// ряд со вписанным шоком. Сигнал — отклонение логарифма ряда от медианы его
// группы (категория × город или район); масштаб, медиана группы и прыжок соседей
// приходят из выгрузки (web/scripts/export_data.py) — один ряд их не сдвигает.

export type Method = 'zscore' | 'panel' | 'cusum' | 'bocpd' | 'forecast'
export const METHODS: Method[] = ['zscore', 'cusum', 'bocpd', 'panel', 'forecast']
/** Chronos-2 в браузере не считается: его счёт приезжает готовым в данных региона. */
export type ShownMethod = Method | 'chronos'
export const SHOWN: ShownMethod[] = ['chronos', ...METHODS]
export interface Group { name: string; med: number[]; scale: number[]; relmed: number[]; relmad: number[] }
const MIN_HIST = 4

export function signal(y: ArrayLike<number>, g: Group) {
  return Array.from(y, (v, t) => Math.log(v) - g.med[t])
}

function lgamma(x: number): number {
  // Ланцош, g = 7: точности хватает на порядок с запасом.
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7]
  if (x < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1 - x)
  x -= 1
  let a = c[0]
  const t = x + 7.5
  for (let i = 1; i < 9; i++) a += c[i] / (x + i)
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a)
}
const tLogpdf = (x: number, df: number, loc: number, scale: number) =>
  lgamma((df + 1) / 2) - lgamma(df / 2) - 0.5 * Math.log(df * Math.PI) - Math.log(scale) - ((df + 1) / 2) * Math.log(1 + ((x - loc) / scale) ** 2 / df)

/** Онлайн-баллы по месяцам, как run_online: до MIN_HIST — нули. */
export function runOnline(method: Method, y: ArrayLike<number>, g: Group, nb: number[]): number[] {
  const d = signal(y, g)
  const T = d.length
  const out = new Array(T).fill(0)
  if (method === 'zscore') {
    for (let t = MIN_HIST; t < T; t++) {
      const past = d.slice(0, t)
      const mu = past.reduce((s, v) => s + v, 0) / t
      const sd = Math.sqrt(past.reduce((s, v) => s + (v - mu) ** 2, 0) / (t - 1))
      out[t] = Math.abs(d[t] - mu) / Math.max(sd, g.scale[t])
    }
  } else if (method === 'panel') {
    for (let t = MIN_HIST; t < T; t++) {
      const jump = d[t] - (d[t - 3] + d[t - 2] + d[t - 1]) / 3
      out[t] = Math.abs(jump - nb[t] - g.relmed[t]) / g.relmad[t]
    }
  } else if (method === 'cusum') {
    let lvl = NaN, sp = 0, sn = 0
    for (let t = MIN_HIST; t < T; t++) {
      if (Number.isNaN(lvl)) lvl = d.slice(0, t).reduce((s, v) => s + v, 0) / t
      const e = (d[t] - lvl) / g.scale[t]
      sp = Math.max(0, sp + e - 0.5)
      sn = Math.max(0, sn - e - 0.5)
      lvl = 0.7 * lvl + 0.3 * d[t]
      out[t] = Math.max(sp, sn)
    }
  } else if (method === 'forecast') {
    let lvl = NaN
    for (let t = MIN_HIST; t < T; t++) {
      if (Number.isNaN(lvl)) { lvl = d[0]; for (let j = 1; j < t; j++) lvl = 0.5 * d[j] + 0.5 * lvl }
      out[t] = Math.abs(d[t] - lvl) / g.scale[t]
      lvl = 0.5 * d[t] + 0.5 * lvl
    }
  } else {
    // BOCPD (Adams, MacKay 2007), нормальная-гамма; прогрев на t = 0…2, t = 3 пропущен, как в run_online.
    let R: number[] = [], mu: number[] = [], k: number[] = [], a: number[] = [], b: number[] = []
    const step = (x: number) => {
      if (!R.length) { R = [1]; mu = [x]; k = [1]; a = [1]; b = [1]; return 0 }
      const logp = R.map((r, i) => tLogpdf(x, 2 * a[i], mu[i], Math.sqrt((b[i] * (k[i] + 1)) / (a[i] * k[i]))) + Math.log(Math.max(r, 1e-300)))
      const top = Math.max(...logp)
      const w = logp.map((v) => Math.exp(v - top))
      const cp = w.reduce((s, v) => s + v, 0) / 24
      const nr = [cp, ...w.map((v) => v * (1 - 1 / 24))]
      const sum = nr.reduce((s, v) => s + v, 0)
      const mu1 = mu.map((m, i) => (k[i] * m + x) / (k[i] + 1))
      const b1 = b.map((bb, i) => bb + (k[i] * (x - mu[i]) ** 2) / (2 * (k[i] + 1)))
      mu = [x, ...mu1]; k = [1, ...k.map((v) => v + 1)]; a = [1, ...a.map((v) => v + 0.5)]; b = [1, ...b1]
      R = nr.map((v) => v / sum)
      return R[0] + R[1]
    }
    for (let t = 0; t < MIN_HIST - 1; t++) step(d[t] / g.scale[t])
    for (let t = MIN_HIST; t < T; t++) out[t] = step(d[t] / g.scale[t])
  }
  return out
}

export const DET_INFO: Record<ShownMethod, { name: string; short: string; color: string; note: string }> = {
  zscore: { name: 'Робастный z‑счёт', short: 'z‑счёт', color: 'var(--m-ensemble)', note: 'Отклонение месяца от среднего своей истории в единицах разброса' },
  cusum: { name: 'CUSUM', short: 'CUSUM', color: 'var(--m-snaive)', note: 'Копит отклонения одного знака' },
  chronos: { name: 'Chronos-2', short: 'Chronos', color: 'var(--m-chronos)', note: 'Выход месяца за коридор прогноза Chronos-2' },
  bocpd: { name: 'BOCPD', short: 'BOCPD', color: 'var(--m-prophet)', note: 'Вероятность, что режим сменился в этом или прошлом месяце' },
  panel: { name: 'Отрыв от соседей', short: 'Соседи', color: 'var(--m-panel)', note: 'Прыжок ряда за вычетом прыжка соседних муниципалитетов' },
  forecast: { name: 'Ошибка прогноза', short: 'Прогноз', color: 'var(--m-lgbm)', note: 'Выход за коридор прогноза на месяц вперёд' },
}

export type Kind = 'step' | 'ramp' | 'spike'
export const KIND_NAME: Record<Kind, string> = { step: 'Ступень', ramp: 'Рампа', spike: 'Всплеск' }
export interface Shock { tau: number; kind: Kind; size: number }

/** Шок как в detect.inject: ступень, рампа за три месяца или выброс на месяц, в логарифмах. */
export function injectShock(y: ArrayLike<number>, s: Shock) {
  return Array.from(y, (v, t) => {
    const eff = s.kind === 'step' ? (t >= s.tau ? s.size : 0) : s.kind === 'ramp' ? s.size * Math.min(1, Math.max(0, (t - s.tau + 1) / 3)) : t === s.tau ? s.size : 0
    return v * Math.exp(eff)
  })
}

export const alarmsOf = (s: number[], thr: number, from = 0) => s.map((v, t) => (t >= from && v > thr ? t : -1)).filter((t) => t >= 0)

export interface Eval { recall: number; precision: number; f1: number; fa100: number; delay: number; alarms: number; byKind: Record<Kind, number> }
/** detect.evaluate: шок найден, если первая тревога в окне [τ, τ + 2]; учёт — с месяца first. */
export function evaluate(rows: { alarms: number[]; T: number; shock: Shock | null }[], first = 6, maxDelay = 2): Eval {
  let tp = 0, hits = 0, fa = 0, months = 0, total = 0, dsum = 0
  const kind: Record<Kind, [number, number]> = { step: [0, 0], ramp: [0, 0], spike: [0, 0] }
  for (const r of rows) {
    const a = r.alarms.filter((t) => t >= first)
    total += a.length
    months += r.T - first
    if (r.shock) {
      hits++
      kind[r.shock.kind][1]++
      const win = a.filter((t) => t >= r.shock!.tau && t <= r.shock!.tau + maxDelay)
      if (win.length) { tp++; dsum += win[0] - r.shock.tau; kind[r.shock.kind][0]++ }
      fa += a.filter((t) => t < r.shock!.tau || t > r.shock!.tau + maxDelay).length
    } else fa += a.length
  }
  const recall = hits ? tp / hits : NaN, precision = tp / Math.max(total, 1)
  return {
    recall, precision, f1: (2 * precision * recall) / Math.max(precision + recall, 1e-9), fa100: (fa / months) * 100,
    delay: tp ? dsum / tp : NaN, alarms: total,
    byKind: { step: kind.step[0] / (kind.step[1] || 1), ramp: kind.ramp[0] / (kind.ramp[1] || 1), spike: kind.spike[0] / (kind.spike[1] || 1) },
  }
}
