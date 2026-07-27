"""
Knowledge Base Manager — FAISS index builder.

Source of truth for KB content: Postgres (kb_documents table).
The FAISS index on disk is a derived artefact that can always be rebuilt from Postgres.

Key design choices:
  - Additive: adding a new document appends to the existing FAISS index.
    Existing vectors are never touched.
  - Rebuild: reads ALL documents from Postgres and creates a fresh index.
    Use this after deletions or major content changes.
  - File fallback: if Postgres is unavailable, can still build from local files
    (used for initial bootstrapping via scripts/build_index.py).
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from brain.config import FAISS_INDEX_PATH, KNOWLEDGE_DIR, OPENAI_API_KEY

logger = logging.getLogger("RAGBot.KBManager")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
SUPPORTED_EXTENSIONS = {".txt", ".md"}

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)


class KBManager:
    """Manages the FAISS knowledge base index."""

    def __init__(self) -> None:
        self._embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)

    # ------------------------------------------------------------------
    # Additive update (primary path when ingesting a new document)
    # ------------------------------------------------------------------

    def add_document(
        self,
        content: str,
        title: str,
        source_label: str = "",
    ) -> int:
        """
        Chunk `content` and append the vectors to the existing FAISS index.
        If no index exists yet, creates one.

        This is ADDITIVE — existing vectors are never modified or removed.

        Args:
            content:      Plain text to index.
            title:        Human-readable document title (stored in metadata).
            source_label: Used as the "source" metadata field (e.g. filename).

        Returns:
            Number of new chunks added.
        """
        label = source_label or title
        doc = Document(page_content=content, metadata={"source": label, "title": title})
        chunks = _splitter.split_documents([doc])

        if not chunks:
            logger.warning(f"No chunks produced for document '{title}'")
            return 0

        index_path = Path(FAISS_INDEX_PATH)

        if index_path.exists():
            # Load existing index and append
            try:
                store = FAISS.load_local(
                    FAISS_INDEX_PATH,
                    self._embeddings,
                    allow_dangerous_deserialization=True,
                )
                store.add_documents(chunks)
                logger.info(
                    f"Appended {len(chunks)} chunks from '{title}' to existing index."
                )
            except Exception as e:
                logger.warning(
                    f"Could not load existing index ({e}). Creating fresh index."
                )
                store = FAISS.from_documents(chunks, self._embeddings)
        else:
            # First document ever
            store = FAISS.from_documents(chunks, self._embeddings)
            logger.info(f"Created new index with {len(chunks)} chunks from '{title}'.")

        store.save_local(FAISS_INDEX_PATH)
        return len(chunks)

    # ------------------------------------------------------------------
    # Full rebuild from Postgres (after deletions / major changes)
    # ------------------------------------------------------------------

    def rebuild_from_db(self, db_documents: List[dict]) -> int:
        """
        Rebuild the FAISS index from a list of DB document dicts.

        Args:
            db_documents: List of {"id", "title", "filename", "content"} dicts
                          from storage.get_all_kb_content().

        Returns:
            Total chunks indexed, or 0 if no documents provided.
        """
        if not db_documents:
            logger.warning("rebuild_from_db: no documents provided.")
            return 0

        all_chunks: List[Document] = []
        for doc in db_documents:
            label = doc.get("filename") or doc.get("title", f"doc_{doc['id']}")
            d = Document(
                page_content=doc["content"],
                metadata={"source": label, "title": doc.get("title", label)},
            )
            all_chunks.extend(_splitter.split_documents([d]))

        if not all_chunks:
            return 0

        # Wipe and recreate
        index_path = Path(FAISS_INDEX_PATH)
        if index_path.exists():
            shutil.rmtree(index_path)

        store = FAISS.from_documents(all_chunks, self._embeddings)
        store.save_local(FAISS_INDEX_PATH)
        logger.info(
            f"Rebuilt index: {len(all_chunks)} chunks from {len(db_documents)} document(s)."
        )
        return len(all_chunks)

    # ------------------------------------------------------------------
    # File-based rebuild (bootstrap / offline use)
    # ------------------------------------------------------------------

    def rebuild_from_files(self, source_dir: Optional[Path] = None) -> int:
        """
        Rebuild the index from .txt / .md files in source_dir.
        Used by scripts/build_index.py for initial bootstrapping.

        Returns:
            Number of chunks indexed.
        """
        source_dir = source_dir or KNOWLEDGE_DIR
        files = [
            f
            for f in source_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        if not files:
            logger.warning(f"No supported files found in {source_dir}")
            return 0

        all_chunks: List[Document] = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
                if text.strip():
                    d = Document(page_content=text, metadata={"source": f.name})
                    all_chunks.extend(_splitter.split_documents([d]))
            except Exception as e:
                logger.error(f"Failed to read {f}: {e}")

        if not all_chunks:
            return 0

        index_path = Path(FAISS_INDEX_PATH)
        if index_path.exists():
            shutil.rmtree(index_path)

        store = FAISS.from_documents(all_chunks, self._embeddings)
        store.save_local(FAISS_INDEX_PATH)
        logger.info(f"Built index from files: {len(all_chunks)} chunks.")
        return len(all_chunks)
