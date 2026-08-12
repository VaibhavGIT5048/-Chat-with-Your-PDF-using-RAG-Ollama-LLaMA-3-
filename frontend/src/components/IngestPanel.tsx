'use client'

// Multi-file ingest. Each file gets its own document id; the shared Qdrant
// collection is upserted, so adding a file no longer replaces earlier work.

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
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [chunkSize, setChunkSize] = useState<number>(INGEST_DEFAULTS.chunkSize)
  const [chunkOverlap, setChunkOverlap] = useState<number>(INGEST_DEFAULTS.chunkOverlap)
  const [quality, setQuality] = useState<number>(INGEST_DEFAULTS.qualityThreshold)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [stageIdx, setStageIdx] = useState(0)
  const [stats, setStats] = useState<IngestResponse[]>([])
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

  const takeFiles = (picked: FileList | File[] | null | undefined) => {
    if (!picked) return
    const accepted = Array.from(picked).filter((f) => {
      if (!isAcceptedFile(f.name) || f.size === 0) return false
      return true
    })
    if (accepted.length !== Array.from(picked).length) flash(`Some files were skipped. Accepted: ${ACCEPTED_EXTENSIONS.join(', ')}`)
    if (accepted.length === 0) return
    setFiles(accepted)
    setError(null)
  }

  const submit = async () => {
    if (!files.length || busy) return
    setBusy(true)
    setGlobalBusy('ingesting')
    setElapsed(0)
    setStageIdx(0)
    setError(null)
    setStats([])

    elapsedTimer.current = setInterval(() => setElapsed((s) => s + 1), 1000)
    stageTimer.current = setInterval(
      () => setStageIdx((i) => Math.min(i + 1, INGEST_STAGES.length - 1)),
      STAGE_INTERVAL_MS,
    )

    try {
      for (const file of files) {
        const result = await ingest({ file, chunkSize, chunkOverlap, qualityThreshold: quality })
        setStats((current) => current.concat(result))
        onIngested(result)
      }
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

  const disabled = !files.length || busy || !connected
  const elapsedLabel = `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`
  const showWarning = hasExistingIndex && files.length > 0

  // Once a document already exists, the full two-line pitch ("Drop
  // documents, or click to choose" + accepted-formats copy) is only ever
  // read once — after that it's dead space every time this panel is in view.
  const dropTitle = files.length
    ? `${files.length} document${files.length === 1 ? '' : 's'} selected`
    : dragging
      ? 'Drop them'
      : hasExistingIndex
        ? '+ Add another document'
        : 'Drop documents, or click to choose'
  const dropSubtitle = files.length
    ? files.map((f) => f.name).join(' · ')
    : hasExistingIndex
      ? 'Drop a file here, or click to choose'
      : '.pdf, .txt, .md, Office files and images accepted'

  return (
    <Panel>
      <PanelHeader
        title="Ingest"
        right={<span className="text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-50">{files.length || 'no'} files selected</span>}
      />
      <div className="p-5">
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          className="hidden"
          multiple
          onChange={(e) => takeFiles(e.target.files)}
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
            takeFiles(e.dataTransfer.files)
          }}
          className="cursor-pointer px-5 py-4 text-left transition-colors"
          style={{
            border: `var(--brd-w) dashed ${dragging ? 'var(--accent)' : 'var(--brd)'}`,
            background: dragging ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'transparent',
          }}
        >
          <div className="mb-[3px] text-[15px] font-extrabold tracking-[-0.01em]">{dropTitle}</div>
          <div className="text-[12px] opacity-60">{dropSubtitle}</div>
        </div>

        {showWarning && (
          <div
            role="alert"
            className="mt-[14px] flex gap-[10px] px-[14px] py-3 text-[13px] leading-[1.5]"
            style={{ border: 'var(--brd-w) solid var(--accent)' }}
          >
            <AlertTriangle size={16} style={{ color: 'var(--accent)' }} aria-hidden />
            <span>
              New files are added to your account. Existing documents remain available from Home.
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
          {busy ? 'Ingesting…' : `Ingest ${files.length || ''} document${files.length === 1 ? '' : 's'}`}
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

        {stats.length > 0 && (
          <div className="mt-[18px] pt-4" style={{ borderTop: 'var(--brd-w) solid var(--brd)' }}>
            <div className="mb-3 text-[11px] font-extrabold uppercase tracking-[0.12em] opacity-55">
              {stats.length} file{stats.length === 1 ? '' : 's'} ingested
            </div>
            <div className="grid grid-cols-5" style={{ gap: 'var(--brd-w)', background: 'var(--brd)' }}>
              {[
                ['Pages', stats.reduce((n, s) => n + s.pages, 0)],
                ['Chunks', stats.reduce((n, s) => n + s.chunks, 0)],
                ['Passed', stats.reduce((n, s) => n + s.passed_chunks, 0)],
                ['Penalised', stats.reduce((n, s) => n + s.penalised_chunks, 0)],
                ['Indexed', stats.reduce((n, s) => n + s.indexed_chunks, 0)],
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
                  width: `${Math.round((stats.reduce((n, s) => n + s.passed_chunks, 0) / Math.max(1, stats.reduce((n, s) => n + s.chunks, 0))) * 100)}%`,
                  transition: 'width .9s cubic-bezier(.2,.8,.2,1)',
                }}
              />
            </div>
            <div className="mt-[5px] flex justify-between text-[11.5px] opacity-60">
              <span>
                {stats.reduce((n, s) => n + s.passed_chunks, 0)} of {stats.reduce((n, s) => n + s.chunks, 0)} passed the quality gate (all are indexed)
              </span>
                <span>{stats.reduce((n, s) => n + s.penalised_chunks, 0)} rank-penalised</span>
            </div>
          </div>
        )}
      </div>
    </Panel>
  )
}
