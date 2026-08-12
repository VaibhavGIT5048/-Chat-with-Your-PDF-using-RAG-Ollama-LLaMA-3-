"""Two-tier cache for a document's retrieval artifacts (BM25 index + chunks).

Without it, every /query re-reads that document's bm25.pkl from the Azure Files
share before retrieval can start — an SMB round trip on the hot path of every
single question, for a file that only changes when the document is re-ingested.

Two tiers, because they fail differently:

  1. in-process   — no serialisation, no network, but empty after every
                    scale-to-zero (the app runs at minReplicas=0)
  2. Redis        — survives that, at the cost of a network hop

Azure Files remains the source of truth and the only writer; both tiers are
strictly optional accelerators, and everything still works with neither.

Keys are namespaced by owner_id. A document belongs to exactly one account, so a
key that omitted the owner would be a way to serve one user's index to another.
"""

from __future__ import annotations

import os
import pickle
import threading
from collections import OrderedDict
from typing import Any

import structlog

logger = structlog.get_logger("rag_cache")

# Entries are a BM25 index plus every chunk of a document, so a handful is
# already a lot of memory. The container runs with 4GB and one replica; this is
# a hot-set, not a store.
MAX_LOCAL_ENTRIES = int(os.getenv("DOC_CACHE_LOCAL_ENTRIES", "4"))

# Above this, skip Redis and let Azure Files serve it. A big document would
# otherwise blow past the free tier's per-request size limit, and the failure
# would land on the query path.
MAX_REDIS_BYTES = int(os.getenv("DOC_CACHE_MAX_REDIS_BYTES", str(8 * 1024 * 1024)))

REDIS_TTL_SECONDS = int(os.getenv("DOC_CACHE_TTL_SECONDS", str(24 * 60 * 60)))

_local: "OrderedDict[str, Any]" = OrderedDict()
_local_lock = threading.Lock()

_redis_client = None
_redis_ready = False
_redis_lock = threading.Lock()


def _key(owner_id: str, document_id: str) -> str:
    return f"doc:{owner_id}:{document_id}"


def _get_redis():
    """Connects lazily, once. Returns None whenever Redis is unavailable —
    unconfigured locally, unreachable, or the client library missing — so the
    caller falls through to disk instead of failing the request.
    """
    global _redis_client, _redis_ready
    if _redis_ready:
        return _redis_client

    with _redis_lock:
        if _redis_ready:
            return _redis_client
        _redis_ready = True

        url = os.getenv("REDIS_URL", "").strip()
        if not url:
            logger.info("doc_cache_redis_disabled", reason="REDIS_URL unset")
            _redis_client = None
            return None

        try:
            import redis

            client = redis.Redis.from_url(
                url,
                socket_timeout=2,
                socket_connect_timeout=2,
                # A cache must never become a way to fail a query: a slow or
                # dead Redis should degrade to the disk path, not raise.
                retry_on_timeout=False,
                health_check_interval=30,
            )
            client.ping()
            _redis_client = client
            logger.info("doc_cache_redis_connected")
        except Exception as exc:
            logger.warning("doc_cache_redis_unavailable", error=str(exc))
            _redis_client = None
        return _redis_client


def get(owner_id: str, document_id: str) -> Any | None:
    """Returns the cached artifacts, or None to load from disk."""
    key = _key(owner_id, document_id)

    with _local_lock:
        if key in _local:
            _local.move_to_end(key)
            return _local[key]

    client = _get_redis()
    if client is None:
        return None

    try:
        blob = client.get(key)
    except Exception as exc:
        logger.warning("doc_cache_redis_get_failed", error=str(exc))
        return None
    if not blob:
        return None

    try:
        value = pickle.loads(blob)
    except Exception as exc:
        # A corrupt or stale-format entry is not worth failing a query over.
        logger.warning("doc_cache_unpickle_failed", error=str(exc))
        try:
            client.delete(key)
        except Exception:
            pass
        return None

    _put_local(key, value)
    return value


def put(owner_id: str, document_id: str, value: Any) -> None:
    key = _key(owner_id, document_id)
    _put_local(key, value)

    client = _get_redis()
    if client is None:
        return

    try:
        blob = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        logger.warning("doc_cache_pickle_failed", error=str(exc))
        return

    if len(blob) > MAX_REDIS_BYTES:
        logger.info("doc_cache_too_large_for_redis", bytes=len(blob))
        return

    try:
        client.set(key, blob, ex=REDIS_TTL_SECONDS)
    except Exception as exc:
        logger.warning("doc_cache_redis_set_failed", error=str(exc))


def invalidate(owner_id: str, document_id: str) -> None:
    """Must be called on re-ingest and on delete. A document re-ingested under
    the same id gets new chunks and a new BM25 index; without this the old ones
    would keep answering questions about content that has changed.
    """
    key = _key(owner_id, document_id)
    with _local_lock:
        _local.pop(key, None)

    client = _get_redis()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception as exc:
        logger.warning("doc_cache_redis_delete_failed", error=str(exc))


def _put_local(key: str, value: Any) -> None:
    with _local_lock:
        _local[key] = value
        _local.move_to_end(key)
        while len(_local) > MAX_LOCAL_ENTRIES:
            _local.popitem(last=False)
