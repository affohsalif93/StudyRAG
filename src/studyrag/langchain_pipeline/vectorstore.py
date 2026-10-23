"""Loading, splitting, embedding, and vector store -- done with
LangChain components instead of the bare pipeline's plain functions and
NumPy array. A parallel path, not a replacement, so the two can be
compared.

"Splitting" is intentionally a no-op here: our chunks (src/studyrag/
retrieval/chunks.py) are already structure-aware and the right size --
re-splitting them with a generic LangChain text splitter would undo
that. LangChain's role here is loading them as Documents, embedding,
and the vector store/retriever, not re-deciding chunk boundaries.
"""

from __future__ import annotations

import sqlite3

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from studyrag.config import EMBEDDING_MODEL
from studyrag.retrieval.chunks import build_module_chunks, build_rule_chunks

_SCALAR_TYPES = (str, int, float, bool)


def _chunks_to_documents(chunks: list[dict]) -> list[Document]:
    documents = []
    for chunk in chunks:
        metadata = {
            k: v
            for k, v in chunk.items()
            if k not in ("text", "chunk_id") and (isinstance(v, _SCALAR_TYPES) or v is None)
        }
        documents.append(Document(page_content=chunk["text"], metadata=metadata, id=chunk["chunk_id"]))
    return documents


def build_vectorstore(conn: sqlite3.Connection, persist_dir: str) -> Chroma:
    """Builds the chunks (same functions as the bare pipeline), embeds
    them with LangChain's OpenAIEmbeddings, and persists a Chroma store.
    """
    chunks = build_module_chunks(conn) + build_rule_chunks(conn)
    documents = _chunks_to_documents(chunks)
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return Chroma.from_documents(
        documents,
        embeddings,
        ids=[d.id for d in documents],
        persist_directory=persist_dir,
    )


def load_vectorstore(persist_dir: str) -> Chroma:
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return Chroma(persist_directory=persist_dir, embedding_function=embeddings)
