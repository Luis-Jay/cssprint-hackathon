"""Rebuild the FAISS index."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.document_loader import DocumentLoader
from rag.chunker import TextChunker
from rag.vector_store import VectorStore
from utils.llm_client import get_settings


def reindex() -> bool:
    settings = get_settings()

    base = Path(__file__).resolve().parent.parent
    store_path = str(Path(__file__).resolve().parent / "vector_db")

    print()
    print("=" * 60)
    print("  Rebuilding vector index")
    print("=" * 60)
    print(f"  model:     {settings.embedding_model}")
    print(f"  store:     {store_path}")
    print()

    print("Step 1: Loading documents...")
    loader = DocumentLoader(base_path=str(base / "rag_documents"))
    docs = loader.load_all()
    if not docs:
        print("No documents found!")
        return False

    print("Step 2: Chunking documents...")
    chunker = TextChunker(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = TextChunker.dedupe(chunker.chunk_documents(docs))
    print(f"Ready to embed {len(chunks)} chunks\n")

    print("Step 3: Generating embeddings...")
    t0 = time.perf_counter()
    store = VectorStore(store_path=store_path)
    store.create_from_documents(chunks)
    elapsed = time.perf_counter() - t0

    print("=" * 60)
    print(f"  Reindex complete in {elapsed:.1f}s")
    print(f"  {store.index.ntotal} vectors at {store.index.d} dims")
    print("=" * 60)
    print()
    return True


def main():
    argparse.ArgumentParser(
        description="Rebuild the FAISS index from rag_documents/ with EMBEDDING_MODEL"
    ).parse_args()
    sys.exit(0 if reindex() else 1)


if __name__ == "__main__":
    main()
