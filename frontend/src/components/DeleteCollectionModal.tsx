'use client'

// Typed confirmation before a destructive delete — mirrors the pattern used for
// the ingest-replaces-index warning: never let one click destroy data.

import { useState } from 'react'

import { Button, Mono } from '@/components/ui'

export function DeleteCollectionModal({
  name,
  onCancel,
  onConfirm,
}: {
  name: string
  onCancel: () => void
  onConfirm: () => void
}) {
  const [value, setValue] = useState('')
  const blocked = value !== name

  return (
    <div
      role="presentation"
      onClick={onCancel}
      className="fixed inset-0 z-[60] grid place-items-center p-6"
      style={{ background: 'color-mix(in srgb, #000 55%, transparent)', backdropFilter: 'blur(3px)' }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        className="anim-rise w-full max-w-[460px] p-6"
        style={{
          background: 'var(--panel-solid)',
          border: 'var(--brd-w) solid var(--brd)',
          boxShadow: 'var(--shadow)',
        }}
      >
        <h4 id="delete-title" className="m-0 mb-[10px] text-[20px] font-extrabold tracking-[-0.02em]">
          Delete {name}?
        </h4>
        <p className="m-0 mb-4 text-[13.5px] leading-[1.55] opacity-70">
          This drops the vector collection and everything indexed in it. Type the collection name
          to confirm.
        </p>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={name}
          autoFocus
          className="w-full font-mono text-[13px]"
          style={{
            padding: '10px 12px',
            color: 'var(--ink)',
            background: 'var(--chip-bg)',
            border: 'var(--brd-w) solid var(--brd)',
            borderRadius: 'var(--r-sm)',
          }}
        />
        <div className="mt-[18px] flex gap-[10px]">
          <Button variant="dangerSolid" disabled={blocked} onClick={onConfirm}>
            Delete collection
          </Button>
          <Button variant="chip" onClick={onCancel}>
            Cancel
          </Button>
        </div>
        <div className="sr-only">
          Type <Mono>{name}</Mono> exactly to enable the delete button.
        </div>
      </div>
    </div>
  )
}
