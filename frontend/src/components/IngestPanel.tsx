'use client'

// Single-file ingest, because /ingest recreates the vector collection — a
// second document would silently discard the first. That constraint drives
// every UX decision here: no multi-file queue, and an explicit replace warning.

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle } from 'lucide-react'

import { ACCEPTED_EXTENSIONS, INGEST_DEFAULTS } from '@/config'
import { useActivity } from '@/hooks/useActivity'
import { useToast } from '@/hooks/useToast'
import { INGEST_STAGES } from '@/lib/pipeline'
import { ingest, ApiError } from '@/services/api'
import type { IngestResponse } from '@/types/api'
import { Button, Mono, Panel, PanelHeader, Spinner } from '@/components/ui'

interface Props {
  connected: boolean
  hasExistingIndex: boolean
  onIngested: (stats: IngestResponse) => void
}

interface Slider {
  id: string
  label: string
  value: number
  def: number
  min: number
  max: number
  step: number
  tip: string
  onChange: React.Dispatch<React.SetStateAction<number>>
}

const STAGE_INTERVAL_MS = 6000

function isAcceptedFile(name: string) {
  return ACCEPTED_EXTENSIONS.some((ext) => name.toLowerCase().endsWith(ext))
}

export function IngestPanel({ connected, hasExistingIndex, onIngested }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [chunkSize, setChunkSize] = useState<number>(INGEST_DEFAULTS.chunkSize)
  const [chunkOverlap, setChunkOverlap] = useState<number>(INGEST_DEFAULTS.chunkOverlap)
  const [quality, setQuality] = useState<number>(INGEST_DEFAULTS.qualityThreshold)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [stageIdx, setStageIdx] = useState(0)
  const [stats, setStats] = useState<IngestResponse | null>(null)
  const [error, setError] = useState<{ status: string; detail: string; requestId: string } | null>(
    null,
  )

  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const elapsedTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const stageTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const { setBusy: setGlobalBusy } = useActivity()
  const { flash } = useToast()

  useEffect(
    () => () => {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current)
      if (stageTimer.current) clearInterval(stageTimer.current)
    },
    [],
  )

  const takeFile = (f: File | null | undefined) => {
    if (!f) return
    if (!isAcceptedFile(f.name)) {
      flash(`Only ${ACCEPTED_EXTENSIONS.join(', ')}`)
      return
    }
    if (f.size === 0) {
      flash('That file is empty')
      return
    }
    setFile(f)
    setError(null)
  }

  const submit = async () => {
    if (!file || busy) return
    setBusy(true)
    setGlobalBusy('ingesting')
    setElapsed(0)
    setStageIdx(0)
    setError(null)
    setStats(null)

    elapsedTimer.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    stageTimer.current = setInterval(
      () => setStageIdx((i) => Math.min(i + 1, INGEST_STAGES.length - 1)),
      STAGE_INTERVAL_MS,
    )

    try {
      const result = await ingest({
        file,
        chunkSize,
        chunkOverlap,
        qualityThreshold: quality,
      })
      setStats(result)
      onIngested(result)
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null
      setError({
        status: apiErr?.status ? `HTTP ${apiErr.status}` : 'network error',
        detail: apiErr?.detail ?? (err instanceof Error ? err.message : 'Unknown error'),
        requestId: apiErr?.requestId ?? 'none returned',
      })
    } finally {
      if (elapsedTimer.current) clearInterval(elapsedTimer.current)
      if (stageTimer.current) clearInterval(stageTimer.current)
      setBusy(false)
      setGlobalBusy(null)
    }
  }

  const sliders: Slider[] = [
    {
      id: 'cs',
      label: 'chunk_size',
      value: chunkSize,
      def: INGEST_DEFAULTS.chunkSize,
      min: 400,
      max: 2000,
      step: 100,
      tip: 'characters per chunk',
      onChange: setChunkSize,
    },
    {
      id: 'co',
      label: 'chunk_overlap',
      value: chunkOverlap,
      def: INGEST_DEFAULTS.chunkOverlap,
      min: 50,
      max: 400,
      step: 25,
      tip: 'characters shared between neighbours',
      onChange: setChunkOverlap,
    },
    {
      id: 'qt',
      label: 'quality_threshold',
      value: quality,
      def: INGEST_DEFAULTS.qualityThreshold,
      min: 0,
      max: 7,
      step: 0.5,
      tip: 'minimum chunk score out of 7',
      onChange: setQuality,
    },
  ]

  const disabled = !file || busy || !connected
  const elapsedLabel = `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
  const passedPct = stats && stats.chunks ? Math.round((stats.passed_chunks / stats.chunks) * 100) : 0
  const showWarning = hasExistingIndex && !!file

  return (
    <Panel>
      <PanelHeader
        title="Ingest"
        right={<span className="text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-50">one file at a time</span>}
      />
      <div className="p-5">
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={(e) => takeFile(e.target.files?.[0])}
        />
        <div
          role="button"
          tabIndex={0}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            if (!dragging) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            takeFile(e.dataTransfer.files?.[0])
          }}
          className="cursor-pointer px-5 py-[34px] text-left transition-colors"
          style={{
            border: `var(--brd-w) dashed ${dragging ? 'var(--accent)' : 'var(--brd)'}`,
            background: dragging ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'transparent',
          }}
        >
          <div className="mb-[6px] text-[16px] font-extrabold tracking-[-0.01em]">
            {file ? file.name : dragging ? 'Drop it' : 'Drop a document, or click to choose'}
          </div>
          <div className="text-[12.5px] opacity-60">
            {file
              ? `${Math.max(1, Math.round(file.size / 1024))} KB · one file per ingest`
              : '.pdf primary · .txt and .md accepted · single file only'}
          </div>
        </div>

        {showWarning && (
          <div
            role="alert"
            className="mt-[14px] flex gap-[10px] px-[14px] py-3 text-[13px] leading-[1.5]"
            style={{ border: 'var(--brd-w) solid var(--accent)' }}
          >
            <AlertTriangle size={16} style={{ color: 'var(--accent)' }} aria-hidden />
            <span>
              Ingesting will <span className="font-extrabold">replace</span> the currently indexed
              document. The collection is recreated on every ingest.
            </span>
          </div>
        )}

        <details className="mt-4 pt-[14px]" style={{ borderTop: 'var(--brd-w) solid var(--brd)' }}>
          <summary className="cursor-pointer text-[13px] font-extrabold">
            Advanced parameters
          </summary>
          <div className="mt-4 grid gap-[18px]">
            {sliders.map((s) => (
              <div key={s.id}>
                <div className="mb-[6px] flex items-baseline justify-between">
                  <label htmlFor={s.id} title={s.tip} className="text-[12.5px] font-extrabold">
                    {s.label}
                  </label>
                  <span className="tnum text-[13px] font-extrabold" style={{ color: 'var(--accent)' }}>
                    {s.value}
                  </span>
                </div>
                <input
                  id={s.id}
                  type="range"
                  min={s.min}
                  max={s.max}
                  step={s.step}
                  value={s.value}
                  onChange={(e) => s.onChange(Number(e.target.value))}
                  className="w-full"
                  style={{ accentColor: 'var(--accent)' }}
                />
                <div className="mt-[3px] flex justify-between text-[11px] opacity-50">
                  <span>{s.min}</span>
                  <span>
                    default {s.def} · {s.tip}
                  </span>
                  <span>{s.max}</span>
                </div>
              </div>
            ))}
          </div>
        </details>

        <Button
          variant="solid"
          disabled={disabled}
          onClick={submit}
          className="mt-4 w-full justify-start"
        >
          {busy ? 'Ingesting…' : hasExistingIndex ? 'Replace indexed document' : 'Ingest document'}
        </Button>

        {busy && (
          <div
            className="mt-4 flex items-center gap-[14px] p-[14px]"
            style={{ background: 'var(--chip-bg)', border: 'var(--brd-w) solid var(--brd)' }}
          >
            <Spinner size={22} />
            <div className="min-w-0 flex-1">
              <div className="text-[13.5px] font-extrabold">{INGEST_STAGES[stageIdx]}</div>
              <div className="tnum text-[12px] opacity-60">{elapsedLabel} elapsed · timeout 600s</div>
            </div>
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="mt-4 p-[14px] text-[13px] leading-[1.55]"
            style={{ border: 'var(--brd-w) solid var(--accent)' }}
          >
            <div className="mb-1 font-extrabold">Ingest failed — {error.status}</div>
            <div className="opacity-75">{error.detail}</div>
            <Mono className="mt-[6px] block text-[11.5px] opacity-50">
              X-Request-ID {error.requestId}
            </Mono>
          </div>
        )}

        {stats && (
          <div className="mt-[18px] pt-4" style={{ borderTop: 'var(--brd-w) solid var(--brd)' }}>
            <div className="mb-3 text-[11px] font-extrabold uppercase tracking-[0.12em] opacity-55">
              {stats.filename} · {stats.file_type} · request {stats.request_id.slice(0, 8)}
            </div>
            <div className="grid grid-cols-5" style={{ gap: 'var(--brd-w)', background: 'var(--brd)' }}>
              {[
                ['Pages', stats.pages],
                ['Chunks', stats.chunks],
                ['Passed', stats.passed_chunks],
                ['Dropped', stats.dropped_chunks],
                ['Indexed', stats.indexed_chunks],
              ].map(([k, v]) => (
                <div key={k as string} className="px-[10px] py-3" style={{ background: 'var(--panel-solid)' }}>
                  <div className="tnum text-[22px] font-extrabold tracking-[-0.02em]">{v}</div>
                  <div className="mt-[2px] text-[10.5px] uppercase tracking-[0.06em] opacity-60">
                    {k}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex h-2 overflow-hidden" style={{ background: 'var(--brd)' }}>
              <span
                style={{
                  background: 'var(--accent)',
                  width: `${passedPct}%`,
                  transition: 'width .9s cubic-bezier(.2,.8,.2,1)',
                }}
              />
            </div>
            <div className="mt-[5px] flex justify-between text-[11.5px] opacity-60">
              <span>
                {stats.passed_chunks} of {stats.chunks} passed the quality gate
              </span>
              <span>{stats.dropped_chunks} dropped</span>
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}
