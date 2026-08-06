'use client'

// Sticky chrome shown on every route: brand, nav, connectivity badge, theme and
// motion controls, repo link, instructions download. Also hosts the two global
// banners (backend-connected on landing, reconnecting on workbench).

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Download, Github } from 'lucide-react'

import { API_BASE_URL, REPO_URL, SITE_URL } from '@/config'
import { useHealth } from '@/hooks/useHealth'
import { useToast } from '@/hooks/useToast'
import { useUiPrefs, type Motion } from '@/hooks/useUiPrefs'
import { downloadReadme } from '@/lib/readme'
import { Button, Spinner } from '@/components/ui'
import { StatusBadge } from '@/components/StatusBadge'

const NAV = [
  { href: '/', label: 'Overview' },
  { href: '/setup', label: 'Setup' },
  { href: '/workbench', label: 'Workbench' },
]

export function Header() {
  const pathname = usePathname() ?? '/'
  const { theme, setTheme, motion, setMotion } = useUiPrefs()
  const { isConnected, reconnecting } = useHealth()
  const { flash } = useToast()

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href)

  const onDownload = () => {
    downloadReadme()
    flash('README.txt downloaded')
  }

  const dark = theme === 'nightglass'
  const themeBtn = (active: boolean): React.CSSProperties => ({
    background: active ? 'var(--accent)' : 'transparent',
    color: active ? 'var(--on-accent)' : 'var(--ink)',
    opacity: active ? 1 : 0.55,
  })

  return (
    <>
      <header
        className="sticky top-0 z-40 flex flex-wrap items-center gap-5 px-[26px] py-3"
        style={{
          background: 'var(--head-bg)',
          backdropFilter: 'var(--blur)',
          borderBottom: 'var(--brd-w) solid var(--brd)',
          boxShadow: 'var(--head-shadow)',
        }}
      >
        <Link href="/" className="flex items-center gap-[10px]" style={{ color: 'var(--ink)' }}>
          <span
            className="block h-[22px] w-[22px]"
            style={{ background: 'var(--accent)', borderRadius: 'var(--r-sm)' }}
          />
          <span className="text-[15px] font-extrabold tracking-[-0.02em]">
            GROUNDED<span style={{ color: 'var(--accent)' }}>·</span>RAG
          </span>
        </Link>

        <nav className="flex gap-[2px]" aria-label="Sections">
          {NAV.map((item) => {
            const active = isActive(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className="px-3 py-[7px] text-[12.5px] font-extrabold tracking-[0.02em] transition-opacity hover:opacity-100"
                style={{
                  borderRadius: 'var(--r-sm)',
                  background: active ? 'var(--accent)' : 'transparent',
                  color: active ? 'var(--on-accent)' : 'var(--ink)',
                  opacity: active ? 1 : 0.6,
                }}
              >
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="flex-1" />

        <StatusBadge />

        <div
          className="flex overflow-hidden"
          style={{ border: 'var(--brd-w) solid var(--brd)', borderRadius: 'var(--r-sm)' }}
          role="group"
          aria-label="Theme"
        >
          <button
            onClick={() => setTheme('modernist')}
            aria-pressed={!dark}
            className="cursor-pointer border-0 px-[10px] py-[6px] text-[11.5px] font-extrabold"
            style={themeBtn(!dark)}
          >
            Modernist
          </button>
          <button
            onClick={() => setTheme('nightglass')}
            aria-pressed={dark}
            className="cursor-pointer border-0 px-[10px] py-[6px] text-[11.5px] font-extrabold"
            style={themeBtn(dark)}
          >
            Nightglass
          </button>
        </div>

        <div className="flex items-center gap-[7px]">
          <label
            htmlFor="motion"
            className="text-[11px] font-extrabold uppercase tracking-[0.1em] opacity-50"
          >
            Motion
          </label>
          <select
            id="motion"
            value={motion}
            onChange={(e) => setMotion(e.target.value as Motion)}
            className="px-[7px] py-[5px] text-[12px] font-extrabold"
            style={{
              color: 'var(--ink)',
              background: 'var(--chip-bg)',
              border: 'var(--brd-w) solid var(--brd)',
              borderRadius: 'var(--r-sm)',
            }}
          >
            <option value="full">Full</option>
            <option value="reduced">Reduced</option>
            <option value="off">Off</option>
          </select>
        </div>

        <Button variant="ghost" onClick={onDownload}>
          <Download size={13} aria-hidden /> Instructions
        </Button>

        <a
          href={SITE_URL}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-[6px] text-[12px] font-extrabold"
        >
          Live site
        </a>

        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-[6px] text-[12px] font-extrabold"
        >
          <Github size={14} aria-hidden /> GitHub
        </a>
      </header>

      {/* Landing: surface the connection without hijacking someone mid-read. */}
      {isConnected && pathname === '/' && (
        <div
          className="anim-rise relative z-30 flex flex-wrap items-center gap-4 px-[26px] py-[11px]"
          style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}
        >
          <span className="text-[13px] font-extrabold tracking-[0.02em]">
            Backend connected on {API_BASE_URL} — the workbench is live.
          </span>
          <Link
            href="/workbench"
            className="ambient text-[13px] font-extrabold"
            style={{
              background: 'var(--on-accent)',
              color: 'var(--accent)',
              padding: '7px 14px',
              borderRadius: 'var(--r-sm)',
              animation: 'breathe 3.4s ease-in-out infinite',
            }}
          >
            Launch workbench →
          </Link>
        </div>
      )}

      {/* Lost the backend mid-session: never destructive, never wipes results. */}
      {reconnecting && pathname.startsWith('/workbench') && (
        <div
          role="alert"
          className="relative z-30 flex items-center gap-3 px-[26px] py-[10px] text-[13px]"
          style={{
            background: 'var(--warn-bg)',
            borderBottom: 'var(--brd-w) solid var(--brd)',
          }}
        >
          <Spinner size={13} />
          <span>
            <span className="font-extrabold">Reconnecting.</span> The backend stopped responding —
            your transcript is intact and submits are paused until it returns.
          </span>
        </div>
      )}
    </>
  )
}
