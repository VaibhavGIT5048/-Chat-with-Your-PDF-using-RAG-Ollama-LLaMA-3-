from __future__ import annotations

import os
import json
import pickle
import re
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from pathlib import Path
from langchain_core.documents import Document
from APP.embedding import load_embedding_model

try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None

try:
    from qdrant_client import QdrantClient
    from qdrant_client import models as qdrant_models
except Exception:
    QdrantClient = None
    qdrant_models = None

try:
    from flashrank import Ranker, RerankRequest
except Exception:
    Ranker = None
    RerankRequest = None


class QdrantVectorStore:
    def __init__(self, client, collection_name: str, embeddings):
        self.client = client
        self.collection_name = collection_name
        self.embeddings = embeddings

    def similarity_search(self, query: str, k: int = 5):
        qvec = None
        try:
            qvec = self.embeddings.embed_documents([query])[0]
        except Exception:
            try:
                qvec = self.embeddings.embed_query(query)
            except Exception:
                raise RuntimeError("Embedding backend not available for queries.")

        hits = None
        try:
            hits = self.client.query_points(
                collection_name=self.collection_name,
                query=qvec,
                limit=k,
                with_payload=True,
            ).points
        except AttributeError:
            pass

        if hits is None:
            try:
                hits = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=qvec,
                    limit=k,
                    with_payload=True,
                )
            except TypeError:
                hits = self.client.search(
                    self.collection_name, qvec, limit=k, with_payload=True
                )

        results = []
        for h in hits:
            payload = getattr(h, "payload", None) or (h.get("payload") if isinstance(h, dict) else None)
            if payload is None:
                payload = {}

            text = payload.get("text") if isinstance(payload, dict) else None
            metadata = payload.get("metadata") if isinstance(payload, dict) else {}
            if text is None:
                text = payload.get("payload", {}).get("text") if isinstance(payload, dict) else ""
                metadata = payload.get("payload", {}).get("metadata", {}) if isinstance(payload, dict) else {}

            doc = Document(page_content=text or "", metadata=metadata or {})
            results.append(doc)

        return results


_flashrank_ranker = None


def flashrank_rerank(query: str, candidates: list[Document], k: int = 5) -> list[Document]:
    if Ranker is None or RerankRequest is None or not candidates:
        return candidates[:k]

    global _flashrank_ranker
    if _flashrank_ranker is None:
        cache_dir = os.getenv("FLASHRANK_CACHE_DIR", "data/flashrank_cache")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        _flashrank_ranker = Ranker(cache_dir=cache_dir)

    passages = []
    for idx, doc in enumerate(candidates):
        passages.append({
            "id": str(idx),
            "text": doc.page_content,
            "meta": doc.metadata,
        })

    request = RerankRequest(query=query, passages=passages)
    ranked = _flashrank_ranker.rerank(request)
    top_docs = []
    for item in ranked[:k]:
        index = int(item["id"]) if isinstance(item, dict) and "id" in item else int(getattr(item, "id", 0))
        if 0 <= index < len(candidates):
            top_docs.append(candidates[index])
    return top_docs or candidates[:k]


TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


def tokenize_for_bm25(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def load_passed_chunks(path="data/chunks/chunks_processed.jsonl"):
    potential_paths = [Path(path), Path("../") / path]
    target_path = None
    for p in potential_paths:
        if p.exists():
            target_path = p
            break

    if not target_path:
        print(f"❌ Error: Could not find {path}")
        return []

    processed_chunks = []
    print(f"🔄 Loading data from: {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            processed_chunks.append(Document(
                page_content=data["page_content"],
                metadata=data["metadata"]
            ))
    return processed_chunks


