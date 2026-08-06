// Geometry for the retrieval-pipeline visualiser (viewBox 0 0 940 590).
// `stage` is the choreography step at which a node/edge lights up.
//
// IMPORTANT: this is an illustrative view of the backend pipeline, timed to the
// in-flight request. The frontend makes ONE /query call and has no per-stage
// telemetry, so no measured timings or counts are ever shown here.

export interface PipeNode {
  id: string
  stage: number
  x: number
  y: number
  w: number
  h: number
  label: string
  sub?: string
}

export interface PipeEdge {
  stage: number
  d: string
}

export const PIPE_NODES: PipeNode[] = [
  { id: 'q', stage: 0, x: 360, y: 6, w: 220, h: 44, label: 'Question' },
  { id: 'dense', stage: 1, x: 30, y: 92, w: 300, h: 50, label: 'Dense · OpenAI embedding' },
  { id: 'sparse', stage: 1, x: 610, y: 92, w: 300, h: 50, label: 'Sparse · BM25 keywords' },
  { id: 'qdrant', stage: 2, x: 30, y: 166, w: 300, h: 50, label: 'Qdrant vector search' },
  {
    id: 'rrf',
    stage: 3,
    x: 320,
    y: 250,
    w: 300,
    h: 58,
    label: 'Reciprocal Rank Fusion',
    sub: 'dense 0.65 / sparse 0.35',
  },
  { id: 'gate', stage: 4, x: 320, y: 334, w: 300, h: 44, label: 'Chunk quality-gate weighting' },
  { id: 'rank', stage: 5, x: 320, y: 400, w: 300, h: 44, label: 'Flashrank reranker → top-K' },
  { id: 'neigh', stage: 6, x: 320, y: 466, w: 300, h: 44, label: 'Neighbour context expansion ±1' },
  { id: 'gen', stage: 7, x: 320, y: 532, w: 300, h: 48, label: 'gpt-4o-mini → grounded answer' },
]

export const PIPE_EDGES: PipeEdge[] = [
  { stage: 1, d: 'M470 50 L470 70 L180 70 L180 92' },
  { stage: 1, d: 'M470 50 L470 70 L760 70 L760 92' },
  { stage: 2, d: 'M180 142 L180 166' },
  { stage: 3, d: 'M180 216 L180 232 L400 232 L400 250' },
  { stage: 3, d: 'M760 142 L760 232 L540 232 L540 250' },
  { stage: 4, d: 'M470 308 L470 334' },
  { stage: 5, d: 'M470 378 L470 400' },
  { stage: 6, d: 'M470 444 L470 466' },
  { stage: 7, d: 'M470 510 L470 532' },
]

export const MAX_PIPE_STAGE = 7

/** Rotating copy for the in-flight query indicator. */
export const QUERY_STAGES = [
  'Embedding the question…',
  'Searching dense + sparse indexes…',
  'Fusing rankings (RRF)…',
  'Reranking with Flashrank…',
  'Expanding neighbouring chunks…',
  'Composing a grounded answer…',
]

/** Rotating copy for ingest, which is genuinely slow on real PDFs. */
export const INGEST_STAGES = [
  'Extracting text…',
  'Splitting semantically…',
  'Scoring chunk quality…',
  'Embedding chunks — this is the slow part…',
  'Indexing into Qdrant…',
  'Still going. Real PDFs take minutes, not seconds…',
]
