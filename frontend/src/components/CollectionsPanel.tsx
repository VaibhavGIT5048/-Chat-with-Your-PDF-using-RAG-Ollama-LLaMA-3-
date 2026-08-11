'use client'

import { useCallback, useEffect, useState } from 'react'

import { deleteCollection, listCollections } from '@/services/api'
import { useToast } from '@/hooks/useToast'
import type { CollectionInfo } from '@/types/api'
import { Button, Panel, PanelHeader } from '@/components/ui'
import { DeleteCollectionModal } from '@/components/DeleteCollectionModal'

interface Props {
  /** Bumped by the parent after a successful ingest to trigger a refresh. */
  refreshToken: number
}

export function CollectionsPanel({ refreshToken }: Props) {
  const [collections, setCollections] = useState<CollectionInfo[]>([])
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const { flash } = useToast()

  const refresh = useCallback(async () => {
    try {
      setCollections(await listCollections())
    } catch {
      setCollections([])
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh, refreshToken])

  const handleDeleted = async (name: string) => {
    try {
      await deleteCollection(name)
      flash(`Deleted ${name}`)
    } catch (err) {
      flash(`Delete failed — ${err instanceof Error ? err.message : 'unknown error'}`)
    }
    setDeleteTarget(null)
    void refresh()
  }

  return (
    <Panel>
      <PanelHeader
        title="Collections"
        right={
          <Button variant="chip" onClick={refresh}>
            Refresh
          </Button>
        }
      />
      <div className="px-5 pb-5 pt-[14px]">
        {collections.length === 0 && (
          <div className="py-[14px] text-[13px] opacity-60">
            No collections yet — ingest a document to create one.
          </div>
        )}
        {collections.map((c) => (
          <div
            key={c.name}
            className="flex flex-wrap items-center justify-between gap-[14px] py-3"
            style={{ borderBottom: 'var(--brd-w) solid var(--brd)' }}
          >
            <div>
              <div className="text-[14px] font-extrabold">{c.name}</div>
              <div className="tnum text-[12px] opacity-60">
                {c.vectors_count ?? '—'} vectors · {c.status ?? 'unknown'}
              </div>
            </div>
            <Button variant="danger" onClick={() => setDeleteTarget(c.name)}>
              Delete
            </Button>
          </div>
        ))}
      </div>

      {deleteTarget && (
        <DeleteCollectionModal
          name={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => handleDeleted(deleteTarget)}
        />
      )}
    </Panel>
  )
}
