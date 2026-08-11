"""Routes an upload to parser tiers by extension, escalating on poor output.

The ordering encodes a cost decision: free local extraction is attempted first
wherever it can work, and a paid vendor is only reached when the local result
actually fails the quality check. That keeps the common case (a digital-native
PDF) at zero marginal cost, while a scanned one still gets OCR.

`.csv` deliberately has a single tier. It is already flat, machine-readable
text — sending it to an OCR service would be slower, cost money, and risk
misreading values that were never ambiguous.
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

from APP.parsers.adapters import (
    AzureDocumentIntelligenceParser,
    LocalCsvParser,
    LocalPdfParser,
    LocalTextParser,
    MistralOcrParser,
)
from APP.parsers.base import DocumentParser, ParseResult, is_extraction_acceptable

logger = logging.getLogger("rag_api.parsers")

_local_pdf = LocalPdfParser()
_local_text = LocalTextParser()
_local_csv = LocalCsvParser()
_azure_di = AzureDocumentIntelligenceParser()
_mistral = MistralOcrParser()

# Extension -> ordered tiers. First that is available AND returns acceptable
# output wins; otherwise the next is tried.
ROUTING: dict[str, tuple[DocumentParser, ...]] = {
    ".pdf":   (_local_pdf, _azure_di, _mistral),
    ".txt":   (_local_text,),
    ".md":    (_local_text,),
    ".markdown": (_local_text,),
    ".json":  (_local_text,),
    ".log":   (_local_text,),
    ".csv":   (_local_csv,),          # never leaves the process, by design
    ".docx":  (_azure_di,),
    ".pptx":  (_azure_di,),
    ".xlsx":  (_azure_di,),
    ".png":   (_azure_di, _mistral),
    ".jpg":   (_mistral, _azure_di),
    ".jpeg":  (_mistral, _azure_di),
    ".tiff":  (_azure_di,),
    ".bmp":   (_azure_di,),
    ".heif":  (_azure_di,),
    ".webp":  (_mistral,),            # no Azure support for webp, at all
}

SUPPORTED_EXTENSIONS = tuple(sorted(ROUTING))


def parse_document(raw_bytes: bytes, filename: str, extension: str | None = None) -> ParseResult:
    """Extracts text, escalating through tiers until output is acceptable.

    Raises ValueError when the format is unsupported, or when every configured
    tier produced unusable output — the caller turns that into a 400 rather
    than indexing an empty document, which would otherwise look like a
    successful upload that answers nothing.
    """
    suffix = (extension or "").lower() or _suffix_of(filename)
    tiers = ROUTING.get(suffix)
    if not tiers:
        raise ValueError(
            f"Unsupported file type '{suffix or filename}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    attempted: list[str] = []
    last_error: Exception | None = None
    best: tuple[list[Document], str] | None = None

    for parser in tiers:
        if not parser.is_available():
            logger.info("parser_skipped parser=%s reason=not_configured", parser.name)
            continue

        attempted.append(parser.name)
        try:
            documents = parser.parse(raw_bytes, filename)
        except Exception as exc:  # noqa: BLE001 — try the next tier instead
            last_error = exc
            logger.warning("parser_failed parser=%s error=%s", parser.name, exc)
            continue

        if is_extraction_acceptable(documents):
            # Keyed on how many tiers were actually *attempted*, not on the
            # position in the table: a tier skipped for missing credentials was
            # never tried, so counting it would report a fallback (and imply a
            # paid tier was reached) when none occurred.
            return ParseResult(documents=documents, parser=parser.name, fallback_used=len(attempted) > 1)

        # Keep the best-effort output: if every tier is mediocre, returning
        # the longest attempt beats returning nothing.
        if documents and (best is None or _total_chars(documents) > _total_chars(best[0])):
            best = (documents, parser.name)
        logger.info("parser_output_below_threshold parser=%s", parser.name)

    if best is not None:
        documents, name = best
        logger.warning("parser_accepted_low_quality parser=%s", name)
        return ParseResult(documents=documents, parser=name, fallback_used=True)

    detail = f"tried: {', '.join(attempted)}" if attempted else "no parser configured for this type"
    if last_error is not None:
        detail += f"; last error: {last_error}"
    raise ValueError(f"No text could be extracted from {filename} ({detail})")


def _suffix_of(filename: str) -> str:
    _, _, ext = filename.rpartition(".")
    return f".{ext.lower()}" if ext and ext != filename else ""


def _total_chars(documents: list[Document]) -> int:
    return sum(len(d.page_content) for d in documents)
