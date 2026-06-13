from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pickle
import random
import re
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
from qdrant_client import QdrantClient

# ── project root on sys.path ────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from APP.embedding import load_embedding_model
from APP.generator import SYSTEM_PROMPT
from APP.vector_store import (
    QdrantVectorStore,
    expand_with_neighbors_scored,
    hybrid_retrieve,
)

# RAGAS
from datasets import Dataset
from ragas import evaluate
from ragas.run_config import RunConfig
from ragas.metrics import (
    faithfulness as ragas_faithfulness,
    answer_relevancy as ragas_answer_relevancy,
    context_precision as ragas_context_precision,
    context_recall as ragas_context_recall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings

# ─────────────────────────────────────────────────────────────────────
# 1. CONFIG
# ─────────────────────────────────────────────────────────────────────
OLLAMA_URL        = os.getenv("OLLAMA_URL", "http://localhost:11434")
JUDGE_MODEL       = os.getenv("OLLAMA_JUDGE_MODEL", "llama3.1:8b")
GENERATOR_MODEL   = os.getenv("OLLAMA_GENERATOR_MODEL", "qwen3:8b")
REQUESTED_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    os.getenv("OLLAMA_EMBEDDING_MODEL", "qllama/bge-small-en-v1.5:latest"),
)
EVAL_CONCURRENCY  = int(os.getenv("EVAL_CONCURRENCY", "2"))
GEN_CONCURRENCY   = int(os.getenv("GEN_CONCURRENCY", "2"))

print("🚀 RAG Evaluation Engine (RAGAS-backed)")
print(f"   Judge      : {JUDGE_MODEL}")
print(f"   Generator  : {GENERATOR_MODEL}")
print(f"   Ollama     : {OLLAMA_URL}")


def resolve_embedding_model(preferred: str) -> str:
    candidates = [preferred, "qllama/bge-small-en-v1.5:latest", "qllama/bge-small-en-v1.5", "bge-small-en-v1.5"]

    def normalize(name: str) -> str:
        return name[:-7] if name.endswith(":latest") else name

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{OLLAMA_URL}/api/tags")
            resp.raise_for_status()
        payload = resp.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        available = {
            normalize(item.get("model") or item.get("name") or "")
            for item in models
            if isinstance(item, dict)
        }
        for candidate in candidates:
            if candidate in available or normalize(candidate) in available:
                return candidate
    except Exception:
        pass
    return preferred


EMBEDDING_MODEL = resolve_embedding_model(REQUESTED_EMBEDDING_MODEL)
if EMBEDDING_MODEL != REQUESTED_EMBEDDING_MODEL:
    print(f"   Embedding fallback: {REQUESTED_EMBEDDING_MODEL} -> {EMBEDDING_MODEL}")
else:
    print(f"   Embedding model: {EMBEDDING_MODEL}")

if JUDGE_MODEL == GENERATOR_MODEL:
    print(
        f"⚠️  WARNING: JUDGE_MODEL == GENERATOR_MODEL ('{JUDGE_MODEL}'). "
        "Self-judging inflates faithfulness scores. "
        "Set OLLAMA_JUDGE_MODEL=llama3.1:8b in .env"
    )

# ─────────────────────────────────────────────────────────────────────
# 2. OLLAMA HELPER (used for generation + OOD judge + dataset gen)
# ─────────────────────────────────────────────────────────────────────

async def ollama_generate(prompt: str, model: str, temperature: float = 0.0, max_tokens: int = 700) -> str:
    """Call Ollama /api/generate and return the response string."""
    payload = {
        "model": model,
        "think": False,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
    data = resp.json()
    return data.get("response", "") if isinstance(data, dict) else str(data)


def extract_json(text: str) -> dict | None:
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────────────────────────────
# 2b. GENERATION CACHE — skip regeneration on rerun
# ─────────────────────────────────────────────────────────────────────

GEN_CACHE_PATH = Path("evals/cache/generations.jsonl")
_GEN_CACHE: dict[str, str] = {}


def _gen_cache_key(model: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\x00{prompt}".encode("utf-8")).hexdigest()


def _load_gen_cache() -> None:
    if not GEN_CACHE_PATH.exists():
        return
    with open(GEN_CACHE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                _GEN_CACHE[rec["key"]] = rec["answer"]
            except Exception:
                continue


def _append_gen_cache(key: str, answer: str) -> None:
    GEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GEN_CACHE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "answer": answer}, ensure_ascii=False) + "\n")


