import { fonts, palette } from '../theme'
import type { MlNetworkEvent } from '../types'

interface Props {
  networks: MlNetworkEvent[]
  onOpen: (networkId: string) => void
}

/**
 * The Act 3 banner.
 *
 * It only appears for networks the *rules did not escalate*, because that is
 * the whole claim. A banner that also announced the ring the rules already
 * froze would say nothing — the interesting result is specifically the one no
 * threshold reached.
 */
export function MLBanner({ networks, onOpen }: Props) {
  const missed = networks.filter((network) => network.missed_by_rules)
  if (missed.length === 0) return null

  return (
    <div
      style={{
        position: 'absolute',
        left: 16,
        right: 16,
        bottom: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      {missed.map((network) => (
        <button
          key={network.network_id}
          onClick={() => onOpen(network.network_id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            width: '100%',
            textAlign: 'left',
            background: 'rgba(23,163,152,0.14)',
            border: `1px solid ${palette.teal}`,
            borderRadius: 8,
            padding: '12px 16px',
            cursor: 'pointer',
            backdropFilter: 'blur(6px)',
          }}
        >
          <span
            style={{
              fontFamily: fonts.ui,
              fontSize: 9.5,
              fontWeight: 700,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: palette.ink,
              background: palette.teal,
              padding: '4px 8px',
              borderRadius: 4,
              whiteSpace: 'nowrap',
            }}
          >
            Anomaly model
          </span>
          <span style={{ flex: 1 }}>
            <span
              style={{
                display: 'block',
                fontFamily: fonts.ui,
                fontSize: 13.5,
                fontWeight: 700,
                color: palette.text,
              }}
            >
              Mule network of {network.account_ids.length} connected accounts — no rule fired
            </span>
            <span
              style={{
                display: 'block',
                fontFamily: fonts.mono,
                fontSize: 11,
                color: palette.teal,
                marginTop: 3,
              }}
            >
              {network.network_id} · highest rule score in cluster {network.max_rule_score} ·{' '}
              density {(network.density * 100).toFixed(0)}% · {network.action_label}
            </span>
          </span>
          <span style={{ fontFamily: fonts.ui, fontSize: 11.5, color: palette.teal }}>
            Open case →
          </span>
        </button>
      ))}
    </div>
  )
}
