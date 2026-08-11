import { Suspense } from 'react'
import type { Metadata } from 'next'

import { VerifyEmailView } from '@/components/VerifyEmailView'

export const metadata: Metadata = {
  title: 'Verify email · Grounded RAG',
  description: 'Enter the six-digit code sent to your email address.',
}

export default function VerifyEmailPage() {
  // useSearchParams needs a Suspense boundary in a statically exported app.
  return (
    <Suspense fallback={null}>
      <VerifyEmailView />
    </Suspense>
  )
}