def build_hybrid_indices(chunks):
    if not chunks:
        print("⚠️ No chunks to index. Skipping build.")
        return None, None

    idx_dir = Path("data/indexes")
    idx_dir.mkdir(parents=True, exist_ok=True)

    faiss_dir = idx_dir / "faiss_index"
    if faiss_dir.exists():
        backup_dir = idx_dir / "faiss_index_backup"
        timestamp = int(time.time())
        backup_target = backup_dir / str(timestamp)
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        faiss_dir.rename(backup_target)
        print(f"ℹ️ Detected old FAISS index. Moved to {backup_target}")

    print("🧠 Building Qdrant Semantic Index (Dense)...")
    embeddings = load_embedding_model()

    if QdrantClient is None:
        print("⚠️ qdrant-client not installed.")
        return None, None

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    collection_name = os.getenv("QDRANT_COLLECTION", "chunks_collection")

    texts = [c.page_content for c in chunks]
    batch_size = 64
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]

    print(f"   Embedding {len(texts)} chunks in {len(batches)} batches (parallel)...")
    with ThreadPoolExecutor(max_workers=min(8, len(batches) or 1)) as executor:
        batch_vectors = list(executor.map(embeddings.embed_documents, batches))
    vectors = [vec for batch in batch_vectors for vec in batch]

    vector_size = len(vectors[0]) if vectors else 0

    try:
        if qdrant_models is not None:
            client.recreate_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(size=vector_size, distance=qdrant_models.Distance.COSINE),
            )
        else:
            client.recreate_collection(collection_name=collection_name, vectors_config={"size": vector_size, "distance": "Cosine"})
    except Exception:
        try:
            if qdrant_models is not None:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qdrant_models.VectorParams(size=vector_size, distance=qdrant_models.Distance.COSINE),
                )
            else:
                client.create_collection(collection_name=collection_name, vector_size=vector_size, distance="Cosine")
        except Exception:
            pass

    points = []
    for c, v in zip(chunks, vectors):
        pid = int(c.metadata.get("chunk_id", len(points)))
        payload = {"text": c.page_content, "metadata": c.metadata}
        if qdrant_models is not None:
            points.append(qdrant_models.PointStruct(id=pid, vector=v, payload=payload))
        else:
            points.append({"id": pid, "vector": v, "payload": payload})

    client.upsert(collection_name=collection_name, points=points)
    vectorstore = QdrantVectorStore(client=client, collection_name=collection_name, embeddings=embeddings)

    print("📝 Building BM25 Keyword Index (Sparse)...")
    tokenized_corpus = [tokenize_for_bm25(doc.page_content) for doc in chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    with open(idx_dir / "bm25_data.pkl", "wb") as f:
        pickle.dump({"bm25": bm25, "chunks": chunks}, f)

    print(f"✅ All indices built. Saved to: {idx_dir.absolute()}")
    return vectorstore, bm25


def apply_quality_penalty(chunks, base_scores):
    penalised = []
    for chunk, score in zip(chunks, base_scores):
        gate = chunk.metadata.get("passed_gate", False)
        weight = 1.0 if gate else 0.7
        penalised.append((chunk, score * weight))
    return sorted(penalised, key=lambda x: x[1], reverse=True)


def hybrid_retrieve(
    query: str,
    vectorstore: QdrantVectorStore,
    bm25,
    chunks: list[Document],
    top_n: int = 5,
    rrf_k: int = 15,
) -> list[tuple[Document, float]]:
    # candidate pool: headroom for the reranker without bloating latency
    candidate_k = max(top_n * 5, 25)

    # dense leads for semantic QA; sparse supports exact-term recall
    dense_weight = 0.65
    bm25_weight = 0.35

    semantic_results = vectorstore.similarity_search(query, k=min(candidate_k, len(chunks)))

    tokenized_query = tokenize_for_bm25(query)
    keyword_scores = bm25.get_scores(tokenized_query)
    top_indices = np.argsort(keyword_scores)[::-1][:candidate_k]
    keyword_results = [chunks[i] for i in top_indices if keyword_scores[i] > 0]

    rrf_scores: dict = {}
    doc_map: dict = {}

    # chunk_id can be absent if a Qdrant payload was written by an older or external
    # indexer; skip those rather than dying mid-query.
    for rank, doc in enumerate(semantic_results, 1):
        cid = doc.metadata.get("chunk_id")
        if cid is None:
            continue
        doc_map[cid] = doc
        rrf_scores[cid] = rrf_scores.get(cid, 0) + dense_weight / (rrf_k + rank)

    for rank, doc in enumerate(keyword_results, 1):
        cid = doc.metadata.get("chunk_id")
        if cid is None:
            continue
        doc_map[cid] = doc
        rrf_scores[cid] = rrf_scores.get(cid, 0) + bm25_weight / (rrf_k + rank)

    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    base_results = [(doc_map[cid], score) for cid, score in sorted_results]

    penalised = apply_quality_penalty(
        chunks=[doc for doc, _ in base_results],
        base_scores=[score for _, score in base_results],
    )

    reranked_docs = flashrank_rerank(query, [doc for doc, _ in penalised[:candidate_k]], k=top_n)
    reranked_set = {doc.metadata.get("chunk_id"): doc for doc in reranked_docs}
    if reranked_set:
        return [
            (reranked_set.get(doc.metadata.get("chunk_id"), doc), score)
            for doc, score in penalised
            if doc.metadata.get("chunk_id") in reranked_set
        ][:top_n]
    return penalised[:top_n]


def expand_with_neighbors(
    results: list[tuple[Document, float]],
    chunks: list[Document],
    window: int = 1,
) -> list[Document]:
    """Original expand — returns list[Document] without scores."""
    id_to_doc = {
        doc.metadata["chunk_id"]: doc
        for doc in chunks
        if doc.metadata.get("chunk_id") is not None
    }
    expanded_ids: list[int] = []

    for doc, _ in results:
        cid = doc.metadata.get("chunk_id")
        if cid is None:
            continue
        for neighbor_id in range(cid - window, cid + window + 1):
            if neighbor_id in id_to_doc:
                expanded_ids.append(neighbor_id)

    seen: set[int] = set()
    expanded_docs: list[Document] = []
    for cid in expanded_ids:
        if cid not in seen:
            expanded_docs.append(id_to_doc[cid])
            seen.add(cid)

    return expanded_docs


def expand_with_neighbors_scored(
    results: list[tuple[Document, float]],
    chunks: list[Document],
    window: int = 1,
) -> list[tuple[Document, float]]:
    """Like expand_with_neighbors but returns (doc, score) tuples.
    Neighbors inherit the score of the retrieved doc that pulled them in.
    Directly-retrieved docs keep their own score. Order is preserved and
    de-duplicated (first occurrence / highest-priority anchor wins).
    """
    id_to_doc = {
        doc.metadata["chunk_id"]: doc
        for doc in chunks
        if doc.metadata.get("chunk_id") is not None
    }
    seen: set = set()
    expanded: list[tuple[Document, float]] = []

    for doc, score in results:
        cid = doc.metadata.get("chunk_id")
        if cid is None:
            continue
        for neighbor_id in range(cid - window, cid + window + 1):
            if neighbor_id in id_to_doc and neighbor_id not in seen:
                expanded.append((id_to_doc[neighbor_id], score))
                seen.add(neighbor_id)

    return expanded


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🚀 STARTING: VECTOR STORE & HYBRID SEARCH")
    print("=" * 50)

    all_passed = [c for c in load_passed_chunks() if c.page_content.strip()]
    print(f"📥 Found {len(all_passed)} chunks to index.")

    if all_passed:
        vs, bm = build_hybrid_indices(all_passed)
        test_query = input("\nEnter a test query: ")
        results = hybrid_retrieve(test_query, vs, bm, all_passed)
        for i, (doc, score) in enumerate(results, 1):
            print(f"\n[{i}] RRF Score: {score:.4f} | Page: {doc.metadata.get('page')}")
            print(f"Content: {doc.page_content[:150]}...")
    else:
        print("❌ Build stopped: No data loaded.")