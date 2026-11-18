import type { Envelope, Job, Scenario } from './types'

export async function request<T>(path: string, body?: unknown): Promise<Envelope<T>> {
  const response = await fetch(path, body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json()
  if (!response.ok) {
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((issue: { loc?: string[]; msg: string }) => [issue.loc?.join('.'), issue.msg].filter(Boolean).join(' · ')).join('\n')
      : payload.detail
    throw new Error(detail || 'The server could not complete the request.')
  }
  return payload
}

export async function simulate(scenario: Scenario, update: (job: Job) => void): Promise<Envelope<Job>> {
  let response = await request<Job>('/v1/simulations', scenario)
  update(response.data)
  while (response.data.status === 'queued' || response.data.status === 'running') {
    await new Promise((resolve) => window.setTimeout(resolve, 250))
    response = await request<Job>('/v1/simulations/' + response.data.id)
    update(response.data)
  }
  if (response.data.status === 'failed') throw new Error(response.data.error || 'Simulation failed.')
  return response
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}
