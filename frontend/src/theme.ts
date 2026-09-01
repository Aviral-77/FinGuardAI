/**
 * Light-theme palette (DEMO-SPEC).
 *
 * The demo moved from the dark console to a light bank tool: white ground, dark
 * text, coloured nodes that carry far more contrast against white than against
 * ink. The score bands are the DEMO-SPEC colour ramp -- grey, amber, orange,
 * deep orange, red -- used identically on nodes, badges and the dashboard so a
 * colour reads the same wherever it appears.
 */

export const palette = {
  bg: '#F8FAFC',
  panel: '#FFFFFF',
  panelAlt: '#F1F4F9',
  ink: '#0B2545',
  muted: '#5B6780',
  line: '#DCE3EE',
  ambient: '#C3CBDD',
  teal: '#17A398',
  gold: '#D9A441',
  alert: '#C1121F',
} as const

export const fonts = {
  ui: "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
  mono: "'IBM Plex Mono', 'SF Mono', Menlo, monospace",
} as const

/** Score -> band, exactly the DEMO-SPEC thresholds and colours. */
export interface Band {
  code: string
  label: string
  colour: string
  lower: number
  upper: number
}

export const BANDS: Band[] = [
  { code: 'ALLOW', label: 'Allow', colour: '#9AA7BF', lower: 0, upper: 30 },
  { code: 'ENHANCED_MONITORING', label: 'Enhanced monitoring', colour: '#D9A441', lower: 31, upper: 50 },
  { code: 'STEP_UP_AUTH', label: 'Step-up authentication', colour: '#E08A1E', lower: 51, upper: 70 },
  { code: 'MANUAL_REVIEW', label: 'Manual fraud review', colour: '#D2691E', lower: 71, upper: 85 },
  { code: 'FREEZE', label: 'Temporary block / freeze', colour: '#C1121F', lower: 86, upper: 100 },
]

export function bandForScore(score: number): Band {
  for (const band of BANDS) {
    if (score >= band.lower && score <= band.upper) return band
  }
  return BANDS[BANDS.length - 1]
}

export function bandColour(code: string, score = 0): string {
  const found = BANDS.find((b) => b.code === code)
  return found ? found.colour : bandForScore(score).colour
}

export function formatMoney(value: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

export function shortMoney(value: number): string {
  if (value >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`
  if (value >= 1e5) return `₹${(value / 1e5).toFixed(2)} L`
  if (value >= 1e3) return `₹${(value / 1e3).toFixed(0)}K`
  return `₹${value.toFixed(0)}`
}
