import type {
  CaseFile,
  Comparison,
  DatasetSummary,
  GraphPayload,
  NetworkCase,
  RuleDefinition,
  Band,
} from './types'

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export const api = {
  summary: () => get<DatasetSummary>('/api/dataset/summary'),
  graph: (graphEnabled: boolean) =>
    get<GraphPayload>(`/api/graph?graph_enabled=${graphEnabled}`),
  rules: () => get<{ items: RuleDefinition[]; bands: Band[] }>('/api/rules'),
  caseFile: (accountId: string) => get<CaseFile>(`/api/copilot/${accountId}`),
  networks: () =>
    get<{ items: NetworkCase[]; missed_count: number }>('/api/ml/networks'),
  comparison: () => get<Comparison>('/api/comparison'),
  markdownUrl: (accountId: string) => `/api/copilot/${accountId}/markdown`,
}
