'use client'

// The explainer. Must stand entirely on its own with no backend running — this
// is what most visitors will see and judge the project by.

import Link from 'next/link'
import { ArrowRight, Github } from 'lucide-react'

import { REPO_URL } from '@/config'
import { useUiPrefs } from '@/hooks/useUiPrefs'
import { PipelineVisualiser, useLoopingStage } from '@/components/PipelineVisualiser'
import { Button, Eyebrow, Rule } from '@/components/ui'

const HERO_STATS = [
  { v: '2', k: 'retrieval indexes — dense + sparse' },
  { v: '0.65 / 0.35', k: 'RRF fusion weighting' },
  { v: '±1', k: 'neighbour chunks expanded' },
  { v: '100%', k: 'answers carry citations' },
]

const ARCHITECTURE = [
  {
    role: 'API',
    name: 'FastAPI',
    note: 'Ingest, query, health and collection endpoints. Every response carries an X-Request-ID.',
  },
  {
    role: 'Vectors',
    name: 'Qdrant',
    note: 'Dense vector store, recreated on each ingest so the index always matches the document.',
  },
  {
    role: 'Keywords',
    name: 'BM25',
    note: 'Sparse index running alongside the vectors — catches exact terms embeddings miss.',
  },
  {
    role: 'Reranker',
    name: 'Flashrank',
    note: 'Re-scores the fused candidate set before anything reaches the model.',
  },
  {
    role: 'Models',
    name: 'OpenAI',
    note: 'text-embedding-3-small for vectors, gpt-4o-mini for generation.',
  },
  {
    role: 'Runtime',
    name: 'Docker Compose',
    note: 'API, Qdrant and the evaluation harness on your own machine.',
  },
]

const FEATURES = [
  { t: 'Semantic chunking', d: 'Splits on meaning, not character counts, so chunks stay coherent.' },
  {
    t: 'Chunk quality gate',
    d: 'Scores each chunk out of 7 and drops the ones below your threshold.',
  },
  { t: 'Hybrid retrieval', d: 'Dense vectors and sparse keywords searched in parallel.' },
  {
    t: 'RRF fusion',
    d: 'Reciprocal Rank Fusion merges both rankings — 0.65 dense, 0.35 sparse.',
  },
  { t: 'Reranking', d: 'Flashrank re-orders candidates by true relevance to the question.' },
  { t: 'Neighbour expansion', d: 'Pulls adjacent chunks so answers keep their context.' },
  {
    t: 'Inline citations',
    d: 'Every claim tagged with its file and page, rendered as linked chips.',
  },
  { t: 'RAGAS harness', d: 'Faithfulness and relevancy measured offline, not guessed at.' },
]

