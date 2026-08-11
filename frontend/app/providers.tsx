'use client'

// All client context lives here so app/layout.tsx can stay a Server Component.

import type { ReactNode } from 'react'

import { ActivityProvider } from '@/hooks/useActivity'
import { AuthProvider } from '@/hooks/useAuth'
import { HealthProvider } from '@/hooks/useHealth'
import { ToastProvider } from '@/hooks/useToast'
import { UiPrefsProvider } from '@/hooks/useUiPrefs'
import { ActivityHealthBridge } from '@/components/ActivityHealthBridge'
import { Background } from '@/components/Background'
import { Header } from '@/components/Header'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <UiPrefsProvider>
      <AuthProvider>
        <ToastProvider>
          <HealthProvider>
            <ActivityProvider>
              <ActivityHealthBridge />
              <Background />
              <div className="relative isolate min-h-screen">
                <Header />
                {children}
              </div>
            </ActivityProvider>
          </HealthProvider>
        </ToastProvider>
      </AuthProvider>
    </UiPrefsProvider>
  )
}
