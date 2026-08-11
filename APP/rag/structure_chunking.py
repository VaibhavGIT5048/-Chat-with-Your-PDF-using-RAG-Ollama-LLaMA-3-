"""Structure-aware chunking: split on document headings, not on character
count or sentence-embedding distance.

Why this exists: semantic chunking has to embed every sentence to find topic
breakpoints, which on a self-hosted CPU model dominates ingest time (measured
~6 of 7.5 minutes on a 44-page PDF). A document's own headings already mark
topic boundaries — the author put them there — so reading them costs nothing
and needs no model at all.

Forward-compatible with Phase 3 on purpose: Azure Document Intelligence's
Layout model returns markdown with real `#` headings, and this detects those
first. Until that lands we're working from pdfplumber's plain text, so the
heuristics below infer headings from typography-in-text conventions instead.
Once the parser router supplies markdown, the heuristic path stops firing on
its own — no rewrite needed.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document

# A markdown ATX heading — what Document Intelligence Layout emits (Phase 3).
MD_HEADING = re.compile(r"^(#{1,6})\s+(\S.*)$")

# "1.", "2.3", "IV." style section numbering at line start.
NUMBERED_HEADING = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+(\S.{0,90})$")

# Lines this long are prose, not headings, regardless of other signals.
MAX_HEADING_CHARS = 90
# Below this, an ALL-CAPS line is more likely an acronym or label than a heading.
MIN_HEADING_CHARS = 3

_SENTENCE_END = (".", "!", "?", ",", ";", ":")

# A real heading doesn't trail off on a function word. Cover pages wrap long
# titles across lines ("Travel and Tourism at a" / "Turning Point: Principles"
# / "for Transformative Growth"), and without this each fragment reads as its
# own Title Case heading and shatters the document into stubs.
_DANGLING_WORDS = {
    "a", "an", "the", "and", "or", "but", "for", "nor", "so", "yet",
    "of", "to", "in", "on", "at", "by", "with", "from", "as", "into",
    "over", "under", "between", "through", "during", "per", "via", "is", "are",
}

# A heading whose body is shorter than this isn't a section — it's a caption,
# a stray label, or one line of a wrapped title. Merged into its neighbour.
MIN_SECTION_CHARS = 200

# Trailing page number, as printed in a table of contents ("Foreword 3") or a
# running header ("Travel and Tourism at a Turning Point 3").
TRAILING_PAGE_NUM = re.compile(r"^(.*?\S)\s+\d{1,4}$")

# A wrapped title spans two or three lines, not twenty. Without a cap, a whole
# table-of-contents page collapses into one 200-character "heading".
MAX_MERGED_HEADING_LINES = 3
MAX_MERGED_HEADING_CHARS = 120

# A line repeated on at least this share of pages is a running header/footer
# (the document's own title, printed on every page), never a section heading.
BOILERPLATE_PAGE_RATIO = 0.25
BOILERPLATE_MIN_PAGES = 3


def _strip_trailing_page_number(line: str) -> str:
    """'Foreword 3' -> 'Foreword'. Left alone when only one word precedes the
    number, so genuine headings like 'Chapter 3' or 'Article 7' survive.
    """
    match = TRAILING_PAGE_NUM.match(line)
    if not match:
        return line
    head = match.group(1)
    return head if len(head.split()) >= 2 else line


def _detect_boilerplate(documents: list[Document]) -> set[str]:
    """Lines appearing on a large fraction of pages — running headers/footers.

    These are the single biggest source of junk section labels: a report prints
    its own title at the top of all 44 pages, and every one of those reads as a
    Title Case heading, so the document appears to restart constantly.
    """
    if len(documents) < BOILERPLATE_MIN_PAGES:
        return set()

    # Count the page-number-stripped form: a running header carries the page
    # number ("...Growth 3", "...Growth 4"), so counting raw lines finds no
    # repeats at all and the header slips through onto every page.
    counts: dict[str, int] = {}
    for doc in documents:
        seen_on_page = {
            _strip_trailing_page_number(l.strip())
            for l in doc.page_content.splitlines()
            if l.strip()
        }
        for line in seen_on_page:
            counts[line] = counts.get(line, 0) + 1

    threshold = max(BOILERPLATE_MIN_PAGES, int(len(documents) * BOILERPLATE_PAGE_RATIO))
    return {line for line, n in counts.items() if n >= threshold}


def _is_heading(line: str, boilerplate: set[str] | None = None) -> tuple[bool, str | None]:
    """Returns (is_heading, heading_text). Ordered most-reliable first."""
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_CHARS or len(stripped) < MIN_HEADING_CHARS:
        return False, None

    md = MD_HEADING.match(stripped)
    if md:
        return True, md.group(2).strip()

    # Running headers/footers repeat on most pages; they mark no boundary.
    if boilerplate and (stripped in boilerplate or _strip_trailing_page_number(stripped) in boilerplate):
        return False, None

    # Drop a table-of-contents page number so 'Foreword 3' labels as 'Foreword'.
    stripped = _strip_trailing_page_number(stripped)
    if len(stripped) < MIN_HEADING_CHARS:
        return False, None

    # Prose ends in punctuation; headings generally don't.
    if stripped.endswith(_SENTENCE_END):
        return False, None

    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False, None

    if NUMBERED_HEADING.match(stripped):
        return True, stripped

    # ALL CAPS ("EXECUTIVE SUMMARY")
    if all(c.isupper() for c in letters):
        return True, stripped

    # Title Case ("Global Risks Outlook") — most words capitalised, few words.
    words = stripped.split()
    if 1 < len(words) <= 12:
        # Trailing function word means this is a wrapped line, not a heading.
        if words[-1].strip(",.;:").lower() in _DANGLING_WORDS:
            return False, None
        significant = [w for w in words if len(w) > 3]
        if significant and sum(1 for w in significant if w[0].isupper()) / len(significant) >= 0.8:
            return True, stripped

    return False, None


def _merge_small_sections(sections: list[Document]) -> list[Document]:
    """Folds undersized sections into the next one (or the previous, if last).

    Heading detection on plain text inevitably fires on captions, dates and
    cover-page fragments. Rather than tightening the heuristics until they're
    brittle, let them over-fire and repair it here: anything without a real
    body gets absorbed, so its text survives inside a neighbouring chunk
    instead of becoming a 3-character chunk of its own.
    """
    if not sections:
        return sections

    merged: list[Document] = []
    carry: Document | None = None

    for section in sections:
        if carry is not None:
            section = Document(
                page_content=f"{carry.page_content}\n{section.page_content}".strip(),
                # Keep the LATER section's metadata: its heading is the one
                # with actual content beneath it, so it's the better label.
                metadata=dict(section.metadata),
            )
            carry = None

        if len(section.page_content) < MIN_SECTION_CHARS:
            carry = section
            continue
        merged.append(section)

    if carry is not None:
        if merged:
            tail = merged[-1]
            merged[-1] = Document(
                page_content=f"{tail.page_content}\n{carry.page_content}".strip(),
                metadata=dict(tail.metadata),
            )
        else:
            merged.append(carry)

    return merged


def split_into_sections(documents: list[Document]) -> list[Document]:
    """Groups each page's lines under the heading that precedes them.

    Pages are processed in order and the current heading carries across page
    boundaries, since a section rarely ends where a page does. Each emitted
    Document keeps its own page's metadata — page numbers drive citations, so
    they must not be flattened away — plus a `section` field.
    """
    boilerplate = _detect_boilerplate(documents)

    sections: list[Document] = []
    current_heading: str | None = None
    heading_lines = 0
    buffer: list[str] = []
    buffer_meta: dict | None = None
    buffer_has_body = False

    def flush() -> None:
        nonlocal buffer, buffer_meta, buffer_has_body
        if not buffer or buffer_meta is None:
            buffer = []
            buffer_has_body = False
            return
        body = "\n".join(buffer).strip()
        if body:
            meta = dict(buffer_meta)
            if current_heading:
                meta["section"] = current_heading
            sections.append(Document(page_content=body, metadata=meta))
        buffer = []
        buffer_has_body = False

    for doc in documents:
        for line in doc.page_content.splitlines():
            is_head, heading_text = _is_heading(line, boilerplate)
            if is_head:
                can_merge = (
                    heading_lines < MAX_MERGED_HEADING_LINES
                    and len(current_heading or "") < MAX_MERGED_HEADING_CHARS
                )
                if buffer_has_body or not can_merge:
                    # `not can_merge` matters on table-of-contents pages: every
                    # line there looks like a heading, and without the cap they
                    # all merge into one enormous meaningless label.
                    flush()
                    current_heading = heading_text
                    heading_lines = 1
                    buffer_meta = dict(doc.metadata)
                    # Keep the heading in the body: strong retrieval signal, and
                    # it gives the LLM the section name inline with the content.
                    buffer = [line.strip()]
                else:
                    # Back-to-back headings with nothing between them are one
                    # title wrapped across lines, not separate sections.
                    current_heading = f"{current_heading} {heading_text}".strip() if current_heading else heading_text
                    heading_lines += 1
                    if buffer_meta is None:
                        buffer_meta = dict(doc.metadata)
                    buffer.append(line.strip())
            else:
                if buffer_meta is None:
                    buffer_meta = dict(doc.metadata)
                buffer.append(line)
                if line.strip():
                    buffer_has_body = True
        # Page boundary: flush so the chunk keeps THIS page's number, then
        # continue the same section on the next page.
        flush()
        buffer_meta = None

    flush()
    return _merge_small_sections(sections)


def structure_aware_split(
    documents: list[Document],
    chunk_size: int,
    chunk_overlap: int,
    recursive_splitter_factory,
) -> list[Document]:
    """Sections first; anything still oversized falls back to the recursive
    splitter *within* that section, so a long section degrades to fixed-size
    chunks rather than being emitted as one unwieldy blob.
    """
    sections = split_into_sections(documents)
    if not sections:
        return []

    splitter = recursive_splitter_factory()
    out: list[Document] = []
    for section in sections:
        if len(section.page_content) <= chunk_size:
            out.append(section)
            continue
        for piece in splitter.split_documents([section]):
            # split_documents copies metadata, so `section` survives the split.
            out.append(piece)
    return out
