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
  const [hovered, setHovered] = useState<string | null>(null)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showAfterDelay = (id: string) => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(() => setHovered(id), 360)
  }

  const hideTooltip = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    hoverTimer.current = null
    setHovered(null)
  }

  useEffect(() => () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
  }, [])

  const hoveredNode = PIPE_NODES.find((node) => node.id === hovered)

  function tooltipPosition(node: PipeNode) {
    const width = 276
    const x = node.x >= 600 ? Math.max(14, node.x - width - 16) : node.x + node.w + 16
    const y = node.y > 590 ? node.y - 108 : node.y + node.h + 12
    return { x: Math.min(x, 940 - width - 14), y }
  }

  return (
    <div className={`relative ${className}`}>
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
              tabIndex={0}
              onMouseEnter={() => showAfterDelay(node.id)}
              onMouseLeave={hideTooltip}
              onFocus={() => showAfterDelay(node.id)}
              onBlur={hideTooltip}
              style={{
                opacity: on ? 1 : 0.5,
                transition: 'opacity .3s',
                cursor: node.detail ? 'help' : 'default',
                animation: current && !motionOff ? 'breathe 1.2s ease-in-out infinite' : 'none',
                transformBox: 'fill-box',
                transformOrigin: 'center',
              }}
            >
              <title>{node.detail ?? node.label}</title>
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
                </div>
              </foreignObject>
            </g>
          )
        })}

      </svg>

      {hoveredNode?.detail && (() => {
        const position = tooltipPosition(hoveredNode)
        return (
          <div
            role="tooltip"
            className="anim-rise pointer-events-none absolute z-20 p-3"
            style={{
              left: `${(position.x / 940) * 100}%`,
              top: `${(position.y / 740) * 100}%`,
              width: 'min(276px, calc(100% - 24px))',
              color: 'var(--ink)',
              background: 'var(--panel-solid)',
              border: 'var(--brd-w) solid var(--accent)',
              borderRadius: 'var(--r-sm)',
              boxShadow: 'var(--shadow)',
              fontSize: 12,
              lineHeight: 1.45,
            }}
          >
            <div style={{ color: 'var(--accent)', fontSize: 10, fontWeight: 800, letterSpacing: '.12em', textTransform: 'uppercase', marginBottom: 5 }}>
              {hoveredNode.label}
            </div>
            {hoveredNode.detail}
          </div>
        )
      })()}
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
