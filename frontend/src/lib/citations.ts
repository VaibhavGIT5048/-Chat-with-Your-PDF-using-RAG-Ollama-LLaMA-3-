// The backend's system prompt instructs the model to cite inline as
// `[Source: <filename> | Page: <page>]`. We parse those markers out of the
// answer so they can be rendered as interactive chips linked to source cards.

import type { SourceChunk } from '@/types/api'

const CITATION_RE = /\[Source:\s*([^|\]]+?)\s*\|\s*Page:\s*([^\]]+?)\s*\]/g

export type AnswerPart =
  | { kind: 'text'; text: string }
  | { kind: 'citation'; source: string; page: string; raw: string }

export function parseAnswer(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = []
  let cursor = 0

  // Fresh lastIndex each call — the regex is module-scoped and stateful.
  CITATION_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = CITATION_RE.exec(answer)) !== null) {
    if (match.index > cursor) {
      parts.push({ kind: 'text', text: answer.slice(cursor, match.index) })
    }
    parts.push({ kind: 'citation', source: match[1], page: match[2], raw: match[0] })
    cursor = match.index + match[0].length
  }

  if (cursor < answer.length) {
    parts.push({ kind: 'text', text: answer.slice(cursor) })
  }
  return parts
}

/**
 * Find which source cards a citation refers to. Page is compared as a string
 * because the API types it as `number | string | null`.
 */
export function matchSourceIndices(
  sources: SourceChunk[],
  source: string,
  page: string,
): number[] {
  const wantFile = source.trim().toLowerCase()
  const wantPage = page.trim().toLowerCase()

  const exact = sources.reduce<number[]>((acc, s, i) => {
    const fileMatches = (s.source ?? '').trim().toLowerCase() === wantFile
    const pageMatches = String(s.page ?? '').trim().toLowerCase() === wantPage
    if (fileMatches && pageMatches) acc.push(i)
    return acc
  }, [])
  if (exact.length) return exact

  // Fall back to filename only — the model sometimes cites a page that got
  // merged away by neighbour expansion.
  return sources.reduce<number[]>((acc, s, i) => {
    if ((s.source ?? '').trim().toLowerCase() === wantFile) acc.push(i)
    return acc
  }, [])
}

/**
 * RRF scores are tiny (~0.04) and are NOT similarities. Any bar must be
 * normalised against the max score in the current result set, never treated
 * as a 0–1 fraction.
 */
export function scoreBarPercent(score: number | null, maxScore: number): string {
  if (typeof score !== 'number' || maxScore <= 0) return '0%'
  return `${Math.max(4, (score / maxScore) * 100)}%`
}

export function maxScore(sources: SourceChunk[]): number {
  return sources.reduce((m, s) => (typeof s.score === 'number' ? Math.max(m, s.score) : m), 0)
}

export function formatScore(score: number | null): string {
  return typeof score === 'number' ? score.toFixed(4) : '—'
}
