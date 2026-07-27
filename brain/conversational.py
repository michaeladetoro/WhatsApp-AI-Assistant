"""
RAG conversational handler.

Loads the FAISS vector store at startup and answers questions by:
1. Retrieving the top-k relevant documents from the knowledge base
2. Building a prompt: system instructions + retrieved context + chat history
3. Calling the LLM to generate a grounded answer
4. Surfacing source document names as citations

Degrades gracefully when the FAISS index hasn't been built yet.
"""

import logging
from typing import List, Optional, Tuple

from langchain_community.vectorstores import FAISS
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from brain.config import (
    FAISS_INDEX_PATH,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    OPENAI_API_KEY,
    RAG_K,
    SYSTEM_PROMPT,
)
from utils.formatting import clean_for_whatsapp

logger = logging.getLogger("RAGBot.Conversational")


class RAGHandler:
    """
    Handles all conversational queries using retrieval-augmented generation.
    Initialised once at startup; safe for concurrent async use.
    """

    def __init__(self) -> None:
        self._retriever = None
        self._llm: Optional[ChatOpenAI] = None
        self._embeddings: Optional[OpenAIEmbeddings] = None

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def initialize(self) -> "RAGHandler":
        """Load the embeddings model, FAISS index, and LLM. Call once at startup."""
        self._embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
        self._llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            api_key=OPENAI_API_KEY,
        )
        self._load_index()
        return self

    def _load_index(self) -> None:
        """Attempt to load the FAISS vector store from disk."""
        try:
            store = FAISS.load_local(
                FAISS_INDEX_PATH,
                self._embeddings,
                allow_dangerous_deserialization=True,
            )
            self._retriever = store.as_retriever(
                search_type="mmr",
                search_kwargs={"k": RAG_K, "fetch_k": RAG_K * 3},
            )
            logger.info(f"FAISS index loaded from {FAISS_INDEX_PATH}")
        except Exception as e:
            logger.warning(
                f"FAISS index not loaded ({e}). "
                "POST to /kb/ingest to add documents, or call /kb/rebuild."
            )
            self._retriever = None

    def reload_index(self) -> None:
        """Hot-reload the index after new documents are ingested."""
        self._load_index()

    # ------------------------------------------------------------------
    # Answer
    # ------------------------------------------------------------------

    async def answer(
        self,
        user_message: str,
        history: List[dict],
        username: str = "there",
    ) -> Tuple[str, List[str]]:
        """
        Generate a grounded answer for the user's message.

        Args:
            user_message: The latest message from the user.
            history: List of {"role": "user"|"assistant", "content": str} dicts.
            username: Display name for personalisation.

        Returns:
            (answer_text, list_of_source_document_names)
        """
        context_str = ""
        sources: List[str] = []

        if self._retriever:
            try:
                docs = self._retriever.invoke(user_message)
                if docs:
                    context_str = "\n\n".join(doc.page_content for doc in docs)
                    sources = list(
                        dict.fromkeys(
                            doc.metadata.get("source", "Knowledge Base") for doc in docs
                        )
                    )
            except Exception as e:
                logger.error(f"Retrieval error: {e}")

        messages = self._build_messages(user_message, history, context_str)

        try:
            response = await self._llm.ainvoke(messages)
            answer = clean_for_whatsapp(response.content or "")
        except Exception as e:
            logger.error(f"LLM error: {e}")
            answer = (
                "I'm sorry, I couldn't process that right now. "
                "Please try again or contact support."  # PLACEHOLDER
            )
            sources = []

        return answer, sources

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        user_message: str,
        history: List[dict],
        context_str: str,
    ) -> list:
        """Assemble the LangChain message list."""
        system_content = SYSTEM_PROMPT

        if context_str:
            system_content += f"\n\n---\nKNOWLEDGE BASE:\n{context_str}\n---"

        messages: list = [SystemMessage(content=system_content)]

        if history:
            history_text = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                for m in history[-6:]
            )
            messages.append(
                SystemMessage(content=f"RECENT CONVERSATION:\n{history_text}")
            )

        messages.append(HumanMessage(content=user_message))
        return messages
