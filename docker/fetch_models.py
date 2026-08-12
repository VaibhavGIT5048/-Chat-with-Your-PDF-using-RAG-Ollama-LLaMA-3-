"""Downloads the model weights that get baked into the API image.

Runs in its own build stage, and this file is the ONLY input to that stage's
cache key. That is the point: the download sits behind neither
requirements-api.txt nor the application code, so dependency bumps and code
edits leave the ~2.3GB layer untouched. Editing this file — a new revision, a
different pattern — is what invalidates it.

Without this, the weights are fetched at runtime instead, into a container
directory that does not survive scale-to-zero. Every cold start then
re-downloads multiple gigabytes before the first question can be answered.

Deliberately depends on huggingface_hub alone (no torch, no
sentence-transformers), so the stage stays small and independent.
"""

from __future__ import annotations

import os
import sys

from huggingface_hub import snapshot_download

TARGET = os.environ.get("MODEL_DIR", "/opt/models")

# Pinned by commit sha, never a floating tag: a tag can be moved to point at
# different weights later, which would both break the layer cache silently and
# mean the image ships something other than what was reviewed.
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"

# BAAI/bge-m3 ships PyTorch weights (~2.3GB) AND a full ONNX copy (~2.2GB)
# alongside README images. Pulling the repo wholesale costs ~5GB for a runtime
# that loads exactly one of those. sentence-transformers on the torch backend
# needs the files below and nothing else.
#
# Adding the ONNX backend later (EMBEDDING_BACKEND=onnx) means adding
# "onnx/*" here — at ~2.2GB more image, so validate the speedup on staging
# first, per the note in APP/providers/embedding.py.
BGE_M3_ALLOW = [
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
    "pytorch_model.bin",
    # modules.json declares three modules: the transformer at the repo root,
    # 1_Pooling, and 2_Normalize. Normalize is parameterless so this revision
    # ships no files for it and the pattern matches nothing — kept anyway, so a
    # future revision that does ship a config doesn't silently load without it.
    "1_Pooling/*",
    "2_Normalize/*",
]


def main() -> int:
    # local_dir, not cache_dir. The hub cache is keyed by revision and resolves
    # a repo id through refs/main -> sha; downloading a pinned sha never writes
    # that ref, so an offline load of "BAAI/bge-m3" has nothing to resolve and
    # fails even though the weights are right there. A plain directory sidesteps
    # the whole mechanism: sentence-transformers loads a filesystem path
    # directly, with no hub lookup, no refs, and no offline flags to get right.
    # BGE_MODEL_NAME is set to this path in the image.
    bge_dir = os.path.join(TARGET, "bge-m3")
    os.makedirs(bge_dir, exist_ok=True)

    print(f"↓ BAAI/bge-m3 @ {BGE_M3_REVISION[:12]} -> {bge_dir}", flush=True)
    snapshot_download(
        repo_id="BAAI/bge-m3",
        revision=BGE_M3_REVISION,
        allow_patterns=BGE_M3_ALLOW,
        local_dir=bge_dir,
    )

    # FlashRank fetches its ranker on first construction. Doing it here means
    # the reranker is present in the image too, rather than downloading during
    # the first query after a wake.
    flashrank_dir = os.path.join(TARGET, "flashrank")
    os.makedirs(flashrank_dir, exist_ok=True)
    try:
        from flashrank import Ranker

        print(f"↓ flashrank default ranker -> {flashrank_dir}", flush=True)
        Ranker(cache_dir=flashrank_dir)
    except Exception as exc:
        # Not fatal to the build: the app already falls back to unranked
        # retrieval when flashrank is unavailable, and a runtime download still
        # works. Loud so a silently-missing bake gets noticed.
        print(f"⚠️  flashrank prefetch failed ({exc}) — it will download at runtime", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
