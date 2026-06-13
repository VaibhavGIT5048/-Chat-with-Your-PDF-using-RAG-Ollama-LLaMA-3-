from __future__ import annotations

import json
import os
import pickle
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from langchain_core.documents import Document
from qdrant_client import QdrantClient

from APP.chunking import chunk_documents, save_chunks_jsonl
from APP.embedding import load_embedding_model
from APP.generator import SYSTEM_PROMPT
from APP.pdf_loading import load_pdf
from APP.quality_gate import apply_quality_gate, save_chunks_jsonl as save_processed_jsonl
from APP.schemas import HealthStatus, IngestResponse, QueryRequest, QueryResponse, SourceChunk, CollectionInfo
from APP.vector_store import (
    QdrantVectorStore,
    build_hybrid_indices,
    expand_with_neighbors_scored,
    hybrid_retrieve,
)


@dataclass(slots=True)
class BackendSettings:
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "chunks_collection")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_GENERATOR_MODEL", "qwen3:8b")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "qllama/bge-small-en-v1.5:latest")


class RAGService:
    def __init__(self, settings: BackendSettings | None = None):
        self.settings = settings or BackendSettings()
        self.qdrant = QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key)
        self.embedding_adapter = load_embedding_model(self.settings.embedding_model)
        self._cached_chunks: list[Document] = []
        self._cached_bm25 = None
        self._cached_vectorstore = None

    def collection_exists(self, name: str | None = None) -> bool:
        collection_name = name or self.settings.qdrant_collection
        try:
            collections = self.qdrant.get_collections().collections
            return any(getattr(c, "name", None) == collection_name for c in collections)
        except Exception:
            return False

    def list_collections(self) -> list[CollectionInfo]:
        collections = []
        try:
            response = self.qdrant.get_collections().collections
            for col in response:
                info = getattr(col, "name", None)
                if not info:
                    continue
                vectors_count = None
                status = None
                try:
                    details = self.qdrant.get_collection(info)
                    vectors_count = getattr(details, "vectors_count", None)
                    status = getattr(details, "status", None)
                except Exception:
                    pass
                collections.append(CollectionInfo(name=info, vectors_count=vectors_count, status=status))
        except Exception:
            return []
        return collections

    def delete_collection(self, name: str) -> None:
        self.qdrant.delete_collection(name)
        if name == self.settings.qdrant_collection:
            self._cached_vectorstore = None
            self._cached_bm25 = None
            self._cached_chunks = []

    def _load_upload_to_docs(self, filename: str, raw_bytes: bytes) -> list[Document]:
        suffix = Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)

        try:
            if suffix == ".pdf":
                pages = load_pdf(tmp_path)
                docs = []
                for p in pages:
                    metadata = dict(p.metadata)
                    metadata["source"] = filename  # override temp path with real name
                    docs.append(Document(page_content=p.page_content, metadata=metadata))
                return docs

            text = raw_bytes.decode("utf-8", errors="ignore").strip()
            if not text:
                return []

            return [Document(page_content=text, metadata={"source": filename, "page": 1, "id": str(uuid4())})]
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def ingest(self, filename: str, raw_bytes: bytes, chunk_size: int, chunk_overlap: int, quality_threshold: float) -> IngestResponse:
        docs = self._load_upload_to_docs(filename, raw_bytes)
        if not docs:
            raise ValueError(f"No text could be extracted from {filename}")

        chunks = chunk_documents(docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        Path("chunks").mkdir(parents=True, exist_ok=True)
        save_chunks_jsonl(chunks, "chunks/chunks.jsonl")

        processed_chunks = apply_quality_gate(chunks, threshold_score=quality_threshold)
        save_processed_jsonl(processed_chunks, "chunks/chunks_processed.jsonl")
        passed_chunks = [c for c in processed_chunks if c.metadata.get("passed_gate") is True]
        retrieval_chunks = [c for c in processed_chunks if c.page_content.strip()]

        if not retrieval_chunks:
            raise RuntimeError("No retrievable chunks were produced. Inspect document extraction quality.")

        vectorstore, bm25 = build_hybrid_indices(retrieval_chunks)
        self._cached_vectorstore = vectorstore
        self._cached_bm25 = bm25
        self._cached_chunks = retrieval_chunks

        stats = IngestResponse(
            request_id=str(uuid4()),
            collection_name=self.settings.qdrant_collection,
            filename=filename,
            file_type=Path(filename).suffix.lstrip(".").lower() or "unknown",
            pdfs=1 if Path(filename).suffix.lower() == ".pdf" else None,
            pages=len(docs),
            chunks=len(chunks),
            passed_chunks=len(passed_chunks),
            dropped_chunks=len(chunks) - len(passed_chunks),
            indexed_chunks=len(retrieval_chunks),
        )
        return stats

    def _load_cached_artifacts(self) -> tuple[QdrantVectorStore, Any, list[Document]]:
        if self._cached_vectorstore is not None and self._cached_bm25 is not None and self._cached_chunks:
            return self._cached_vectorstore, self._cached_bm25, self._cached_chunks

        bm25_path = Path("indexes/bm25_data.pkl")
        if not bm25_path.exists():
            raise FileNotFoundError("BM25 artifacts not found. Run /ingest first.")

        with open(bm25_path, "rb") as f:
            data = pickle.load(f)
            bm25, chunks = data["bm25"], data["chunks"]

        vectorstore = QdrantVectorStore(
            client=self.qdrant,
            collection_name=self.settings.qdrant_collection,
            embeddings=self.embedding_adapter,
        )
        self._cached_vectorstore = vectorstore
        self._cached_bm25 = bm25
        self._cached_chunks = chunks
        return vectorstore, bm25, chunks

    def answer(self, request: QueryRequest) -> QueryResponse:
        vectorstore, bm25, chunks = self._load_cached_artifacts()

        top_n = getattr(request, "top_k", None) or 5

        results = hybrid_retrieve(
            query=request.question,
            vectorstore=vectorstore,
            bm25=bm25,
            chunks=chunks,
            top_n=top_n,
        )

        # (A) expanded docs WITH scores — same set feeds prompt AND sources
        expanded = expand_with_neighbors_scored(results=results, chunks=chunks, window=1)

        contexts = []
        for doc, _ in expanded:
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", "?")
            contexts.append(f"[Source: {source} | Page: {page}] {doc.page_content}")

        context_blob = "\n\n".join(contexts)
        prompt = self._build_prompt(request.question, context_blob)
        answer = self._generate_answer(prompt)

        sources = [
            SourceChunk(
                chunk_id=doc.metadata.get("chunk_id"),
                source=doc.metadata.get("source", "unknown"),
                page=doc.metadata.get("page"),
                score=score,
                content=doc.page_content,
            )
            for doc, score in expanded
        ]
        return QueryResponse(
            request_id=str(uuid4()),
            answer=answer,
            sources=sources,
            model=self.settings.ollama_model,
            collection_name=self.settings.qdrant_collection,
        )

    def health(self) -> HealthStatus:
        qdrant_status = "down"
        ollama_status = "down"
        try:
            self.qdrant.get_collections()
            qdrant_status = "up"
        except Exception:
            qdrant_status = "down"

        model_names = self._list_ollama_models()
        ollama_status = "up" if self.settings.ollama_model in model_names else "down"

        return HealthStatus(
            status="ok" if qdrant_status == "up" and ollama_status == "up" else "degraded",
            service="rag-api",
            qdrant=qdrant_status,
            ollama=ollama_status,
            collection_name=self.settings.qdrant_collection,
        )

    @staticmethod
    def _build_prompt(question: str, context_blob: str) -> str:
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"CONTEXT:\n{context_blob}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"ANSWER:\n"
        )

    def _list_ollama_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.settings.ollama_url}/api/tags")
                response.raise_for_status()
        except Exception:
            return []

        payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        names = []
        for item in models:
            if isinstance(item, dict):
                name = item.get("model") or item.get("name")
                if name:
                    names.append(name)
        return names

    def _generate_answer(self, prompt: str) -> str:
        payload = {
            "model": self.settings.ollama_model,
            "think": False,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 512},
        }
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{self.settings.ollama_url}/api/generate", json=payload)
            response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data.get("response", "")
        return str(data)