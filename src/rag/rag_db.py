import os
import logging
import asyncio
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv, find_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain_postgres import PGEngine, PGVectorStore
from config import Config


# Load environment variables from .env
load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_engine() -> object:
    """Create and return a PostgreSQL SQLAlchemy engine using .env configuration."""

    host = Config.PG_HOST
    port = Config.PG_PORT
    user = Config.PG_USER
    password = Config.PG_PASSWORD
    dbname = Config.PG_DATABASE

    # quote the password in case it has special chars
    password_q = quote_plus(password)
    conn_str = f"postgresql+psycopg2://{user}:{password_q}@{host}:{port}/{dbname}"

    logger.info("Creating DB engine for PostgreSQL")
    engine = create_engine(conn_str)
    return engine


class DatabaseRAGPipeline:
    """Simple RAG pipeline that queries pgvector-backed chunks directly from Postgres."""

    def __init__(self, top_k: Optional[int] = None):
        if not os.getenv("OPENAI_API_KEY"):
            raise EnvironmentError("OPENAI_API_KEY must be set before using the RAG pipeline")

        self.top_k = top_k or int(os.getenv("RAG_TOP_K", "10"))
        self.engine = get_db_engine()

        embedding_model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.embeddings = OpenAIEmbeddings(model=embedding_model_name)

        llm_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.llm = ChatOpenAI(model_name=llm_model, temperature=0)

        # Initialize PGVectorStore on top of the existing document_chunks table
        self.vector_store = asyncio.run(self._init_vector_store())
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": self.top_k})

    @staticmethod
    def _format_vector(vector: List[float]) -> str:
        """Convert a Python list into pgvector literal format."""
        return "[" + ",".join(f"{v:.8f}" for v in vector) + "]"

    @staticmethod
    def _normalize_date(value: Optional[Any]) -> Optional[str]:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    async def _init_vector_store(self) -> PGVectorStore:
        """Create a PGVectorStore backed by the existing document_chunks table."""

        host = os.getenv("PG_HOST", "localhost")
        port = os.getenv("PG_PORT", "5432")
        user = os.getenv("PG_USER", "")
        password = os.getenv("PG_PASSWORD", "")
        dbname = os.getenv("PG_DATABASE", "")

        password_q = quote_plus(password)
        conn_str = f"postgresql+asyncpg://{user}:{password_q}@{host}:{port}/{dbname}"

        pg_engine = PGEngine.from_connection_string(url=conn_str)

        store = await PGVectorStore.create(
            engine=pg_engine,
            table_name="document_chunks",
            embedding_service=self.embeddings,
            # Existing columns in document_chunks
            id_column="id",
            content_column="combined_text",
            embedding_column="embedding",
            metadata_columns=["document_id"],
        )
        return store

    def _retrieve_chunks(self, question: str) -> List[Dict[str, Any]]:
        """Fetch the top-k most similar chunks via PGVectorStore and log the retrieval."""
        logger.debug("Retrieving documents via PGVectorStore")

        # Use the LangChain retriever interface (invoke returns a list of Documents)
        docs = self.retriever.invoke(question)

        if not docs:
            return []

        results: List[Dict[str, Any]] = []
        chunk_ids: List[int] = []

        with self.engine.begin() as conn:
            for doc in docs:
                metadata = dict(getattr(doc, "metadata", {}) or {})
                chunk_id = metadata.get("id") or metadata.get("chunk_id")
                document_id = metadata.get("document_id")

                row: Dict[str, Any] = {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "chunk_text": getattr(doc, "page_content", "") or "",
                    "combined_text": getattr(doc, "page_content", "") or "",
                }

                # Enrich with metadata from documents table, if available
                if document_id is not None:
                    doc_row = conn.execute(
                        text(
                            """
                            SELECT source, source_type, title, date, file_path
                            FROM documents
                            WHERE id = :doc_id
                            """
                        ),
                        {"doc_id": document_id},
                    ).mappings().first()
                    if doc_row:
                        row.update(doc_row)

                results.append(row)

                if chunk_id is not None:
                    try:
                        chunk_ids.append(int(chunk_id))
                    except (TypeError, ValueError):
                        pass

            # Log retrieval
            if chunk_ids:
                conn.execute(
                    text(
                        """
                        INSERT INTO retrieval_logs (query, retrieved_chunk_ids)
                        VALUES (:query, :chunk_ids)
                        """
                    ),
                    {"query": question, "chunk_ids": chunk_ids},
                )

        # Normalize date fields
        for row in results:
            row["date"] = self._normalize_date(row.get("date"))

        logger.info("Retrieved %d chunks for the query", len(results))
        return results

    @staticmethod
    def _build_context(chunks: List[Dict[str, Any]]) -> str:
        context_blocks = []
        for chunk in chunks:
            chunk_text = chunk.get("chunk_text") or chunk.get("combined_text") or ""
            block = (
                f"Source: {chunk.get('title') or 'Unknown'} | "
                f"Type: {chunk.get('source_type') or 'Unknown'} | "
                f"Date: {chunk.get('date') or 'Unknown'}\n"
                f"{chunk_text.strip()}"
            )
            context_blocks.append(block.strip())
        return "\n\n".join(context_blocks)

    @staticmethod
    def _format_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources: Dict[int, Dict[str, Any]] = {}
        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id in sources:
                continue
            sources[doc_id] = {
                "document_id": doc_id,
                "source": chunk.get("source"),
                "source_type": chunk.get("source_type"),
                "title": chunk.get("title"),
                "date": chunk.get("date"),
                "file_path": chunk.get("file_path"),
            }
        return list(sources.values())

    def answer_question(self, question: str) -> Dict[str, Any]:
        """Return an answer along with supporting sources from the database."""
        if not question.strip():
            return {
                "question": question,
                "answer": "Please provide a non-empty question.",
                "sources": [],
            }

        chunks = self._retrieve_chunks(question)
        if not chunks:
            return {
                "question": question,
                "answer": "I could not find any relevant information in the knowledge base.",
                "sources": [],
            }

        context = self._build_context(chunks)
        prompt = (
            "You are a helpful compliance assistant. Use only the provided context to answer the question. "
            "If the answer is not in the context, say you do not know.\n\n"
            f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
        )

        logger.debug("Sending prompt to LLM")
        llm_response = self.llm.invoke(prompt)

        # langchain_openai.ChatOpenAI returns an AIMessage; get its text content
        if hasattr(llm_response, "content"):
            answer = str(llm_response.content).strip()
        else:
            answer = str(llm_response).strip()
        sources = self._format_sources(chunks)

        return {
            "question": question,
            "answer": answer,
            "sources": sources,
        }


if __name__ == "__main__":
    try:
        pipeline = DatabaseRAGPipeline()
        print("Database-backed RAG pipeline ready. Ask a question (or 'exit' to quit):")
        while True:
            q = input("Q: ")
            if not q or q.strip().lower() in ("exit", "quit"):
                break
            response = pipeline.answer_question(q)
            print("\nAnswer:\n", response["answer"], "\n", sep="")

            if response["sources"]:
                print("Sources:")
                for src in response["sources"]:
                    date_val = src.get("date") or "Unknown date"
                    title = src.get("title") or "Untitled"
                    source_type = src.get("source_type") or "Unknown type"
                    file_path = src.get("file_path") or "N/A"
                    print(f"- {title} | {source_type} | {date_val} | {file_path}")
            else:
                print("No supporting sources found.")
            print()

    except Exception as e:
        logger.exception("Error initializing RAG module: %s", e)
        raise
