import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Controls } from './components/Controls'
import { CopilotPanel } from './components/CopilotPanel'
import { FeedPanel } from './components/FeedPanel'
import { ForceGraph } from './components/ForceGraph'
import { Header } from './components/Header'
import { MLBanner } from './components/MLBanner'
import { fonts, palette } from './theme'
import type { Comparison, DatasetSummary, GraphPayload, NetworkCase } from './types'
import { useReplay } from './useReplay'

export default function App() {
  const { state, start, pause, resume, step, setSpeed } = useReplay()

  const [graph, setGraph] = useState<GraphPayload | null>(null)
  const [summary, setSummary] = useState<DatasetSummary | null>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [networkCases, setNetworkCases] = useState<NetworkCase[]>([])

  const [graphEnabled, setGraphEnabled] = useState(true)
  const [speed, setSpeedValue] = useState(60)
  const [selected, setSelected] = useState<string | null>(null)
  const [openNetwork, setOpenNetwork] = useState<string | null>(null)
  const [lockedAccounts, setLockedAccounts] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.summary(), api.comparison(), api.networks()])
      .then(([summaryData, comparisonData, networksData]) => {
        setSummary(summaryData)
        setComparison(comparisonData)
        setNetworkCases(networksData.items)
      })
      .catch((err) => setError(String(err)))
  }, [])

  useEffect(() => {
    api.graph(graphEnabled).then(setGraph).catch((err) => setError(String(err)))
  }, [graphEnabled])

  const handlePlay = useCallback(() => {
    setLockedAccounts(new Set())
    setOpenNetwork(null)
    start(speed, graphEnabled)
  }, [start, speed, graphEnabled])

  const handleSpeed = useCallback(
    (next: number) => {
      setSpeedValue(next)
      setSpeed(next)
    },
    [setSpeed],
  )

  const handleToggleGraph = useCallback(
    (enabled: boolean) => {
      setGraphEnabled(enabled)
      setLockedAccounts(new Set())
      setOpenNetwork(null)
      setSelected(null)
      // Restart against the other engine immediately: the comparison only
      // reads if both sides are watched running, not described.
      start(speed, enabled)
    },
    [start, speed],
  )

  const handleApprove = useCallback((accountIds: string[]) => {
    setLockedAccounts((previous) => {
      const next = new Set(previous)
      accountIds.forEach((id) => next.add(id))
      return next
    })
  }, [])

  const selectAccount = useCallback((accountId: string) => {
    setOpenNetwork(null)
    setSelected(accountId)
  }, [])

  const ringFrozen = lockedAccounts.size > 0
  const frozen = useMemo(() => {
    const combined = new Set(state.frozen)
    lockedAccounts.forEach((id) => combined.add(id))
    return combined
  }, [state.frozen, lockedAccounts])

  const activeNetworkCase = useMemo(
    () => networkCases.find((n) => n.network_id === openNetwork) ?? null,
    [networkCases, openNetwork],
  )

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: palette.ink,
        color: palette.text,
        fontFamily: fonts.ui,
        overflow: 'hidden',
      }}
    >
      <Header
        summary={summary}
        clock={state.clock}
        ringFrozen={ringFrozen}
        frozenCount={frozen.size}
        graphEnabled={graphEnabled}
        progress={state.progress}
      />

      {error && (
        <div
          style={{
            background: palette.alert,
            color: '#FFFFFF',
            padding: '8px 16px',
            fontSize: 12,
          }}
        >
          {error} — is the backend running on port 8000?
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <FeedPanel feed={state.feed} firings={state.firings} onSelect={selectAccount} />

        <main style={{ flex: 1, position: 'relative', minWidth: 0 }}>
          {graph ? (
            <ForceGraph
              graph={graph}
              liveScores={state.scores}
              liveBands={state.bands}
              mlFlagged={state.mlFlagged}
              mlMissed={state.mlMissed}
              pulses={state.pulses}
              selected={selected}
              onSelect={selectAccount}
              frozen={frozen}
            />
          ) : (
            <div
              style={{
                display: 'grid',
                placeItems: 'center',
                height: '100%',
                color: palette.muted,
                fontSize: 13,
              }}
            >
              Loading network…
            </div>
          )}
          <MLBanner networks={state.networks} onOpen={setOpenNetwork} />
        </main>

        <CopilotPanel
          accountId={selected}
          networkCase={activeNetworkCase}
          onApprove={handleApprove}
          approved={
            activeNetworkCase
              ? activeNetworkCase.members.every((m) => lockedAccounts.has(m.account_id))
              : selected
                ? lockedAccounts.has(selected)
                : false
          }
          onSelect={selectAccount}
          onClearNetwork={() => setOpenNetwork(null)}
        />
      </div>

      <Controls
        running={state.running}
        paused={state.paused}
        complete={state.complete}
        speed={speed}
        graphEnabled={graphEnabled}
        comparison={comparison}
        onPlay={handlePlay}
        onPause={pause}
        onResume={resume}
        onStep={step}
        onSpeed={handleSpeed}
        onToggleGraph={handleToggleGraph}
      />
    </div>
  )
}
