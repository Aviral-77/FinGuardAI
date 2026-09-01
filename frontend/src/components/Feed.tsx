import { fonts, palette, formatMoney } from '../theme'
import type { FeedRow } from '../useLive'

/** Left zone: the live transaction tape, trading-terminal styled (light). */
export function Feed({ feed, onSelect }: { feed: FeedRow[]; onSelect: (id: string) => void }) {
  return (
    <aside
      style={{
        width: 320,
        flexShrink: 0,
        background: palette.panel,
        borderRight: `1px solid ${palette.line}`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          padding: '11px 14px',
          borderBottom: `1px solid ${palette.line}`,
          fontFamily: fonts.ui,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.09em',
          textTransform: 'uppercase',
          color: palette.muted,
        }}
      >
        Live transaction feed
      </header>
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {feed.length === 0 && (
          <p style={{ padding: '16px 14px', margin: 0, color: palette.muted, fontFamily: fonts.ui, fontSize: 12 }}>
            Ambient traffic only. Fire a beat to begin.
          </p>
        )}
        {feed.map((row) =>
          row.rejected ? (
            <div
              key={row.id}
              style={{
                padding: '8px 14px',
                borderBottom: `1px solid ${palette.line}`,
                borderLeft: `3px solid ${palette.alert}`,
                background: 'rgba(193,18,31,0.06)',
                fontFamily: fonts.mono,
                fontSize: 11,
                color: palette.alert,
              }}
            >
              <div style={{ fontWeight: 600 }}>BLOCKED</div>
              <div style={{ color: palette.muted, fontFamily: fonts.ui, fontSize: 10.5, marginTop: 2 }}>
                {row.reason}
              </div>
            </div>
          ) : (
            <button
              key={row.id}
              onClick={() => onSelect(row.to_account)}
              style={{
                display: 'grid',
                gridTemplateColumns: '42px 1fr auto',
                gap: 8,
                alignItems: 'baseline',
                width: '100%',
                textAlign: 'left',
                padding: '6px 14px',
                border: 'none',
                borderBottom: `1px solid ${palette.panelAlt}`,
                background: 'transparent',
                cursor: 'pointer',
                fontFamily: fonts.mono,
                fontSize: 11,
                color: palette.muted,
              }}
            >
              <span>{row.timestamp.slice(11, 16)}</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: palette.ink }}>
                {row.from_account.replace('ACC-', '')} → {row.to_account.replace('ACC-', '')}
              </span>
              <span style={{ color: palette.ink }}>{formatMoney(row.amount)}</span>
            </button>
          ),
        )}
      </div>
    </aside>
  )
}