async def cached_generate(prompt: str, model: str) -> str:
    key = _gen_cache_key(model, prompt)
    if key in _GEN_CACHE:
        return _GEN_CACHE[key]
    answer = await ollama_generate(prompt, model=model, temperature=0.0, max_tokens=512)
    _GEN_CACHE[key] = answer
    _append_gen_cache(key, answer)
    return answer


# ─────────────────────────────────────────────────────────────────────
# 3. OOD JUDGE (kept — RAGAS has no "correct refusal" classifier)
# ─────────────────────────────────────────────────────────────────────

OOD_JUDGE_PROMPT_TEMPLATE = """\
You are evaluating whether an AI correctly refused to answer an out-of-scope question.

CONTEXT (what the AI was given):
{context}

QUESTION (not answerable from context):
{question}

ANSWER:
{answer}

Classify the answer. Return ONLY a JSON object, no preamble:
{{
  "correct_refusal": true/false,
  "hallucinated": true/false,
  "irrelevant": true/false,
  "reason": "short explanation"
}}

Rules:
- correct_refusal = answer explicitly says info is not in the document
- hallucinated = answer provides unsupported facts
- irrelevant = answer neither refuses nor answers meaningfully
- Exactly ONE of the three booleans must be true.
"""


async def judge_ood(question: str, answer: str, contexts: list[str]) -> tuple[dict | None, str]:
    context_blob = "\n\n".join(contexts)
    prompt = OOD_JUDGE_PROMPT_TEMPLATE.format(
        context=context_blob,
        question=question,
        answer=answer,
    )
    raw = await ollama_generate(prompt, model=JUDGE_MODEL, temperature=0, max_tokens=300)
    payload = extract_json(raw)
    return payload, raw


# ─────────────────────────────────────────────────────────────────────
# 4. DATASET GENERATION
# ─────────────────────────────────────────────────────────────────────

QA_TEMPLATES = [
    "Generate ONE specific factual question answerable from this context.\nReturn JSON with keys: question, ground_truth.\n\nContext:\n{context}\n\nJSON:",
    "Generate ONE question about a number, statistic, or percentage in this context.\nReturn JSON with keys: question, ground_truth.\n\nContext:\n{context}\n\nJSON:",
    "Generate ONE question asking what something means or how something works based on this context.\nReturn JSON with keys: question, ground_truth.\n\nContext:\n{context}\n\nJSON:",
    "Generate ONE question comparing two concepts from this context.\nReturn JSON with keys: question, ground_truth.\n\nContext:\n{context}\n\nJSON:",
]

OOD_TEMPLATE = (
    "Generate ONE question that CANNOT be answered from the document below.\n"
    "It should be answerable from general knowledge but not from this context.\n"
    "Return JSON with keys: question, ground_truth.\n\n"
    "Context:\n{context}\n\nJSON:"
)


def load_chunks_jsonl(path: str) -> list[dict]:
    chunks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("page_content", "").strip():
                chunks.append(record)
    return chunks


def coverage_sample(chunks: list, n: int, seed: int = 42) -> list:
    if not chunks or n <= 0:
        return []
    n = min(n, len(chunks))
    random.seed(seed)
    step = max(len(chunks) / n, 1)
    picks = []
    for i in range(n):
        start = int(i * step)
        end = int(min((i + 1) * step, len(chunks)))
        segment = chunks[start:max(end, start + 1)]
        picks.append(random.choice(segment))
    return picks


