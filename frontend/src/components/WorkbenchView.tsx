'use client'

// The live workbench. Ingest, query, source inspection and collection
// management stay in one route so the user can move from setup to answers
// without losing context.

import { useCallback, useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import { Search } from 'lucide-react'

import { API_BASE_URL } from '@/config'
import { useActivity } from '@/hooks/useActivity'
import { useHealth } from '@/hooks/useHealth'
import { useToast } from '@/hooks/useToast'
import { useUiPrefs } from '@/hooks/useUiPrefs'
import { formatScore, maxScore, matchSourceIndices, parseAnswer, scoreBarPercent } from '@/lib/citations'
import { MAX_PIPE_STAGE, QUERY_STAGES } from '@/lib/pipeline'
import { ApiError, query } from '@/services/api'
import type { SourceChunk } from '@/types/api'
import { CollectionsPanel } from '@/components/CollectionsPanel'
import { IngestPanel } from '@/components/IngestPanel'
import { PipelineVisualiser } from '@/components/PipelineVisualiser'
import { Button, Eyebrow, Mono, Panel, PanelHeader, Spinner } from '@/components/ui'

interface Turn {
  id: string
  question: string
  topK: number
  pending: boolean
  answer?: string
  sources: SourceChunk[]
  model?: string
  requestId?: string
  error?: string
  errorTitle?: string
}

interface CitationFocus {
  turnId: string
  source: string
  page: string
}

const DEFAULT_TOP_K = 4

export function WorkbenchView() {
  const { health, isConnected } = useHealth()
  const { setBusy } = useActivity()
  const { flash, announce } = useToast()
  const { motionOff } = useUiPrefs()

  const [question, setQuestion] = useState('')
  const [topK, setTopK] = useState(DEFAULT_TOP_K)
  const [transcript, setTranscript] = useState<Turn[]>([])
  const [querying, setQuerying] = useState(false)
  const [thinkingIdx, setThinkingIdx] = useState(0)
  const [typed, setTyped] = useState(0)
  const [pipeStage, setPipeStage] = useState(-1)
  const [focus, setFocus] = useState<CitationFocus | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)

  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const typeTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const clearTimers = useCallback(() => {
    if (stageTimer.current) clearInterval(stageTimer.current)
    if (typeTimer.current) clearInterval(typeTimer.current)
    stageTimer.current = null
    typeTimer.current = null
  }, [])

  useEffect(() => () => clearTimers(), [clearTimers])

  const latestId = transcript.at(-1)?.id ?? null

  const startTyping = useCallback(
    (answer: string) => {
      if (motionOff) {
        setTyped(answer.length)
        return
      }

      if (typeTimer.current) clearInterval(typeTimer.current)
      setTyped(0)
      const step = Math.max(2, Math.round(answer.length / 90))
      typeTimer.current = setInterval(() => {
        setTyped((current) => {
          const next = current + step
          if (next >= answer.length) {
            if (typeTimer.current) clearInterval(typeTimer.current)
            typeTimer.current = null
            return answer.length
          }
          return next
        })
      }, 26)
    },
    [motionOff],
  )

  const patchTurn = useCallback((id: string, patch: Partial<Turn>) => {
    setTranscript((current) => current.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn)))
  }, [])

  const submitQuery = useCallback(async () => {
    const trimmed = question.trim()
    if (!trimmed || querying || !isConnected) return

    const id = `q-${Date.now()}`
    setTranscript((current) => current.concat([{ id, question: trimmed, topK, pending: true, sources: [] }]))
    setQuestion('')
    setQuerying(true)
    setThinkingIdx(0)
    setTyped(0)
    setPipeStage(0)
    setFocus(null)
    setBusy('querying')
    clearTimers()

    stageTimer.current = setInterval(() => {
      setThinkingIdx((current) => (current + 1) % QUERY_STAGES.length)
      setPipeStage((current) => Math.min(current + 1, MAX_PIPE_STAGE))
    }, 620)

    try {
      const result = await query(trimmed, topK)
      const sources = result.sources ?? []
      patchTurn(id, {
        pending: false,
        answer: result.answer,
        sources,
        model: result.model,
        requestId: result.request_id,
      })
      setPipeStage(MAX_PIPE_STAGE)
      announce(`Answer ready with ${sources.length} sources.`)
      startTyping(result.answer)
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null
      const notIngested = apiErr?.isNotIngested ?? false
      const detail =
        notIngested
          ? 'Nothing is indexed yet, so there is nothing to ground an answer in. Ingest a document and ask again.'
          : apiErr?.detail ?? (err instanceof Error ? err.message : 'Unknown error')
      patchTurn(id, {
        pending: false,
        error: detail,
        errorTitle: notIngested
          ? 'No document indexed yet'
          : `Request failed${apiErr?.status ? ` — HTTP ${apiErr.status}` : ''}`,
        requestId: apiErr?.requestId ?? 'none returned',
      })
      flash(notIngested ? 'Ingest a document first' : `Query failed — ${detail}`)
    } finally {
      if (stageTimer.current) clearInterval(stageTimer.current)
      stageTimer.current = null
      setQuerying(false)
      setBusy(null)
    }
  }, [announce, clearTimers, flash, isConnected, patchTurn, question, querying, setBusy, startTyping, topK])

  const connected = isConnected
  const hasExistingIndex = Boolean(health?.collection_name)
  const emptyTranscript = transcript.length === 0

  const renderAnswer = (turn: Turn) => {
    const visibleAnswer =
      turn.id === latestId && turn.answer && typed < turn.answer.length ? turn.answer.slice(0, typed) : turn.answer ?? ''
    const parts = parseAnswer(visibleAnswer)

    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-[12px] opacity-55">
          <span className="font-extrabold uppercase tracking-[0.12em]">{turn.model ?? 'unknown model'}</span>
          <span>·</span>
          <Mono className="text-[11.5px]">request {turn.requestId?.slice(0, 8) ?? '—'}</Mono>
        </div>

        <div className="text-[15px] leading-[1.7]">
          {parts.map((part, index) => {
            if (part.kind === 'text') {
              return <span key={`${turn.id}-text-${index}`}>{part.text}</span>
            }

            const active = focus?.turnId === turn.id && focus.source === part.source && focus.page === part.page
            return (
              <button
                key={`${turn.id}-citation-${index}`}
                type="button"
                onClick={() =>
                  setFocus((current) =>
                    active ? null : { turnId: turn.id, source: part.source, page: part.page },
                  )
                }
                className="mx-[3px] inline-flex items-center rounded-[var(--r-sm)] border px-2 py-[2px] text-[12.5px] font-extrabold transition-transform"
                style={{
                  verticalAlign: '1px',
                  borderColor: 'var(--accent)',
                  background: active
                    ? 'var(--accent)'
                    : 'color-mix(in srgb, var(--accent) 12%, transparent)',
                  color: active ? 'var(--on-accent)' : 'var(--accent-hi)',
                }}
              >
                {part.source} · p{part.page}
              </button>
            )
          })}
          {turn.id === latestId && turn.answer && typed < turn.answer.length && (
            <span className="ml-1 inline-block align-baseline text-[16px]" style={{ animation: 'caret 1s step-end infinite' }}>
              |
            </span>
          )}
        </div>
      </div>
    )
  }

  return (
    <main className="relative z-10 mx-auto max-w-[1320px] px-[26px] pb-20 pt-8">
      <section className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-[52ch]">
          <Eyebrow className="mb-4">Workbench</Eyebrow>
          <h1 className="m-0 text-[clamp(34px,4.8vw,58px)] font-extrabold leading-[0.96] tracking-[-0.035em]">
            Ingest a PDF, ask a question, inspect the sources.
          </h1>
          <p className="m-0 mt-4 text-[17px] leading-[1.55] opacity-70">
            The backend stays honest: every answer is grounded, every citation is clickable, and every
            collection delete is typed-confirmed.
          </p>
        </div>

        {!connected && (
          <Panel className="max-w-[440px]">
            <div className="p-5">
              <div className="mb-2 text-[11px] font-extrabold uppercase tracking-[0.12em] opacity-55">
                Backend unavailable
              </div>
              <div className="text-[14px] leading-[1.55] opacity-75">
                Waiting for backend on <span className="font-extrabold">{API_BASE_URL}</span>.
                The workbench will activate automatically once /health reports ok.
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                <Link href="/setup">
                  <Button variant="ghost">Back to setup</Button>
                </Link>
                <Button variant="chip" onClick={() => flash('Check the setup page for the next step')}>
                  What now?
                </Button>
              </div>
            </div>
          </Panel>
        )}
      </section>

      <div className="grid gap-7 lg:grid-cols-[minmax(320px,0.9fr)_minmax(420px,1.5fr)]">
        <div className="grid gap-7">
          <IngestPanel
            connected={connected}
            hasExistingIndex={hasExistingIndex}
            onIngested={() => setRefreshToken((token) => token + 1)}
          />

          <Panel>
            <PanelHeader title="Quick status" right={<span className="text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-50">live</span>} />
            <div className="grid gap-3 p-5 text-[13px] leading-[1.55]">
              <div className="flex justify-between gap-4">
                <span className="opacity-65">Backend</span>
                <span className="font-extrabold">{connected ? 'Connected' : 'Offline'}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="opacity-65">Collection</span>
                <span className="font-extrabold">{health?.collection_name ?? '—'}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="opacity-65">Transit mode</span>
                <span className="font-extrabold">{querying ? QUERY_STAGES[thinkingIdx] : 'Ready'}</span>
              </div>
            </div>
          </Panel>
        </div>

        <div className="grid gap-7">
          <Panel>
            <PanelHeader
              title="Query"
              right={
                <div className="flex items-center gap-3">
                  <label htmlFor="top-k" className="text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-55">
                    top-k
                  </label>
                  <select
                    id="top-k"
                    value={topK}
                    onChange={(e) => setTopK(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                    className="px-[7px] py-[5px] text-[12px] font-extrabold"
                    style={{
                      color: 'var(--ink)',
                      background: 'var(--chip-bg)',
                      border: 'var(--brd-w) solid var(--brd)',
                      borderRadius: 'var(--r-sm)',
                    }}
                  >
                    {[3, 4, 5, 6, 8, 10].map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </div>
              }
            />

            <div className="p-5">
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    e.preventDefault()
                    void submitQuery()
                  }
                }}
                placeholder="What is the carbon intensity reduction goal, and by when?"
                rows={3}
                className="w-full resize-y px-[14px] py-[14px] text-[15.5px] leading-[1.55]"
                style={{
                  fontFamily: 'var(--font-archivo)',
                  color: 'var(--ink)',
                  background: 'var(--chip-bg)',
                  border: 'var(--brd-w) solid var(--brd)',
                  borderRadius: 'var(--r-sm)',
                }}
              />

              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Button variant="solid" onClick={() => void submitQuery()} disabled={!question.trim() || querying || !connected}>
                  {querying ? <Spinner size={14} /> : <Search size={14} aria-hidden />}
                  {querying ? 'Retrieving…' : 'Ask'}
                </Button>
                <div className="text-[12px] opacity-60">
                  {querying ? QUERY_STAGES[thinkingIdx] : connected ? 'Cmd/Ctrl + Enter to submit' : 'Connect the backend first'}
                </div>
              </div>
            </div>
          </Panel>

          {emptyTranscript ? (
            <Panel>
              <div className="grid gap-3 p-11">
                <div className="flex gap-1">
                  <span className="h-2 w-2 rounded-full bg-[var(--accent)] opacity-80" />
                  <span className="h-2 w-2 rounded-full bg-[var(--accent)] opacity-50" />
                  <span className="h-2 w-2 rounded-full bg-[var(--accent)] opacity-30" />
                </div>
                <div className="text-[19px] font-extrabold tracking-[-0.02em]">
                  {hasExistingIndex ? 'Ask something specific.' : 'Ingest a document first.'}
                </div>
                <div className="max-w-[52ch] text-[13.5px] leading-[1.55] opacity-65">
                  {hasExistingIndex
                    ? 'Questions are answered only from the indexed document. Anything it cannot support, it will say so rather than invent.'
                    : 'Nothing is indexed yet, so there is nothing to retrieve from. Drop a PDF into the ingest panel and the transcript starts here.'}
                </div>
              </div>
            </Panel>
          ) : (
            transcript
              .slice()
              .reverse()
              .map((turn) => {
                const sourceMax = maxScore(turn.sources)
                const focusedIndices =
                  focus?.turnId === turn.id ? matchSourceIndices(turn.sources, focus.source, focus.page) : []
                const typedAnswer =
                  turn.id === latestId && turn.answer && typed < turn.answer.length
                    ? turn.answer.slice(0, typed)
                    : turn.answer ?? ''
                const parts = turn.pending || turn.error ? [] : parseAnswer(typedAnswer)

                return (
                  <Panel key={turn.id}>
                    <div className="grid gap-4 p-5">
                      <div className="flex flex-wrap items-baseline gap-3">
                        <div className="text-[12px] font-extrabold uppercase tracking-[0.1em] opacity-55">Question</div>
                        <div className="text-[16px] font-extrabold tracking-[-0.01em]">{turn.question}</div>
                      </div>

                      {turn.pending && (
                        <div className="flex items-center gap-3 text-[13px] opacity-70">
                          <Spinner size={16} />
                          <span>{QUERY_STAGES[thinkingIdx]}</span>
                        </div>
                      )}

                      {turn.error && (
                        <div role="alert" className="grid gap-2 p-[14px] text-[13px] leading-[1.55]" style={{ border: 'var(--brd-w) solid var(--accent)' }}>
                          <div className="font-extrabold">{turn.errorTitle ?? 'Request failed'}</div>
                          <div className="opacity-75">{turn.error}</div>
                          <Mono className="text-[11.5px] opacity-50">X-Request-ID {turn.requestId ?? 'none returned'}</Mono>
                        </div>
                      )}

                      {turn.answer && !turn.error && (
                        <div className="grid gap-4">
                          {renderAnswer(turn)}

                          <div>
                            <div className="mb-3 text-[11px] font-extrabold uppercase tracking-[0.12em] opacity-55">
                              Sources {turn.sources.length ? `(${turn.sources.length})` : ''}
                            </div>

                            {turn.sources.length === 0 ? (
                              <div className="text-[13px] opacity-60">The backend returned no sources for this answer.</div>
                            ) : (
                              <div className="grid gap-3">
                                {turn.sources.map((source, index) => {
                                  const focused = focusedIndices.includes(index)
                                  return (
                                    <button
                                      key={`${turn.id}-${index}`}
                                      type="button"
                                      onClick={() =>
                                        setFocus((current) =>
                                          current?.turnId === turn.id && current.source === source.source && current.page === String(source.page ?? '—')
                                            ? null
                                            : { turnId: turn.id, source: source.source, page: String(source.page ?? '—') },
                                        )
                                      }
                                      className="grid gap-3 text-left transition-transform"
                                      style={{
                                        padding: '16px',
                                        background: focused ? 'color-mix(in srgb, var(--accent) 10%, var(--panel-solid))' : 'var(--panel-solid)',
                                        border: `var(--brd-w) solid ${focused ? 'var(--accent)' : 'var(--brd)'}`,
                                        transform: focused ? 'translateY(-1px)' : 'none',
                                      }}
                                    >
                                      <div className="flex flex-wrap items-baseline justify-between gap-3">
                                        <div className="text-[14px] font-extrabold">{source.source}</div>
                                        <div className="flex flex-wrap gap-3 text-[11px] font-extrabold uppercase tracking-[0.08em] opacity-55">
                                          <span>{source.page ?? 'page —'}</span>
                                          <span>chunk {source.chunk_id ?? '—'}</span>
                                          <span>score {formatScore(source.score)}</span>
                                        </div>
                                      </div>

                                      <div className="h-[6px] overflow-hidden" style={{ background: 'var(--brd)' }}>
                                        <span
                                          className="block h-full"
                                          style={{
                                            width: scoreBarPercent(source.score, sourceMax),
                                            background: 'var(--accent)',
                                            transition: 'width .9s cubic-bezier(.2,.8,.2,1)',
                                          }}
                                        />
                                      </div>

                                      <div className="text-[13px] leading-[1.6] opacity-78">
                                        {source.content || 'No excerpt returned.'}
                                      </div>
                                    </button>
                                  )
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {!turn.pending && !turn.error && !turn.answer && (
                        <div className="text-[13px] opacity-60">No answer returned.</div>
                      )}

                      {turn.requestId && (
                        <div className="text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-45">
                          request {turn.requestId.slice(0, 8)}
                        </div>
                      )}
                    </div>
                  </Panel>
                )
              })
          )}

          <Panel>
            <PanelHeader
              title="Pipeline"
              right={<span className="text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-50">illustrative</span>}
            />
            <div className="p-6">
              <div className="max-w-[940px]">
                <PipelineVisualiser stage={pipeStage} />
              </div>
            </div>
          </Panel>
        </div>

        <div className="lg:col-span-2">
          <CollectionsPanel refreshToken={refreshToken} />
        </div>
      </div>
    </main>
  )
}