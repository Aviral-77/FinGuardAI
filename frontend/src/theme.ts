/**
 * Palette and type from CLAUDE.md section 7.
 *
 * The colour split carries the argument, so it is worth stating plainly:
 * red is what the *rules* caught, teal is what the *model* caught. Gold marks
 * the victim. Everything else is grey noise. An audience should be able to read
 * "rules found this / AI found this" off the graph without a legend.
 */

export const palette = {
  ink: '#0B2545',
  panel: '#0F2547',
  panelRaised: '#143059',
  teal: '#17A398',
  gold: '#D9A441',
  alert: '#C1121F',
  muted: '#7E93B4',
  line: '#1E3A63',
  text: '#E8EFF9',
  textDim: '#9DB2D0',
} as const

export const fonts = {
  ui: "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
  mono: "'IBM Plex Mono', 'SF Mono', Menlo, monospace",
} as const

/**
 * Band → colour, cool through to red as the score climbs.
 *
 * Note that no band uses the gold: gold is reserved for the victim, who is not
 * a suspect and must not read as one. On the graph the victim keeps its band
 * colour and is marked with a gold ring instead, so "this is the person who was
 * defrauded" and "this account scored 51-70" can never be confused for each
 * other.
 */
export const bandColour: Record<string, string> = {
  ALLOW: '#33507F',
  ENHANCED_MONITORING: '#5B87C4',
  STEP_UP_AUTH: '#D98324',
  MANUAL_REVIEW: '#E2673B',
  FREEZE: palette.alert,
}

export const bandOrder = [
  'ALLOW',
  'ENHANCED_MONITORING',
  'STEP_UP_AUTH',
  'MANUAL_REVIEW',
  'FREEZE',
] as const

export const categoryColour: Record<string, string> = {
  mule: '#E2673B',
  scam: palette.gold,
  takeover: '#B36AC7',
  graph: palette.alert,
}

export function formatMoney(value: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatClock(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