async def _gen_qa(chunk: dict, q_type: int, gen_sem: asyncio.Semaphore) -> dict | None:
    async with gen_sem:
        template = QA_TEMPLATES[q_type % len(QA_TEMPLATES)]
        prompt = template.format(context=chunk["page_content"][:1200])
        raw = await ollama_generate(prompt, model=GENERATOR_MODEL, temperature=0.2, max_tokens=250)
        payload = extract_json(raw)
        if not payload or not payload.get("question") or not payload.get("ground_truth"):
            return None
        return {
            "question": payload["question"].strip(),
            "ground_truth": payload["ground_truth"].strip(),
            "ood": False,
            "gold_context": chunk["page_content"].strip(),
        }


async def _gen_ood(chunk: dict, gen_sem: asyncio.Semaphore) -> dict | None:
    async with gen_sem:
        prompt = OOD_TEMPLATE.format(context=chunk["page_content"][:800])
        raw = await ollama_generate(prompt, model=GENERATOR_MODEL, temperature=0.4, max_tokens=250)
        payload = extract_json(raw)
        if not payload or not payload.get("question"):
            return None
        return {
            "question": payload["question"].strip(),
            "ground_truth": "This information is not present in the document.",
            "ood": True,
            "gold_context": None,
        }


async def build_dataset(chunks_path: str, num_questions: int, seed: int, ood_ratio: float) -> list[dict]:
    chunks = load_chunks_jsonl(chunks_path)
    if not chunks:
        raise ValueError(f"No chunks found in {chunks_path}")

    ood_count = int(round(num_questions * max(0.0, min(ood_ratio, 1.0))))
    in_count = max(num_questions - ood_count, 0)

    in_sample = coverage_sample(chunks, in_count, seed=seed)
    ood_sample = coverage_sample(chunks, ood_count, seed=seed + 1)

    gen_sem = asyncio.Semaphore(GEN_CONCURRENCY)

    in_tasks = [_gen_qa(c, i, gen_sem) for i, c in enumerate(in_sample)]
    ood_tasks = [_gen_ood(c, gen_sem) for c in ood_sample]

    in_results = await asyncio.gather(*in_tasks)
    ood_results = await asyncio.gather(*ood_tasks)

    dataset = [r for r in in_results if r] + [r for r in ood_results if r]
    random.shuffle(dataset)
    print(f"✅ Dataset: {len(dataset)} questions "
          f"({len([r for r in dataset if not r['ood']])} in-scope, "
          f"{len([r for r in dataset if r['ood']])} OOD)")
    return dataset


# ─────────────────────────────────────────────────────────────────────
# 5. RAG STUDENT — uses production stack (Qdrant + BM25 + bge)
# ─────────────────────────────────────────────────────────────────────

def _load_production_indices():
    """Load the same BM25 + Qdrant indices used in production."""
    bm25_path = Path("indexes/bm25_data.pkl")
    if not bm25_path.exists():
        raise FileNotFoundError("indexes/bm25_data.pkl not found. Run /ingest first.")

    with open(bm25_path, "rb") as f:
        data = pickle.load(f)
    bm25 = data["bm25"]
    chunks = data["chunks"]

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    client = QdrantClient(url=qdrant_url)
    embeddings = load_embedding_model(EMBEDDING_MODEL)

    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=os.getenv("QDRANT_COLLECTION", "chunks_collection"),
        embeddings=embeddings,
    )
    return vectorstore, bm25, chunks, embeddings


async def get_rag_answer(
    question: str,
    vectorstore: QdrantVectorStore,
    bm25,
    chunks: list,
    top_n: int = 5,
) -> tuple[str, list[str], float]:
    start = time.time()
    results = await asyncio.to_thread(
        lambda: hybrid_retrieve(question, vectorstore, bm25, chunks, top_n=top_n)
    )
    retrieval_ms = (time.time() - start) * 1000.0

    # (A) same expanded context the production API uses, WITH scores
    expanded = expand_with_neighbors_scored(results=results, chunks=chunks, window=1)
    contexts = [doc.page_content for doc, _ in expanded]

    # production-identical prompt (canonical SYSTEM_PROMPT, temperature=0)
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"CONTEXT:\n{chr(10).join(contexts)}\n\n"
        f"QUESTION: {question}\n\n"
        f"ANSWER (use ONLY the context above):"
    )
    answer = await cached_generate(prompt, model=GENERATOR_MODEL)
    return answer, contexts, retrieval_ms


