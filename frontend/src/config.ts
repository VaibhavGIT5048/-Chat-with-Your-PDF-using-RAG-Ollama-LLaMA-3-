// Single source of truth for anything environment- or endpoint-shaped.
// Pointing the app at a different backend must only require changing
// NEXT_PUBLIC_API_BASE_URL — nothing here is duplicated elsewhere.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') || 'http://localhost:8000'

export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/+$/, '') ||
  'https://vaibhavgit5048.github.io/private-rag-core'

export const REPO_URL =
  'https://github.com/VaibhavGIT5048/private-rag-core'

export const ROUTES = {
  health: '/health',
  ready: '/ready',
  ingest: '/ingest',
  query: '/query',
  collections: '/collections',
  collection: (name: string) => `/collections/${encodeURIComponent(name)}`,
} as const

// /health is cheap (server-side cached) but crosses the network; ingest runs one
// embedding call per semantic split and legitimately takes minutes on a real PDF.
export const TIMEOUTS = {
  health: 8_000,
  query: 120_000,
  ingest: 600_000,
} as const

// Faster cadence on /setup, where the visitor is explicitly waiting for the stack.
export const POLL_MS = {
  setup: 5_000,
  other: 20_000,
} as const

export const INGEST_DEFAULTS = {
  chunkSize: 1000,
  chunkOverlap: 150,
  qualityThreshold: 4.0,
  topK: 4,
} as const

export const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md'] as const

export const STORAGE_KEYS = {
  theme: 'rag.theme',
  motion: 'rag.motion',
  pipelineOpen: 'rag.pipelineOpen',
  hasConnected: 'rag.hasConnected',
} as const
