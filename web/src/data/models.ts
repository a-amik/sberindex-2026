// Шесть моделей на графиках и подписи для полной таблицы метрик.
export type ModelKey = 'prophet' | 'snaive' | 'panel' | 'lgbm' | 'chronos' | 'ensemble' | 'strict'
export interface ModelInfo { key: ModelKey; real: string; name: string; short: string; kind: string; cov: number; color: string }

// cov — какую долю внешнего сигнала модель берёт в сценариях стенда.
export const MODELS: ModelInfo[] = [
  { key: 'prophet', real: 'prophet_default', name: 'Prophet, базовая модель', short: 'Prophet', kind: 'Базовая', cov: 0, color: 'var(--m-prophet)' },
  { key: 'snaive', real: 'snaive_growth', name: 'Прошлогодние траты с поправкой на рост', short: 'Год назад с ростом', kind: 'Правило', cov: 0, color: 'var(--m-snaive)' },
  { key: 'panel', real: 'panel_blend_sesseas_bytype', name: 'Сезонность по всем муниципалитетам одного типа', short: 'Панель', kind: 'Правило', cov: 0, color: 'var(--m-panel)' },
  { key: 'lgbm', real: 'lgbm', name: 'LightGBM по данным всех муниципалитетов', short: 'LightGBM', kind: 'Бустинг', cov: 0.8, color: 'var(--m-lgbm)' },
  { key: 'chronos', real: 'chronos2_dev', name: 'Chronos-2 на относительных уровнях трат муниципалитетов', short: 'Chronos-2', kind: 'Фундаментальная', cov: 1, color: 'var(--m-chronos)' },
  { key: 'ensemble', real: 'ensemble', name: 'Ансамбль моделей по срокам прогноза', short: 'Ансамбль', kind: 'Ансамбль', cov: 0.9, color: 'var(--m-ensemble)' },
  // Сдаваемая и рабочая модель сайта: ансамбль с поправкой роста фактора на шагах 4—12 и интервалами (37_strict.py).
  { key: 'strict', real: 'ensemble_strict', name: 'Наш итоговый прогноз', short: 'Наш прогноз', kind: 'Итог', cov: 0.9, color: 'var(--m-strict)' },
]
export const MODEL = Object.fromEntries(MODELS.map((m) => [m.key, m])) as Record<ModelKey, ModelInfo>
export const byReal = (r: string) => MODELS.find((m) => m.real === r)

/** Подпись любой модели из results/metrics по её имени. */
export function modelLabel(name: string): [string, string] {
  const shown = byReal(name)
  if (shown) return [shown.name, shown.kind]
  if (name === 'ensemble_signals') return ['Ансамбль с внешними признаками', 'Ансамбль']
  if (name.startsWith('chronosbolt')) return [`Chronos-Bolt, ${({ chronosbolt_dev: 'на относительных уровнях трат муниципалитетов', chronosbolt_raw: 'на исходных тратах' } as Record<string, string>)[name] ?? name}`, 'Фундаментальная']
  if (name.startsWith('chronos2')) return [`Chronos-2, ${({ chronos2_cov: 'с внешними признаками', chronos2_raw: 'на исходных тратах', chronos2_raw_cl: 'на исходных тратах с ограничением значений' } as Record<string, string>)[name] ?? name}`, 'Фундаментальная']
  if (name.startsWith('prophet')) return [`Prophet, ${name === 'prophet_yearly3_mult' ? 'годовая сезонность, 3 гармоники, пропорциональна уровню трат' : name}`, 'Базовая']
  if (name.startsWith('panel_')) {
    const [, src, sm, by] = name.match(/panel_(blend|national|panel)_(ses|sesseas)(_bytype)?/) ?? []
    const s = { blend: 'ряд РФ и данные муниципалитетов', national: 'ряд РФ', panel: 'данные муниципалитетов' }[src as 'blend']
    return [`Перенос сезонности: ${s}, ${sm === 'ses' ? 'экспоненциальное сглаживание' : 'сглаживание с сезонностью'}${by ? ', по типу муниципалитета' : ''}`, 'Правило']
  }
  if (name.startsWith('factor_only')) return [`Только общая динамика группы${name.endsWith('bytype') ? ', по типу муниципалитета' : ''}`, 'Правило']
  return [({ ar1: 'AR(1)', naive: 'Последнее значение', snaive: 'Траты год назад', snaive_growth: 'Прошлогодние траты с поправкой на рост' } as Record<string, string>)[name] ?? name, 'Простая']
}
