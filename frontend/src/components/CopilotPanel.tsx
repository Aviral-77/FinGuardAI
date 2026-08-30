import { useEffect, useState } from 'react'
import { api } from '../api'
import { bandColour, categoryColour, fonts, formatMoney, palette } from '../theme'
import type { CaseFile, NetworkCase } from '../types'

interface Props {
  accountId: string | null
  networkCase: NetworkCase | null
  onApprove: (accountIds: string[]) => void
  approved: boolean
  onSelect: (accountId: string) => void
  onClearNetwork: () => void
}

/**
 * The right zone: the investigator copilot.
 *
 * The brief's second failure is that an alert arrives as an id, a score and a
 * rule number, and the analyst spends 30-45 minutes assembling context. This
 * panel is that context, pre-assembled -- and the action verb is given more
 * weight than the number, because the brief asks for recommendations, not flags.
 */
export function CopilotPanel({
  accountId,
  networkCase,
  onApprove,
  approved,
  onSelect,
  onClearNetwork,
}: Props) {
  const [caseFile, setCaseFile] = useState<CaseFile | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!accountId) {
      setCaseFile(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .caseFile(accountId)
      .then((data) => !cancelled && setCaseFile(data))
      .catch((err) => !cancelled && setError(String(err)))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [accountId])

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
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span style={sectionLabel}>Investigator copilot</span>
        {networkCase && (
          <button onClick={onClearNetwork} style={ghostButton}>
            close
          </button>
        )}
      </header>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {networkCase ? (
          <NetworkView networkCase={networkCase} onSelect={onSelect} onApprove={onApprove} approved={approved} />
        ) : !accountId ? (
          <Empty />
        ) : loading ? (
          <p style={dimText}>Loading case file…</p>
        ) : error ? (
          <p style={{ ...dimText, color: palette.alert }}>{error}</p>
        ) : caseFile ? (
          <AccountView caseFile={caseFile} onApprove={onApprove} approved={approved} onSelect={onSelect} />
        ) : null}
      </div>
    </aside>
  )
}

function Empty() {
  return (
    <div style={{ padding: '28px 18px' }}>
      <p style={{ ...dimText, padding: 0 }}>
        Select an account on the graph to open its case file.
      </p>
      <p style={{ ...dimText, padding: 0, marginTop: 14, fontSize: 11.5 }}>
        Every score here is the sum of named rules. The anomaly model reports
        alongside it and never contributes points to it.
      </p>
    </div>
  )
}

