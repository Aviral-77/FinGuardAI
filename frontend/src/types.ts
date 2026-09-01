export interface NodeSummary {
  account_id: string
  score: number
  band_code: string
  band_label: string
  rule_ids: string[]
  frozen: boolean
  role: string
  known_suspicious: boolean
}

export interface EdgeSummary {
  source: string
  target: string
  count: number
  total_amount: number
}

export interface RingInfo {
  accounts: string[]
  count: number
  value_in_motion: number
}

export interface Snapshot {
  nodes: NodeSummary[]
  edges: EdgeSummary[]
  frozen: string[]
  ring: RingInfo | null
  flagged: string[]
  monitored_accounts: number
  transactions: number
}

export interface BreakdownRow {
  rule_id: string
  rule_name: string
  category: string
  points: number
  counted: boolean
  running_score: number
  timestamp: string
  message: string
  evidence_txn_ids: string[]
}

export interface CaseFile {
  account_id: string
  generated_at: string
  profile: {
    name: string
    age_band: string
    role: string
  }
  score: number
  band_code: string
  band_label: string
  recommended_action: {
    code: string
    label: string
    verb: string
    detail: string
    blocking: boolean
    reason: string
  } | null
  breakdown: BreakdownRow[]
  activity: { credits: number; debits: number; total_in: number; total_out: number }
  network: { direct_counterparties: string[]; counterparty_count: number }
  summary: string
  evidence: {
    txn_id: string
    timestamp: string
    from_account: string
    to_account: string
    amount: number
    cited_by: string[]
  }[]
  frozen: boolean
  reported: boolean
  actionable: boolean
  evidence_note?: string
}

/* ---- live WebSocket events -------------------------------------------- */

export interface WsSnapshot extends Snapshot {
  kind: 'snapshot'
}
export interface WsReset {
  kind: 'reset'
}
export interface WsTransaction {
  kind: 'transaction'
  transaction_id: string
  from_account: string
  to_account: string
  amount: number
  timestamp: string
  channel: string
}
export interface WsScoreUpdate {
  kind: 'score_update'
  nodes: NodeSummary[]
}
export interface WsRingDetected extends RingInfo {
  kind: 'ring_detected'
}
export interface WsFrozen {
  kind: 'frozen'
  account_id: string
}
export interface WsReported {
  kind: 'reported'
  account_id: string
}
export interface WsRejected {
  kind: 'rejected'
  from_account: string
  to_account: string
  reason: string
}

export type WsEvent =
  | WsSnapshot
  | WsReset
  | WsTransaction
  | WsScoreUpdate
  | WsRingDetected
  | WsFrozen
  | WsReported
  | WsRejected