# ─────────────────────────────────────────────────────────────────────
# 6. CLASSIC METRICS (retrieval + lexical overlap — independent of judge)
# ─────────────────────────────────────────────────────────────────────

REFUSAL_PATTERN = re.compile(
    r"\b(cannot find|not in the document|not provided|not available"
    r"|cannot locate|no information|not mentioned|not covered"
    r"|outside the scope|based on the (provided |given )?context|cannot answer)\b",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def exact_match(pred: str, truth: str) -> int:
    return 1 if normalize_text(pred) == normalize_text(truth) else 0


def token_f1(pred: str, truth: str) -> float:
    pred_tokens = re.findall(r"\w+", pred.lower())
    truth_tokens = re.findall(r"\w+", truth.lower())
    if not pred_tokens or not truth_tokens:
        return 0.0
    pred_c: dict[str, int] = {}
    truth_c: dict[str, int] = {}
    for t in pred_tokens:
        pred_c[t] = pred_c.get(t, 0) + 1
    for t in truth_tokens:
        truth_c[t] = truth_c.get(t, 0) + 1
    overlap = sum(min(c, truth_c.get(t, 0)) for t, c in pred_c.items())
    precision = overlap / len(pred_tokens)
    recall = overlap / len(truth_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def retrieval_hit(gold_context: str | None, retrieved: list[str]) -> tuple[int | None, float | None]:
    if not gold_context:
        return None, None
    gold_norm = normalize_text(gold_context)
    for rank, ctx in enumerate(retrieved, 1):
        if gold_norm in normalize_text(ctx) or normalize_text(ctx) in gold_norm:
            return rank, 1.0 / rank
    return None, 0.0


# ─────────────────────────────────────────────────────────────────────
# 7. EVAL LOOP — Phase A: run RAG + collect raw rows (no LLM judge yet)
# ─────────────────────────────────────────────────────────────────────

eval_sem: asyncio.Semaphore


async def run_one(
    row: dict,
    vectorstore: QdrantVectorStore,
    bm25,
    chunks: list,
) -> dict:
    """Run retrieval + generation for one question. Judging happens later
    (RAGAS batch for in-scope, judge_ood per-row for OOD)."""
    async with eval_sem:
        question = row["question"]
        gold_context = row.get("gold_context")
        ood = row.get("ood", False)

        answer, contexts, retrieval_ms = await get_rag_answer(question, vectorstore, bm25, chunks)

        refused = bool(REFUSAL_PATTERN.search(answer))
        hit_rank, mrr = retrieval_hit(gold_context, contexts)

        em = exact_match(answer, row["ground_truth"]) if not ood else None
        f1 = token_f1(answer, row["ground_truth"]) if not ood else None

        return {
            "question":      question,
            "answer":        answer,
            "contexts":      contexts,
            "ground_truth":  row.get("ground_truth", ""),
            "ood":           ood,
            "refused":       refused,
            "retrieval_ms":  round(retrieval_ms, 2),
            "hit_rank":      hit_rank,
            "mrr":           mrr,
            "exact_match":   em,
            "f1":            f1,
        }


async def run_ood_judging(results: list[dict]) -> None:
    """Mutates OOD rows in-place with judge_ood output."""
    ood_rows = [r for r in results if r["ood"]]
    tasks = [judge_ood(r["question"], r["answer"], r["contexts"]) for r in ood_rows]
    payloads = await asyncio.gather(*tasks)

    for row, (payload, raw) in zip(ood_rows, payloads):
        correct_refusal = False
        hallucinated = False
        irrelevant_ood = False
        ood_reason = ""
        if payload:
            correct_refusal = bool(payload.get("correct_refusal"))
            hallucinated = bool(payload.get("hallucinated"))
            irrelevant_ood = bool(payload.get("irrelevant"))
            ood_reason = payload.get("reason", "")

        if correct_refusal:
            verdict = "Correct Refusal"
        elif hallucinated:
            verdict = "Hallucinated"
        else:
            verdict = "Irrelevant"

        row["verdict"] = verdict
        row["ood_correct_refusal"] = correct_refusal
        row["ood_hallucinated"] = hallucinated
        row["ood_irrelevant"] = irrelevant_ood
        row["ood_reason"] = ood_reason
        row["judge_raw"] = raw
        # placeholders so the in-scope columns exist for all rows
        row["faithfulness"] = None
        row["answer_relevancy"] = None
        row["context_precision"] = None
        row["context_recall"] = None


# ─────────────────────────────────────────────────────────────────────
# 8. RAGAS BATCH JUDGING — in-scope rows
# ─────────────────────────────────────────────────────────────────────

def build_ragas_judge():
    judge_llm = LangchainLLMWrapper(
        ChatOllama(model=JUDGE_MODEL, base_url=OLLAMA_URL, temperature=0, timeout=600)
    )
    judge_embeddings = LangchainEmbeddingsWrapper(
        OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_URL)
    )
    return judge_llm, judge_embeddings


def run_ragas_judging(results: list[dict]) -> None:
    """Mutates in-scope rows in-place with RAGAS scores + derived verdict."""
    in_rows = [r for r in results if not r["ood"]]
    if not in_rows:
        return

    ragas_dataset = Dataset.from_list([
        {
            "question": r["question"],
            "answer": r["answer"],
            "contexts": r["contexts"],
            "ground_truth": r["ground_truth"],
        }
        for r in in_rows
    ])

    judge_llm, judge_embeddings = build_ragas_judge()

    print("\n⚖️  Running RAGAS metrics (faithfulness, answer_relevancy, "
          "context_precision, context_recall)...")
    ragas_result = evaluate(
        ragas_dataset,
        metrics=[
            ragas_faithfulness,
            ragas_answer_relevancy,
            ragas_context_precision,
            ragas_context_recall,
        ],
        llm=judge_llm,
        embeddings=judge_embeddings,
        run_config=RunConfig(timeout=600, max_workers=1, max_retries=2),
        batch_size=1,
    )
    ragas_df = ragas_result.to_pandas()

    for i, r in enumerate(in_rows):
        faithfulness_score = ragas_df.loc[i, "faithfulness"]
        relevancy_score = ragas_df.loc[i, "answer_relevancy"]
        precision_score = ragas_df.loc[i, "context_precision"]
        recall_score = ragas_df.loc[i, "context_recall"]

        r["faithfulness"] = faithfulness_score
        r["answer_relevancy"] = relevancy_score
        r["context_precision"] = precision_score
        r["context_recall"] = recall_score

        # Verdict, with NaN-safe handling — a row the judge couldn't score
        # is marked "Unscored", not silently treated as 0.0
        if pd.isna(faithfulness_score) or pd.isna(relevancy_score):
            verdict = "Unscored"
        elif r["refused"] and r["hit_rank"] is None:
            # Model refused AND the gold context wasn't even retrieved —
            # this is a correct refusal, not a hallucination/false refusal.
            verdict = "Correct Refusal"
        elif faithfulness_score < 0.5:
            verdict = "Hallucinated"
        elif relevancy_score < 0.5:
            verdict = "Irrelevant"
        elif r["refused"] and r["hit_rank"] is not None:
            verdict = "False Refusal"
        else:
            verdict = "Excellent"

        r["verdict"] = verdict
        # placeholders so the OOD columns exist for all rows
        r["ood_correct_refusal"] = None
        r["ood_hallucinated"] = None
        r["ood_irrelevant"] = None
        r["ood_reason"] = ""
        r["judge_raw"] = ""


# ─────────────────────────────────────────────────────────────────────
# 9. REPORTING
# ─────────────────────────────────────────────────────────────────────

def print_report(df: pd.DataFrame, elapsed: float) -> None:
    df_in = df[df["ood"] == False]
    df_ood = df[df["ood"] == True]
    in_n = len(df_in)
    ood_n = len(df_ood)

    def pct(series, val):
        return (series == val).sum() / max(len(series), 1) * 100

    avg_r_ms = df["retrieval_ms"].mean()
    p95_r_ms = df["retrieval_ms"].quantile(0.95)

    print(f"\n{'═'*64}")
    print(f"🏁 EVALUATION COMPLETE  |  {elapsed:.1f}s total")
    print(f"   Avg retrieval: {avg_r_ms:.1f}ms  |  P95: {p95_r_ms:.1f}ms")
    print(f"{'─'*64}")
    print(f"IN-SCOPE  (N={in_n})")
    if in_n:
        for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
            col = pd.to_numeric(df_in[metric], errors="coerce").dropna()
            val = col.mean() if len(col) else float("nan")
            print(f"  {metric:<26}: {val:.3f}")
        print(f"  {'Excellent %':<26}: {pct(df_in['verdict'], 'Excellent'):.1f}%")
        print(f"  {'Hallucinated %':<26}: {pct(df_in['verdict'], 'Hallucinated'):.1f}%")
        print(f"  {'False Refusal %':<26}: {pct(df_in['verdict'], 'False Refusal'):.1f}%")
        print(f"  {'Correct Refusal %':<26}: {pct(df_in['verdict'], 'Correct Refusal'):.1f}%")
        print(f"  {'Unscored %':<26}: {pct(df_in['verdict'], 'Unscored'):.1f}%")
        mrr_val = df_in["mrr"].dropna().mean()
        f1_val = df_in["f1"].dropna().mean()
        print(f"  {'MRR':<26}: {mrr_val:.3f}")
        print(f"  {'Token F1':<26}: {f1_val:.3f}")
    print(f"{'─'*64}")
    print(f"OOD  (N={ood_n})")
    if ood_n:
        print(f"  {'Correct Refusal %':<26}: {df_ood['ood_correct_refusal'].mean()*100:.1f}%")
        print(f"  {'Hallucinated %':<26}: {df_ood['ood_hallucinated'].mean()*100:.1f}%")
        print(f"  {'Irrelevant %':<26}: {df_ood['ood_irrelevant'].mean()*100:.1f}%")
    print(f"{'═'*64}\n")


def save_results(df: pd.DataFrame, elapsed: float) -> None:
    Path("evals/experiments").mkdir(parents=True, exist_ok=True)

    df_in = df[df["ood"] == False]
    df_ood = df[df["ood"] == True]

    def mean_numeric(series):
        col = pd.to_numeric(series, errors="coerce").dropna()
        return round(col.mean(), 3) if len(col) else None

    summary = {
        "timestamp":       time.strftime("%Y-%m-%d %H:%M"),
        "elapsed_s":       round(elapsed, 2),
        "total_questions": len(df),
        "in_scope":        len(df_in),
        "ood":             len(df_ood),
        "judge_model":     JUDGE_MODEL,
        "generator_model": GENERATOR_MODEL,
        "metrics": {
            "faithfulness":      mean_numeric(df_in["faithfulness"]) if len(df_in) else None,
            "answer_relevancy":  mean_numeric(df_in["answer_relevancy"]) if len(df_in) else None,
            "context_precision": mean_numeric(df_in["context_precision"]) if len(df_in) else None,
            "context_recall":    mean_numeric(df_in["context_recall"]) if len(df_in) else None,
            "mrr":               round(df_in["mrr"].dropna().mean(), 3) if len(df_in) else None,
            "token_f1":          round(df_in["f1"].dropna().mean(), 3) if len(df_in) else None,
        },
        "ood_metrics": {
            "correct_refusal_rate": round(df_ood["ood_correct_refusal"].mean(), 3) if len(df_ood) else None,
            "hallucination_rate":   round(df_ood["ood_hallucinated"].mean(), 3) if len(df_ood) else None,
        },
    }

    results_path = "evals/results.json"
    Path(results_path).parent.mkdir(parents=True, exist_ok=True)
    Path(results_path).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"📊 Results saved → {results_path}")

    baseline_path = "evals/experiments/baseline_scores.json"
    if not Path(baseline_path).exists():
        Path(baseline_path).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"📌 Baseline saved → {baseline_path}")

    # contexts column is a list — stringify for CSV
    df_out = df.copy()
    if "contexts" in df_out.columns:
        df_out["contexts"] = df_out["contexts"].apply(lambda c: json.dumps(c, ensure_ascii=False))

    csv_path = "evals/experiments/fast_eval_report.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"📋 Full report   → {csv_path}")


