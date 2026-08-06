'use client'

// One shared "what is the app doing right now" signal. The canvas background,
// the status badge and the pipeline visualiser all subscribe to it so every
// surface reacts coherently instead of animating independently.

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

import type { Activity } from '@/types/api'

interface ActivityContextValue {
  activity: Activity
  setBusy: (busy: 'querying' | 'ingesting' | null) => void
  /** Fires the one-shot celebratory "connected" burst. */
  pulseConnected: () => void
  setOffline: (offline: boolean) => void
}

const ActivityContext = createContext<ActivityContextValue | null>(null)

const CONNECTED_PULSE_MS = 1600

export function ActivityProvider({ children }: { children: ReactNode }) {
  const [busy, setBusyState] = useState<'querying' | 'ingesting' | null>(null)
  const [offline, setOfflineState] = useState(false)
  const [pulsing, setPulsing] = useState(false)
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => { if (pulseTimer.current) clearTimeout(pulseTimer.current) }, [])

  const pulseConnected = useCallback(() => {
    setPulsing(true)
    if (pulseTimer.current) clearTimeout(pulseTimer.current)
    pulseTimer.current = setTimeout(() => setPulsing(false), CONNECTED_PULSE_MS)
  }, [])

  // Busy states win over ambient ones: an in-flight request is the most
  // informative thing we can show.
  const activity: Activity = busy
    ? busy
    : pulsing
      ? 'connected'
      : offline
        ? 'offline'
        : 'idle'

  const value = useMemo<ActivityContextValue>(
    () => ({
      activity,
      setBusy: setBusyState,
      pulseConnected,
      setOffline: setOfflineState,
    }),
    [activity, pulseConnected],
  )

  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>
}

export function useActivity() {
  const ctx = useContext(ActivityContext)
  if (!ctx) throw new Error('useActivity must be used inside <ActivityProvider>')
  return ctx
}
