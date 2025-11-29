import os
import re
import json
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv, find_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from langchain_openai import ChatOpenAI
from tqdm import tqdm

# ========================= CONFIG =========================
load_dotenv(find_dotenv())
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_FILE = "pdf_keywords_extracted.json"
INCREMENTAL_FILE = "pdf_keywords_extracted_progress.json"
MAX_TOKENS_PER_LLM_CALL = 30_000
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# =========================================================


def get_engine():
    conn_str = (
        f"postgresql+psycopg2://"
        f"{os.getenv('PG_USER')}:{quote_plus(os.getenv('PG_PASSWORD'))}@"
        f"{os.getenv('PG_HOST', 'localhost')}:{os.getenv('PG_PORT', '5432')}/"
        f"{os.getenv('PG_DATABASE')}"
    )
    return create_engine(conn_str, future=True)


def get_all_pdf_documents(engine) -> List[Dict]:
    sql = text("""
        SELECT id, title, source, source_type, date, file_path
        FROM public.documents
        WHERE source_type ILIKE '%pdf%'
           OR file_path ILIKE '%.pdf'
        ORDER BY date DESC NULLS LAST, title
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings()
        return [dict(r) for r in rows]


def get_full_text_for_document(engine, document_id: int) -> str:
    sql = text("""
        SELECT combined_text
        FROM public.document_chunks
        WHERE document_id = :doc_id
        ORDER BY chunk_index ASC NULLS LAST
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {"doc_id": document_id})
        rows = result.mappings().fetchall()
        texts = [row["combined_text"] or "" for row in rows]
        return "\n\n".join(texts).strip()


def truncate_for_llm(text: str, max_tokens: int = MAX_TOKENS_PER_LLM_CALL) -> str:
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Text truncated for keyword extraction]"


def extract_keywords_llm(text: str, llm) -> Dict[str, List[str]]:
    prompt = f"""
You are an expert compliance and regulatory analyst.

From the document below, extract:

1. All affected sectors, industries, or types of entities that are regulated, obligated, or in scope.
   Examples: "banks", "virtual asset service providers", "real estate agents", "law firms"

2. Any specific named companies or institutions explicitly mentioned as being affected or in scope.

Return ONLY this exact JSON structure (no markdown, no extra text):

{{
  "affected_sectors": ["banks", "credit unions", "cryptocurrency exchanges"],
  "named_companies": ["Binance", "HSBC", "Revolut"]
}}

Document:
{truncate_for_llm(text)}

JSON only:
"""

    try:
        resp = llm.invoke(prompt)
        content = resp.content.strip()

        # Remove ```json ... ``` blocks if present
        content = re.sub(r"^```json\s*|```$", "", content, flags=re.MULTILINE).strip()

        data = json.loads(content)

        sectors = data.get("affected_sectors", [])
        companies = data.get("named_companies", [])

        # Clean and validate
        sectors = [s.strip() for s in sectors if isinstance(s, str) and s.strip()][:40]
        companies = [c.strip() for c in companies if isinstance(c, str) and c.strip()][:40]

        return {
            "affected_sectors": sectors,
            "named_companies": companies
        }

    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode failed: {e}\nRaw response:\n{content}")
    except Exception as e:
        logger.error(f"Unexpected error in LLM parsing: {e}")

    fallback_matches = re.findall(r'"([^"]{3,100})"', content)
    fallback = [m.strip() for m in fallback_matches if m.strip()][:40]

    return {
        "affected_sectors": fallback,
        "named_companies": []
    }


def load_progress() -> set:
    if not os.path.exists(INCREMENTAL_FILE):
        return set()
    try:
        with open(INCREMENTAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {item["document_id"] for item in data}
    except Exception as e:
        logger.warning(f"Could not load progress file: {e}")
        return set()


def save_progress(results: List[Dict]):
    with open(INCREMENTAL_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def main():
    engine = get_engine()
    llm = ChatOpenAI(model=MODEL_NAME, temperature=0)

    documents = get_all_pdf_documents(engine)
    already_done = load_progress()

    results = []
    if os.path.exists(INCREMENTAL_FILE):
        try:
            with open(INCREMENTAL_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
        except:
            results = []

    print(f"Found {len(documents)} PDF documents")
    print(f"Already processed: {len(already_done)}\n")

    for doc in tqdm(documents, desc="Extracting sectors & companies"):
        doc_id = doc["id"]
        if doc_id in already_done:
            continue

        title = doc.get("title") or "Untitled"
        full_text = get_full_text_for_document(engine, doc_id)

        if not full_text.strip():
            logger.warning(f"No text for document ID {doc_id} – {title}")
            extraction = {"affected_sectors": [], "named_companies": []}
        else:
            extraction = extract_keywords_llm(full_text, llm)

        entry = {
            "document_id": doc_id,
            "title": title,
            "source": doc.get("source"),
            "source_type": doc.get("source_type"),
            "date": str(doc["date"]) if doc.get("date") else None,
            "file_path": doc.get("file_path"),
            "affected_sectors": extraction["affected_sectors"],
            "named_companies": extraction["named_companies"],
            
        }

        results.append(entry)
        save_progress(results)

    print(f"\nFinished! Processed {len(results)} documents.")
    print(f"Final output: {OUTPUT_FILE}")
    print(f"Progress backup: {INCREMENTAL_FILE}")


if __name__ == "__main__":
    main()