# ─────────────────────────────────────────────────────────────────────
# 10. MAIN
# ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    global eval_sem

    parser = argparse.ArgumentParser(description="Local RAG evaluation using RAGAS (Ollama judge, no OpenAI)")
    parser.add_argument("--chunks",        default="chunks/chunks_processed.jsonl")
    parser.add_argument("--dataset",       default="evals/datasets/auto_eval.jsonl")
    parser.add_argument("--num-questions", type=int,   default=20)
    parser.add_argument("--seed",          type=int,   default=42)
    parser.add_argument("--ood-ratio",     type=float, default=0.3)
    parser.add_argument("--regenerate",    action="store_true")
    args = parser.parse_args()

    eval_sem = asyncio.Semaphore(EVAL_CONCURRENCY)

    # load generation cache (skip regeneration on rerun)
    _load_gen_cache()
    if _GEN_CACHE:
        print(f"♻️  Loaded {len(_GEN_CACHE)} cached generations")

    # ── Dataset ──────────────────────────────────────────────────────
    Path(args.dataset).parent.mkdir(parents=True, exist_ok=True)
    if args.regenerate or not Path(args.dataset).exists():
        print(f"\n📝 Generating dataset from {args.chunks}...")
        dataset = await build_dataset(
            chunks_path=args.chunks,
            num_questions=args.num_questions,
            seed=args.seed,
            ood_ratio=args.ood_ratio,
        )
        with open(args.dataset, "w", encoding="utf-8") as f:
            for row in dataset:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"💾 Dataset saved → {args.dataset}")
    else:
        dataset = []
        with open(args.dataset, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    dataset.append(json.loads(line))
        print(f"📂 Loaded existing dataset ({len(dataset)} rows) from {args.dataset}")

    # ── Load production indices ───────────────────────────────────────
    print("\n🔌 Loading production indices (Qdrant + BM25)...")
    vectorstore, bm25, chunks, _ = _load_production_indices()
    print(f"✅ Loaded {len(chunks)} chunks")

    # ── Phase A: run RAG (retrieval + generation) for all questions ────
    print(f"\n📊 Running retrieval + generation ({EVAL_CONCURRENCY} parallel workers)...")
    start_time = time.time()
    tasks = [run_one(row, vectorstore, bm25, chunks) for row in dataset]
    total = len(tasks)
    results = []
    done = 0

    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        done += 1
        elapsed_so_far = max(time.time() - start_time, 0.001)
        rate = done / elapsed_so_far
        eta = (total - done) / rate if rate > 0 else 0
        bar_len = 28
        filled = int(bar_len * done / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(
            f"\r  [{bar}] {done}/{total}  {elapsed_so_far:.0f}s elapsed  ETA {eta:.0f}s"
        )
        sys.stdout.flush()
    print()

    # ── Phase B: judging ────────────────────────────────────────────
    # In-scope rows -> RAGAS batch evaluation
    run_ragas_judging(results)
    # OOD rows -> custom refusal/hallucination classifier
    await run_ood_judging(results)

    elapsed = time.time() - start_time
    df = pd.DataFrame(results)

    print_report(df, elapsed)
    save_results(df, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
