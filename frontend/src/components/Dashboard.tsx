import { useEffect, useState } from 'react'
import { api } from '../api'
import { BANDS, bandColour, fonts, formatMoney, palette } from '../theme'
import type { CaseFile } from '../types'

interface Props {
  accountId: string | null
  frozen: Set<string>
  onFreeze: (id: string) => void
  onReport: (id: string) => void
  /** bump to force a re-fetch after a score/freeze change */
  version: number
}

/**
 * Right zone: the investigator dashboard.
 *
 * Empty until a node is selected. Then it leads with the recommended action
 * (the brief wants the verb prominent, not the number), shows the band
 * indicator across all five bands, the score breakdown summing visibly to the
 * total, and the case narrative. Action controls (Freeze / Report / Download)
 * are enabled only once the score is actually actionable -- Beat 1's whole
 * point is that they stay disabled.
 */
export function Dashboard({ accountId, frozen, onFreeze, onReport, version }: Props) {
  const [caseFile, setCaseFile] = useState<CaseFile | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!accountId) {
      setCaseFile(null)
      return
    }
    let cancelled = false
    setLoading(true)
    api
      .account(accountId)
      .then((data) => !cancelled && setCaseFile(data))
      .catch(() => !cancelled && setCaseFile(null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [accountId, version])

  return (
    <aside
      style={{
        width: 400,
        flexShrink: 0,
        background: palette.panel,
        borderLeft: `1px solid ${palette.line}`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <header
        style={{
          padding: '11px 16px',
          borderBottom: `1px solid ${palette.line}`,
          fontFamily: fonts.ui,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.09em',
          textTransform: 'uppercase',
          color: palette.muted,
        }}
      >
        Investigator
      </header>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {!accountId ? (
          <Empty />
        ) : loading && !caseFile ? (
          <p style={dim}>Loading…</p>
        ) : caseFile ? (
          <CaseView
            caseFile={caseFile}
            isFrozen={frozen.has(caseFile.account_id)}
            onFreeze={() => onFreeze(caseFile.account_id)}
            onReport={() => onReport(caseFile.account_id)}
          />
        ) : null}
      </div>
    </aside>
  )
}

function Empty() {
  return (
    <div style={{ padding: '26px 18px' }}>
      <p style={{ ...dim, padding: 0 }}>No account under investigation.</p>
      <p style={{ ...dim, padding: 0, marginTop: 12, fontSize: 11.5 }}>
        Select a node to open its case. Every point in a score traces to a named rule.
      </p>
    </div>
  )
}

function CaseView({
  caseFile,
  isFrozen,
  onFreeze,
  onReport,
}: {
  caseFile: CaseFile
  isFrozen: boolean
  onFreeze: () => void
  onReport: () => void
}) {
  const colour = bandColour(caseFile.band_code, caseFile.score)
  const action = caseFile.recommended_action
  const actionable = caseFile.actionable

  return (
    <div style={{ padding: '16px 16px 26px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2 style={{ margin: 0, fontFamily: fonts.mono, fontSize: 17, color: palette.ink, fontWeight: 600 }}>
          {caseFile.account_id}
        </h2>
        <span style={{ fontFamily: fonts.ui, fontSize: 11, color: palette.muted }}>
          {caseFile.profile.role} · {caseFile.profile.age_band}
        </span>
      </div>

      {/* Action verb first. */}
      <div style={{ marginTop: 12, padding: '12px 14px', borderRadius: 8, background: colour, color: '#FFFFFF' }}>
        <div style={{ fontFamily: fonts.ui, fontSize: 15, fontWeight: 700 }}>
          {action ? action.label : 'Allow'}
        </div>
        <div style={{ fontFamily: fonts.mono, fontSize: 22, fontWeight: 600, marginTop: 4 }}>
          {caseFile.score} <span style={{ fontSize: 12, opacity: 0.85 }}>/ 100</span>
        </div>
      </div>

      <BandMeter score={caseFile.score} />

      {!actionable && (
        <div
          style={{
            marginTop: 10,
            padding: '9px 12px',
            borderRadius: 6,
            background: palette.panelAlt,
            border: `1px solid ${palette.line}`,
            fontFamily: fonts.ui,
            fontSize: 11.5,
            color: palette.muted,
            fontStyle: 'italic',
          }}
        >
          {caseFile.evidence_note ?? 'Insufficient evidence for action. Watching for onward movement.'}
        </div>
      )}

      <Section>Case summary</Section>
      <p style={{ fontFamily: fonts.ui, fontSize: 12.5, lineHeight: 1.55, color: palette.ink, margin: 0 }}>
        {caseFile.summary}
      </p>

      {caseFile.breakdown.length > 0 && (
        <>
          <Section>
            Triggered rules{' '}
            <span style={{ color: palette.muted, fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
              (sum to {caseFile.score})
            </span>
          </Section>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {caseFile.breakdown.map((row, i) => (
              <div key={`${row.rule_id}-${i}`} style={{ background: palette.panelAlt, borderRadius: 5, padding: '8px 10px' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontFamily: fonts.mono,
                    fontSize: 11.5,
                    color: palette.ink,
                  }}
                >
                  <span style={{ fontWeight: 600 }}>
                    {row.rule_id} · {row.rule_name}
                  </span>
                  <span>
                    {row.counted ? `+${row.points}` : '+0'} <span style={{ color: palette.muted }}>→ {row.running_score}</span>
                  </span>
                </div>
                <div style={{ fontFamily: fonts.ui, fontSize: 11, color: palette.muted, marginTop: 4, lineHeight: 1.45 }}>
                  {row.message}
                  <span style={{ float: 'right', fontFamily: fonts.mono }}>{row.timestamp.slice(11, 16)}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <Section>Activity</Section>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <Stat label="Received" value={formatMoney(caseFile.activity.total_in)} />
        <Stat label="Sent" value={formatMoney(caseFile.activity.total_out)} />
        <Stat label="Counterparties" value={String(caseFile.network.counterparty_count)} />
        <Stat label="Credits" value={String(caseFile.activity.credits)} />
      </div>

      {/* Actions: enabled only when the case is actionable. */}
      <div style={{ display: 'flex', gap: 8, marginTop: 20, flexWrap: 'wrap' }}>
        <button
          onClick={onFreeze}
          disabled={!actionable || isFrozen}
          style={btn(actionable && !isFrozen ? palette.alert : '#B7C0D2', '#FFFFFF')}
        >
          {isFrozen ? 'Frozen' : 'Freeze accounts'}
        </button>
        <button
          onClick={onReport}
          disabled={!actionable}
          style={btn(actionable ? palette.ink : '#B7C0D2', '#FFFFFF')}
        >
          {caseFile.reported ? 'Filed' : 'Report'}
        </button>
        <a
          href={api.reportPdfUrl(caseFile.account_id)}
          target="_blank"
          rel="noreferrer"
          style={{
            ...btn(palette.panel, palette.ink),
            border: `1px solid ${palette.line}`,
            textDecoration: 'none',
            textAlign: 'center',
            pointerEvents: actionable ? 'auto' : 'none',
            opacity: actionable ? 1 : 0.5,
          }}
        >
          Download report
        </a>
      </div>
      {!actionable && (
        <p style={{ ...dim, padding: 0, marginTop: 8, fontSize: 10.5 }}>
          Action controls unlock once a mule pattern is confirmed.
        </p>
      )}
    </div>
  )
}

function BandMeter({ score }: { score: number }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', gap: 1 }}>
        {BANDS.map((band) => {
          const active = score >= band.lower
          return (
            <div
              key={band.code}
              title={band.label}
              style={{ flex: band.upper - band.lower + 1, background: active ? band.colour : palette.panelAlt }}
            />
          )
        })}
      </div>
    </div>
  )
}

function Section({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: fonts.ui,
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: '0.09em',
        textTransform: 'uppercase',
        color: palette.muted,
        marginTop: 20,
        marginBottom: 8,
        paddingBottom: 5,
        borderBottom: `1px solid ${palette.line}`,
      }}
    >
      {children}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: palette.panelAlt, borderRadius: 5, padding: '8px 10px' }}>
      <div style={{ fontFamily: fonts.ui, fontSize: 10, color: palette.muted }}>{label}</div>
      <div style={{ fontFamily: fonts.mono, fontSize: 12.5, color: palette.ink, marginTop: 2 }}>{value}</div>
    </div>
  )
}

const dim: React.CSSProperties = {
  padding: '18px 16px',
  fontFamily: fonts.ui,
  fontSize: 12.5,
  color: palette.muted,
  lineHeight: 1.55,
}

function btn(bg: string, fg: string): React.CSSProperties {
  return {
    flex: 1,
    minWidth: 100,
    padding: '9px 12px',
    borderRadius: 6,
    border: 'none',
    background: bg,
    color: fg,
    fontFamily: fonts.ui,
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
  }
}
