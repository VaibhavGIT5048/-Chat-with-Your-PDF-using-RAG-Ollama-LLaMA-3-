'use client'

// Minimal toast + a polite ARIA live region, so state changes are announced to
// screen readers as well as shown visually.

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
import { AnimatePresence, motion } from 'framer-motion'

interface ToastContextValue {
  toast: string | null
  flash: (message: string) => void
  /** Text pushed to the ARIA live region (not shown visually). */
  announce: (message: string) => void
  announcement: string
}

const ToastContext = createContext<ToastContextValue | null>(null)

const TOAST_MS = 2400

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const flash = useCallback((message: string) => {
    setToast(message)
    setAnnouncement(message)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setToast(null), TOAST_MS)
  }, [])

  const announce = useCallback((message: string) => setAnnouncement(message), [])

  const value = useMemo<ToastContextValue>(
    () => ({ toast, flash, announce, announcement }),
    [toast, flash, announce, announcement],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ type: 'spring', stiffness: 420, damping: 30 }}
            className="fixed bottom-6 left-1/2 z-[70] -translate-x-1/2 px-[18px] py-3 text-[13.5px] font-extrabold"
            style={{
              background: 'var(--panel-solid)',
              border: 'var(--brd-w) solid var(--brd)',
              borderRadius: 'var(--r-sm)',
              boxShadow: 'var(--shadow)',
            }}
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
