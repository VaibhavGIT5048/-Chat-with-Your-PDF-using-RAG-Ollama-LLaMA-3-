import { Suspense } from 'react'
import type { Metadata } from 'next'

import { AuthCallbackView } from '@/components/AuthCallbackView'

export const metadata: Metadata = {
  title: 'Signing in · Grounded RAG',
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <AuthCallbackView />
    </Suspense>
  )
}
