// The only place in the app that calls fetch. Every function is typed, every
// request has an AbortController timeout, and every failure surfaces the
// FastAPI `detail` string plus the X-Request-ID for debuggability.

import { API_BASE_URL, ROUTES, TIMEOUTS } from '@/config'
import type {
  CollectionInfo,
  DeleteCollectionResponse,
  HealthStatus,
  IngestParams,
  IngestResponse,
  QueryResponse,
} from '@/types/api'

export class ApiError extends Error {
  readonly status: number | null
  readonly detail: string
  readonly requestId: string | null

  constructor(status: number | null, detail: string, requestId: string | null) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.requestId = requestId
  }

  /** 404 from /query means nothing has been ingested yet — an empty state, not an error. */
  get isNotIngested() {
    return this.status === 404
  }
}

interface RequestOptions {
  method?: string
  body?: BodyInit
  headers?: Record<string, string>
  timeout: number
  signal?: AbortSignal
}

async function request<T>(path: string, opts: RequestOptions): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), opts.timeout)

  // Respect an externally supplied signal (component unmount) as well as the timeout.
  const onExternalAbort = () => controller.abort()
  opts.signal?.addEventListener('abort', onExternalAbort)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: opts.method ?? 'GET',
      body: opts.body,
      headers: opts.headers,
      signal: controller.signal,
    })
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError'
    throw new ApiError(
      null,
      aborted
        ? `Request timed out after ${Math.round(opts.timeout / 1000)}s`
        : 'Could not reach the backend. Is the stack running?',
      null,
    )
  } finally {
    clearTimeout(timer)
    opts.signal?.removeEventListener('abort', onExternalAbort)
  }

  const headerRequestId = response.headers.get('X-Request-ID')

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    // Some error paths return an empty body; fall through with payload = null.
  }

  const bodyRecord = (payload ?? {}) as Record<string, unknown>
  const bodyRequestId = typeof bodyRecord.request_id === 'string' ? bodyRecord.request_id : null

  if (!response.ok) {
    const detail =
      typeof bodyRecord.detail === 'string'
        ? bodyRecord.detail
        : `HTTP ${response.status} ${response.statusText}`.trim()
    throw new ApiError(response.status, detail, bodyRequestId ?? headerRequestId)
  }

  return payload as T
}

export function getHealth(signal?: AbortSignal) {
  return request<HealthStatus>(ROUTES.health, { timeout: TIMEOUTS.health, signal })
}

export function ingest({ file, chunkSize, chunkOverlap, qualityThreshold }: IngestParams) {
  const form = new FormData()
  form.append('file', file)
  form.append('chunk_size', String(chunkSize))
  form.append('chunk_overlap', String(chunkOverlap))
  form.append('quality_threshold', String(qualityThreshold))

  // No Content-Type header: the browser must set the multipart boundary itself.
  return request<IngestResponse>(ROUTES.ingest, {
    method: 'POST',
    body: form,
    timeout: TIMEOUTS.ingest,
  })
}

export function query(question: string, topK: number) {
  return request<QueryResponse>(ROUTES.query, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
    timeout: TIMEOUTS.query,
  })
}

export function listCollections() {
  return request<CollectionInfo[]>(ROUTES.collections, { timeout: TIMEOUTS.health })
}

export function deleteCollection(name: string) {
  return request<DeleteCollectionResponse>(ROUTES.collection(name), {
    method: 'DELETE',
    timeout: TIMEOUTS.health,
  })
}
