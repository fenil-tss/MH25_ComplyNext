from utils import openai_embed_model
from typing import List, Dict, Any
from sqlalchemy import func, select, text
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
# from database import DatabaseManager, Documents, DocChunk, CompanyProfile


class RAGEngine:
    def __init__(self):
        self.embeddings = openai_embed_model
        
    def ingest_document(self, title: str, markdown_text: str, source="upload"):
        """
        Splits markdown, creates a Document record, and inserts DocChunks.
        """
        # 1. Text Splitting Strategy
        headers_to_split_on = [("#", "H1"), ("##", "H2"), ("###", "H3")]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        header_splits = markdown_splitter.split_text(markdown_text)
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        final_chunks = text_splitter.split_documents(header_splits)
        return final_chunks

        with DatabaseManager() as db:
            # 2. Create Parent Document
            new_doc = Documents(
                title=title,
                source=source,
                description=markdown_text[:200] + "..."
            )
            db.session.add(new_doc)
            db.session.flush() # Flush to get new_doc.id

            # 3. Generate Embeddings
            texts = [c.page_content for c in final_chunks]
            vectors = self.embeddings.embed_documents(texts)

            # 4. Create Chunk Records
            chunk_objs = []
            for i, (chunk, vector) in enumerate(zip(final_chunks, vectors)):
                # Flatten metadata for storage (e.g., "H1: Intro, H2: Scope")
                meta_str = ", ".join([f"{k}: {v}" for k, v in chunk.metadata.items()])
                
                doc_chunk = DocChunk(
                    document_id=new_doc.id,
                    chunk_index=i,
                    chunk_text=chunk.page_content,
                    combined_text=f"Metadata: {meta_str}\n\nContent: {chunk.page_content}",
                    chunk_embed=vector,
                    affected_sectors=[] # Placeholder for advanced extraction
                )
                chunk_objs.append(doc_chunk)
            
            db.session.add_all(chunk_objs)
            # Commit handled by context manager
            
        return len(chunk_objs)

    # def hybrid_search(self, query: str, limit=5, alpha=60) -> List[DocChunk]:
    #     """
    #     Performs Vector Search + Keyword Search and merges via Reciprocal Rank Fusion (RRF).
    #     """
    #     query_vec = self.embeddings.embed_query(query)
        
    #     with DatabaseManager() as db:
    #         # 1. Vector Search (Semantic)
    #         # Using pgvector l2_distance or cosine_distance
    #         vector_results = db.session.execute(
    #             select(DocChunk)
    #             .order_by(DocChunk.chunk_embed.cosine_distance(query_vec))
    #             .limit(50)
    #         ).scalars().all()

    #         # 2. Keyword Search (Lexical)
    #         # Using Postgres websearch_to_tsquery for natural language support
    #         keyword_results = db.session.execute(
    #             select(DocChunk)
    #             .filter(func.to_tsvector('english', DocChunk.chunk_text)
    #             .op('@@')(func.websearch_to_tsquery('english', query)))
    #             .limit(50)
    #         ).scalars().all()

    #         # 3. RRF Fusion (Python-side)
    #         # Map {doc_id: score}
    #         rrf_score = {}

    #         # Process Vector Ranks
    #         for rank, doc in enumerate(vector_results):
    #             rrf_score[doc.id] = rrf_score.get(doc.id, 0) + (1 / (alpha + rank))

    #         # Process Keyword Ranks
    #         for rank, doc in enumerate(keyword_results):
    #             rrf_score[doc.id] = rrf_score.get(doc.id, 0) + (1 / (alpha + rank))

    #         # Sort by RRF Score
    #         sorted_ids = sorted(rrf_score, key=rrf_score.get, reverse=True)[:limit]
            
    #         # Fetch final objects in order
    #         # Note: We fetch all then sort in Python to maintain order
    #         final_docs = []
    #         lookup = {d.id: d for d in vector_results + keyword_results}
            
    #         for did in sorted_ids:
    #             if did in lookup:
    #                 final_docs.append(lookup[did])
                    
    #         return final_docs

    # def save_profile(self, name: str, bio: str, entity_type: str, products: List[str]):
    #     with DatabaseManager() as db:
    #         profile = CompanyProfile(
    #             company_name=name,
    #             about_text=bio,
    #             entity_type=entity_type,
    #             products=products
    #         )
    #         db.session.add(profile)

