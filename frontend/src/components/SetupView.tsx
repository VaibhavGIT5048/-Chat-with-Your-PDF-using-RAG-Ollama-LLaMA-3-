'use client'

// The gateway. Two prominent links (repo + downloadable instructions), real
// copy-pasteable commands, and a live waiting indicator that auto-advances to
// the workbench the moment /health reports ok.

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Check, Copy, Download, Github } from 'lucide-react'

import { API_BASE_URL, REPO_URL } from '@/config'
import { useHealth } from '@/hooks/useHealth'
import { useToast } from '@/hooks/useToast'
import { downloadDevWorkflow, downloadEnvExample, downloadParserSetup, downloadReadme } from '@/lib/readme'
import { Button, Eyebrow, Mono, Rule, Spinner } from '@/components/ui'

const REPO_DIR = 'Semantic-Question-Answering-over-Large-Documents-using-RAG-LLaMA-3-Ollama'

const COMMANDS = [
  { n: '01', cmd: `git clone ${REPO_URL}.git` },
  { n: '02', cmd: `cd ${REPO_DIR}` },
  { n: '03', cmd: 'cp .env.example .env', note: 'then open .env and set OPENAI_API_KEY=sk-…' },
  { n: '04', cmd: 'docker compose up -d', note: 'first boot pulls images — a few minutes' },
]

const ADVANCE_DELAY_MS = 2000

function CopyableCommand({ n, cmd, note }: { n: string; cmd: string; note?: string }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { flash } = useToast()

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd)
      setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1600)
    } catch {
      // Clipboard needs a secure context and permission; tell the user rather
      // than failing silently.
      flash('Copy blocked by the browser — select the text manually')
    }
  }

  return (
    <div
      className="flex items-start gap-4 px-[18px] py-4"
      style={{ background: 'var(--panel)', backdropFilter: 'var(--blur)' }}
    >
      <span className="tnum pt-[3px] text-[12px] font-extrabold opacity-40">{n}</span>
      <div className="min-w-0 flex-1">
        <Mono className="block break-all text-[13px] leading-[1.6]">{cmd}</Mono>
        {note && <div className="mt-[6px] text-[12px] opacity-55">{note}</div>}
      </div>
      <Button variant="chip" onClick={copy} aria-label={`Copy command: ${cmd}`}>
        {copied ? <Check size={12} aria-hidden /> : <Copy size={12} aria-hidden />}
        {copied ? 'Copied' : 'Copy'}
      </Button>
    </div>
  )
}

