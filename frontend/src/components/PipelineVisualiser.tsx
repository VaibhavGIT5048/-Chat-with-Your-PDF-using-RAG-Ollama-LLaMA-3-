'use client'

// Animated node-graph of the real backend retrieval and ingest pipeline. Auth,
// query rewriting and guardrails precede scoped hybrid retrieval; parser
// routing is shown as the parallel ingest path.
//
// HONESTY: the frontend makes ONE /query call and receives ONE response, so it
// has no per-stage telemetry. This is an illustrative choreography timed to the
// in-flight request — never presented as measured latency or counts.

import { useEffect, useRef, useState } from 'react'

import { MAX_PIPE_STAGE, PIPE_EDGES, PIPE_NODES } from '@/lib/pipeline'
import { useUiPrefs } from '@/hooks/useUiPrefs'

interface Props {
  /** Highest stage currently lit. -1 = all dim, MAX_PIPE_STAGE = complete. */
  stage: number
  className?: string
}

export function PipelineVisualiser({ stage, className = '' }: Props) {
  const { motionOff, motionFull } = useUiPrefs()

  return (
    <div className={className}>
      <svg
        viewBox="0 0 940 740"
        style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }}
        role="img"
        aria-label="Illustrative view of the pipeline: authentication and guardrails, query rewriting, parser routing, bge-m3 dense and BM25 sparse retrieval, RRF fusion, quality weighting, Flashrank reranking, neighbour expansion and gpt-5-mini answer generation."
      >
        {PIPE_EDGES.map((edge, i) => {
          const on = stage >= edge.stage
          return (
            <path
              key={i}
              d={edge.d}
              style={{
                fill: 'none',
                stroke: on ? 'var(--accent)' : 'var(--brd)',
                strokeWidth: 2,
                opacity: on ? 1 : 0.45,
                strokeDasharray: on ? '6 8' : undefined,
                animation: on && motionFull ? 'dash 1s linear infinite' : 'none',
                transition: 'opacity .3s, stroke .3s',
              }}
            />
          )
        })}

        {PIPE_NODES.map((node) => {
          const on = stage >= node.stage
          const current = stage === node.stage
          return (
            <g
              key={node.id}
              style={{
                opacity: on ? 1 : 0.5,
                transition: 'opacity .3s',
                animation: current && !motionOff ? 'breathe 1.2s ease-in-out infinite' : 'none',
                transformBox: 'fill-box',
                transformOrigin: 'center',
              }}
            >
              <rect
                x={node.x}
                y={node.y}
                width={node.w}
                height={node.h}
                rx={2}
                style={{
                  fill: on ? 'color-mix(in srgb, var(--accent) 14%, transparent)' : 'transparent',
                  stroke: on ? 'var(--accent)' : 'var(--brd)',
                  strokeWidth: 2,
                  transition: 'fill .3s, stroke .3s',
                }}
              />
              <foreignObject x={node.x} y={node.y} width={node.w} height={node.h}>
                <div
                  className="flex h-full flex-col justify-center gap-[2px] px-4"
                  style={{ color: 'var(--ink)' }}
                >
                  <div className="text-[15px] font-extrabold leading-[1.15] tracking-[-0.01em]">
                    {node.label}
                  </div>
                  {node.sub && (
                    <div className="font-mono text-[11.5px] leading-[1.2] opacity-60">
                      {node.sub}
                    </div>
                  )}
                </div>
              </foreignObject>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/**
 * Drives the landing page's looping "how it works" walkthrough. Pauses when the
 * section is off-screen so it never animates invisibly.
 */
export function useLoopingStage(enabled: boolean, intervalMs = 700) {
  const [stage, setStage] = useState(-1)
  const ref = useRef<HTMLDivElement | null>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      { threshold: 0.15 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!enabled || !inView) return
    const id = setInterval(
      () => setStage((s) => (s >= MAX_PIPE_STAGE ? -1 : s + 1)),
      intervalMs,
    )
    return () => clearInterval(id)
  }, [enabled, inView, intervalMs])

  // With motion disabled, show the whole graph lit rather than a frozen partial.
  return { ref, stage: enabled ? stage : MAX_PIPE_STAGE }
}
