import { useEffect, useMemo, useRef, useState } from 'react'
import { computeLayout, type LayoutNode } from '../layout'
import { bandColour, fonts, palette, shortMoney } from '../theme'
import type { EdgeSummary, NodeSummary, RingInfo } from '../types'

interface Props {
  nodes: Map<string, NodeSummary>
  edges: EdgeSummary[]
  frozen: Set<string>
  ring: RingInfo | null
  pulses: { from: string; to: string; born: number }[]
  selected: string | null
  onSelect: (id: string) => void
}

const PULSE_MS = 1200

/**
 * The centre canvas: a light-theme force-directed account graph.
 *
 * Grey ambient nodes; a node turns amber then red as its score climbs; a red
 * dashed boundary on a light wash is drawn around a detected ring. Score
 * badges sit on the nodes and update live. The layout is seeded, so the ring
 * assembles in the same place every run -- the presenter knows where to point.
 */
export function Canvas({ nodes, edges, frozen, ring, pulses, selected, onSelect }: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState({ width: 900, height: 700 })
  const [hover, setHover] = useState<string | null>(null)

  const live = useRef({ nodes, frozen, ring, pulses, selected, hover })
  live.current = { nodes, frozen, ring, pulses, selected, hover }

  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const box = entries[0].contentRect
      setSize({ width: Math.max(400, box.width), height: Math.max(360, box.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // The layout is keyed on the *set* of node ids and the edges, so it only
  // recomputes when the graph's shape changes -- not on every score tick.
  const nodeIds = useMemo(() => [...nodes.keys()].sort().join(','), [nodes])
  const layout = useMemo(() => {
    const ids = nodeIds ? nodeIds.split(',') : []
    return computeLayout(
      ids,
      edges.map((e) => ({ source: e.source, target: e.target, weight: e.count })),
      { width: size.width, height: size.height, seed: 42, repulsion: 9000, centrePull: 0.008, springLength: 52 },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeIds, edges.length, size.width, size.height])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const ratio = window.devicePixelRatio || 1
    canvas.width = size.width * ratio
    canvas.height = size.height * ratio
    ctx.scale(ratio, ratio)

    let frame = 0
    const render = () => {
      const s = live.current
      const now = performance.now()
      ctx.clearRect(0, 0, size.width, size.height)
      ctx.fillStyle = palette.panel
      ctx.fillRect(0, 0, size.width, size.height)

      // Ring wash + dashed boundary, drawn under everything.
      if (s.ring) {
        const pts = s.ring.accounts.map((id) => layout.get(id)).filter(Boolean) as LayoutNode[]
        if (pts.length >= 3) {
          const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length
          const cy = pts.reduce((a, p) => a + p.y, 0) / pts.length
          const r = Math.max(...pts.map((p) => Math.hypot(p.x - cx, p.y - cy))) + 26
          ctx.beginPath()
          ctx.arc(cx, cy, r, 0, Math.PI * 2)
          ctx.fillStyle = 'rgba(193,18,31,0.06)'
          ctx.fill()
          ctx.setLineDash([6, 5])
          ctx.strokeStyle = palette.alert
          ctx.lineWidth = 1.5
          ctx.stroke()
          ctx.setLineDash([])
          ctx.fillStyle = palette.alert
          ctx.font = `600 11px ${fonts.ui}`
          ctx.textAlign = 'center'
          ctx.fillText(
            `MULE RING DETECTED · ${s.ring.count} accounts · ${shortMoney(s.ring.value_in_motion)} in motion`,
            cx,
            cy - r - 8,
          )
        }
      }

      // Edges.
      for (const edge of edges) {
        const a = layout.get(edge.source)
        const b = layout.get(edge.target)
        if (!a || !b) continue
        const hot =
          (s.nodes.get(edge.source)?.score ?? 0) >= 51 && (s.nodes.get(edge.target)?.score ?? 0) >= 51
        const touch = s.selected && (edge.source === s.selected || edge.target === s.selected)
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        if (touch) {
          ctx.strokeStyle = palette.gold
          ctx.lineWidth = 1.8
          ctx.globalAlpha = 0.95
        } else if (hot) {
          ctx.strokeStyle = palette.alert
          ctx.lineWidth = 1.3
          ctx.globalAlpha = 0.5
        } else {
          ctx.strokeStyle = palette.ambient
          ctx.lineWidth = 0.7
          ctx.globalAlpha = 0.55
        }
        ctx.stroke()
        ctx.globalAlpha = 1
      }

      // Transfers in flight.
      for (const pulse of s.pulses) {
        const a = layout.get(pulse.from)
        const b = layout.get(pulse.to)
        if (!a || !b) continue
        const t = (now - pulse.born) / PULSE_MS
        if (t < 0 || t > 1) continue
        ctx.beginPath()
        ctx.arc(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, 2.6, 0, Math.PI * 2)
        ctx.fillStyle = palette.gold
        ctx.globalAlpha = 1 - t * 0.6
        ctx.fill()
        ctx.globalAlpha = 1
      }

      // Nodes.
      const chips: { x: number; y: number; label: string; colour: string; pri: number }[] = []
      for (const [id, node] of s.nodes) {
        const p = layout.get(id)
        if (!p) continue
        const score = node.score
        const isSel = s.selected === id
        const isHover = s.hover === id
        const radius = 4 + Math.min(score / 12, 8) + (isSel || isHover ? 1.5 : 0)
        const colour = score > 0 ? bandColour(node.band_code, score) : palette.ambient

        if (score >= 86) {
          const pulse = 0.5 + 0.5 * Math.sin(now / 320)
          ctx.beginPath()
          ctx.arc(p.x, p.y, radius + 7 + pulse * 4, 0, Math.PI * 2)
          ctx.fillStyle = palette.alert
          ctx.globalAlpha = 0.14 + pulse * 0.14
          ctx.fill()
          ctx.globalAlpha = 1
        }

        ctx.beginPath()
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2)
        ctx.fillStyle = colour
        ctx.fill()
        if (node.role === 'victim') {
          ctx.beginPath()
          ctx.arc(p.x, p.y, radius + 3, 0, Math.PI * 2)
          ctx.strokeStyle = palette.gold
          ctx.lineWidth = 2
          ctx.stroke()
        }
        if (isSel || isHover) {
          ctx.beginPath()
          ctx.arc(p.x, p.y, radius + 2.5, 0, Math.PI * 2)
          ctx.strokeStyle = palette.ink
          ctx.lineWidth = 1.4
          ctx.stroke()
        }

        // Frozen lock badge.
        if (s.frozen.has(id)) {
          ctx.beginPath()
          ctx.arc(p.x, p.y, radius, 0, Math.PI * 2)
          ctx.fillStyle = 'rgba(255,255,255,0.55)'
          ctx.fill()
          ctx.fillStyle = palette.teal
          ctx.font = `700 ${Math.round(radius * 1.3)}px ${fonts.ui}`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText('\u{1F512}', p.x, p.y + 0.5)
        }

        if (score >= 31 || isSel || isHover) {
          chips.push({ x: p.x, y: p.y - radius - 12, label: String(score), colour, pri: score + (isSel ? 999 : 0) })
        }
      }

      // Score badges last, with simple collision avoidance.
      chips.sort((a, b) => b.pri - a.pri)
      const placed: { x: number; y: number; w: number }[] = []
      ctx.textBaseline = 'middle'
      for (const chip of chips) {
        ctx.font = `600 10px ${fonts.mono}`
        const w = ctx.measureText(chip.label).width + 9
        if (placed.some((o) => Math.abs(o.x - chip.x) < (o.w + w) / 2 + 2 && Math.abs(o.y - chip.y) < 15)) continue
        placed.push({ x: chip.x, y: chip.y, w })
        ctx.fillStyle = chip.colour
        ctx.beginPath()
        ctx.roundRect(chip.x - w / 2, chip.y - 7, w, 14, 7)
        ctx.fill()
        ctx.fillStyle = '#FFFFFF'
        ctx.textAlign = 'center'
        ctx.fillText(chip.label, chip.x, chip.y)
      }

      frame = requestAnimationFrame(render)
    }
    frame = requestAnimationFrame(render)
    return () => cancelAnimationFrame(frame)
  }, [edges, layout, size.width, size.height])

  const pick = (event: React.MouseEvent<HTMLCanvasElement>): string | null => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    let best: { id: string; d: number } | null = null
    layout.forEach((n: LayoutNode, id: string) => {
      const d = Math.hypot(n.x - x, n.y - y)
      if (d < 13 && (!best || d < best.d)) best = { id, d }
    })
    return best ? (best as { id: string }).id : null
  }

  return (
    <div ref={wrapperRef} style={{ position: 'relative', width: '100%', height: '100%' }}>
      <canvas
        ref={canvasRef}
        style={{ width: size.width, height: size.height, cursor: hover ? 'pointer' : 'default' }}
        onMouseMove={(e) => setHover(pick(e))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => {
          const id = pick(e)
          if (id) onSelect(id)
        }}
      />
      {nodes.size === 0 && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            placeItems: 'center',
            color: palette.muted,
            fontFamily: fonts.ui,
            fontSize: 13,
            pointerEvents: 'none',
          }}
        >
          A normal afternoon at the bank — press <b>&nbsp;Reset&nbsp;</b> then run the beats.
        </div>
      )}
    </div>
  )
}
