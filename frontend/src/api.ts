import type { CaseFile, Snapshot } from './types'

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok && response.status !== 409) {
    throw new Error(`${response.url} -> ${response.status}`)
  }
  return (await response.json()) as T
}

export const api = {
  state: () => fetch('/api/state').then((r) => jsonOrThrow<Snapshot>(r)),

  account: (id: string) => fetch(`/api/account/${id}`).then((r) => jsonOrThrow<CaseFile>(r)),

  reset: () => fetch('/api/demo/reset', { method: 'POST' }).then((r) => jsonOrThrow<Snapshot & { reset: boolean }>(r)),

  fireBeat: (n: number, staggerMs = 450) =>
    fetch(`/api/demo/beat/${n}?stagger_ms=${staggerMs}`, { method: 'POST' }).then((r) => r.json()),

  blockedAttempt: () =>
    fetch('/api/demo/blocked-attempt', { method: 'POST' }).then((r) => r.json()),

  freeze: (id: string) =>
    fetch(`/api/account/${id}/freeze`, { method: 'POST' }).then((r) => r.json()),

  report: (id: string) =>
    fetch(`/api/account/${id}/report`, { method: 'POST' }).then((r) => r.json()),

  reportPdfUrl: (id: string) => `/api/account/${id}/report.pdf`,
}
