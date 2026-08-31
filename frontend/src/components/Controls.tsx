import { fonts, palette } from '../theme'
import type { Comparison } from '../types'

interface Props {
  running: boolean
  paused: boolean
  complete: boolean
  speed: number
  graphEnabled: boolean
  comparison: Comparison | null
  onPlay: () => void
  onPause: () => void
  onResume: () => void
  onStep: () => void
  onSpeed: (speed: number) => void
  onToggleGraph: (enabled: boolean) => void
}

const SPEEDS = [
  { label: '0.5×', value: 30 },
  { label: '1×', value: 60 },
  { label: '2×', value: 130 },
  { label: '4×', value: 280 },
]

export function Controls({
  running,
  paused,
  complete,
  speed,
  graphEnabled,
  comparison,
  onPlay,
  onPause,
  onResume,
  onStep,
  onSpeed,
  onToggleGraph,
}: Props) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '9px 16px',
        background: palette.panel,
        borderTop: `1px solid ${palette.line}`,
        flexShrink: 0,
      }}
    >
      {!running || complete ? (
        <button onClick={onPlay} style={{ ...button, background: palette.teal, color: palette.ink }}>
          {complete ? 'Replay' : 'Play'}
        </button>
      ) : paused ? (
        <button onClick={onResume} style={{ ...button, background: palette.teal, color: palette.ink }}>
          Resume
        </button>
      ) : (
        <button onClick={onPause} style={button}>
          Pause
        </button>
      )}
      <button onClick={onStep} style={button}>
        Step
      </button>

      <div style={{ display: 'flex', gap: 3, marginLeft: 4 }}>
        {SPEEDS.map((option) => (
          <button
            key={option.value}
            onClick={() => onSpeed(option.value)}
            style={{
              ...button,
              padding: '5px 9px',
              background: speed === option.value ? palette.panelRaised : 'transparent',
              color: speed === option.value ? palette.text : palette.muted,
            }}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div style={{ flex: 1 }} />

      {/* The proof toggle. Flipping it restarts the replay against a genuinely
          smaller rule set, rather than hiding rows from the same result. */}
      <button
        onClick={() => onToggleGraph(!graphEnabled)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          cursor: 'pointer',
          fontFamily: fonts.ui,
          fontSize: 12,
          color: palette.text,
          background: 'none',
          border: 'none',
          padding: 0,
        }}
      >
        <span style={{ color: graphEnabled ? palette.muted : palette.gold, fontWeight: 600 }}>
          Rules-only view
        </span>
        <span
          style={{
            width: 34,
            height: 18,
            borderRadius: 9,
            background: graphEnabled ? palette.line : palette.gold,
            position: 'relative',
            transition: 'background 180ms',
            display: 'inline-block',
          }}
        >
          <span
            style={{
              position: 'absolute',
              top: 2,
              left: graphEnabled ? 2 : 18,
              width: 14,
              height: 14,
              borderRadius: 7,
              background: '#FFFFFF',
              transition: 'left 180ms',
            }}
          />
        </span>
      </button>

      {comparison && (
        <span
          style={{
            fontFamily: fonts.mono,
            fontSize: 11,
            color: palette.muted,
            borderLeft: `1px solid ${palette.line}`,
            paddingLeft: 12,
          }}
        >
          full {comparison.full.frozen.length} frozen · rules-only{' '}
          <strong style={{ color: comparison.rules_only.frozen.length ? palette.text : palette.gold }}>
            {comparison.rules_only.frozen.length}
          </strong>
        </span>
      )}
    </div>
  )
}

const button: React.CSSProperties = {
  padding: '6px 13px',
  borderRadius: 5,
  border: `1px solid ${palette.line}`,
  background: palette.panelRaised,
  color: palette.text,
  fontFamily: fonts.ui,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
}
