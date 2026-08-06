'use client'

// Wires the health poller into the shared activity signal, and fires the
// one-shot "connected" burst on the down → up transition. Renders nothing.

import { useEffect, useRef } from 'react'

import { useActivity } from '@/hooks/useActivity'
import { useHealth } from '@/hooks/useHealth'
import { useToast } from '@/hooks/useToast'

export function ActivityHealthBridge() {
  const { state, isConnected } = useHealth()
  const { pulseConnected, setOffline } = useActivity()
  const { announce } = useToast()
  const wasConnected = useRef(false)

  useEffect(() => {
    setOffline(state === 'offline')
  }, [state, setOffline])

  useEffect(() => {
    if (isConnected && !wasConnected.current) {
      wasConnected.current = true
      pulseConnected()
      announce('Backend connected.')
    } else if (!isConnected && wasConnected.current && state === 'offline') {
      wasConnected.current = false
      announce('Backend connection lost. Reconnecting.')
    }
  }, [isConnected, state, pulseConnected, announce])

  return null
}
