// Geometry for the retrieval + ingest pipeline visualiser (viewBox 0 0 940 740).
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
  { id: 'q', stage: 0, x: 360, y: 6, w: 220, h: 42, label: 'Question' },
  { id: 'guard', stage: 1, x: 360, y: 70, w: 220, h: 42, label: 'JWT + prompt guardrails' },
  { id: 'rewrite', stage: 2, x: 360, y: 134, w: 220, h: 42, label: 'Query rewrite' },
  { id: 'dense', stage: 3, x: 30, y: 216, w: 300, h: 50, label: 'Dense · bge-m3 embedding' },
  { id: 'sparse', stage: 3, x: 610, y: 216, w: 300, h: 50, label: 'Sparse · BM25 keywords' },
  { id: 'qdrant', stage: 4, x: 30, y: 290, w: 300, h: 50, label: 'Qdrant filtered search' },
  { id: 'rrf', stage: 5, x: 320, y: 372, w: 300, h: 58, label: 'Reciprocal Rank Fusion', sub: 'dense 0.65 / sparse 0.35' },
  { id: 'gate', stage: 6, x: 320, y: 456, w: 300, h: 44, label: 'Chunk quality-gate weighting' },
  { id: 'rank', stage: 7, x: 320, y: 526, w: 300, h: 44, label: 'Flashrank reranker → top-K' },
  { id: 'neigh', stage: 8, x: 320, y: 596, w: 300, h: 44, label: 'Neighbour context expansion ±1' },
  { id: 'gen', stage: 9, x: 320, y: 666, w: 300, h: 48, label: 'gpt-5-mini → cited answer' },
  { id: 'parser', stage: 2, x: 670, y: 134, w: 240, h: 42, label: 'Parser router' },
]

export const PIPE_EDGES: PipeEdge[] = [
  { stage: 1, d: 'M470 48 L470 70' },
  { stage: 2, d: 'M470 112 L470 134' },
  { stage: 2, d: 'M580 155 L670 155' },
  { stage: 3, d: 'M470 176 L470 196 L180 196 L180 216' },
  { stage: 3, d: 'M470 176 L470 196 L760 196 L760 216' },
  { stage: 4, d: 'M180 266 L180 290' },
  { stage: 5, d: 'M180 340 L180 354 L400 354 L400 372' },
  { stage: 5, d: 'M760 266 L760 354 L540 354 L540 372' },
  { stage: 6, d: 'M470 430 L470 456' },
  { stage: 7, d: 'M470 500 L470 526' },
  { stage: 8, d: 'M470 570 L470 596' },
  { stage: 9, d: 'M470 640 L470 666' },
]

export const MAX_PIPE_STAGE = 9

/** Rotating copy for the in-flight query indicator. */
export const QUERY_STAGES = [
  'Checking auth and data guardrails…',
  'Rewriting the question against chat history…',
  'Embedding with bge-m3…',
  'Searching dense + sparse indexes…',
  'Fusing rankings (RRF)…',
  'Reranking with Flashrank…',
  'Expanding neighbouring chunks…',
  'Composing a grounded answer…',
]

/** Rotating copy for ingest, which is genuinely slow on real PDFs. */
export const INGEST_STAGES = [
  'Routing file to the best parser…',
  'Extracting structured text…',
  'Splitting by document sections…',
  'Scoring chunk quality…',
  'Embedding chunks — this is the slow part…',
  'Indexing into Qdrant…',
  'Still going. Real PDFs take minutes, not seconds…',
]
