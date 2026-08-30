import { fonts, palette, formatClock } from '../theme'
import type { DatasetSummary } from '../types'

interface Props {
  summary: DatasetSummary | null
  clock: string | null
  ringFrozen: boolean
  frozenCount: number
  graphEnabled: boolean
  progress: number
}

export function Header({
  summary,
  clock,
  ringFrozen,
  frozenCount,
  graphEnabled,
  progress,
}: Props) {
  return (
    <header
      style={{
        height: 56,
        flexShrink: 0,
        background: ringFrozen ? palette.alert : palette.panel,
        borderBottom: `1px solid ${palette.line}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 18px',
        gap: 18,
        position: 'relative',
        transition: 'background 400ms ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span
          style={{
            fontFamily: fonts.ui,
            fontSize: 16,
            fontWeight: 700,
            color: '#FFFFFF',
            letterSpacing: '-0.01em',
          }}
        >
          FinGuard AI
        </span>
        <span style={{ fontFamily: fonts.ui, fontSize: 11, color: ringFrozen ? 'rgba(255,255,255,0.85)' : palette.muted }}>
          {ringFrozen ? 'RING FROZEN' : 'Fraud room'}
        </span>
      </div>

      {!graphEnabled && (
        <span
          style={{
            fontFamily: fonts.ui,
            fontSize: 10.5,
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: palette.ink,
            background: palette.gold,
            padding: '3px 8px',
            borderRadius: 4,
          }}
        >
          Rules-only view
        </span>
      )}

      <div style={{ flex: 1 }} />

      <Metric label="Window" value={clock ? formatClock(clock) : '—'} />
      <Metric label="Accounts" value={summary ? String(summary.accounts) : '—'} />
      <Metric label="Transactions" value={summary ? String(summary.transactions) : '—'} />
      <Metric label="Frozen" value={String(frozenCount)} highlight={frozenCount > 0} />

      <div
        style={{
          position: 'absolute',
          left: 0,
          bottom: 0,
          height: 2,
          width: `${progress * 100}%`,
          background: ringFrozen ? '#FFFFFF' : palette.teal,
          transition: 'width 220ms linear',
        }}
      />
    </header>
  )
}

function Metric({
  label,
  value,
  highlight,
}: {
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div
        style={{
          fontFamily: fonts.ui,
          fontSize: 9,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'rgba(255,255,255,0.55)',
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 12.5,
          color: highlight ? '#FFFFFF' : 'rgba(255,255,255,0.9)',
          fontWeight: highlight ? 700 : 500,
        }}
      >
        {value}
      </div>
    </div>
  )
}
