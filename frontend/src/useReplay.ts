import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  ActionEvent,
  MlNetworkEvent,
  ReplayEvent,
  RuleFiredEvent,
  TransactionEvent,
} from './types'

const FEED_LIMIT = 40
const PULSE_LIMIT = 60
const PULSE_MS = 1400

export interface ReplayState {
  connected: boolean
  running: boolean
  paused: boolean
  clock: string | null
  feed: TransactionEvent[]
  firings: RuleFiredEvent[]
  scores: Map<string, number>
  bands: Map<string, string>
  frozen: Set<string>
  mlFlagged: Set<string>
  mlMissed: Set<string>
  networks: MlNetworkEvent[]
  latestAction: ActionEvent | null
  pulses: { from: string; to: string; born: number }[]
  complete: boolean
  progress: number
}

const EMPTY: ReplayState = {
  connected: false,
  running: false,
  paused: false,
  clock: null,
  feed: [],
  firings: [],
  scores: new Map(),
  bands: new Map(),
  frozen: new Set(),
  mlFlagged: new Set(),
  mlMissed: new Set(),
  networks: [],
  latestAction: null,
  pulses: [],
  complete: false,
  progress: 0,
}

export function useReplay() {
  const socketRef = useRef<WebSocket | null>(null)
  const [state, setState] = useState<ReplayState>(EMPTY)
  const totalRef = useRef(0)
  const seenRef = useRef(0)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/replay`)
    socketRef.current = socket

    socket.onopen = () => setState((s) => ({ ...s, connected: true }))
    socket.onclose = () => setState((s) => ({ ...s, connected: false, running: false }))

    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as ReplayEvent & { total_events?: number }
      seenRef.current += 1

      setState((previous) => {
        const next: ReplayState = {
          ...previous,
          clock: 'at' in event && event.at ? event.at : previous.clock,
          progress: totalRef.current ? Math.min(1, seenRef.current / totalRef.current) : 0,
        }

        switch (event.kind) {
          case 'ready': {
            totalRef.current = event.total_events ?? 0
            seenRef.current = 0
            // A fresh run must not inherit the previous run's reds -- that is
            // exactly what would make the rules-only toggle look like a lie.
            return {
              ...EMPTY,
              connected: true,
              running: true,
              paused: false,
            }
          }
          case 'transaction': {
            const pulse = { from: event.from_account, to: event.to_account, born: performance.now() }
            const cutoff = performance.now() - PULSE_MS
            next.feed = [event, ...previous.feed].slice(0, FEED_LIMIT)
            next.pulses = [pulse, ...previous.pulses.filter((p) => p.born > cutoff)].slice(
              0,
              PULSE_LIMIT,
            )
            return next
          }
          case 'rule_fired': {
            next.scores = new Map(previous.scores).set(event.account_id, event.score_after)
            next.bands = new Map(previous.bands).set(event.account_id, event.band_code)
            next.firings = [event, ...previous.firings].slice(0, 60)
            if (event.band_code === 'FREEZE') {
              next.frozen = new Set(previous.frozen).add(event.account_id)
            }
            return next
          }
          case 'action': {
            next.latestAction = event
            if (event.code === 'FREEZE') {
              next.frozen = new Set(previous.frozen).add(event.account_id)
            }
            return next
          }
          case 'ml_flag': {
            next.mlFlagged = new Set(previous.mlFlagged).add(event.account_id)
            return next
          }
          case 'ml_network': {
            next.networks = [...previous.networks, event]
            if (event.missed_by_rules) {
              const missed = new Set(previous.mlMissed)
              event.account_ids.forEach((id) => missed.add(id))
              next.mlMissed = missed
            }
            return next
          }
          case 'complete': {
            next.running = false
            next.complete = true
            next.progress = 1
            return next
          }
          default:
            return next
        }
      })
    }

    return () => socket.close()
  }, [])

  const send = useCallback((payload: Record<string, unknown>) => {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload))
    }
  }, [])

  const start = useCallback(
    (speed: number, graphEnabled: boolean) => {
      send({ cmd: 'start', speed, graph_enabled: graphEnabled })
    },
    [send],
  )

  const pause = useCallback(() => {
    send({ cmd: 'pause' })
    setState((s) => ({ ...s, paused: true }))
  }, [send])

  const resume = useCallback(() => {
    send({ cmd: 'resume' })
    setState((s) => ({ ...s, paused: false }))
  }, [send])

  const step = useCallback(() => {
    send({ cmd: 'step' })
    setState((s) => ({ ...s, paused: true }))
  }, [send])

  const setSpeed = useCallback((speed: number) => send({ cmd: 'speed', speed }), [send])

  return { state, start, pause, resume, step, setSpeed }
}
