"""
RAG Retrieval Pipeline
Retrieve relevant context from vector store for LLM queries
"""
import logging
import threading
from pathlib import Path
from typing import List, Optional

from rag.vector_store import VectorStore
from rag.document_loader import Document
from rag.ranking import BM25, detect_agencies, fuse, rerank

logger = logging.getLogger(__name__)

# Anchor on the package directory rather than the process CWD, so the store
# resolves no matter where uvicorn is launched from.
DEFAULT_STORE_PATH = str(Path(__file__).resolve().parent / "vector_db")

SEPARATOR = "\n\n---\n\n"


class RAGRetriever:
    """Retrieve relevant context from vector store"""

    def __init__(self, vector_store_path: str = DEFAULT_STORE_PATH):
        self.vector_store = VectorStore(store_path=vector_store_path)
        self.vector_store.load()
        docs = self.vector_store.documents
        self.bm25 = BM25([d.page_content for d in docs])
        self.sources = [d.metadata.get("source", "Unknown") for d in docs]

    def search(self, query: str, k: int) -> List[Document]:
        """
        Hybrid search: vector and keyword candidates fused, then steered
        toward the permit stage the question is about.
        """
        pool = max(k * 8, 40)
        scores = fuse([
            self.vector_store.vector_search(query, pool),
            self.bm25.search(query, pool),
        ])
        agencies = detect_agencies(query)
        picked = rerank(scores, self.sources, agencies, k)
        return [self.vector_store.documents[i] for i in picked]

    def retrieve_context(
        self,
        query: str,
        top_k: int = 3,
        filter_ordinance: Optional[str] = None,
        max_chars: Optional[int] = None
    ) -> str:
        """Retrieve relevant context for a query"""
        import observability as obs

        # Only over-fetch when we are going to filter results away
        k = top_k * 2 if filter_ordinance else top_k
        with obs.span("retrieval", f"Searching {self.vector_store.index.ntotal} "
                                   f"ordinance chunks", query=query, top_k=top_k) as sp:
            results = self.search(query, k)
            sp["hits"] = len(results)
            sp["agencies"] = sorted(detect_agencies(query))

        if filter_ordinance:
            results = [
                doc for doc in results
                if doc.metadata.get("ordinance_number") == filter_ordinance
            ][:top_k]
        else:
            results = results[:top_k]

        # Format context
        context_parts = []

        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "Unknown")
            ordinance = doc.metadata.get("ordinance_number", "N/A")

            context_parts.append(
                f"[Source {i}: {source} | Ordinance {ordinance}]\n{doc.page_content}"
            )

        # Report what was actually retrieved, per source, so the UI can show
        # which ordinances the answer is standing on.
        sources = [
            {
                "source": doc.metadata.get("source", "Unknown"),
                "ordinance": doc.metadata.get("ordinance_number", "N/A"),
                "chars": len(doc.page_content),
                "preview": doc.page_content[:220],
            }
            for doc in results
        ]

        if max_chars is None:
            obs.emit("retrieval", f"Retrieved {len(results)} chunks",
                     chunks=len(results), sources=sources)
            return SEPARATOR.join(context_parts)

        # Trim on chunk boundaries instead of mid-sentence
        kept: List[str] = []
        used = 0
        for part in context_parts:
            cost = len(part) + (len(SEPARATOR) if kept else 0)
            if used + cost > max_chars:
                break
            kept.append(part)
            used += cost

        obs.emit(
            "retrieval",
            f"Kept {len(kept)} of {len(results)} chunks ({used} chars)",
            status="warn" if len(kept) < len(results) else "ok",
            chunks_retrieved=len(results),
            chunks_kept=len(kept),
            chars=used,
            budget=max_chars,
            sources=sources[:len(kept)],
            dropped=[s["source"] for s in sources[len(kept):]],
        )
        return SEPARATOR.join(kept)

    def retrieve_documents(
        self,
        query: str,
        top_k: int = 3
    ) -> List[Document]:
        """Retrieve relevant documents (not just text)"""
        return self.search(query, top_k)

    def close(self):
        """
        No-op, kept for backwards compatibility.

        The retriever is a process-wide singleton (see get_retriever); tearing
        it down per request is exactly the behaviour that cost 7s a call.
        """
        pass


_retriever: Optional[RAGRetriever] = None
_retriever_lock = threading.Lock()


def get_retriever(vector_store_path: str = DEFAULT_STORE_PATH) -> RAGRetriever:
    """Process-wide singleton retriever."""
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:  # double-checked under the lock
                logger.info("Building RAG retriever (one-time, ~7s)...")
                _retriever = RAGRetriever(vector_store_path)
                logger.info("RAG retriever ready")
    return _retriever


def test_retriever():
    """Test the RAG retriever"""
    print("\n" + "="*60)
    print("  Testing RAG Retriever")
    print("="*60)
    print()

    try:
        retriever = get_retriever()

        # Test queries
        test_queries = [
            "What is Ordinance 8119?",
            "What documents do I need for DTI registration?",
            "What are the BIR requirements for online sellers?",
            "What is the process for getting a Mayor's permit in Manila?"
        ]

        for query in test_queries:
            print(f"\nQuery: '{query}'")
            print("-" * 60)

            context = retriever.retrieve_context(query, top_k=2)

            # Show preview
            preview = context[:300] + "..." if len(context) > 300 else context
            print(preview)
            print()

        print("="*60)
        print("RAG Retriever Working!")
        print("="*60)

    except FileNotFoundError:
        print("Vector store not found!")
        print("Run: python rag/vector_store.py")
        print()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_retriever()
