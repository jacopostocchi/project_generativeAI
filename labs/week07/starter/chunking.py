"""Chunking. TODO 1.

One decision, two numbers, and they trade against each other. Smaller chunks
raise the chance that a retrieved passage is entirely on topic and lower the
chance that the whole answer is inside one of them. Larger chunks do the
reverse.

The thing that makes the trade measurable is that every chunk keeps its
doc_id and its section. The gold set names sections, the scorer resolves
sections to chunk ids at scoring time, and so the same gold set scores any
size you try. If chunks lost their section, changing the chunker would
invalidate the gold set and the sweep in block 3 would be impossible.
"""

from __future__ import annotations

from dataclasses import dataclass

from corpus_loader import Section, load_sections


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    section: str
    text: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.doc_id, self.section)

    @property
    def section_key(self) -> str:
        """The form the gold set names sections in: DOC-ID::Section."""
        return f"{self.doc_id}::{self.section}"


def chunk_sections(sections: list[Section], size: int = 600,
                   overlap: int = 80) -> list[Chunk]:
    """TODO 1. Split each section into chunks, keeping its identity.

    Character windows over the section body, with the section heading
    prepended to every chunk. `size` counts body characters, not the
    heading. The stride is `size - overlap`.
    """
    if size <= 0:
        raise ValueError(f"size must be positive, got {size}")
    if not 0 <= overlap < size:
        raise ValueError(f"overlap must be in [0, {size}), got {overlap}")

    stride = size - overlap
    chunks: list[Chunk] = []

    for sec in sections:
        body = sec.text.strip()
        if not body:
            continue

        heading = f"{sec.section}\n"
        n = len(body)
        start = 0
        index = 0

        while True:
            piece = body[start:start + size]
            chunks.append(Chunk(
                chunk_id=f"{sec.doc_id}#{sec.section}#{index}",
                doc_id=sec.doc_id,
                section=sec.section,
                text=heading + piece,
            ))
            index += 1

            if start + size >= n:
                break
            start += stride
            # a tail entirely inside the previous window adds a duplicate
            if n <= start + overlap:
                break

    return chunks


def load_chunks(size: int = 600, overlap: int = 80) -> list[Chunk]:
    return chunk_sections(load_sections(), size=size, overlap=overlap)
