"""Parser interface and the extraction-quality check that drives fallback.

Every adapter returns `list[Document]` with `source`/`page` metadata, because
citations depend on page numbers and the chunker groups by page.

Adapters must not raise for "this vendor isn't configured" — that is a routing
decision, not an error. `is_available()` reports it so the router can skip to
the next tier without exception handling as control flow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_core.documents import Document

# Below this many characters per page, extraction is treated as failed and the
# next tier is tried. A scanned page with no text layer typically yields a
# handful of stray characters rather than nothing at all, so "empty" is the
# wrong test.
MIN_CHARS_PER_PAGE = 120

# Proportion of characters that must be printable text. Failed OCR and binary
# leakage produce high ratios of control bytes and replacement characters.
MIN_PRINTABLE_RATIO = 0.80

_PRINTABLE = re.compile(r"[^\x20-\x7e -￿\s]")


@dataclass
class ParseResult:
    documents: list[Document]
    parser: str          # which adapter produced this, surfaced to the user
    fallback_used: bool = False


class DocumentParser:
    """One extraction backend."""

    name: str = "base"
    #: Extensions this adapter can handle, lowercase and dot-prefixed.
    extensions: tuple[str, ...] = ()

    def is_available(self) -> bool:
        """False when credentials or dependencies are absent. The router skips
        unavailable parsers silently — a missing vendor key is a configuration
        state, not a failure."""
        return True

    def parse(self, raw_bytes: bytes, filename: str) -> list[Document]:
        raise NotImplementedError


def extraction_quality(documents: list[Document]) -> float:
    """Rough 0..1 score for whether extraction actually worked.

    Two failure modes matter: a scanned PDF with no text layer (almost no
    characters), and OCR that returned mojibake (characters, but not text).
    A pure length check misses the second, so this weighs both.
    """
    if not documents:
        return 0.0

    total_chars = sum(len(d.page_content) for d in documents)
    if total_chars == 0:
        return 0.0

    avg_chars = total_chars / len(documents)
    density = min(avg_chars / MIN_CHARS_PER_PAGE, 1.0)

    joined = "".join(d.page_content for d in documents)
    junk = len(_PRINTABLE.findall(joined))
    printable_ratio = 1.0 - (junk / max(len(joined), 1))

    if printable_ratio < MIN_PRINTABLE_RATIO:
        return 0.0

    return density * printable_ratio


def is_extraction_acceptable(documents: list[Document]) -> bool:
    return extraction_quality(documents) >= 0.5
