/**
 * A small, seeded force-directed layout.
 *
 * Written rather than pulled in for one reason: determinism. The brief's
 * working principle is that the ring forms identically on every run, and every
 * off-the-shelf force graph seeds its initial positions from `Math.random`, so
 * the ring would land somewhere different each time the page loaded. Here the
 * PRNG is seeded, the node order is sorted, and the simulation is run to a
 * fixed iteration count -- so the same data always draws the same picture, and
 * the presenter knows where to point.
 *
 * The model is the standard one: repulsion between all nodes, springs along
 * edges, and a weak pull to centre. Barnes-Hut would be worth it above a few
 * thousand nodes; at ~250 the direct O(n^2) pass is well under a frame.
 */

export interface LayoutNode {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  fixed?: boolean
}

export interface LayoutEdge {
  source: string
  target: string
  weight: number
}

/** Mulberry32 — small, fast, and identical across browsers. */
function seededRandom(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export interface LayoutOptions {
  width: number
  height: number
  seed?: number
  iterations?: number
  repulsion?: number
  springLength?: number
  springStrength?: number
  centrePull?: number
  damping?: number
}

export function computeLayout(
  nodeIds: string[],
  edges: LayoutEdge[],
  options: LayoutOptions,
): Map<string, LayoutNode> {
  const {
    width,
    height,
    seed = 42,
    iterations = 320,
    repulsion = 5200,
    springLength = 46,
    springStrength = 0.045,
    centrePull = 0.012,
    damping = 0.86,
  } = options

  const random = seededRandom(seed)
  const ids = [...nodeIds].sort()
  const nodes = new Map<string, LayoutNode>()

  // Seed on a phyllotaxis spiral rather than uniformly at random: it spreads
  // nodes evenly with no initial clumps, so the simulation converges in far
  // fewer iterations and never traps a cluster inside another.
  const golden = Math.PI * (3 - Math.sqrt(5))
  ids.forEach((id, index) => {
    const radius = Math.sqrt(index / Math.max(ids.length, 1)) * Math.min(width, height) * 0.42
    const angle = index * golden + random() * 0.12
    nodes.set(id, {
      id,
      x: width / 2 + radius * Math.cos(angle),
      y: height / 2 + radius * Math.sin(angle),
      vx: 0,
      vy: 0,
    })
  })

  const list = ids.map((id) => nodes.get(id)!)
  const links = edges
    .filter((e) => nodes.has(e.source) && nodes.has(e.target))
    .map((e) => ({ a: nodes.get(e.source)!, b: nodes.get(e.target)!, weight: e.weight }))

  for (let step = 0; step < iterations; step += 1) {
    // Cooling: large moves early to untangle, small ones late to settle.
    const cooling = 1 - step / iterations

    for (let i = 0; i < list.length; i += 1) {
      const a = list[i]
      for (let j = i + 1; j < list.length; j += 1) {
        const b = list[j]
        let dx = a.x - b.x
        let dy = a.y - b.y
        let distanceSq = dx * dx + dy * dy
        if (distanceSq < 0.01) {
          // Perfectly coincident nodes have no direction to separate along;
          // nudge them deterministically rather than with a random jitter.
          dx = (i - j) * 0.01 + 0.01
          dy = 0.01
          distanceSq = dx * dx + dy * dy
        }
        const distance = Math.sqrt(distanceSq)
        const force = (repulsion / distanceSq) * cooling
        const fx = (dx / distance) * force
        const fy = (dy / distance) * force
        a.vx += fx
        a.vy += fy
        b.vx -= fx
        b.vy -= fy
      }
    }

    for (const link of links) {
      const dx = link.b.x - link.a.x
      const dy = link.b.y - link.a.y
      const distance = Math.sqrt(dx * dx + dy * dy) || 0.01
      // Repeated transfers between a pair pull them tighter, so a ring that
      // cycles among itself visibly draws together.
      const strength = springStrength * Math.min(1 + Math.log1p(link.weight) * 0.35, 2.4)
      const force = (distance - springLength) * strength
      const fx = (dx / distance) * force
      const fy = (dy / distance) * force
      link.a.vx += fx
      link.a.vy += fy
      link.b.vx -= fx
      link.b.vy -= fy
    }

    for (const node of list) {
      node.vx += (width / 2 - node.x) * centrePull
      node.vy += (height / 2 - node.y) * centrePull
      node.vx *= damping
      node.vy *= damping
      node.x += Math.max(-24, Math.min(24, node.vx))
      node.y += Math.max(-24, Math.min(24, node.vy))
      node.x = Math.max(24, Math.min(width - 24, node.x))
      node.y = Math.max(24, Math.min(height - 24, node.y))
    }
  }

  return nodes
}
