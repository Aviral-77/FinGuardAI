import { useEffect, useMemo, useRef, useState } from 'react'
import { computeLayout, type LayoutNode } from '../layout'
import { bandColour, palette, fonts } from '../theme'
import type { GraphPayload } from '../types'

interface Props {
  graph: GraphPayload
  /** Score per account as the replay has revealed it so far. */
  liveScores: Map<string, number>
  liveBands: Map<string, string>
  /** Accounts the anomaly model has flagged, revealed at the end of the replay. */
  mlFlagged: Set<string>
  /** Accounts inside an ML network the rules missed — these get the teal halo. */
  mlMissed: Set<string>
  /** Transfers currently animating along their edge. */
  pulses: { from: string; to: string; born: number }[]
  selected: string | null
  onSelect: (accountId: string) => void
  frozen: Set<string>
}

const PULSE_MS = 1400

export function ForceGraph({
  graph,
  liveScores,
  liveBands,
  mlFlagged,
  mlMissed,
  pulses,
  selected,
  onSelect,
  frozen,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 900, height: 700 })
  const [hover, setHover] = useState<string | null>(null)

  // Keep the live props in a ref so the animation loop reads current values
  // without being torn down and rebuilt on every replay event.
  const live = useRef({ liveScores, liveBands, mlFlagged, mlMissed, pulses, selected, hover, frozen })
  live.current = { liveScores, liveBands, mlFlagged, mlMissed, pulses, selected, hover, frozen }

  useEffect(() => {
    const element = wrapperRef.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const box = entries[0].contentRect
      setSize({ width: Math.max(400, box.width), height: Math.max(360, box.height) })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const layout = useMemo(() => {
    const ids = graph.nodes.map((n) => n.id)
    const edges = graph.edges.map((e) => ({
      source: e.source,
      target: e.target,
      weight: e.count,
    }))
    return computeLayout(ids, edges, {
      width: size.width,
      height: size.height,
      seed: 42,
      // Tuned for ~250 nodes on a wide canvas: enough repulsion to use the
      // full frame, and a weak centre pull so clusters separate instead of
      // piling into the middle.
      repulsion: 11000,
      centrePull: 0.006,
      springLength: 60,
      iterations: 420,
    })
  }, [graph, size.width, size.height])

  const nodeById = useMemo(
    () => new Map(graph.nodes.map((n) => [n.id, n])),
    [graph],
  )

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return

    const ratio = window.devicePixelRatio || 1
    canvas.width = size.width * ratio
    canvas.height = size.height * ratio
    context.scale(ratio, ratio)

    let frame = 0
    const render = () => {
      const state = live.current
      context.clearRect(0, 0, size.width, size.height)
      context.fillStyle = palette.ink
      context.fillRect(0, 0, size.width, size.height)

      // --- edges -------------------------------------------------------
      for (const edge of graph.edges) {
        const a = layout.get(edge.source)
        const b = layout.get(edge.target)
        if (!a || !b) continue
        const hot =
          (state.liveScores.get(edge.source) ?? 0) >= 51 &&
          (state.liveScores.get(edge.target) ?? 0) >= 51
        const missed =
          state.mlMissed.has(edge.source) && state.mlMissed.has(edge.target)
        const touchingSelection =
          state.selected !== null &&
          (edge.source === state.selected || edge.target === state.selected)

        context.beginPath()
        context.moveTo(a.x, a.y)
        context.lineTo(b.x, b.y)
        if (touchingSelection) {
          context.strokeStyle = palette.gold
          context.lineWidth = 1.8
          context.globalAlpha = 0.95
        } else if (hot) {
          context.strokeStyle = palette.alert
          context.lineWidth = 1.5
          context.globalAlpha = 0.75
        } else if (missed) {
          context.strokeStyle = palette.teal
          context.lineWidth = 1.4
          context.globalAlpha = 0.7
        } else {
          context.strokeStyle = palette.line
          context.lineWidth = 0.7
          context.globalAlpha = 0.42
        }
        context.stroke()
        context.globalAlpha = 1
      }

      // --- transfers in flight ----------------------------------------
      const now = performance.now()
      for (const pulse of state.pulses) {
        const a = layout.get(pulse.from)
        const b = layout.get(pulse.to)
        if (!a || !b) continue
        const progress = (now - pulse.born) / PULSE_MS
        if (progress < 0 || progress > 1) continue
        const x = a.x + (b.x - a.x) * progress
        const y = a.y + (b.y - a.y) * progress
        context.beginPath()
        context.arc(x, y, 2.6, 0, Math.PI * 2)
        context.fillStyle = palette.gold
        context.globalAlpha = 1 - progress * 0.65
        context.fill()
        context.globalAlpha = 1
      }

      // --- nodes -------------------------------------------------------
      const chips: {
        x: number
        y: number
        label: string
        colour: string
        priority: number
        id: string
        showName: boolean
        nameY: number
      }[] = []

      for (const node of graph.nodes) {
        const position = layout.get(node.id)
        if (!position) continue
        const score = state.liveScores.get(node.id) ?? 0
        const band = state.liveBands.get(node.id) ?? 'ALLOW'
        const isSelected = state.selected === node.id
        const isHover = state.hover === node.id
        const radius = 3 + Math.min(node.degree, 14) * 0.42 + (score >= 51 ? 2 : 0)

        // Teal halo: the anomaly model found this, and no rule did. This is
        // the Act 3 signal, and it is deliberately a different colour from
        // every rule outcome so the two claims never blur together.
        if (state.mlMissed.has(node.id)) {
          const pulse = 0.5 + 0.5 * Math.sin(now / 420)
          context.beginPath()
          context.arc(position.x, position.y, radius + 7 + pulse * 3, 0, Math.PI * 2)
          context.fillStyle = palette.teal
          context.globalAlpha = 0.16 + pulse * 0.16
          context.fill()
          context.globalAlpha = 1
          context.beginPath()
          context.arc(position.x, position.y, radius + 4, 0, Math.PI * 2)
          context.strokeStyle = palette.teal
          context.lineWidth = 1.4
          context.stroke()
        } else if (state.mlFlagged.has(node.id) && score < 51) {
          context.beginPath()
          context.arc(position.x, position.y, radius + 4, 0, Math.PI * 2)
          context.strokeStyle = palette.teal
          context.globalAlpha = 0.5
          context.lineWidth = 1
          context.stroke()
          context.globalAlpha = 1
        }

        // Red halo when the ring is caught.
        if (state.frozen.has(node.id)) {
          const pulse = 0.5 + 0.5 * Math.sin(now / 300)
          context.beginPath()
          context.arc(position.x, position.y, radius + 8 + pulse * 4, 0, Math.PI * 2)
          context.fillStyle = palette.alert
          context.globalAlpha = 0.18 + pulse * 0.2
          context.fill()
          context.globalAlpha = 1
        }

        context.beginPath()
        context.arc(position.x, position.y, radius, 0, Math.PI * 2)
        context.fillStyle = bandColour[band] ?? bandColour.ALLOW
        context.fill()

        // The victim wears a gold ring rather than a gold fill. They are not a
        // suspect, and a fill would put them on the same scale as the mules.
        if (node.role === 'victim') {
          context.beginPath()
          context.arc(position.x, position.y, radius + 3.5, 0, Math.PI * 2)
          context.strokeStyle = palette.gold
          context.lineWidth = 2
          context.stroke()
        }

        if (node.known_suspicious) {
          context.strokeStyle = '#FFFFFF'
          context.lineWidth = 1.2
          context.setLineDash([2, 2])
          context.stroke()
          context.setLineDash([])
        }

        if (isSelected || isHover) {
          context.beginPath()
          context.arc(position.x, position.y, radius + 3, 0, Math.PI * 2)
          context.strokeStyle = palette.text
          context.lineWidth = 1.4
          context.stroke()
        }

        // Chips are collected, not drawn here: inside a tight ring they land on
        // top of each other and the scores become unreadable at exactly the
        // moment they matter most. They get their own pass below.
        if (score > 0 && (score >= 31 || isSelected || isHover)) {
          chips.push({
            x: position.x,
            y: position.y - radius - 17,
            label: String(score),
            colour: bandColour[band] ?? bandColour.ALLOW,
            priority: score + (isSelected || isHover ? 1000 : 0),
            id: node.id,
            showName: isSelected || isHover || state.frozen.has(node.id),
            nameY: position.y + radius + 4,
          })
        }
      }

      // --- chips, drawn last so nothing is painted over them --------------
      // Highest score wins a contested spot: in an overlap, the account that
      // crossed furthest is the one the analyst needs to see.
      chips.sort((a, b) => b.priority - a.priority)
      const placed: { x: number; y: number; w: number; h: number }[] = []
      context.textAlign = 'center'
      for (const chip of chips) {
        context.font = `600 10px ${fonts.mono}`
        const width = context.measureText(chip.label).width + 10
        const box = { x: chip.x - width / 2, y: chip.y, w: width, h: 14 }
        const clashes = placed.some(
          (other) =>
            box.x < other.x + other.w + 2 &&
            box.x + box.w + 2 > other.x &&
            box.y < other.y + other.h + 2 &&
            box.y + box.h + 2 > other.y,
        )
        if (clashes) continue
        placed.push(box)

        context.fillStyle = chip.colour
        context.beginPath()
        context.roundRect(box.x, box.y, width, 14, 7)
        context.fill()
        context.fillStyle = '#FFFFFF'
        context.textBaseline = 'middle'
        context.fillText(chip.label, chip.x, chip.y + 7.5)

        if (chip.showName) {
          context.font = `500 9px ${fonts.mono}`
          context.fillStyle = palette.textDim
          context.textBaseline = 'top'
          context.fillText(chip.id.replace('ACC-', ''), chip.x, chip.nameY)
        }
      }

      frame = requestAnimationFrame(render)
    }

    frame = requestAnimationFrame(render)
    return () => cancelAnimationFrame(frame)
  }, [graph, layout, size.width, size.height])

  const pick = (event: React.MouseEvent<HTMLCanvasElement>): string | null => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    let best: { id: string; distance: number } | null = null
    layout.forEach((node: LayoutNode, id: string) => {
      const distance = Math.hypot(node.x - x, node.y - y)
      if (distance < 12 && (!best || distance < best.distance)) {
        best = { id, distance }
      }
    })
    return best ? (best as { id: string }).id : null
  }

  return (
    <div ref={wrapperRef} style={{ position: 'relative', width: '100%', height: '100%' }}>
      <canvas
        ref={canvasRef}
        style={{ width: size.width, height: size.height, cursor: hover ? 'pointer' : 'default' }}
        onMouseMove={(event) => setHover(pick(event))}
        onMouseLeave={() => setHover(null)}
        onClick={(event) => {
          const id = pick(event)
          if (id) onSelect(id)
        }}
      />
      <Legend />
      {hover && nodeById.get(hover) && (
        <div
          style={{
            position: 'absolute',
            bottom: 12,
            left: 12,
            background: palette.panelRaised,
            border: `1px solid ${palette.line}`,
            borderRadius: 6,
            padding: '8px 10px',
            fontFamily: fonts.mono,
            fontSize: 11,
            color: palette.text,
            pointerEvents: 'none',
          }}
        >
          {hover} · score {liveScores.get(hover) ?? 0}
          {nodeById.get(hover)!.rule_ids.length > 0 &&
            ` · ${nodeById.get(hover)!.rule_ids.join(' ')}`}
        </div>
      )}
    </div>
  )
}

function Legend() {
  const items = [
    { colour: palette.gold, label: 'Victim', ring: true },
    { colour: bandColour.STEP_UP_AUTH, label: 'Step-up auth' },
    { colour: bandColour.MANUAL_REVIEW, label: 'Manual review' },
    { colour: palette.alert, label: 'Frozen — caught by rules' },
    { colour: palette.teal, label: 'Found by anomaly model only' },
  ]
  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        right: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        background: 'rgba(15,37,71,0.82)',
        border: `1px solid ${palette.line}`,
        borderRadius: 6,
        padding: '8px 10px',
        pointerEvents: 'none',
      }}
    >
      {items.map((item) => (
        <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 4,
              background: 'ring' in item && item.ring ? 'transparent' : item.colour,
              border: 'ring' in item && item.ring ? `2px solid ${item.colour}` : 'none',
              display: 'inline-block',
            }}
          />
          <span style={{ fontFamily: fonts.ui, fontSize: 10.5, color: palette.textDim }}>
            {item.label}
          </span>
        </div>
      ))}
    </div>
  )
}
