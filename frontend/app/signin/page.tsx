import type { Metadata } from 'next'

import { SignInView } from '@/components/SignInView'

export const metadata: Metadata = {
  title: 'Sign in · Grounded RAG',
  description: 'Sign in with GitHub, Google, or email to access your documents.',
}

export default function SignInPage() {
  return <SignInView />
}
