'use client'

// The visitor's persistent signal for the whole gated flow. Colour is always
// paired with text, and the pulse rhythm differs per state so the status is
// legible without relying on hue.

import { useState } from 'react'

import { API_BASE_URL } from '@/config'
import { useHealth } from '@/hooks/useHealth'
import { useUiPrefs } from '@/hooks/useUiPrefs'
import type { HealthState } from '@/types/api'

const LABEL: Record<HealthState, string> = {
  ok: 'Connected',
  degraded: 'Degraded',
  offline: 'Offline',
  checking: 'Checking',
}

function colorFor(state: HealthState) {
  if (state === 'ok') return 'var(--ok)'
  if (state === 'degraded') return 'var(--warn)'
  if (state === 'offline') return 'var(--accent)'
  return 'var(--brd)'
}

function pulseFor(state: HealthState) {
  switch (state) {
    case 'ok':
      return 'dotpulse 2.6s ease-in-out infinite'
    case 'degraded':
      return 'dotpulse 1.1s ease-in-out infinite'
    case 'offline':
      return 'dotpulse 3.6s ease-in-out infinite'
    default:
      return 'dotpulse 0.7s ease-in-out infinite'
  }
}

export function StatusBadge() {
  const { state, health, attempts } = useHealth()
  const { motionOff } = useUiPrefs()
  const [open, setOpen] = useState(false)

  return (
    <div
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <div
        tabIndex={0}
        role="status"
        aria-live="polite"
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="flex cursor-default items-center gap-2 px-[11px] py-[6px]"
        style={{
          border: 'var(--brd-w) solid var(--brd)',
          borderRadius: 'var(--r-sm)',
          background: 'var(--chip-bg)',
        }}
      >
        <span className="relative block h-2 w-2">
          <span
            className="ambient absolute inset-0 rounded-full"
            style={{
              background: colorFor(state),
              animation: motionOff ? 'none' : pulseFor(state),
            }}
          />
        </span>
        <span className="text-[11px] font-extrabold uppercase tracking-[0.1em]">
          {LABEL[state]}
        </span>
      </div>

      {open && (
        <div
          className="anim-rise absolute right-0 top-[42px] z-50 w-[min(360px,calc(100vw-24px))] max-w-[calc(100vw-24px)] overflow-hidden p-[14px]"
          style={{
            background: 'var(--panel-solid)',
            border: 'var(--brd-w) solid var(--brd)',
            borderRadius: 'var(--r-sm)',
            boxShadow: 'var(--shadow)',
          }}
        >
          <div className="mb-2 text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-55">
            Backend subsystems
          </div>
          <div className="grid gap-[8px] text-[13px]">
            <div className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-4">
              <span>Qdrant</span>
              <span className="tnum min-w-0 break-words text-right font-extrabold">{health?.qdrant ?? 'unknown'}</span>
            </div>
            <div className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-4">
              <span>OpenAI</span>
              <span className="tnum min-w-0 break-words text-right font-extrabold">{health?.openai ?? 'unknown'}</span>
            </div>
            <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-4">
              <span>Collection</span>
              <span className="min-w-0 break-all text-right font-extrabold">{health?.collection_name ?? '—'}</span>
            </div>
          </div>
          <div className="my-3" style={{ height: 'var(--brd-w)', background: 'var(--brd)' }} />
          <div className="min-w-0 text-[12px] leading-[1.5] opacity-60">
            Polling <span className="break-all font-extrabold">{API_BASE_URL}/health</span> · attempt{' '}
            {attempts}
          </div>
        </div>
      )}
    </div>
  )
}
