import os
import fitz
from tqdm import tqdm
from typing import List, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import quote_plus

from dotenv import load_dotenv, find_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.documents import Document
from langchain.chains import RetrievalQA
from langchain_core.prompts import ChatPromptTemplate

import tiktoken

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
load_dotenv(find_dotenv())

LANGCHAIN_TRACING = os.getenv("LANGCHAIN_TRACING_V2")
LANGCHAIN_ENDPOINT = os.getenv("LANGCHAIN_ENDPOINT")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")

if LANGCHAIN_TRACING:
    os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING
if LANGCHAIN_ENDPOINT:
    os.environ["LANGCHAIN_ENDPOINT"] = LANGCHAIN_ENDPOINT
if LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY must be set in the environment or .env file")

pg_host = os.getenv("PG_HOST", "localhost")
pg_port = os.getenv("PG_PORT", "5432")
pg_user = os.getenv("PG_USER", "postgres")
pg_password = os.getenv("PG_PASSWORD", "")
pg_database = os.getenv("PG_DATABASE", "postgres")

password_q = quote_plus(pg_password)
PGVECTOR_CONN = f"postgresql+psycopg2://{pg_user}:{password_q}@{pg_host}:{pg_port}/{pg_database}"
PSYCOPG_CONN = f"postgresql://{pg_user}:{password_q}@{pg_host}:{pg_port}/{pg_database}"

COLLECTION_NAME = os.getenv("PGVECTOR_COLLECTION", "pdf_rag_openai")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("RAG_TOP_K", "5"))

# -------------------------------------------------
# 1. FETCH METADATA
# -------------------------------------------------
def fetch_docs() -> List[Dict]:
    conn = psycopg2.connect(PSYCOPG_CONN, cursor_factory=RealDictCursor)

    cur = conn.cursor()
    cur.execute("SELECT id, title, file_path, source_url FROM documents WHERE file_path IS NOT NULL")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

# -------------------------------------------------
# 2. EXTRACT PDF TEXT
# -------------------------------------------------
def extract_text(path: str) -> str:
    if not os.path.exists(path): return ""
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text

# -------------------------------------------------
# 3. BUILD VECTOR STORE
# -------------------------------------------------
def build_vector_store(docs: List[Dict]):
    embeddings = OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"))

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    langchain_docs = []
    for row in tqdm(docs, desc="Chunking PDFs"):
        text = extract_text(row["file_path"])
        if not text: continue

        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            meta = {
                "doc_id": row["id"],
                "title": row["title"],
                "source_url": row["source_url"],
                "file_path": row["file_path"],
                "chunk_idx": i,
            }
            langchain_docs.append(Document(page_content=chunk, metadata=meta))

    if not langchain_docs:
        raise ValueError("No PDF content found to embed. Ensure file_path entries are valid.")

    vectorstore = PGVector.from_documents(
        documents=langchain_docs,
        embedding=embeddings,
        connection_string=PGVECTOR_CONN,
        collection_name=COLLECTION_NAME,
    )
    return vectorstore

# -------------------------------------------------
# 4. TOKEN COUNTER
# -------------------------------------------------
enc = tiktoken.get_encoding("cl100k_base")
def count_tokens(s: str) -> int:
    return len(enc.encode(s))

# -------------------------------------------------
# 5. RETRIEVAL WITH SCORES
# -------------------------------------------------
def retrieve_with_scores(vectorstore, query: str, k: int = TOP_K):
    return vectorstore.similarity_search_with_score(query, k=k)

# -------------------------------------------------
# 6. QA CHAIN (cites title + score)
# -------------------------------------------------
def build_qa_chain(vectorstore):

    template = """You are an expert. Answer using ONLY the context.

Context:
{context}

Question: {question}

Answer (cite document title and similarity score):"""
    prompt = ChatPromptTemplate.from_template(template)

    llm_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    qa = RetrievalQA.from_chain_type(
        llm=ChatOpenAI(model_name=llm_model, temperature=0),
        retriever=vectorstore.as_retriever(search_kwargs={"k": TOP_K}),
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )
    return qa

# -------------------------------------------------
# MAIN
# -------------------------------------------------
if __name__ == "__main__":
    print("Loading PDFs from DB...")
    docs = fetch_docs()
    print(f"{len(docs)} PDFs found.")

    print("Building vector store...")
    vectorstore = build_vector_store(docs)
    print("Ready.")

    qa_chain = build_qa_chain(vectorstore)

    while True:
        q = input("\nQuestion (or 'exit'): ").strip()
        if q.lower() in {"exit", "quit"}: break

        # Retrieve with scores
        scored = retrieve_with_scores(vectorstore, q, k=TOP_K)
        result = qa_chain({"query": q})

        print("\n" + "="*80)
        print("ANSWER:")
        print(result["result"])

        print(f"\nTokens in  : {count_tokens(q)} (question)")
        print(f"Retrieved: {len(scored)} chunks\n")

        for i, (doc, score) in enumerate(scored, 1):
            m = doc.metadata
            print(f"--- [{i}] Score: {score:.4f} ---")
            print(f"Title : {m['title']}")
            print(f"File  : {os.path.basename(m['file_path'])}")
            print(f"Chunk : {doc.page_content[:200]}...")
        print("="*80)