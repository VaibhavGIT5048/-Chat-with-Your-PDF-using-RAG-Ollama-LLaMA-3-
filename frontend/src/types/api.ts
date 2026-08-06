// Mirrors the FastAPI response models exactly. Fields the backend declares as
// nullable are nullable here too — the UI must guard them.

export type SubsystemState = 'up' | 'down'

export interface HealthStatus {
  status: 'ok' | 'degraded'
  service: string
  qdrant: SubsystemState
  openai: SubsystemState
  collection_name: string | null
}

export interface IngestResponse {
  request_id: string
  collection_name: string
  filename: string
  file_type: string
  pdfs: number | null
  pages: number
  chunks: number
  passed_chunks: number
  dropped_chunks: number
  indexed_chunks: number
}

export interface SourceChunk {
  chunk_id: number | string | null
  source: string
  page: number | string | null
  /** Reciprocal Rank Fusion score — NOT a 0–1 similarity. Values are small (~0.04). */
  score: number | null
  content: string
}

export interface QueryResponse {
  request_id: string
  answer: string
  sources: SourceChunk[]
  model: string
  collection_name: string
}

export interface CollectionInfo {
  name: string
  vectors_count: number | null
  status: string | null
}

export interface DeleteCollectionResponse {
  deleted: string
  request_id: string
}

export interface IngestParams {
  file: File
  chunkSize: number
  chunkOverlap: number
  qualityThreshold: number
}

/** Connectivity state derived from polling /health. */
export type HealthState = 'checking' | 'ok' | 'degraded' | 'offline'

/** Drives the reactive canvas background and other ambient surfaces. */
export type Activity = 'idle' | 'querying' | 'ingesting' | 'connected' | 'offline'