export function LandingView() {
  const { motionOff } = useUiPrefs()
  const { ref: pipeRef, stage } = useLoopingStage(!motionOff)

  return (
    <main className="relative z-10">
      <section className="mx-auto max-w-[1180px] px-[26px] pb-16 pt-[90px]">
        <Eyebrow className="mb-[26px]">Self-hosted retrieval-augmented generation</Eyebrow>
        <h1 className="m-0 mb-[26px] max-w-[15ch] text-[clamp(44px,7vw,92px)] font-extrabold leading-[0.95] tracking-[-0.035em]">
          Ask questions of any PDF.
        </h1>
        <p className="m-0 mb-[38px] max-w-[56ch] text-[clamp(18px,2vw,23px)] leading-[1.45] opacity-70">
          Answers grounded in the document itself, with every claim cited back to the page it came
          from. Hybrid retrieval, a reranker, and a quality gate — running in your own Docker
          network.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/setup">
            <Button variant="cta" breathe>
              Try it yourself <ArrowRight size={16} aria-hidden />
            </Button>
          </Link>
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            <Button variant="secondary">
              <Github size={16} aria-hidden /> View the repository
            </Button>
          </a>
        </div>

        <Rule className="mt-16" />
        <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))]">
          {HERO_STATS.map((s) => (
            <div
              key={s.k}
              className="py-[26px] pr-[26px]"
              style={{ borderRight: 'var(--brd-w) solid var(--brd)' }}
            >
              <div className="tnum text-[32px] font-extrabold tracking-[-0.03em]">{s.v}</div>
              <div className="mt-1 text-[12px] opacity-60">{s.k}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-[1180px] px-[26px] pb-20">
        <Rule className="mb-12" />
        <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-12">
          <div>
            <Eyebrow className="mb-[14px]">The problem</Eyebrow>
            <h3 className="mb-[14px] text-[27px] font-extrabold tracking-[-0.02em]">
              A plain LLM will confidently invent what your document says.
            </h3>
            <p className="m-0 leading-[1.6] opacity-70">
              It has never read your file. Ask it about a 200-page report and it produces something
              plausible, unattributable, and occasionally wrong in the exact places that matter.
            </p>
          </div>
          <div>
            <Eyebrow className="mb-[14px]">The approach</Eyebrow>
            <h3 className="mb-[14px] text-[27px] font-extrabold tracking-[-0.02em]">
              Retrieve first. Answer only from what was retrieved. Cite it.
            </h3>
            <p className="m-0 leading-[1.6] opacity-70">
              The document is split semantically, scored for quality, and indexed twice — dense
              vectors and sparse keywords. Every question runs both, fuses the rankings, reranks,
              and hands only the surviving chunks to the model.
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1180px] px-[26px] pb-[90px]">
        <Rule className="mb-10" />
        <div className="mb-2 flex flex-wrap items-baseline gap-4">
          <h2 className="m-0 text-[38px] font-extrabold tracking-[-0.03em]">How it works</h2>
          <span
            className="text-[12px] opacity-55"
            title="Illustrative view of the backend pipeline"
          >
            Illustrative view of the backend pipeline — not measured telemetry.
          </span>
        </div>
        <div ref={pipeRef} className="mt-7">
          <PipelineVisualiser stage={stage} />
        </div>
      </section>

      <section className="mx-auto max-w-[1180px] px-[26px] pb-[90px]">
        <Rule className="mb-10" />
        <h2 className="m-0 mb-7 text-[38px] font-extrabold tracking-[-0.03em]">Architecture</h2>
        <div
          className="grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))]"
          style={{ gap: 'var(--brd-w)', background: 'var(--brd)' }}
        >
          {ARCHITECTURE.map((a) => (
            <div
              key={a.name}
              className="p-6"
              style={{ background: 'var(--panel)', backdropFilter: 'var(--blur)' }}
            >
              <div
                className="mb-[10px] text-[11px] font-extrabold uppercase tracking-[0.12em]"
                style={{ color: 'var(--accent)' }}
              >
                {a.role}
              </div>
              <div className="mb-[6px] text-[19px] font-extrabold tracking-[-0.02em]">{a.name}</div>
              <div className="text-[13px] leading-[1.5] opacity-65">{a.note}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-[1180px] px-[26px] pb-[90px]">
        <Rule className="mb-10" />
        <h2 className="m-0 mb-7 text-[38px] font-extrabold tracking-[-0.03em]">
          What&apos;s in the pipeline
        </h2>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-x-10 gap-y-[26px]">
          {FEATURES.map((f) => (
            <div key={f.t} style={{ borderTop: 'var(--brd-w) solid var(--brd)' }} className="pt-[14px]">
              <div className="mb-[5px] text-[16px] font-extrabold tracking-[-0.01em]">{f.t}</div>
              <div className="text-[13px] leading-[1.5] opacity-65">{f.d}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Stated accurately: self-hosted retrieval, but generation is OpenAI's API. */}
      <section className="mx-auto max-w-[1180px] px-[26px] pb-[90px]">
        <div className="p-11" style={{ background: 'var(--accent)', color: 'var(--on-accent)' }}>
          <div className="mb-4 text-[11px] font-extrabold uppercase tracking-[0.14em] opacity-75">
            Where your data goes
          </div>
          <p className="m-0 mb-4 max-w-[44ch] text-[clamp(20px,2.4vw,30px)] font-extrabold leading-[1.28] tracking-[-0.02em]">
            Retrieval, storage and orchestration are fully self-hosted in your own Docker network.
          </p>
          <p className="m-0 max-w-[60ch] text-[15px] leading-[1.55] opacity-85">
            Document text and your questions are sent to OpenAI&apos;s API for embeddings and
            generation. This is not a fully local or offline system, and it is not described as one.
          </p>
        </div>
      </section>

      <footer style={{ borderTop: 'var(--brd-w) solid var(--brd)' }}>
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-6 px-[26px] py-7 text-[13px]">
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="font-extrabold">
            Repository →
          </a>
          <span className="opacity-55">MIT licence</span>
          <span className="opacity-55">Vaibhav · Semantic Q&amp;A over Large Documents</span>
          <div className="flex-1" />
          <Link href="/setup">
            <Button variant="ghost">Run it locally →</Button>
          </Link>
        </div>
      </footer>
    </main>
  )
}
