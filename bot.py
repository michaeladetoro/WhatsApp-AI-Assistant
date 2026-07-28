import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional, Union

import httpx
import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Security, UploadFile, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pywa_async import WhatsApp, filters, types

from brain.config import (
    IP_ADDRESS,
    KB_API_SECRET,
    PORT,
    WA_ACCESS_TOKEN,
    WA_APP_ID,
    WA_APP_SECRET,
    WA_PHONE_NUMBER_ID,
    WA_VERIFY_TOKEN,
)
from brain.conversational import RAGHandler
from brain.fast_path import get_fast_response
from brain.kb_manager import KBManager
from services.ingestor import Ingestor, UnsupportedFileTypeError
from services.storage import BotStorage
from services.stt import SpeechToText
from utils.formatting import truncate
from utils.logger import setup_logger

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
setup_logger(name="RAGBot", force_root=True)
logger = logging.getLogger("RAGBot")

# ---------------------------------------------------------------------------
# Global services (initialised in lifespan)
# ---------------------------------------------------------------------------
storage = BotStorage()
rag_handler = RAGHandler()
kb_manager = KBManager()
stt = SpeechToText()

user_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_processed_ids: set[str] = set()
_PROCESSED_IDS_MAX = 1000


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RAGBot starting up...")
    await storage.initialize()
    rag_handler.initialize()
    logger.info("All services ready.")

    # Start TTL background task for messages
    ttl_task = asyncio.create_task(_ttl_loop())

    yield

    ttl_task.cancel()
    await storage.close()
    logger.info("RAGBot shut down.")


async def _ttl_loop():
    """Background task to enforce the 4-hour database TTL for messages."""
    while True:
        try:
            await storage.clear_old_messages(hours=4)
        except Exception as e:
            logger.error(f"TTL loop error: {e}")
        await asyncio.sleep(3600)  # Run once an hour


# ---------------------------------------------------------------------------
# FastAPI + WhatsApp client
# ---------------------------------------------------------------------------
app = FastAPI(
    title="WhatsApp RAG Bot",
    description="WhatsApp-native AI assistant powered by a continuously managed knowledge base.",
    version="1.0.0",
    lifespan=lifespan,
)

wa = WhatsApp(
    phone_id=WA_PHONE_NUMBER_ID,
    token=WA_ACCESS_TOKEN,
    server=app,
    verify_token=WA_VERIFY_TOKEN,
    app_id=WA_APP_ID,
    app_secret=WA_APP_SECRET,
)
wa.api._session.timeout = httpx.Timeout(30.0)


# ---------------------------------------------------------------------------
# KB endpoint security
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)


def _require_kb_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> None:
    """
    Optional bearer-token guard for KB management endpoints.
    If KB_API_SECRET is blank, all requests are allowed (dev mode).
    Set KB_API_SECRET in .env to lock these endpoints down.
    """
    if not KB_API_SECRET:
        return  # Auth disabled — dev/staging only
    if not credentials or credentials.credentials != KB_API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing KB API secret.")


# ---------------------------------------------------------------------------
# Core pipeline helpers
# ---------------------------------------------------------------------------
async def _typing(msg: Union[types.Message, types.CallbackButton]) -> asyncio.Task:
    async def _loop():
        while True:
            try:
                await msg.indicate_typing()
            except Exception:
                pass
            await asyncio.sleep(4)

    return asyncio.create_task(_loop())


def _dedup(message_id: str) -> bool:
    """Returns True if this message ID was already processed (duplicate)."""
    if message_id in _processed_ids:
        return True
    _processed_ids.add(message_id)
    if len(_processed_ids) > _PROCESSED_IDS_MAX:
        _processed_ids.discard(next(iter(_processed_ids)))
    return False


