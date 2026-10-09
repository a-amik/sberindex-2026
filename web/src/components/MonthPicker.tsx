import { useEffect, useRef, useState } from 'react'
import { FIRST_FC, META, monthLong } from '../data/real'
import { useApp } from '../store'
import { I } from './icons'

const MN = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
const tone = (w: number) => (w < 0.05 ? 'var(--ok)' : w < 0.09 ? 'var(--shift)' : 'var(--warn)')

/**
 * Календарь месяцев прогноза: 2025—2027 годы, каждый месяц окрашен ожидаемой точностью
 * прогноза для выбранной категории. Первые 12 месяцев — точность измерена на бэктесте;
 * дальше — оценена по росту ошибки с горизонтом, такие месяцы заштрихованы.
 */
export function MonthPicker() {
  const { target, setTarget, cat } = useApp()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const off = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', off)
    addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', off); removeEventListener('keydown', esc) }
  }, [open])
  const err = META.horizonErr[cat === 0 ? 'Все категории' : META.cats[cat]] ?? META.horizonErr['Все']
  const h = target - FIRST_FC + 1
  const label = monthLong(target)
  // Цвет точки: прошлый месяц — факт, серый.
  const dot = h < 1 ? 'var(--text-3)' : tone(err[h - 1])
  return (
    <div className="menu-wrap mp" ref={ref}>
      <button className="mp-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)} title="Выбор месяца">
        {I.calendar}<span>{label[0].toUpperCase() + label.slice(1)}</span>
        <i className="mp-dot" style={{ background: dot }} />
      </button>
      {open && (
        <div className="menu mp-pop" role="dialog" aria-label="Выбор месяца">
          <div className="small" style={{ padding: '4px 6px 8px' }}>Цвет — средняя ошибка</div>
          <div className="mp-year">
            <b>2024</b>
            <div className="mp-grid">
              {MN.map((m, mi) => {
                const t = FIRST_FC - 12 + mi
                return <button key={m} className={`mp-cell fact${t === target ? ' on' : ''}`} data-tip={`${monthLong(t)}: факт`} onClick={() => { setTarget(t); setOpen(false) }}>{m}</button>
              })}
            </div>
          </div>
          {[2025, 2026, 2027].map((y, yi) => (
            <div key={y} className="mp-year">
              <b>{y}</b>
              <div className="mp-grid">
                {MN.map((m, mi) => {
                  const t = FIRST_FC + yi * 12 + mi, hh = t - FIRST_FC + 1, w = err[hh - 1]
                  return (
                    <button key={m} className={`mp-cell${t === target ? ' on' : ''}${hh > 12 ? ' est' : ''}`} style={{ '--c': tone(w) } as React.CSSProperties}
                      data-tip={`${monthLong(t)}: средняя ошибка ${(w * 100).toFixed(1).replace('.', ',')} % — ${hh > 12 ? 'оценка; используем предыдущие прогнозы' : 'проверка на истории'}`}
                      onClick={() => { setTarget(t); setOpen(false) }}>{m}</button>
                  )
                })}
              </div>
            </div>
          ))}
          <div className="mp-legend small">
            <span><i style={{ background: 'var(--ok)' }} />до 5 %</span>
            <span><i style={{ background: 'var(--shift)' }} />5—9 %</span>
            <span><i style={{ background: 'var(--warn)' }} />больше 9 %</span>
            <span><i className="hatch" />оценка</span>
            <span><i style={{ background: 'var(--text-3)' }} />факт</span>
          </div>
        </div>
      )}
    </div>
  )
}
