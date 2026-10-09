/**
 * <nl-loader> — знак «Неслучайных связей» в круге: буква «Н» из узлов и связей.
 *
 * variant="noise"  «Из шума»: точки блуждают, собираются в граф, связи чертятся, граф отпускает.
 * variant="pulse"  «Импульс»: граф стоит тихо, по связям бежит сигнал, узлы загораются по ходу.
 * variant="wave"   «Пульс»: перекладина колеблется сигналом и успокаивается в прямую связь.
 * variant="link"   «Из шума и импульс» (выбор участника 04.10.2026): точки собираются из шума,
 *                  импульс прочерчивает связи «Н», граф держится, рассыпается — и снова.
 *
 * Атрибут t (0…1) ставит неподвижный кадр круга — из той же функции снята раскадровка
 * стенда. Размер — шириной и высотой элемента; фон круга — --nl-bg, линия — --nl-ink.
 * При prefers-reduced-motion знак стоит собранным.
 */
;(() => {
  if (!('customElements' in window) || customElements.get('nl-loader')) return

  const A = [30, 27], E = [30, 50], B = [30, 73], C = [70, 27], F = [70, 50], D = [70, 73]
  const NODES = [A, E, B, C, F, D]
  const EDGES = [[0, 1], [1, 2], [3, 4], [4, 5], [1, 4]]
  // Случайные точки вокруг: шум, из которого знак выделяет связь.
  const STRAY = [[50, 22], [52, 79], [17, 40], [84, 61], [49, 36], [50, 64]]
  const LOOP = { noise: 2600, pulse: 2200, wave: 2400, link: 3600 }
  // Путь импульса: вверх по левой стойке, назад к середине, через перекладину, вверх и вниз по правой.
  const PATH = [2, 1, 0, 1, 4, 3, 4, 5]
  const still = matchMedia('(prefers-reduced-motion: reduce)')

  const clamp = (x) => Math.max(0, Math.min(1, x))
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
  const seg = (p, a, b) => clamp((p - a) / (b - a))
  const lerp = (a, b, k) => a + (b - a) * k
  // Блуждание точки: сумма двух синусов, фаза от номера — у каждой точки своя дорожка.
  const wander = (i, ms, amp) => [
    amp * (Math.sin(ms / 610 + i * 1.7) * 0.6 + Math.sin(ms / 270 + i * 2.9) * 0.4),
    amp * (Math.cos(ms / 530 + i * 2.3) * 0.6 + Math.sin(ms / 330 + i * 1.1) * 0.4),
  ]

  const TEMPLATE =
    '<style>:host{display:inline-block;width:32px;height:32px;flex:none;vertical-align:middle}' +
    'svg{display:block;width:100%;height:100%;overflow:visible}</style>' +
    '<svg viewBox="0 0 100 100" aria-hidden="true">' +
    '<circle cx="50" cy="50" r="50" fill="var(--nl-bg, #0e1714)"/>' +
    '<g class="stray"></g><g class="edges"></g><g class="nodes"></g></svg>'

  class NlLoader extends HTMLElement {
    static observedAttributes = ['t', 'variant']
    connectedCallback() {
      if (!this.shadowRoot) {
        const root = this.attachShadow({ mode: 'open' })
        root.innerHTML = TEMPLATE
        const ns = 'http://www.w3.org/2000/svg'
        const mk = (tag, parent, attrs) => {
          const el = document.createElementNS(ns, tag)
          for (const k in attrs) el.setAttribute(k, attrs[k])
          parent.appendChild(el)
          return el
        }
        const ink = 'var(--nl-ink, #21A038)'
        const g = (c) => root.querySelector(c)
        this.strays = STRAY.map(() => mk('circle', g('.stray'), { r: 3.2, fill: ink, opacity: 0.45 }))
        this.base = EDGES.map(() => mk('path', g('.edges'), { stroke: ink, 'stroke-width': 6.5, 'stroke-linecap': 'round', fill: 'none', opacity: 0 }))
        this.edges = EDGES.map(() => mk('path', g('.edges'), { stroke: ink, 'stroke-width': 6.5, 'stroke-linecap': 'round', fill: 'none', pathLength: 1 }))
        this.nodes = NODES.map(() => mk('circle', g('.nodes'), { r: 6.5, fill: ink }))
        this.cores = NODES.map(() => mk('circle', g('.nodes'), { r: 2.6, fill: 'var(--nl-bg, #0e1714)' }))
      }
      if (!this.hasAttribute('role')) this.setAttribute('role', 'status')
      if (!this.hasAttribute('aria-label')) this.setAttribute('aria-label', 'Загрузка')
      this.t0 = performance.now()
      const tick = (now) => {
        this.draw(now)
        this.raf = requestAnimationFrame(tick)
      }
      if (this.hasAttribute('t')) this.draw(null)
      else if (still.matches) this.frame(0.6, 0, true)
      else this.raf = requestAnimationFrame(tick)
    }
    disconnectedCallback() { cancelAnimationFrame(this.raf) }
    attributeChangedCallback() { if (this.nodes && this.hasAttribute('t')) this.draw(null) }

    draw(now) {
      const v = this.getAttribute('variant') || 'noise'
      if (now === null) {
        const p = +this.getAttribute('t') || 0
        return this.frame(p, p * LOOP[v] + 4000)
      }
      const ms = now - this.t0
      this.frame((ms % LOOP[v]) / LOOP[v], ms + 4000)
    }

    /** Кадр круга p∈[0,1); ms — непрерывное время для блуждания шума. */
    frame(p, ms, rest = false) {
      const v = this.getAttribute('variant') || 'noise'
      let pos = NODES.map((n) => n.slice())
      let draw = EDGES.map(() => 1)
      let glow = NODES.map(() => 1)
      let strayOp = 0.4
      let bar = null

      if (!rest && v === 'noise') {
        // 0—.35 сборка, .35—.55 чертятся связи, .55—.8 держит, .8—1 отпускает.
        const s = ease(seg(p, 0, 0.35)) * (1 - ease(seg(p, 0.86, 1)))
        pos = NODES.map((n, i) => { const w = wander(i, ms, 15); return [lerp(n[0] + w[0], n[0], s), lerp(n[1] + w[1], n[1], s)] })
        const drawIn = ease(seg(p, 0.33, 0.56)), drawOut = ease(seg(p, 0.78, 0.9))
        draw = EDGES.map((_, k) => clamp(drawIn * 1.6 - k * 0.15) * (1 - drawOut))
        glow = NODES.map(() => 0.55 + 0.45 * s)
        strayOp = 0.5 - 0.3 * s
      } else if (!rest && v === 'link') {
        // .00—.24 сборка из шума, .24—.66 импульс чертит связи, .66—.82 держит, .82—1 рассыпается.
        const s = ease(seg(p, 0, 0.24)) * (1 - ease(seg(p, 0.84, 1)))
        pos = NODES.map((n, i) => { const w = wander(i, ms, 15); return [lerp(n[0] + w[0], n[0], s), lerp(n[1] + w[1], n[1], s)] })
        const k = seg(p, 0.24, 0.66) * (PATH.length - 1)
        const fade = 1 - ease(seg(p, 0.8, 0.9))
        draw = EDGES.map(() => 0)
        this.legDir = EDGES.map(() => 1)
        glow = NODES.map(() => 0.5 + 0.2 * s)
        for (let j = 0; j < PATH.length - 1; j++) {
          const f = clamp(k - j)
          if (f <= 0) continue
          const a = PATH[j], b = PATH[j + 1]
          const e = EDGES.findIndex(([x, y]) => (x === a && y === b) || (x === b && y === a))
          if (f > draw[e]) { draw[e] = f; this.legDir[e] = EDGES[e][0] === a ? 1 : -1 }
          glow[a] = 1
          if (f >= 1) glow[b] = 1
        }
        draw = draw.map((d) => d * fade)
        if (k >= PATH.length - 1) glow = glow.map((g) => lerp(0.5, g, fade))
        strayOp = 0.5 - 0.3 * s
      } else if (!rest && v === 'pulse') {
        // Сигнал идёт снизу по левой стойке вверх, назад к середине, через перекладину,
        // вверх по правой и вниз: каждая связь загорается, когда он на ней.
        const path = [2, 1, 0, 1, 4, 3, 4, 5]
        const k = p * (path.length - 1)
        const at = Math.floor(k), f = k - at
        draw = EDGES.map(() => 0.28)
        glow = NODES.map(() => 0.45)
        for (let j = 0; j < path.length; j++) {
          const d = Math.abs(k - j)
          glow[path[j]] = Math.max(glow[path[j]], 1 - Math.min(1, d / 1.3) * 0.55)
        }
        this.pulse = [path[at], path[Math.min(path.length - 1, at + 1)], f]
      } else if (!rest && v === 'wave') {
        // Перекладина — сигнал: амплитуда затухает к прямой и снова раскачивается.
        const amp = 15 * Math.pow(Math.cos(Math.PI * p), 2)
        bar = { amp, ph: p * Math.PI * 6 }
        glow = NODES.map((_, i) => (i === 1 || i === 4 ? 1 : 0.75))
        glow[1] = glow[4] = 0.65 + 0.35 * (1 - amp / 15)
      }

      this.nodes.forEach((c, i) => {
        c.setAttribute('cx', pos[i][0]); c.setAttribute('cy', pos[i][1]); c.setAttribute('opacity', glow[i])
        this.cores[i].setAttribute('cx', pos[i][0]); this.cores[i].setAttribute('cy', pos[i][1])
      })
      this.edges.forEach((e, k) => {
        const [a, b] = EDGES[k]
        const [x1, y1] = pos[a], [x2, y2] = pos[b]
        if (bar && k === 4) {
          let d = `M${x1},${y1}`
          for (let s = 1; s <= 24; s++) {
            const u = s / 24
            const env = Math.sin(Math.PI * u)
            d += `L${lerp(x1, x2, u).toFixed(2)},${(lerp(y1, y2, u) + bar.amp * env * Math.sin(u * Math.PI * 4 - bar.ph)).toFixed(2)}`
          }
          e.setAttribute('d', d)
        } else e.setAttribute('d', `M${x1},${y1}L${x2},${y2}`)
        this.base[k].setAttribute('d', e.getAttribute('d'))
        this.base[k].setAttribute('opacity', v === 'pulse' && !rest ? 0.3 : 0)
        if (v === 'pulse' && !rest) {
          const [na, nb, f] = this.pulse
          const on = (a === na && b === nb) || (a === nb && b === na)
          // Сигнал рисует связь от того узла, откуда пришёл; поверх тихой копии — яркий кусок.
          e.setAttribute('stroke-dasharray', !on ? '1 0' : na === a ? `${f} 1` : `0 ${1 - f} ${f} 1`)
          e.setAttribute('stroke-dashoffset', 0)
          // Пройденная связь гаснет следом за сигналом, а не пропадает разом.
          const lit = Math.max(0, glow[a] + glow[b] - 1.25)
          e.setAttribute('opacity', on ? 1 : lit)
        } else if (v === 'link' && !rest && this.legDir && this.legDir[k] < 0) {
          // Связь, которую импульс прошёл от второго конца, чертится от него.
          e.setAttribute('stroke-dasharray', `0 ${1 - draw[k]} ${draw[k]} 1`)
          e.setAttribute('stroke-dashoffset', 0)
          e.setAttribute('opacity', 1)
        } else {
          e.setAttribute('stroke-dasharray', `${draw[k]} 1`)
          e.setAttribute('stroke-dashoffset', 0)
          e.setAttribute('opacity', 1)
        }
      })
      this.strays.forEach((c, i) => {
        const w = rest ? [0, 0] : wander(i + 7, ms, 6)
        c.setAttribute('cx', STRAY[i][0] + w[0]); c.setAttribute('cy', STRAY[i][1] + w[1]); c.setAttribute('opacity', strayOp)
      })
    }
  }
  customElements.define('nl-loader', NlLoader)
})()
