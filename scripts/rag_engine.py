#!/usr/bin/env python3
"""
Simple RAG engine — vector DB for persistent knowledge retrieval.
Uses TF-IDF (no external dependencies) for semantic search.
"""
import re
import math
import json
import os
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional
from pathlib import Path


class SimpleVectorDB:
    """
    Simple vector database using TF-IDF.
    No external dependencies — pure Python.
    Stores documents and retrieves by semantic similarity.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self.documents = []  # [{id, text, metadata}]
        self.vocabulary = set()
        self.idf = {}
        self.tf_cache = {}
        
        if db_path and db_path.exists():
            self.load()
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        text = text.lower()
        tokens = re.findall(r'\b\w+\b', text)
        return tokens
    
    def _compute_tf(self, text: str) -> Dict[str, float]:
        """Compute term frequency."""
        tokens = self._tokenize(text)
        if not tokens:
            return {}
        counter = Counter(tokens)
        total = len(tokens)
        return {term: count / total for term, count in counter.items()}
    
    def _compute_idf(self):
        """Compute inverse document frequency."""
        N = len(self.documents)
        if N == 0:
            return
        
        # Count documents containing each term
        df = defaultdict(int)
        for doc in self.documents:
            tokens = set(self._tokenize(doc['text']))
            for token in tokens:
                df[token] += 1
        
        # IDF = log(N / df)
        self.idf = {term: math.log(N / (df_count + 1)) for term, df_count in df.items()}
        self.vocabulary = set(self.idf.keys())
    
    def _compute_tfidf_vector(self, text: str) -> Dict[str, float]:
        """Compute TF-IDF vector for a text."""
        tf = self._compute_tf(text)
        return {term: tf_val * self.idf.get(term, 0) for term, tf_val in tf.items()}
    
    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Compute cosine similarity between two sparse vectors."""
        if not vec1 or not vec2:
            return 0.0
        
        # Dot product
        common_terms = set(vec1.keys()) & set(vec2.keys())
        dot_product = sum(vec1[t] * vec2[t] for t in common_terms)
        
        # Magnitudes
        mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot_product / (mag1 * mag2)
    
    def add_document(self, text: str, metadata: Optional[Dict] = None) -> str:
        """Add a document to the DB."""
        doc_id = f"doc_{len(self.documents)}"
        self.documents.append({
            'id': doc_id,
            'text': text,
            'metadata': metadata or {},
        })
        # Recompute IDF (could be optimized)
        self._compute_idf()
        return doc_id
    
    def add_documents(self, texts: List[str], metadatas: Optional[List[Dict]] = None) -> List[str]:
        """Add multiple documents."""
        ids = []
        for i, text in enumerate(texts):
            meta = metadatas[i] if metadatas and i < len(metadatas) else None
            doc_id = f"doc_{len(self.documents)}"
            self.documents.append({
                'id': doc_id,
                'text': text,
                'metadata': meta or {},
            })
            ids.append(doc_id)
        self._compute_idf()
        return ids
    
    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Search for similar documents."""
        if not self.documents:
            return []
        
        query_vec = self._compute_tfidf_vector(query)
        
        results = []
        for doc in self.documents:
            doc_vec = self._compute_tfidf_vector(doc['text'])
            similarity = self._cosine_similarity(query_vec, doc_vec)
            results.append({
                'id': doc['id'],
                'text': doc['text'],
                'metadata': doc['metadata'],
                'similarity': similarity,
            })
        
        # Sort by similarity descending
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def save(self):
        """Save DB to disk."""
        if not self.db_path:
            return
        data = {
            'documents': self.documents,
            'vocabulary': list(self.vocabulary),
            'idf': self.idf,
        }
        self.db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    
    def load(self):
        """Load DB from disk."""
        if not self.db_path or not self.db_path.exists():
            return
        data = json.loads(self.db_path.read_text())
        self.documents = data.get('documents', [])
        self.vocabulary = set(data.get('vocabulary', []))
        self.idf = data.get('idf', {})


# === RAG Engine ===

class RAGEngine:
    """
    Retrieval-Augmented Generation engine.
    1. Indexes knowledge (documents, facts, examples)
    2. Retrieves relevant context before generation
    3. Augments prompt with retrieved context
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db = SimpleVectorDB(db_path)
        self.context_cache = {}
    
    def index_knowledge(self, texts: List[str], metadatas: Optional[List[Dict]] = None):
        """Index knowledge base."""
        self.db.add_documents(texts, metadatas)
        if self.db.db_path:
            self.db.save()
        print(f"[RAG] Indexed {len(texts)} documents. Total: {len(self.db.documents)}")
    
    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """Retrieve relevant context for a query."""
        results = self.db.search(query, top_k=top_k)
        if not results:
            return ""
        
        # Build context string
        context_parts = []
        for i, r in enumerate(results):
            if r['similarity'] > 0.01:  # threshold
                context_parts.append(f"[Context {i+1}] (similarity: {r['similarity']:.2f})\n{r['text'][:500]}")
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    def augment_prompt(self, system_prompt: str, user_prompt: str, top_k: int = 3) -> str:
        """Augment user prompt with retrieved context."""
        context = self.retrieve_context(user_prompt, top_k=top_k)
        if context:
            return f"{user_prompt}\n\n=== RELEVANT CONTEXT ===\n{context}\n=== END CONTEXT ==="
        return user_prompt
    
    def stats(self) -> Dict:
        """Return DB statistics."""
        return {
            'total_documents': len(self.db.documents),
            'vocabulary_size': len(self.db.vocabulary),
            'db_path': str(self.db.db_path) if self.db.db_path else None,
        }


if __name__ == "__main__":
    print("=== RAG Engine Test ===\n")
    
    rag = RAGEngine()
    
    # Index some knowledge
    knowledge = [
        "GLM-5 is the latest model from Zhipu AI, released in 2025. It supports multimodal input including text, images, and documents.",
        "GPT-5 from OpenAI was released in 2025. It excels at reasoning and coding tasks. Cost: $20/month for Plus tier.",
        "Qwen3.5-4B is an open-source model from Alibaba, released February 2026. It runs on consumer hardware with 4GB+ RAM.",
        "Claude 4.8 from Anthropic released in 2026. Known for strong safety features and long context window (200k tokens).",
        "Gemma 4 from Google released April 2026. Available in E2B, E4B, 12B, 26B MoE, and 31B Dense variants. Apache 2.0 license.",
    ]
    
    rag.index_knowledge(knowledge)
    
    # Test retrieval
    queries = [
        "What is the latest Zhipu model?",
        "Which models are open source?",
        "What model runs on consumer hardware?",
    ]
    
    for q in queries:
        print(f"\nQuery: {q}")
        context = rag.retrieve_context(q, top_k=2)
        print(f"Context:\n{context[:300]}")
    
    print(f"\n\nStats: {rag.stats()}")
