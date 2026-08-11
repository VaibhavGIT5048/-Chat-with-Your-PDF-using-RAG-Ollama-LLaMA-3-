import { Suspense } from 'react'
import { WorkbenchView } from '@/components/WorkbenchView'

export default function Page() {
  return (
    <Suspense fallback={null}>
      <WorkbenchView />
    </Suspense>
  )
}
