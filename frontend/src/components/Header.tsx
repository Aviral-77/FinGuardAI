import { fonts, palette } from '../theme'
import type { Beat } from '../useLive'

const STATUS: Record<Beat, { label: string; bg: string; fg: string }> = {
  idle: { label: 'MONITORING', bg: palette.panelAlt, fg: palette.muted },
  monitoring: { label: 'UNDER WATCH', bg: '#FBF0D8', fg: '#8A6D1F' },
  ring: { label: 'MULE RING DETECTED', bg: '#FBE0E2', fg: palette.alert },
  contained: { label: 'RING CONTAINED', bg: palette.teal, fg: '#FFFFFF' },
}

export function Header({
  beat,
  connected,
  monitored,
  transactions,
  frozenCount,
}: {
  beat: Beat
  connected: boolean
  monitored: number
  transactions: number
  frozenCount: number
}) {
  const status = STATUS[beat]
  return (
    <header
      style={{
        height: 54,
        flexShrink: 0,
        background: palette.panel,
        borderBottom: `1px solid ${palette.line}`,
        display: 'flex',
        alignItems: 'center',
        padding: '0 18px',
        gap: 16,
      }}
    >
      <span style={{ fontFamily: fonts.ui, fontSize: 16, fontWeight: 700, color: palette.ink, letterSpacing: '-0.01em' }}>
        FinGuard <span style={{ color: palette.teal }}>AI</span>
      </span>

      <span
        style={{
          fontFamily: fonts.ui,
          fontSize: 10.5,
          fontWeight: 700,
          letterSpacing: '0.09em',
          padding: '4px 10px',
          borderRadius: 5,
          background: status.bg,
          color: status.fg,
        }}
      >
        {status.label}
      </span>

      <div style={{ flex: 1 }} />

      <Metric label="Accounts" value={monitored ? monitored.toLocaleString() : '—'} />
      <Metric label="Transactions" value={transactions.toLocaleString()} />
      <Metric label="Frozen" value={String(frozenCount)} highlight={frozenCount > 0} />
      <span
        title={connected ? 'Live' : 'Disconnected'}
        style={{ width: 9, height: 9, borderRadius: 5, background: connected ? palette.teal : '#C9D2E0' }}
      />
    </header>
  )
}

function Metric({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div style={{ fontFamily: fonts.ui, fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', color: palette.muted }}>
        {label}
      </div>
      <div style={{ fontFamily: fonts.mono, fontSize: 12.5, color: highlight ? palette.alert : palette.ink, fontWeight: highlight ? 700 : 500 }}>
        {value}
      </div>
    </div>
  )
}
