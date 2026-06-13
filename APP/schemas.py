from __future__ import annotations

from pydantic import BaseModel, Field


class SourceChunk(BaseModel):
    chunk_id: int | str | None = None
    source: str = "unknown"
    page: int | str | None = None
    score: float | None = None
    content: str


class IngestResponse(BaseModel):
    request_id: str
    collection_name: str
    filename: str
    file_type: str
    pdfs: int | None = None
    pages: int = 0
    chunks: int = 0
    passed_chunks: int = 0
    dropped_chunks: int = 0
    indexed_chunks: int = 0


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=20)


class QueryResponse(BaseModel):
    request_id: str
    answer: str
    sources: list[SourceChunk] = Field(default_factory=list)
    model: str
    collection_name: str


class HealthStatus(BaseModel):
    status: str
    service: str
    qdrant: str
    ollama: str
    collection_name: str | None = None


class CollectionInfo(BaseModel):
    name: str
    vectors_count: int | None = None
    status: str | None = None
