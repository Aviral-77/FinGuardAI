import { useState } from 'react'
import { fonts, palette } from '../theme'

/**
 * The presenter's control strip.
 *
 * Hidden by default (a small tab), so it does not clutter the bank tool on
 * screen, and revealed with a click or the ` key. Each button fires a preset
 * trigger against the API so nothing has to be typed on stage.
 */
export function ControlStrip({
  onReset,
  onBeat1,
  onBeat2,
  onBlocked,
  busy,
  ringDetected,
}: {
  onReset: () => void
  onBeat1: () => void
  onBeat2: () => void
  onBlocked: () => void
  busy: boolean
  ringDetected: boolean
}) {
  const [open, setOpen] = useState(true)

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{ ...tab, right: 12 }} title="Show demo controls (`)">
        ▸ demo
      </button>
    )
  }

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 10px',
        background: 'rgba(255,255,255,0.96)',
        border: `1px solid ${palette.line}`,
        borderRadius: 10,
        boxShadow: '0 6px 24px rgba(11,37,71,0.12)',
      }}
    >
      <span style={{ fontFamily: fonts.ui, fontSize: 10, fontWeight: 700, letterSpacing: '0.09em', textTransform: 'uppercase', color: palette.muted }}>
        Demo
      </span>
      <Btn onClick={onReset} disabled={busy}>
        0 · Reset
      </Btn>
      <Btn onClick={onBeat1} disabled={busy} accent={palette.gold}>
        1 · Victim transfer
      </Btn>
      <Btn onClick={onBeat2} disabled={busy} accent={palette.alert}>
        2 · Fan-out
      </Btn>
      <Btn onClick={onBlocked} disabled={busy || !ringDetected} accent={palette.teal}>
        3 · Blocked attempt
      </Btn>
      <button onClick={() => setOpen(false)} style={{ ...ghost }} title="Hide">
        ✕
      </button>
    </div>
  )
}

function Btn({
  children,
  onClick,
  disabled,
  accent,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  accent?: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '7px 12px',
        borderRadius: 6,
        border: `1px solid ${accent ?? palette.line}`,
        background: disabled ? palette.panelAlt : palette.panel,
        color: disabled ? palette.muted : accent ?? palette.ink,
        fontFamily: fonts.ui,
        fontSize: 12,
        fontWeight: 600,
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {children}
    </button>
  )
}

const tab: React.CSSProperties = {
  position: 'absolute',
  bottom: 12,
  padding: '6px 10px',
  borderRadius: 8,
  border: `1px solid ${palette.line}`,
  background: palette.panel,
  color: palette.muted,
  fontFamily: fonts.ui,
  fontSize: 11,
  cursor: 'pointer',
}

const ghost: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  color: palette.muted,
  cursor: 'pointer',
  fontSize: 12,
  padding: '4px 6px',
}
