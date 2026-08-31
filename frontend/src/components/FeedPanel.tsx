import { fonts, palette, formatMoney } from '../theme'
import type { RuleFiredEvent, TransactionEvent } from '../types'
import { categoryColour } from '../theme'

interface Props {
  feed: TransactionEvent[]
  firings: RuleFiredEvent[]
  onSelect: (accountId: string) => void
}

/**
 * The left zone: a live transaction tape, trading-terminal styled.
 *
 * Rule firings are interleaved into the same column rather than given their own
 * panel. The point of the demo is that a rule fires *because of* a transfer you
 * just watched arrive, and splitting them into two lists loses that link.
 */
export function FeedPanel({ feed, firings, onSelect }: Props) {
  // Take a bounded slice of each *before* merging. Merging first and then
  // truncating loses the rule firings entirely during a busy stretch -- dozens
  // of transfers arrive between rules, and the alerts are the one thing that
  // must never scroll away.
  const merged = [
    ...feed.slice(0, 30).map((event) => ({ kind: 'txn' as const, at: event.at, event })),
    ...firings.slice(0, 14).map((event) => ({ kind: 'rule' as const, at: event.at, event })),
  ].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))

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
      <PanelHeader title="Live transaction feed" count={feed.length} />
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {merged.length === 0 && (
          <p
            style={{
              padding: '16px 14px',
              margin: 0,
              color: palette.textDim,
              fontFamily: fonts.ui,
              fontSize: 12,
            }}
          >
            Press Play to replay the window.
          </p>
        )}
        {merged.map((row) =>
          row.kind === 'txn' ? (
            <TransactionRow key={row.event.txn_id} event={row.event} onSelect={onSelect} />
          ) : (
            <RuleRow
              key={`${row.event.account_id}-${row.event.rule_id}-${row.event.at}`}
              event={row.event}
              onSelect={onSelect}
            />
          ),
        )}
      </div>
    </aside>
  )
}

function PanelHeader({ title, count }: { title: string; count?: number }) {
  return (
    <header
      style={{
        padding: '11px 14px',
        borderBottom: `1px solid ${palette.line}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
    >
      <span
        style={{
          fontFamily: fonts.ui,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.09em',
          textTransform: 'uppercase',
          color: palette.textDim,
        }}
      >
        {title}
      </span>
      {count !== undefined && (
        <span style={{ fontFamily: fonts.mono, fontSize: 11, color: palette.muted }}>{count}</span>
      )}
    </header>
  )
}

function TransactionRow({
  event,
  onSelect,
}: {
  event: TransactionEvent
  onSelect: (id: string) => void
}) {
  return (
    <div
      style={{
        padding: '6px 14px',
        borderBottom: `1px solid rgba(30,58,99,0.4)`,
        fontFamily: fonts.mono,
        fontSize: 11,
        color: palette.textDim,
        display: 'grid',
        gridTemplateColumns: '46px 1fr auto',
        gap: 8,
        alignItems: 'baseline',
      }}
    >
      <span style={{ color: palette.muted }}>{event.at.slice(11, 16)}</span>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <button onClick={() => onSelect(event.from_account)} style={linkStyle}>
          {event.from_account.replace('ACC-', '')}
        </button>
        <span style={{ color: palette.muted }}> → </span>
        <button onClick={() => onSelect(event.to_account)} style={linkStyle}>
          {event.to_account.replace('ACC-', '')}
        </button>
      </span>
      <span style={{ color: palette.text }}>{formatMoney(event.amount)}</span>
    </div>
  )
}

function RuleRow({
  event,
  onSelect,
}: {
  event: RuleFiredEvent
  onSelect: (id: string) => void
}) {
  const colour = categoryColour[event.category] ?? palette.alert
  return (
    <button
      onClick={() => onSelect(event.account_id)}
      style={{
        display: 'block',
        width: '100%',
        textAlign: 'left',
        padding: '8px 14px 8px 11px',
        borderBottom: `1px solid rgba(30,58,99,0.4)`,
        borderLeft: `3px solid ${colour}`,
        background: 'rgba(193,18,31,0.07)',
        color: palette.text,
        cursor: 'pointer',
        font: 'inherit',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontFamily: fonts.mono,
          fontSize: 11,
        }}
      >
        <span style={{ color: colour, fontWeight: 600 }}>
          {event.rule_id} {event.account_id.replace('ACC-', '')}
        </span>
        <span style={{ color: palette.text }}>
          {event.counted ? `+${event.points}` : '+0'} → {event.score_after}
        </span>
      </div>
      <div
        style={{
          fontFamily: fonts.ui,
          fontSize: 10.5,
          color: palette.textDim,
          marginTop: 3,
          lineHeight: 1.4,
        }}
      >
        {event.rule_name}
        {event.crossed_into && (
          <strong style={{ color: colour }}> · {event.band_label}</strong>
        )}
      </div>
    </button>
  )
}

const linkStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  padding: 0,
  font: 'inherit',
  color: palette.text,
  cursor: 'pointer',
  textDecoration: 'none',
}
