'use client'

// ONE health poller for the whole app, published via context. The status badge,
// the reactive background, the /setup auto-advance and the /workbench guard all
// read from here — no per-component polling.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { usePathname } from 'next/navigation'

import { POLL_MS, STORAGE_KEYS } from '@/config'
import { getHealth } from '@/services/api'
import type { HealthState, HealthStatus } from '@/types/api'

interface HealthContextValue {
  health: HealthStatus | null
  state: HealthState
  attempts: number
  lastCheckedAt: number | null
  /** True once /health has returned ok at any point this session or previously. */
  everConnected: boolean
  /** Backend was connected, then stopped responding. */
  reconnecting: boolean
  isConnected: boolean
  checkNow: () => void
}

const HealthContext = createContext<HealthContextValue | null>(null)

export function HealthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [state, setState] = useState<HealthState>('checking')
  const [attempts, setAttempts] = useState(0)
  const [lastCheckedAt, setLastCheckedAt] = useState<number | null>(null)
  const [everConnected, setEverConnected] = useState(false)

  // Poll cadence depends on the route; keep it in a ref so the loop can read the
  // current value without being torn down and recreated on every navigation.
  const isSetupRoute = pathname?.startsWith('/setup') ?? false
  const intervalRef = useRef(isSetupRoute ? POLL_MS.setup : POLL_MS.other)
  intervalRef.current = isSetupRoute ? POLL_MS.setup : POLL_MS.other

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEYS.hasConnected) === '1') setEverConnected(true)
    } catch {
      // localStorage can throw in private browsing modes; non-fatal.
    }
  }, [])

  const poll = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setAttempts((n) => n + 1)
    try {
      const body = await getHealth(controller.signal)
      if (!mountedRef.current) return
      setHealth(body)
      setState(body.status === 'ok' ? 'ok' : 'degraded')
      setLastCheckedAt(Date.now())
      if (body.status === 'ok') {
        setEverConnected(true)
        try {
          localStorage.setItem(STORAGE_KEYS.hasConnected, '1')
        } catch {
          /* ignore */
        }
      }
    } catch {
      if (!mountedRef.current) return
      setHealth(null)
      setState('offline')
      setLastCheckedAt(Date.now())
    }
  }, [])

  // Self-rescheduling loop so a cadence change takes effect on the next tick
  // without cancelling an in-flight request.
  useEffect(() => {
    mountedRef.current = true
    let stopped = false

    const tick = async () => {
      await poll()
      if (stopped) return
      timerRef.current = setTimeout(tick, intervalRef.current)
    }
    tick()

    return () => {
      stopped = true
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
      abortRef.current?.abort()
    }
  }, [poll])

  const checkNow = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    void poll().then(() => {
      timerRef.current = setTimeout(function again() {
        void poll().then(() => {
          timerRef.current = setTimeout(again, intervalRef.current)
        })
      }, intervalRef.current)
    })
  }, [poll])

  const value = useMemo<HealthContextValue>(
    () => ({
      health,
      state,
      attempts,
      lastCheckedAt,
      everConnected,
      reconnecting: state === 'offline' && everConnected,
      isConnected: state === 'ok',
      checkNow,
    }),
    [health, state, attempts, lastCheckedAt, everConnected, checkNow],
  )

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>
}

export function useHealth() {
  const ctx = useContext(HealthContext)
  if (!ctx) throw new Error('useHealth must be used inside <HealthProvider>')
  return ctx
}
