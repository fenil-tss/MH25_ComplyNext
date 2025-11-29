import os
import json
import asyncio
import asyncpg
from datetime import datetime
from tqdm.asyncio import tqdm
from dotenv import load_dotenv
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
import spacy
import importlib
from typing import List
from rag.keyword_extraction import extract_keywords_llm
from config import Config

# Load spacy model once
nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])  # faster
nlp.enable_pipe("senter")  # ensure sentence boundary detection

# --------------------------
# Load environment variables
# --------------------------
load_dotenv()

DB_CONFIG = {
    "user": Config.PG_USER,
    "password": Config.PG_PASSWORD,
    "database": Config.PG_DATABASE,
    "host": Config.PG_HOST,
    "port": Config.PG_PORT,
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --------------------------
# Initialize embeddings model and LLM
# --------------------------
embeddings_model = OpenAIEmbeddings(
    model="text-embedding-3-small", openai_api_key=OPENAI_API_KEY
)

llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=0,
    openai_api_key=OPENAI_API_KEY
)

# --------------------------
# Create Tables (with pgvector)
# --------------------------
CREATE_TABLES_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    source TEXT,
    source_url TEXT,
    source_type TEXT,
    date DATE,
    title TEXT,
    description TEXT NULL,
    detail_url TEXT,
    type TEXT,
    file_url TEXT,
    file_path TEXT,
    downloaded_on TIMESTAMP,
    parsed_on TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doc_chunk (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER,
    chunk_text TEXT,
    combined_text TEXT,
    chunk_embed VECTOR(1536),
    affected_sectors TEXT[],
    affected_sectors_embed VECTOR(1536),
    named_companies TEXT[],
    named_companies_embed VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_profile (
    company_id SERIAL PRIMARY KEY,
    company_name TEXT,
    website TEXT,
    scraped_at TIMESTAMP,
    emails TEXT[] NULL,
    phones TEXT[] NULL,
    about_url TEXT,
    about_text TEXT,
    about_embed VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_product (
    product_id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES company_profile(company_id) ON DELETE CASCADE,
    product_title TEXT,
    product_description TEXT,
    product_url TEXT,
    product_embed VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retrieval_logs (
    id SERIAL PRIMARY KEY,
    query TEXT,
    retrieved_chunk_ids INTEGER[],
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_doc_chunk_document_id ON doc_chunk(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunk_embedding ON doc_chunk USING ivfflat (chunk_embed vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_company_product_company_id ON company_product(company_id);
CREATE INDEX IF NOT EXISTS idx_company_product_embedding ON company_product USING ivfflat (product_embed vector_cosine_ops);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_file_path ON documents(file_path) WHERE file_path IS NOT NULL;
"""

# --------------------------
# Utility Functions
# --------------------------

def split_into_sentences(text: str) -> List[str]:
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]

def create_sentence_chunks(sentences: List[str], sentences_per_chunk: int = 3) -> List[str]:
    chunks = []
    for i in range(0, len(sentences), sentences_per_chunk):
        chunk = " ".join(sentences[i:i + sentences_per_chunk])
        if len(chunk.strip()) > 50:  # avoid tiny chunks
            chunks.append(chunk.strip())
    return chunks

def sanitize_text(text: str) -> str:
    """Remove null bytes and unprintable chars from text before DB insert."""
    if not text:
        return ""
    return text.replace("\x00", "").replace("\ufffd", "").strip()

async def init_db():
    """Initialize database: create tables and handle duplicate cleanup."""
    conn = await asyncpg.connect(**DB_CONFIG)
    
    # First, create tables (without unique index)
    tables_sql = CREATE_TABLES_SQL.replace(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_file_path ON documents(file_path) WHERE file_path IS NOT NULL;',
        ''
    )
    await conn.execute(tables_sql)
    
    # Check for duplicate file_paths and clean them up
    duplicate_check = """
        SELECT file_path, COUNT(*) as cnt, array_agg(id ORDER BY id) as doc_ids
        FROM documents
        WHERE file_path IS NOT NULL
        GROUP BY file_path
        HAVING COUNT(*) > 1;
    """
    
    duplicates = await conn.fetch(duplicate_check)
    
    if duplicates:
        print(f"⚠️  Found {len(duplicates)} duplicate file_path entries. Cleaning up...")
        
        # Use a transaction for atomic cleanup
        async with conn.transaction():
            for dup in duplicates:
                file_path = dup['file_path']
                doc_ids = dup['doc_ids']  # Array of document IDs with same file_path
                
                if not doc_ids or len(doc_ids) < 2:
                    continue
                
                # Keep the first document (oldest ID), delete the rest
                keep_id = doc_ids[0]
                delete_ids = doc_ids[1:]
                
                # Delete chunks for documents we're removing (CASCADE should handle this, but being explicit)
                if delete_ids:
                    await conn.execute(
                        "DELETE FROM doc_chunk WHERE document_id = ANY($1);",
                        delete_ids
                    )
                
                # Delete duplicate documents
                await conn.execute(
                    "DELETE FROM documents WHERE id = ANY($1);",
                    delete_ids
                )
                
                print(f"  Cleaned: {file_path} - kept document_id {keep_id}, removed {len(delete_ids)} duplicate(s)")
        
        print("✅ Duplicate cleanup complete.")
    
    # Now create the unique index
    try:
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_file_path ON documents(file_path) WHERE file_path IS NOT NULL;"
        )
        print("✅ Unique index on file_path created.")
    except Exception as e:
        print(f"⚠️  Could not create unique index (may already exist or have duplicates): {e}")
        # If index creation fails, we'll rely on application-level duplicate checks
    
    await conn.close()
    print("✅ Database initialization complete.")


async def check_document_exists(conn, file_path: str) -> int:
    """
    Check if a document with the given file_path already exists.
    
    Args:
        conn: Database connection
        file_path: File path to check
    
    Returns:
        document_id if exists, None otherwise
    """
    if not file_path:
        return None
    
    query = "SELECT id FROM documents WHERE file_path = $1 LIMIT 1;"
    return await conn.fetchval(query, file_path)


async def check_chunks_exist(conn, document_id: int) -> bool:
    """
    Check if chunks already exist for a document.
    
    Args:
        conn: Database connection
        document_id: Document ID to check
    
    Returns:
        True if chunks exist, False otherwise
    """
    query = "SELECT COUNT(*) FROM doc_chunk WHERE document_id = $1;"
    count = await conn.fetchval(query, document_id)
    return count > 0 if count else False


async def insert_document(conn, record):
    """
    Insert document metadata and return document ID.
    Uses ON CONFLICT to handle duplicates gracefully.
    """
    file_path = record.get("file_path")
    
    # First check if document exists
    existing_id = await check_document_exists(conn, file_path)
    if existing_id:
        return existing_id
    
    # Insert new document
    query = """
        INSERT INTO documents (
            source, source_url, source_type, date, title, description,
            detail_url, type, file_url, file_path, downloaded_on
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        RETURNING id;
    """
    date_val = None
    if record.get("date"):
        try:
            date_val = datetime.strptime(record["date"], "%b %d, %Y").date()
        except:
            pass

    return await conn.fetchval(
        query,
        record.get("source"),
        record.get("source_url"),
        record.get("source_type"),
        date_val,
        record.get("title"),
        record.get("description"),
        record.get("detail_url"),
        record.get("type"),
        record.get("file_url"),
        file_path,
        datetime.strptime(record["downloaded_on"], "%Y-%m-%d %H:%M:%S")
        if record.get("downloaded_on")
        else None,
    )

async def process_pdf(file_path: str):
    """Use doc_split_header.doc_chunking to obtain content_chunks only.

    If doc_split_header is not available or raises, fall back to the
    original sentence-based chunking.
    """
    # Prefer letting doc_split_header handle loading and chunking
    try:
        mod = importlib.import_module("doc_split_header")
        doc_chunking = getattr(mod, "doc_chunking", None)
        if callable(doc_chunking):
            try:
                result = doc_chunking(file_path, include_table_chunks=False)
                # Accept dict or object-like return
                if isinstance(result, dict) and "content_chunks" in result:
                    raw_chunks = result["content_chunks"]
                elif isinstance(result, (list, tuple)):
                    raw_chunks = list(result)
                elif hasattr(result, "content_chunks"):
                    raw_chunks = list(getattr(result, "content_chunks"))
                else:
                    raw_chunks = []
            except Exception:
                raw_chunks = []
        else:
            raw_chunks = []
    except Exception:
        raw_chunks = []

    # If we didn't get chunks from doc_split_header, fallback to older method
    if not raw_chunks:
        # Original loader-based fallback: load pages and sentence-chunk
        loader = PyMuPDFLoader(file_path)
        pages = loader.load()

        full_text = "\n\n".join(page.page_content for page in pages)
        full_text = sanitize_text(full_text)
        full_text = " ".join(full_text.split())

        sentences = split_into_sentences(full_text)
        return create_sentence_chunks(sentences, sentences_per_chunk=3)

    # Sanitize and filter the content_chunks
    clean_chunks = []
    for c in raw_chunks:
        if not isinstance(c, str):
            c = str(c)
        c = sanitize_text(c)
        c = " ".join(c.split())
        if len(c) > 50:
            clean_chunks.append(c)

    return clean_chunks


async def embed_and_store_chunks(
    conn, 
    document_id, 
    title, 
    description, 
    chunks, 
    affected_sectors=None, 
    named_companies=None,
    batch_size=16
):
    """
    Embed chunks and insert into DB (batched for performance).
    
    Args:
        conn: Database connection
        document_id: Document ID
        title: Document title
        description: Document description
        chunks: List of text chunks
        affected_sectors: List of affected sectors (extracted at document level)
        named_companies: List of named companies (extracted at document level)
        batch_size: Batch size for embedding generation
    """
    description = description or ""  # handle null case
    affected_sectors = affected_sectors or []
    named_companies = named_companies or []
    
    # Generate embeddings for sectors and companies (entire list as string)
    sectors_text = ", ".join(affected_sectors) if affected_sectors else ""
    companies_text = ", ".join(named_companies) if named_companies else ""
    
    sectors_embed = None
    companies_embed = None
    
    if sectors_text:
        try:
            sectors_embed_vector = embeddings_model.embed_query(sectors_text)
            sectors_embed = "[" + ",".join(map(str, sectors_embed_vector)) + "]"
        except Exception as e:
            print(f"⚠️ Error embedding sectors: {e}")
    
    if companies_text:
        try:
            companies_embed_vector = embeddings_model.embed_query(companies_text)
            companies_embed = "[" + ",".join(map(str, companies_embed_vector)) + "]"
        except Exception as e:
            print(f"⚠️ Error embedding companies: {e}")
    
    insert_query = """
        INSERT INTO doc_chunk (
            document_id, chunk_index, chunk_text, combined_text, chunk_embed,
            affected_sectors, affected_sectors_embed, named_companies, named_companies_embed
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """

    # Process in batches to reduce OpenAI API calls and DB overhead
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        combined_texts = [
            f"Title: {title}\nDescription: {description}\n\n{chunk}"
            for chunk in batch
        ]

        vectors = embeddings_model.embed_documents(combined_texts)

        for idx, (chunk_text, combined_text, vector) in enumerate(zip(batch, combined_texts, vectors)):
            clean_chunk_text = sanitize_text(chunk_text)
            clean_combined_text = sanitize_text(combined_text)
            vector_str = "[" + ",".join(map(str, vector)) + "]"
            await conn.execute(
                insert_query,
                document_id,
                i + idx,
                clean_chunk_text,
                clean_combined_text,
                vector_str,
                affected_sectors,  # TEXT[] array
                sectors_embed,     # VECTOR(1536) or NULL
                named_companies,   # TEXT[] array
                companies_embed    # VECTOR(1536) or NULL
            )


# --------------------------
# Main Processing Function
# --------------------------

async def ingest_json(json_path: str):
    """
    Read JSON, parse PDFs, embed and store in DB.
    
    Duplicate Detection Strategy:
    - Uses file_path as the unique identifier for documents
    - Checks if a document with the same file_path already exists
    - If document exists and has chunks: skips processing (duplicate)
    - If document exists but has no chunks: processes chunks (recovery case)
    - If document doesn't exist: creates new document and processes chunks
    """
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    conn = await asyncpg.connect(**DB_CONFIG)

    stats = {"processed": 0, "skipped_duplicates": 0, "skipped_missing": 0, "errors": 0}
    
    for record in tqdm(records, desc="Processing Documents"):
        try:
            # Normalize key casing
            record = {k.lower(): v for k, v in record.items()}

            file_path = record.get("file_path")
            if not file_path or not os.path.exists(file_path):
                print(f"⚠️ Skipping: file not found - {file_path}")
                stats["skipped_missing"] += 1
                continue

            # Check if document already exists
            existing_doc_id = await check_document_exists(conn, file_path)
            if existing_doc_id:
                # Check if chunks already exist
                has_chunks = await check_chunks_exist(conn, existing_doc_id)
                if has_chunks:
                    print(f"⏭️  Skipping duplicate: {file_path} (document_id: {existing_doc_id}, chunks already exist)")
                    stats["skipped_duplicates"] += 1
                    continue
                else:
                    # Document exists but no chunks - use existing document_id
                    document_id = existing_doc_id
                    print(f"ℹ️  Document exists but no chunks found, processing: {file_path} (document_id: {document_id})")
            else:
                # Insert new document
                document_id = await insert_document(conn, record)

            # 2. Parse & chunk PDF
            chunks = await process_pdf(file_path)
            
            if not chunks:
                print(f"⚠️  No chunks extracted from: {file_path}")
                stats["skipped_missing"] += 1
                continue

            # 3. Extract keywords (sectors and companies) from full document text
            # Combine all chunks to get full document text for extraction
            full_text = "\n\n".join(chunks)
            if full_text.strip():
                print(f"  Extracting keywords for document {document_id}...")
                keywords = extract_keywords_llm(full_text, llm)
                affected_sectors = keywords.get("affected_sectors", [])
                named_companies = keywords.get("named_companies", [])
            else:
                affected_sectors = []
                named_companies = []

            # 4. Embed and store chunks with keywords
            await embed_and_store_chunks(
                conn,
                document_id,
                record.get("title"),
                record.get("description"),
                chunks,
                affected_sectors=affected_sectors,
                named_companies=named_companies,
            )
            
            stats["processed"] += 1

        except Exception as e:
            print(f"❌ Error processing {record.get('title')}: {e}")
            stats["errors"] += 1
            import traceback
            traceback.print_exc()

    await conn.close()
    print("\n✅ Processing complete!")
    print(f"   Processed: {stats['processed']}")
    print(f"   Skipped (duplicates): {stats['skipped_duplicates']}")
    print(f"   Skipped (missing files/no chunks): {stats['skipped_missing']}")
    print(f"   Errors: {stats['errors']}")


# --------------------------
# Entry Point
# --------------------------

if __name__ == "__main__":
    asyncio.run(init_db())
    asyncio.run(ingest_json("rbi_notifications.json"))
    # asyncio.run(ingest_json("sebi_notifications.json"))