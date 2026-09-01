import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { Canvas } from './components/Canvas'
import { ControlStrip } from './components/ControlStrip'
import { Dashboard } from './components/Dashboard'
import { Feed } from './components/Feed'
import { Header } from './components/Header'
import { fonts, palette } from './theme'
import { useLive } from './useLive'

export default function App() {
  const { state, refresh } = useLive()
  const [selected, setSelected] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    refresh()
  }, [refresh])

  // Re-fetch the open case whenever scores or freezes move.
  useEffect(() => {
    setVersion((v) => v + 1)
  }, [state.nodes, state.frozen])

  const guard = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true)
      try {
        await fn()
      } finally {
        setBusy(false)
      }
    },
    [],
  )

  const onReset = useCallback(() => {
    setSelected(null)
    // Reload the snapshot after resetting so Beat 0 shows the ambient grey-node
    // field -- "a normal afternoon at the bank" -- rather than a blank canvas.
    return guard(async () => {
      await api.reset()
      await refresh()
    })
  }, [guard, refresh])

  const onBeat1 = useCallback(() => guard(async () => {
    await api.fireBeat(1)
    setSelected('ACC-V001')
  }), [guard])

  const onBeat2 = useCallback(() => guard(() => api.fireBeat(2)), [guard])

  const onBlocked = useCallback(() => guard(() => api.blockedAttempt()), [guard])

  const onFreeze = useCallback(
    (id: string) => {
      // Freeze the whole detected ring when freezing a member, so the closing
      // beat contains the network rather than one node.
      const targets = state.ring && state.ring.accounts.includes(id) ? state.ring.accounts : [id]
      return guard(async () => {
        for (const t of targets) await api.freeze(t)
      })
    },
    [guard, state.ring],
  )

  const onReport = useCallback((id: string) => guard(() => api.report(id)), [guard])

  // ` toggles nothing here but keydown 0/1/2/3 fire the beats for a hands-free demo.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === '0') onReset()
      if (e.key === '1') onBeat1()
      if (e.key === '2') onBeat2()
      if (e.key === '3') onBlocked()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onReset, onBeat1, onBeat2, onBlocked])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: palette.bg,
        color: palette.ink,
        fontFamily: fonts.ui,
        overflow: 'hidden',
      }}
    >
      <Header
        beat={state.beat}
        connected={state.connected}
        monitored={state.monitored}
        transactions={state.transactionCount}
        frozenCount={state.frozen.size}
      />
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <Feed feed={state.feed} onSelect={setSelected} />
        <main style={{ flex: 1, position: 'relative', minWidth: 0, background: palette.panel }}>
          <Canvas
            nodes={state.nodes}
            edges={state.edges}
            frozen={state.frozen}
            ring={state.ring}
            pulses={state.pulses}
            selected={selected}
            onSelect={setSelected}
          />
          <ControlStrip
            onReset={onReset}
            onBeat1={onBeat1}
            onBeat2={onBeat2}
            onBlocked={onBlocked}
            busy={busy}
            ringDetected={!!state.ring}
          />
        </main>
        <Dashboard
          accountId={selected}
          frozen={state.frozen}
          onFreeze={onFreeze}
          onReport={onReport}
          version={version}
        />
      </div>
    </div>
  )
}