async def handle_message(
    msg: Union[types.Message, types.CallbackButton], text: str
) -> None:
    """
    Core message pipeline:
      1. Onboarding welcome (first-time users)
      2. Fast-path regex check
      3. RAG retrieval → LLM answer
      4. Reply + save to history
    """
    user_id: str = msg.from_user.wa_id
    username: str = (getattr(msg.from_user, "name", None) or "there").split()[0]

    await msg.mark_as_read()

    # --- Onboarding ---
    if not storage.has_onboarded(user_id):
        storage.mark_onboarded(user_id)
        welcome = (
            f"Hello {username}! 👋 I'm your AI assistant.\n\n"  # PLACEHOLDER — customise
            "Ask me anything and I'll search my knowledge base to find the best answer.\n\n"
            "You can type or send a *voice note*. Let's go! 😊"
        )
        await msg.reply_text(welcome)
        if text.strip().lower() in {"hi", "hello", "hey", "yo", "start"}:
            return

    typing_task = await _typing(msg)

    try:
        # --- Fast path ---
        fast = get_fast_response(text, username=username)
        if fast:
            typing_task.cancel()
            await msg.reply_text(truncate(fast))
            await storage.save_message(user_id, "user", text)
            await storage.save_message(user_id, "assistant", fast)
            return

        # --- RAG ---
        history = await storage.get_history(user_id)
        answer, _ = await rag_handler.answer(text, history, username=username)
        reply_text = truncate(answer)

    except Exception as e:
        logger.error(f"Pipeline error for {user_id}: {e}", exc_info=True)
        reply_text = "I'm sorry, something went wrong. Please try again."  # PLACEHOLDER
    finally:
        typing_task.cancel()

    await msg.reply_text(reply_text)
    await storage.save_message(user_id, "user", text)
    await storage.save_message(user_id, "assistant", reply_text)


# ---------------------------------------------------------------------------
# WhatsApp event handlers
# ---------------------------------------------------------------------------
@wa.on_message(filters.text)
async def on_text(client: WhatsApp, msg: types.Message) -> None:
    user_id = msg.from_user.wa_id
    if _dedup(msg.id):
        return
    logger.info(f"[{user_id}] Text: '{msg.text[:80]}'")
    async with user_locks[user_id]:
        await handle_message(msg, msg.text)


@wa.on_message(filters.audio)
async def on_audio(client: WhatsApp, msg: types.Message) -> None:
    user_id = msg.from_user.wa_id
    logger.info(f"[{user_id}] Voice note received")
    async with user_locks[user_id]:
        try:
            await msg.mark_as_read()
            media = await client.get_media_url(msg.audio.id)
            resp = await client.api._session.get(media.url)
            text = await stt.transcribe(resp.content, filename="voice.ogg")
            if not text:
                await msg.reply_text(
                    "I couldn't transcribe that. Please try typing your message."
                )
                return
            await handle_message(msg, text)
        except Exception as e:
            logger.error(f"[{user_id}] Voice error: {e}", exc_info=True)
            await msg.reply_text(
                "I had trouble processing that voice note. Please try typing."
            )


# ---------------------------------------------------------------------------
# Knowledge Base Management Endpoints
# ---------------------------------------------------------------------------


