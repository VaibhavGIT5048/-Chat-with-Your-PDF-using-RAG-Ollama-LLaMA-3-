import type { Metadata } from 'next'

import './globals.css'
import { Providers } from './providers'

const fontStack = 'ui-sans-serif, system-ui, sans-serif'

export const metadata: Metadata = {
  title: 'Grounded RAG — Ask questions of any PDF',
  description:
    'Answers grounded in your document, with every claim cited back to its page. Hybrid dense + sparse retrieval, reranking and a chunk quality gate, self-hosted in your own Docker network.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // data-theme is set to nightglass up-front so first paint matches the
    // default; UiPrefsProvider corrects it from localStorage on mount.
    <html
      lang="en"
      data-theme="nightglass"
      data-motion="full"
      style={{ ['--font-archivo' as never]: fontStack }}
    >
      <body className="font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
