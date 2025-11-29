from utils import openai_embed_model
from typing import List, Dict, Any
from sqlalchemy import func, select, text
from database_manager.dao import DatabaseManager, DocChunk


class RAGEngine:
    def __init__(self):
        self.embeddings = openai_embed_model
        

    def hybrid_search(self, query: str, limit=5, alpha=60) -> List[DocChunk]:
        """
        Performs Vector Search + Keyword Search and merges via Reciprocal Rank Fusion (RRF).
        """
        query_vec = self.embeddings.embed_query(query)
        
        with DatabaseManager() as db:
            # 1. Vector Search (Semantic)
            # Using pgvector l2_distance or cosine_distance
            vector_results = db.session.execute(
                select(DocChunk)
                .order_by(DocChunk.chunk_embed.cosine_distance(query_vec))
                .limit(50)
            ).scalars().all()

            # 2. Keyword Search (Lexical)
            # Using Postgres websearch_to_tsquery for natural language support
            keyword_results = db.session.execute(
                select(DocChunk)
                .filter(func.to_tsvector('english', DocChunk.chunk_text)
                .op('@@')(func.websearch_to_tsquery('english', query)))
                .limit(50)
            ).scalars().all()

            # 3. RRF Fusion (Python-side)
            # Map {doc_id: score}
            rrf_score = {}

            # Process Vector Ranks
            for rank, doc in enumerate(vector_results):
                rrf_score[doc.id] = rrf_score.get(doc.id, 0) + (1 / (alpha + rank))

            # Process Keyword Ranks
            for rank, doc in enumerate(keyword_results):
                rrf_score[doc.id] = rrf_score.get(doc.id, 0) + (1 / (alpha + rank))

            # Sort by RRF Score
            sorted_ids = sorted(rrf_score, key=rrf_score.get, reverse=True)[:limit]
            
            # Fetch final objects in order
            # Note: We fetch all then sort in Python to maintain order
            final_docs = []
            lookup = {d.id: d for d in vector_results + keyword_results}
            
            for did in sorted_ids:
                if did in lookup:
                    final_docs.append(lookup[did])
                    
            return final_docs