export function SetupView() {
  const router = useRouter()
  const { isConnected, health, attempts, lastCheckedAt, checkNow } = useHealth()
  const [advancing, setAdvancing] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  // Auto-advance only from here, where the visitor is explicitly waiting — and
  // always with a visible escape hatch.
  useEffect(() => {
    if (!isConnected || cancelled) {
      setAdvancing(false)
      return
    }
    setAdvancing(true)
    clearTimer()
    timer.current = setTimeout(() => router.push('/workbench'), ADVANCE_DELAY_MS)
    return clearTimer
  }, [isConnected, cancelled, router, clearTimer])

  useEffect(() => clearTimer, [clearTimer])

  const cancel = () => {
    clearTimer()
    setAdvancing(false)
    setCancelled(true)
  }

  const lastCheckedLabel = lastCheckedAt
    ? `last checked ${new Date(lastCheckedAt).toLocaleTimeString()}`
    : 'checking…'

  return (
    <main className="relative z-10 mx-auto max-w-[1000px] px-[26px] pb-[90px] pt-16">
      <Eyebrow className="mb-[18px]">Step 1 of 1</Eyebrow>
      <h1 className="m-0 mb-[18px] max-w-[20ch] text-[clamp(36px,5vw,60px)] font-extrabold leading-none tracking-[-0.035em]">
        Run the backend on your machine.
      </h1>
      <p className="m-0 mb-10 max-w-[58ch] text-[18px] opacity-70">
        The stack runs in Docker on your own hardware. Four commands, one API key, a few minutes on
        first boot. This page watches for it and takes you through the moment it answers.
      </p>

      {/* The two links, as twin cards. */}
      <div
        className="mb-11 grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))]"
        style={{ gap: 'var(--brd-w)', background: 'var(--brd)' }}
      >
        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer"
          className="block p-[26px] transition-colors"
          style={{ background: 'var(--panel)', backdropFilter: 'var(--blur)', color: 'var(--ink)' }}
        >
          <div className="mb-3 text-[11px] font-extrabold uppercase tracking-[0.12em] opacity-55">
            Link 1
          </div>
          <div className="mb-2 flex items-center gap-2 text-[24px] font-extrabold tracking-[-0.025em]">
            <Github size={20} aria-hidden /> GitHub repository →
          </div>
          <div className="text-[13px] leading-[1.5] opacity-60">
            Source for the API, Qdrant compose file and evaluation harness.
          </div>
        </a>

        <button
          onClick={downloadReadme}
          className="block w-full cursor-pointer border-0 p-[26px] text-left transition-colors"
          style={{ background: 'var(--panel)', backdropFilter: 'var(--blur)', color: 'var(--ink)' }}
        >
          <div className="mb-3 text-[11px] font-extrabold uppercase tracking-[0.12em] opacity-55">
            Link 2
          </div>
          <div className="mb-2 flex items-center gap-2 text-[24px] font-extrabold tracking-[-0.025em]">
            <Download size={20} aria-hidden /> Download instructions →
          </div>
          <div className="text-[13px] leading-[1.5] opacity-60">
            README.txt generated in your browser — every command, no network request.
          </div>
        </button>
      </div>

      <div className="mb-11 grid gap-3 sm:grid-cols-3">
        <Button variant="ghost" onClick={downloadEnvExample}>Download env example</Button>
        <Button variant="ghost" onClick={downloadParserSetup}>Download parser setup</Button>
        <Button variant="ghost" onClick={downloadDevWorkflow}>Download dev workflow</Button>
      </div>

      <Rule className="mb-8" />
      <h3 className="m-0 mb-[6px] text-[24px] font-extrabold tracking-[-0.02em]">Prerequisites</h3>
      <ul className="m-0 mb-9 list-disc pl-5 text-[15px] leading-[1.7] opacity-70">
        <li>A GitHub, Google, or email account</li>
        <li>For local development: Docker Desktop installed <em>and running</em></li>
      </ul>

      <h3 className="m-0 mb-4 text-[24px] font-extrabold tracking-[-0.02em]">Setup</h3>
      <div className="mb-9 grid" style={{ gap: 'var(--brd-w)', background: 'var(--brd)' }}>
        {COMMANDS.map((c) => (
          <CopyableCommand key={c.n} {...c} />
        ))}
      </div>

      <h3 className="m-0 mb-3 text-[24px] font-extrabold tracking-[-0.02em]">Verify</h3>
      <div
        className="mb-3 p-[18px]"
        style={{
          background: 'var(--panel)',
          backdropFilter: 'var(--blur)',
          border: 'var(--brd-w) solid var(--brd)',
        }}
      >
        <Mono className="text-[13px]">curl http://localhost:8000/health</Mono>
        <div className="mt-[10px] text-[12px] leading-[1.6] opacity-60">
          Expect <Mono>{'{"status":"ok","qdrant":"up","openai":"up",…}'}</Mono> after the hosted API
          wakes. For local Docker development, first boot pulls images and may take a few minutes.
        </div>
      </div>

      {/* Mixed-content reality: localhost is exempt in Chrome/Edge/Firefox, not Safari. */}
      <div
        className="mb-10 flex gap-[14px] p-[18px]"
        style={{ border: 'var(--brd-w) solid var(--accent)' }}
      >
        <span
          className="text-[13px] font-extrabold tracking-[0.06em]"
          style={{ color: 'var(--accent)' }}
        >
          SAFARI
        </span>
        <div className="text-[13.5px] leading-[1.6] opacity-80">
          This page is served over HTTPS and reaches a backend on <Mono>http://localhost</Mono>.
          That works in Chrome, Edge and modern Firefox.{' '}
          <span className="font-extrabold">Safari blocks it.</span> Use Chrome, or run this frontend
          locally instead.
        </div>
      </div>

      <Rule className="mb-8" />

      <div
        className="p-[26px]"
        style={{
          background: 'var(--panel)',
          backdropFilter: 'var(--blur)',
          border: `var(--brd-w) solid ${isConnected ? 'var(--accent)' : 'var(--brd)'}`,
        }}
      >
        {isConnected ? (
          <div className="grid justify-items-start gap-[14px]">
            <div className="relative h-[54px] w-[54px]" aria-hidden>
              <span
                className="ambient absolute inset-0 rounded-full"
                style={{
                  background: 'var(--accent)',
                  opacity: 0.25,
                  animation: 'ringout 1.6s ease-out infinite',
                }}
              />
              <span
                className="absolute rounded-full"
                style={{ inset: 14, background: 'var(--accent)' }}
              />
            </div>
            <h3 className="m-0 text-[28px] font-extrabold tracking-[-0.025em]">
              Backend detected.
            </h3>
            <div className="text-[14px] opacity-70">
              Qdrant {health?.qdrant ?? '—'} · OpenAI {health?.openai ?? '—'} · collection{' '}
              {health?.collection_name ?? '—'}
            </div>
            {advancing ? (
              <div className="flex flex-wrap items-center gap-[14px]">
                <span className="text-[15px] font-extrabold">Taking you to the workbench…</span>
                <Button variant="chip" onClick={cancel}>
                  Cancel / stay here
                </Button>
              </div>
            ) : (
              <Button variant="cta" onClick={() => router.push('/workbench')}>
                Open the workbench →
              </Button>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-start gap-[18px]">
            <div className="mt-[5px]">
              <Spinner />
            </div>
            <div className="min-w-[260px] flex-1">
              <div className="mb-[6px] text-[21px] font-extrabold tracking-[-0.02em]">
                Waiting for backend on {API_BASE_URL}…
              </div>
              <div className="text-[13px] opacity-60">
                Polling /health every 5 seconds · attempt {attempts} · {lastCheckedLabel}
              </div>
              <div
                className="relative mt-[14px] overflow-hidden"
                style={{ height: 2, background: 'var(--brd)' }}
                aria-hidden
              >
                <span
                  className="ambient absolute inset-0"
                  style={{ background: 'var(--accent)', animation: 'shimmer 1.5s linear infinite' }}
                />
              </div>
            </div>
            <Button variant="secondary" onClick={checkNow}>
              Check now
            </Button>
          </div>
        )}
      </div>

      <details className="mt-8 pt-[18px]" style={{ borderTop: 'var(--brd-w) solid var(--brd)' }}>
        <summary className="cursor-pointer text-[14px] font-extrabold">
          Advanced — pointing at a non-default backend
        </summary>
        <div className="mt-3 max-w-[70ch] text-[13.5px] leading-[1.65] opacity-70">
          <p className="m-0 mb-[10px]">
            Set <Mono>NEXT_PUBLIC_API_BASE_URL</Mono> at build time to point the frontend anywhere —
            a tunnelled dev API, or a permanently hosted one. Changing the backend location requires
            editing exactly that one variable.
          </p>
          <p className="m-0">
            A publicly reachable <em>HTTPS</em> backend makes this hosted site work for everyone, in
            every browser, with no local Docker at all — including Safari.
          </p>
        </div>
      </details>
    </main>
  )
}