function AccountView({
  caseFile,
  onApprove,
  approved,
  onSelect,
}: {
  caseFile: CaseFile
  onApprove: (ids: string[]) => void
  approved: boolean
  onSelect: (id: string) => void
}) {
  const colour = bandColour[caseFile.band_code] ?? bandColour.ALLOW
  const action = caseFile.recommended_action

  return (
    <div style={{ padding: '16px 16px 28px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <h2
          style={{
            margin: 0,
            fontFamily: fonts.mono,
            fontSize: 17,
            color: palette.text,
            fontWeight: 600,
          }}
        >
          {caseFile.account_id}
        </h2>
        <span style={{ fontFamily: fonts.ui, fontSize: 11, color: palette.muted }}>
          {caseFile.profile.role} · {caseFile.profile.age_band}
        </span>
      </div>

      {/* Action first, score second: the brief asks for the verb to lead. */}
      {action && (
        <div
          style={{
            marginTop: 12,
            padding: '12px 14px',
            borderRadius: 7,
            background: colour,
            color: caseFile.band_code === 'STEP_UP_AUTH' ? palette.ink : '#FFFFFF',
          }}
        >
          <div
            style={{
              fontFamily: fonts.ui,
              fontSize: 15,
              fontWeight: 700,
              letterSpacing: '0.01em',
            }}
          >
            {action.label}
          </div>
          <div style={{ fontFamily: fonts.ui, fontSize: 11.5, marginTop: 4, opacity: 0.92 }}>
            {action.detail}
          </div>
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 11,
              marginTop: 8,
              opacity: 0.95,
            }}
          >
            score {caseFile.score} / 100
          </div>
        </div>
      )}

      <Section title="Summary" />
      <p
        style={{
          fontFamily: fonts.ui,
          fontSize: 12.5,
          lineHeight: 1.55,
          color: palette.text,
          margin: 0,
        }}
      >
        {caseFile.summary}
      </p>

      {caseFile.breakdown.length > 0 && (
        <>
          <Section title="Triggered rules" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {caseFile.breakdown.map((row, index) => (
              <div
                key={`${row.rule_id}-${index}`}
                style={{
                  borderLeft: `3px solid ${categoryColour[row.category] ?? palette.muted}`,
                  background: palette.panelRaised,
                  borderRadius: 4,
                  padding: '8px 10px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontFamily: fonts.mono,
                    fontSize: 11.5,
                    color: palette.text,
                  }}
                >
                  <span style={{ fontWeight: 600 }}>
                    {row.rule_id} · {row.rule_name}
                  </span>
                  <span>
                    {row.counted ? `+${row.points}` : '+0'}{' '}
                    <span style={{ color: palette.muted }}>→ {row.running_score}</span>
                  </span>
                </div>
                <div
                  style={{
                    fontFamily: fonts.ui,
                    fontSize: 11,
                    color: palette.textDim,
                    marginTop: 4,
                    lineHeight: 1.45,
                  }}
                >
                  {row.message}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {caseFile.anomaly && (caseFile.anomaly.flagged || caseFile.anomaly.elevated) && (
        <>
          <Section title="Anomaly model" accent={palette.teal} />
          <div
            style={{
              border: `1px solid ${palette.teal}`,
              borderRadius: 6,
              padding: '10px 12px',
              background: 'rgba(23,163,152,0.09)',
            }}
          >
            <div style={{ fontFamily: fonts.mono, fontSize: 11.5, color: palette.teal }}>
              rank {caseFile.anomaly.rank} · score {caseFile.anomaly.score.toFixed(3)}
              {caseFile.anomaly.flagged ? ' · flagged' : ' · elevated'}
            </div>
            <p
              style={{
                fontFamily: fonts.ui,
                fontSize: 11.5,
                color: palette.text,
                margin: '7px 0 0',
                lineHeight: 1.5,
              }}
            >
              {caseFile.anomaly.explanation}
            </p>
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {caseFile.anomaly.top_features.map((feature) => (
                <div
                  key={feature.feature}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontFamily: fonts.mono,
                    fontSize: 10.5,
                    color: palette.textDim,
                  }}
                >
                  <span>{feature.label}</span>
                  <span style={{ color: palette.teal }}>
                    {feature.z_score > 0 ? '+' : ''}
                    {feature.z_score.toFixed(1)}σ
                  </span>
                </div>
              ))}
            </div>
            <p
              style={{
                fontFamily: fonts.ui,
                fontSize: 10.5,
                color: palette.muted,
                margin: '9px 0 0',
                fontStyle: 'italic',
              }}
            >
              Reported separately — the anomaly score contributes no points to
              the rule score above.
            </p>
          </div>
        </>
      )}

      <Section title="Activity" />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <Stat label="Received" value={formatMoney(caseFile.activity.total_in)} />
        <Stat label="Sent" value={formatMoney(caseFile.activity.total_out)} />
        <Stat label="Credits" value={String(caseFile.activity.credits)} />
        <Stat label="Counterparties" value={String(caseFile.network.counterparty_count)} />
      </div>

      {caseFile.evidence.length > 0 && (
        <>
          <Section title="Evidence" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {caseFile.evidence.slice(0, 6).map((row) => (
              <div
                key={row.txn_id}
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 10.5,
                  color: palette.textDim,
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '4px 0',
                  borderBottom: `1px solid rgba(30,58,99,0.5)`,
                }}
              >
                <span>
                  {row.timestamp.slice(5, 16).replace('T', ' ')}{' '}
                  <button style={linkButton} onClick={() => onSelect(row.from_account)}>
                    {row.from_account.replace('ACC-', '')}
                  </button>
                  →
                  <button style={linkButton} onClick={() => onSelect(row.to_account)}>
                    {row.to_account.replace('ACC-', '')}
                  </button>
                </span>
                <span style={{ color: palette.text, whiteSpace: 'nowrap' }}>
                  {formatMoney(row.amount)}{' '}
                  <span style={{ color: palette.alert }}>{row.cited_by.join(',')}</span>
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
        <button
          onClick={() => onApprove([caseFile.account_id, ...caseFile.network.direct_counterparties])}
          disabled={approved || !action?.blocking}
          style={{
            ...primaryButton,
            background: approved ? palette.muted : palette.alert,
            cursor: approved || !action?.blocking ? 'default' : 'pointer',
            opacity: !action?.blocking ? 0.4 : 1,
          }}
        >
          {approved ? 'Locked' : `Approve — ${action?.verb ?? 'Allow'}`}
        </button>
        <a
          href={api.markdownUrl(caseFile.account_id)}
          target="_blank"
          rel="noreferrer"
          style={{ ...secondaryButton, textDecoration: 'none', textAlign: 'center' }}
        >
          Export case
        </a>
      </div>
    </div>
  )
}

function NetworkView({
  networkCase,
  onSelect,
  onApprove,
  approved,
}: {
  networkCase: NetworkCase
  onSelect: (id: string) => void
  onApprove: (ids: string[]) => void
  approved: boolean
}) {
  const missed = networkCase.missed_by_rules
  const accent = missed ? palette.teal : palette.alert
  return (
    <div style={{ padding: '16px 16px 28px' }}>
      <div
        style={{
          border: `1px solid ${accent}`,
          borderRadius: 7,
          padding: '12px 14px',
          background: missed ? 'rgba(23,163,152,0.1)' : 'rgba(193,18,31,0.1)',
        }}
      >
        <div style={{ fontFamily: fonts.mono, fontSize: 12, color: accent, fontWeight: 600 }}>
          {networkCase.network_id}
        </div>
        <div
          style={{
            fontFamily: fonts.ui,
            fontSize: 14,
            fontWeight: 700,
            color: palette.text,
            marginTop: 6,
            lineHeight: 1.4,
          }}
        >
          {networkCase.headline}
        </div>
      </div>

      <Section title="Why" accent={accent} />
      <ul
        style={{
          margin: 0,
          paddingLeft: 16,
          fontFamily: fonts.ui,
          fontSize: 12,
          color: palette.text,
          lineHeight: 1.55,
        }}
      >
        {networkCase.rationale.map((line, index) => (
          <li key={index} style={{ marginBottom: 6 }}>
            {line}
          </li>
        ))}
      </ul>

      <Section title="Members" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {networkCase.members.map((member) => (
          <button
            key={member.account_id}
            onClick={() => onSelect(member.account_id)}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              width: '100%',
              background: palette.panelRaised,
              border: 'none',
              borderRadius: 4,
              padding: '7px 10px',
              cursor: 'pointer',
              fontFamily: fonts.mono,
              fontSize: 11,
              color: palette.text,
            }}
          >
            <span>{member.account_id.replace('ACC-', '')}</span>
            <span style={{ display: 'flex', gap: 10 }}>
              <span style={{ color: member.rule_score > 0 ? palette.alert : palette.muted }}>
                rules {member.rule_score}
              </span>
              <span style={{ color: accent }}>ml {member.anomaly_score.toFixed(2)}</span>
            </span>
          </button>
        ))}
      </div>

      <div
        style={{
          marginTop: 16,
          padding: '10px 12px',
          borderRadius: 6,
          background: palette.panelRaised,
        }}
      >
        <div style={sectionLabel}>Recommended action</div>
        <div
          style={{
            fontFamily: fonts.ui,
            fontSize: 14,
            fontWeight: 700,
            color: accent,
            marginTop: 5,
          }}
        >
          {networkCase.recommended_action.label}
        </div>
      </div>

      <button
        onClick={() => onApprove(networkCase.members.map((m) => m.account_id))}
        disabled={approved}
        style={{
          ...primaryButton,
          width: '100%',
          marginTop: 16,
          background: approved ? palette.muted : accent,
          color: missed ? palette.ink : '#FFFFFF',
          cursor: approved ? 'default' : 'pointer',
        }}
      >
        {approved ? 'Network locked' : `Approve — lock ${networkCase.account_count} accounts`}
      </button>
    </div>
  )
}

function Section({ title, accent }: { title: string; accent?: string }) {
  return (
    <div
      style={{
        ...sectionLabel,
        color: accent ?? palette.textDim,
        marginTop: 20,
        marginBottom: 8,
        paddingBottom: 5,
        borderBottom: `1px solid ${palette.line}`,
      }}
    >
      {title}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: palette.panelRaised, borderRadius: 5, padding: '8px 10px' }}>
      <div style={{ fontFamily: fonts.ui, fontSize: 10, color: palette.muted }}>{label}</div>
      <div style={{ fontFamily: fonts.mono, fontSize: 12.5, color: palette.text, marginTop: 2 }}>
        {value}
      </div>
    </div>
  )
}

const sectionLabel: React.CSSProperties = {
  fontFamily: fonts.ui,
  fontSize: 10.5,
  fontWeight: 600,
  letterSpacing: '0.09em',
  textTransform: 'uppercase',
  color: palette.textDim,
}

const dimText: React.CSSProperties = {
  padding: '18px 16px',
  fontFamily: fonts.ui,
  fontSize: 12.5,
  color: palette.textDim,
  lineHeight: 1.55,
}

const primaryButton: React.CSSProperties = {
  flex: 1,
  padding: '10px 12px',
  borderRadius: 6,
  border: 'none',
  color: '#FFFFFF',
  fontFamily: fonts.ui,
  fontSize: 12.5,
  fontWeight: 600,
}

const secondaryButton: React.CSSProperties = {
  padding: '10px 12px',
  borderRadius: 6,
  border: `1px solid ${palette.line}`,
  background: 'transparent',
  color: palette.textDim,
  fontFamily: fonts.ui,
  fontSize: 12.5,
  cursor: 'pointer',
}

const ghostButton: React.CSSProperties = {
  background: 'none',
  border: 'none',
  padding: 0,
  fontFamily: fonts.ui,
  fontSize: 11,
  color: palette.muted,
  cursor: 'pointer',
}

const linkButton: React.CSSProperties = {
  background: 'none',
  border: 'none',
  padding: '0 3px',
  font: 'inherit',
  color: palette.text,
  cursor: 'pointer',
}
