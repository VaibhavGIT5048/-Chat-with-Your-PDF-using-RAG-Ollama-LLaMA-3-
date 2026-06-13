from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import uuid4

import structlog
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from APP.api_service import RAGService
from APP.schemas import CollectionInfo, HealthStatus, IngestResponse, QueryRequest, QueryResponse


structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger("rag_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    service = RAGService()
    app.state.rag_service = service
    app.state.collection_exists = service.collection_exists()
    logger.info(
        "startup_complete",
        collection_name=service.settings.qdrant_collection,
        collection_exists=app.state.collection_exists,
    )
    try:
        yield
    finally:
        pass  # httpx clients are context-managed, nothing to close
        logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local RAG API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        start = time.perf_counter()
        request.state.request_id = request_id
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = getattr(response, "status_code", 500)
            if response is not None:
                response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_complete",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        logger.warning(
            "http_exception",
            request_id=request_id,
            status_code=exc.status_code,
            detail=str(exc.detail),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "request_id": request_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        logger.exception("unhandled_exception", request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    def get_service(request: Request) -> RAGService:
        service = getattr(request.app.state, "rag_service", None)
        if service is None:
            service = RAGService()
            request.app.state.rag_service = service
            request.app.state.collection_exists = service.collection_exists()
        return service

    @app.get("/health", response_model=HealthStatus)
    async def health(request: Request) -> HealthStatus:
        service = get_service(request)
        return service.health()

    @app.get("/ready", response_model=HealthStatus)
    async def ready(request: Request) -> HealthStatus:
        service = get_service(request)
        status = service.health()
        if status.qdrant != "up" or status.ollama != "up":
            raise HTTPException(status_code=503, detail=status.model_dump())
        return status

    @app.post("/ingest", response_model=IngestResponse)
    async def ingest(
        request: Request,
        file: UploadFile = File(...),
        chunk_size: int = Form(1000),
        chunk_overlap: int = Form(150),
        quality_threshold: float = Form(4.0),
    ) -> IngestResponse:
        service = get_service(request)
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        try:
            response = service.ingest(
                filename=file.filename or "upload",
                raw_bytes=payload,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                quality_threshold=quality_threshold,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return response.model_copy(update={"request_id": getattr(request.state, "request_id", response.request_id)})

    @app.post("/query", response_model=QueryResponse)
    async def query(request: Request, payload: QueryRequest) -> QueryResponse:
        service = get_service(request)
        try:
            response = service.answer(payload)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return response.model_copy(update={"request_id": getattr(request.state, "request_id", response.request_id)})

    @app.get("/collections", response_model=list[CollectionInfo])
    async def list_collections(request: Request) -> list[CollectionInfo]:
        service = get_service(request)
        return service.list_collections()

    @app.delete("/collections/{name}")
    async def delete_collection(request: Request, name: str):
        service = get_service(request)
        try:
            service.delete_collection(name)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"deleted": name, "request_id": getattr(request.state, "request_id", str(uuid4()))}

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("APP.main:app", host="0.0.0.0", port=8000, reload=False)