export interface GraphNode {
  id: string
  role: string
  score: number
  band_code: string
  rule_ids: string[]
  known_suspicious: boolean
  anomaly_score: number
  anomaly_flagged: boolean
  ml_network: string | null
  degree: number
}

export interface GraphEdge {
  source: string
  target: string
  count: number
  total_amount: number
  first_seen: string
}

export interface GraphPayload {
  graph_enabled: boolean
  nodes: GraphNode[]
  edges: GraphEdge[]
  communities: string[][]
}

export interface RuleDefinition {
  rule_id: string
  name: string
  category: string
  points: number
  description: string
  requires_graph: boolean
  fired: number
  accounts: number
}

export interface Band {
  code: string
  label: string
  lower: number
  upper: number
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

export interface FeatureDeparture {
  feature: string
  label: string
  unit: string
  value: number
  population_mean: number
  z_score: number
  direction: string
}

export interface CaseFile {
  account_id: string
  generated_at: string
  profile: {
    name: string
    age_band: string
    role: string
    open_date: string
    kyc_date: string
    dormant: boolean
    known_suspicious: boolean
    phone: string
    address: string
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
  activity: {
    credits: number
    debits: number
    total_in: number
    total_out: number
  }
  network: {
    direct_counterparties: string[]
    counterparty_count: number
    ml_networks: string[]
  }
  anomaly: {
    score: number
    rank: number
    flagged: boolean
    elevated: boolean
    top_features: FeatureDeparture[]
    explanation: string
  } | null
  summary: string
  evidence: {
    txn_id: string
    timestamp: string
    from_account: string
    to_account: string
    amount: number
    channel: string
    cited_by: string[]
  }[]
}

export interface NetworkCase {
  network_id: string
  account_count: number
  density: number
  mean_anomaly: number
  max_rule_score: number
  missed_by_rules: boolean
  recommended_action: { code: string; label: string }
  rationale: string[]
  headline: string
  members: {
    account_id: string
    rule_score: number
    rule_ids: string[]
    anomaly_score: number
    anomaly_rank: number | null
    explanation: string
  }[]
}

export interface Comparison {
  full: EngineSnapshot
  rules_only: EngineSnapshot
  ring_accounts_caught_by_full: string[]
  ring_accounts_caught_by_rules_only: string[]
  missed_networks: NetworkCase[]
}

export interface EngineSnapshot {
  flagged_accounts: number
  rules_fired: string[]
  frozen: string[]
  highest_score: number
  actions: number
}

export interface DatasetSummary {
  accounts: number
  transactions: number
  device_sessions: number
  beneficiaries: number
  window_start: string
  window_end: string
  total_value: number
  bands: Record<string, number>
  rules_fired: Record<string, number>
  flagged_accounts: number
  ml_networks: number
  missed_networks: number
}

/* ---- replay events ---------------------------------------------------- */

export interface ReplayBase {
  at: string
  kind: string
}

export interface TransactionEvent extends ReplayBase {
  kind: 'transaction'
  txn_id: string
  from_account: string
  to_account: string
  amount: number
  channel: string
}

export interface RuleFiredEvent extends ReplayBase {
  kind: 'rule_fired'
  account_id: string
  rule_id: string
  rule_name: string
  category: string
  points: number
  counted: boolean
  score_before: number
  score_after: number
  band_code: string
  band_label: string
  crossed_into: string | null
  message: string
  evidence_txn_ids: string[]
}

export interface ActionEvent extends ReplayBase {
  kind: 'action'
  account_id: string
  code: string
  label: string
  verb: string
  score: number
  triggered_by?: string
  reason: string
}

export interface MlFlagEvent extends ReplayBase {
  kind: 'ml_flag'
  account_id: string
  anomaly_score: number
  rank: number
  rule_score: number
  top_features: FeatureDeparture[]
}

export interface MlNetworkEvent extends ReplayBase {
  kind: 'ml_network'
  network_id: string
  account_ids: string[]
  density: number
  mean_anomaly: number
  max_rule_score: number
  missed_by_rules: boolean
  action_code: string
  action_label: string
  rationale: string[]
}

export type ReplayEvent =
  | TransactionEvent
  | RuleFiredEvent
  | ActionEvent
  | MlFlagEvent
  | MlNetworkEvent
  | (ReplayBase & { kind: 'complete'; flagged_accounts: number; missed_networks: number })
  | (ReplayBase & { kind: 'ready'; total_events: number })
