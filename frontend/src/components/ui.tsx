'use client'

// Shared primitives. Styling leans on the CSS custom properties so both themes
// come for free.

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

type Variant = 'cta' | 'secondary' | 'ghost' | 'chip' | 'solid' | 'danger' | 'dangerSolid'

const BASE =
  'inline-flex items-center gap-2 font-extrabold tracking-[0.01em] cursor-pointer transition-[background,color,transform,opacity] duration-200 disabled:opacity-45 disabled:cursor-not-allowed'

const VARIANTS: Record<Variant, string> = {
  cta: 'text-[15px] px-[22px] py-[13px] border-0',
  secondary: 'text-[15px] px-[22px] py-[13px]',
  ghost: 'text-[12px] px-[10px] py-[6px]',
  chip: 'text-[11.5px] px-[9px] py-[5px]',
  solid: 'text-[13px] px-4 py-[10px] border-0',
  danger: 'text-[11.5px] px-[9px] py-[5px] bg-transparent',
  dangerSolid: 'text-[13px] px-4 py-[10px] border-0',
}

function variantStyle(variant: Variant): React.CSSProperties {
  const radius = { borderRadius: 'var(--r-sm)' }
  switch (variant) {
    case 'cta':
    case 'solid':
      return { ...radius, background: 'var(--accent)', color: 'var(--on-accent)' }
    case 'secondary':
      return {
        ...radius,
        background: 'transparent',
        color: 'var(--ink)',
        border: 'var(--brd-w) solid var(--brd)',
      }
    case 'ghost':
      return {
        ...radius,
        background: 'transparent',
        color: 'var(--accent-hi)',
        border: 'var(--brd-w) solid var(--brd)',
      }
    case 'chip':
      return {
        ...radius,
        background: 'var(--chip-bg)',
        color: 'var(--ink)',
        border: 'var(--brd-w) solid var(--brd)',
      }
    case 'danger':
      return { ...radius, color: 'var(--accent)', border: 'var(--brd-w) solid var(--accent)' }
    case 'dangerSolid':
      return { ...radius, background: 'var(--accent)', color: 'var(--on-accent)' }
  }
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  breathe?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'solid', breathe = false, className = '', style, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={`${BASE} ${VARIANTS[variant]} ${breathe ? 'ambient' : ''} ${className}`}
      style={{
        ...variantStyle(variant),
        ...(breathe && !rest.disabled ? { animation: 'breathe 4s ease-in-out infinite' } : null),
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  )
})

/** Glass surface used for every major panel. */
export function Panel({
  children,
  className = '',
  style,
}: {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}) {
  return (
    <div
      className={className}
      style={{
        background: 'var(--panel)',
        backdropFilter: 'var(--blur)',
        border: 'var(--brd-w) solid var(--brd)',
        borderRadius: 'var(--r-sm)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function PanelHeader({ title, right }: { title: string; right?: ReactNode }) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-4 px-5 py-4"
      style={{ borderBottom: 'var(--brd-w) solid var(--brd)' }}
    >
      <h4 className="m-0 text-[15px] tracking-[0.02em]">{title}</h4>
      {right}
    </div>
  )
}

export function Rule({ className = '' }: { className?: string }) {
  return (
    <div
      className={className}
      style={{ height: 'var(--brd-w)', background: 'var(--brd)' }}
      aria-hidden
    />
  )
}

export function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`text-[11px] font-extrabold uppercase tracking-[0.14em] ${className}`}
      style={{ color: 'var(--accent)' }}
    >
      {children}
    </div>
  )
}

export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <span
      className="ambient block shrink-0 rounded-full"
      style={{
        width: size,
        height: size,
        border: '2px solid var(--accent)',
        borderTopColor: 'transparent',
        animation: 'spin 0.9s linear infinite',
      }}
      aria-hidden
    />
  )
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <code className={`font-mono ${className}`}>{children}</code>
}
