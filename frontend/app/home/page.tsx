import type { Metadata } from 'next'

import { HomeView } from '@/components/HomeView'

export const metadata: Metadata = {
  title: 'Your documents · Grounded RAG',
  description: 'Every document you have ingested, ready to resume.',
}

export default function HomePage() {
  return <HomeView />
}
