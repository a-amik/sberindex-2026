import { Seg } from './ui'
import { type Factors } from '../data/whatif'
import { useApp } from '../store'
import { fmt0, fmt1, fmt2, signed } from '../lib/util'

export function Slider({ label, v, min, max, step, unit, onChange, fmtV }: { label: string; v: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void; fmtV?: (v: number) => string }) {
  const fmt = fmtV ?? ((x: number) => (min < 0 ? signed(x, Number.isInteger(x) ? fmt0 : step < 0.5 ? fmt2 : fmt1) : fmt0(x)))
  return (
    <div className="range">
      <div className="range-top"><span>{label}</span><b>{fmt(v)}{unit}</b></div>
      <input type="range" min={min} max={max} step={step} value={v} onChange={(e) => onChange(+e.target.value)} aria-label={label} />
    </div>
  )
}

/**
 * Ручки своего сочетания: двенадцать первичных факторов сценария. Любое движение делает сценарий «своим».
 * Без f и onChange ручки двигают общий сценарий сервиса, с ними — локальный (шит региона).
 */
export function ScenarioKnobs({ f: own, onChange, one = false }: { f?: Factors; onChange?: (p: Partial<Factors>) => void; one?: boolean }) {
  const global = useApp((s) => s.scn.f)
  const set = useApp((s) => s.set)
  const f = own ?? global
  const upd = onChange ?? ((p: Partial<Factors>) => { const s = useApp.getState().scn; set({ scn: { ...s, key: 'custom', f: { ...s.f, ...p } } }) })
  return (
    <div className={`knobs grid ${one ? '' : 'g3'}`}>
      <Slider label="Ключевая ставка" v={f.rate} min={-3} max={3} step={0.25} unit=" п. п." onChange={(rate) => upd({ rate })} />
      <Slider label="Потепление летом" v={f.heat} min={-4} max={4} step={0.5} unit=" °C" onChange={(heat) => upd({ heat })} />
      <Slider label="Дополнительные выходные" v={f.off} min={0} max={4} step={1} unit=" дн." onChange={(off) => upd({ off })} />
      <Slider label="ФОТ обработки к среднему" v={f.fotManuf} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotManuf) => upd({ fotManuf })} />
      <Slider label="ФОТ добычи к среднему" v={f.fotMining} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotMining) => upd({ fotMining })} />
      <Slider label="ФОТ сельского хозяйства" v={f.fotAgri} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotAgri) => upd({ fotAgri })} />
      <Slider label="ФОТ бюджетного сектора" v={f.fotBudget} min={-6} max={6} step={0.5} unit=" п. п." onChange={(fotBudget) => upd({ fotBudget })} />
      <Slider label="Нефть в рублях" v={f.oil} min={-50} max={50} step={5} unit=" %" onChange={(oil) => upd({ oil })} />
      <Slider label="НДС" v={f.vat} min={-2} max={4} step={1} unit=" п. п." onChange={(vat) => upd({ vat })} />
      <Slider label="Ослабление рубля" v={f.fx} min={-20} max={20} step={5} unit=" %" onChange={(fx) => upd({ fx })} />
      <Slider label="Мобильный интернет отключён" v={f.netOff} min={0} max={15} step={1} unit=" дн./мес." onChange={(netOff) => upd({ netOff })} />
      <div><Seg value={f.flood ? 'on' : 'off'} onChange={(v) => upd({ flood: v === 'on' })} items={[['off', 'Без паводка'], ['on', 'Паводок']]} /></div>
    </div>
  )
}
