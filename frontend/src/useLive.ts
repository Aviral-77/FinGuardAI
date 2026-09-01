import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type {
  EdgeSummary,
  NodeSummary,
  RingInfo,
  WsEvent,
  WsTransaction,
} from './types'

export type Beat = 'idle' | 'monitoring' | 'ring' | 'contained'

export interface FeedRow {
  id: string
  from_account: string
  to_account: string
  amount: number
  timestamp: string
  rejected?: boolean
  reason?: string
}

export interface LiveState {
  connected: boolean
  nodes: Map<string, NodeSummary>
  edges: EdgeSummary[]
  frozen: Set<string>
  ring: RingInfo | null
  feed: FeedRow[]
  pulses: { from: string; to: string; born: number }[]
  beat: Beat
  monitored: number
  transactionCount: number
  ringJustDetected: number // timestamp, to trigger the banner animation
}

const FEED_LIMIT = 40
const PULSE_LIMIT = 50
const PULSE_MS = 1200

export function useLive() {
  const socketRef = useRef<WebSocket | null>(null)
  const [state, setState] = useState<LiveState>(() => ({
    connected: false,
    nodes: new Map(),
    edges: [],
    frozen: new Set(),
    ring: null,
    feed: [],
    pulses: [],
    beat: 'idle',
    monitored: 0,
    transactionCount: 0,
    ringJustDetected: 0,
  }))

  const apply = useCallback((event: WsEvent) => {
    setState((prev) => {
      switch (event.kind) {
        case 'snapshot': {
          const nodes = new Map(event.nodes.map((n) => [n.account_id, n]))
          return {
            ...prev,
            nodes,
            edges: event.edges,
            frozen: new Set(event.frozen),
            ring: event.ring,
            monitored: event.monitored_accounts,
            transactionCount: event.transactions,
            beat: event.ring ? 'ring' : event.flagged.length > 0 ? 'monitoring' : 'idle',
          }
        }
        case 'reset': {
          return {
            ...prev,
            nodes: new Map(),
            edges: [],
            frozen: new Set(),
            ring: null,
            feed: [],
            pulses: [],
            beat: 'idle',
            ringJustDetected: 0,
          }
        }
        case 'transaction': {
          const tx = event as WsTransaction
          const row: FeedRow = {
            id: tx.transaction_id,
            from_account: tx.from_account,
            to_account: tx.to_account,
            amount: tx.amount,
            timestamp: tx.timestamp,
          }
          const born = performance.now()
          return {
            ...prev,
            feed: [row, ...prev.feed].slice(0, FEED_LIMIT),
            transactionCount: prev.transactionCount + 1,
            pulses: [
              { from: tx.from_account, to: tx.to_account, born },
              ...prev.pulses.filter((p) => p.born > born - PULSE_MS),
            ].slice(0, PULSE_LIMIT),
          }
        }
        case 'score_update': {
          const nodes = new Map(prev.nodes)
          for (const node of event.nodes) nodes.set(node.account_id, node)
          const anyFlagged = [...nodes.values()].some((n) => n.band_code !== 'ALLOW')
          return {
            ...prev,
            nodes,
            beat: prev.beat === 'idle' && anyFlagged ? 'monitoring' : prev.beat,
          }
        }
        case 'ring_detected': {
          const ring: RingInfo = {
            accounts: event.accounts,
            count: event.count,
            value_in_motion: event.value_in_motion,
          }
          return {
            ...prev,
            ring,
            beat: prev.beat === 'contained' ? 'contained' : 'ring',
            ringJustDetected: Date.now(),
          }
        }
        case 'frozen': {
          const frozen = new Set(prev.frozen).add(event.account_id)
          const nodes = new Map(prev.nodes)
          const node = nodes.get(event.account_id)
          if (node) nodes.set(event.account_id, { ...node, frozen: true })
          // Any freeze of a ring member contains the ring.
          const contained = prev.ring ? prev.ring.accounts.some((a) => frozen.has(a)) : false
          return { ...prev, frozen, nodes, beat: contained ? 'contained' : prev.beat }
        }
        case 'rejected': {
          const row: FeedRow = {
            id: `rej-${performance.now()}`,
            from_account: event.from_account,
            to_account: event.to_account,
            amount: 0,
            timestamp: new Date().toISOString(),
            rejected: true,
            reason: event.reason,
          }
          return { ...prev, feed: [row, ...prev.feed].slice(0, FEED_LIMIT) }
        }
        default:
          return prev
      }
    })
  }, [])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/live`)
    socketRef.current = socket
    socket.onopen = () => setState((s) => ({ ...s, connected: true }))
    socket.onclose = () => setState((s) => ({ ...s, connected: false }))
    socket.onmessage = (m) => apply(JSON.parse(m.data) as WsEvent)
    return () => socket.close()
  }, [apply])

  // Prune expired pulses on a light interval so the canvas cleans up even when
  // no new transactions arrive.
  useEffect(() => {
    const timer = setInterval(() => {
      setState((s) => {
        const cutoff = performance.now() - PULSE_MS
        if (s.pulses.every((p) => p.born > cutoff)) return s
        return { ...s, pulses: s.pulses.filter((p) => p.born > cutoff) }
      })
    }, 600)
    return () => clearInterval(timer)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const snap = await api.state()
      apply({ kind: 'snapshot', ...snap })
    } catch {
      /* backend not up yet; the socket will deliver a snapshot on connect */
    }
  }, [apply])

  return { state, refresh }
}