@app.post(
    "/kb/ingest",
    summary="Ingest a document into the knowledge base",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def ingest_document(
    file: UploadFile = File(
        ..., description="Document to ingest (PDF, DOCX, PPTX, TXT, MD, Images)"
    ),
    title: Optional[str] = None,
):
    """
    Upload a document and add it to the knowledge base.

    - The document is converted to plain text.
    - The text is saved to Postgres (persistently) and chunked into the FAISS index.
    - This is **additive** — existing KB content is never overwritten or removed.
    - Supported formats: `.pdf`, `.docx`, `.pptx`, `.txt`, `.md`, Excel, and images (`.png`, `.jpg`, etc.)

    **Authentication:** Include `Authorization: Bearer <KB_API_SECRET>` header.
    """
    filename = file.filename or "upload"
    doc_title = title or filename

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # 1. Extract text
    try:
        text = await Ingestor.extract(file_bytes, filename)
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Ingestor error for '{filename}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {e}")

    if not text.strip():
        raise HTTPException(
            status_code=422, detail="No text could be extracted from this file."
        )

    source_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"

    # 2. Save to Postgres (non-destructive)
    doc_id = await storage.save_kb_document(
        title=doc_title,
        content=text,
        filename=filename,
        source_type=source_type,
    )

    # 3. Append to FAISS index (additive)
    chunks_added = kb_manager.add_document(
        content=text,
        title=doc_title,
        source_label=filename,
    )

    # 4. Hot-reload the retriever
    rag_handler.reload_index()

    logger.info(f"Ingested '{filename}' — {chunks_added} chunks added, doc_id={doc_id}")

    return {
        "status": "success",
        "document_id": doc_id,
        "title": doc_title,
        "filename": filename,
        "source_type": source_type,
        "chunks_added": chunks_added,
        "characters_extracted": len(text),
    }

@app.get(
    "/kb/analytics",
    summary="Get basic analytics for the dashboard",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def kb_analytics():
    """
    Return basic analytics for the dashboard.
    """
    analytics = await storage.get_dashboard_analytics()
    return analytics


@app.get(
    "/kb/status",
    summary="List all documents in the knowledge base",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def kb_status():
    """
    Return metadata for all documents stored in the knowledge base.
    Does not return the full text content — only titles, filenames, and timestamps.
    """
    documents = await storage.list_kb_documents()
    return {
        "total_documents": len(documents),
        "index_loaded": rag_handler._retriever is not None,
        "documents": documents,
    }


@app.post(
    "/kb/rebuild",
    summary="Rebuild the FAISS index from all Postgres documents",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def kb_rebuild():
    """
    Perform a full rebuild of the FAISS vector index from all documents in Postgres.

    Use this after:
    - Deleting documents (`DELETE /kb/{id}`)
    - Manual changes to the kb_documents table
    - Index corruption

    This operation replaces the existing index on disk.
    """
    db_docs = await storage.get_all_kb_content()

    if not db_docs:
        return {
            "status": "skipped",
            "message": "No documents found in the database. Upload documents via POST /kb/ingest first.",
        }

    chunks = kb_manager.rebuild_from_db(db_docs)
    rag_handler.reload_index()

    return {
        "status": "success",
        "documents_processed": len(db_docs),
        "chunks_indexed": chunks,
    }


@app.delete(
    "/kb/messages",
    summary="Clear all conversation messages",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def kb_clear_messages():
    """
    Clear all user conversation history from the database.
    Does not affect the knowledge base.
    """
    deleted = await storage.clear_all_messages()
    return {"status": "success", "messages_deleted": deleted}


@app.delete(
    "/kb/all",
    summary="Clear the entire knowledge base",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def kb_clear_all():
    """
    Delete ALL documents from the Postgres database AND wipe the FAISS index.
    """
    deleted = await storage.clear_all_kb_documents()
    kb_manager.rebuild_from_db([])  # Pass empty list to wipe index
    rag_handler.reload_index()
    return {"status": "success", "documents_deleted": deleted, "index_status": "wiped"}


@app.patch(
    "/kb/{document_id}",
    summary="Rename a document in the knowledge base",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def kb_rename(document_id: int, request: Request):
    """
    Rename a document in Postgres by its ID.
    """
    body = await request.json()
    new_filename = body.get("filename")
    if not new_filename:
        raise HTTPException(status_code=400, detail="Missing 'filename' in request body.")
        
    updated = await storage.rename_kb_document(document_id, new_filename)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    return {"status": "renamed", "document_id": document_id, "new_filename": new_filename}


@app.delete(
    "/kb/{document_id}",
    summary="Remove a document from the knowledge base",
    tags=["Admin: Knowledge Base"],
    dependencies=[Depends(_require_kb_auth)],
)
async def kb_delete(document_id: int):
    """
    Delete a document from Postgres by its ID.

    **Important:** This removes the document record but does NOT automatically
    update the FAISS index. Call `POST /kb/rebuild` after deleting documents
    to apply the change to the vector index.
    """
    deleted_title = await storage.delete_kb_document(document_id)
    if not deleted_title:
        raise HTTPException(
            status_code=404, detail=f"Document {document_id} not found."
        )
    return {
        "status": "deleted",
        "document_id": document_id,
        "title": deleted_title,
        "note": "Call POST /kb/rebuild to remove this document's vectors from the search index.",
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("bot:app", host=IP_ADDRESS, port=PORT, reload=False)
