"""Vector Store Management Creates and manages a FAISS vector database."""
import json
import os
import sys
import pickle
from pathlib import Path
from typing import List, Optional
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.document_loader import Document, DocumentLoader
from rag.chunker import TextChunker

META_FILENAME = "meta.json"


DEFAULT_LOCAL_MODEL = "intfloat/multilingual-e5-small"


class LocalEmbeddings:
    """Local sentence-transformers embeddings (FREE, no API calls)"""

    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL):
        """
        Initialize local embeddings model

        Args:
            model_name: HuggingFace model name. The default reads English,
                Filipino and Taglish; all-MiniLM-L6-v2 was English-only and
                matched Tagalog questions to unrelated passages.
        """
        from sentence_transformers import SentenceTransformer

        print(f"Loading embedding model: {model_name}")
        print("(Downloads on first run, then cached)")

        self.model_name = model_name
        # E5 models were trained with these prefixes and rank noticeably
        # worse without them.
        self.uses_e5_prefixes = "e5" in model_name.lower()
        self.model = SentenceTransformer(model_name)
        # Renamed in sentence-transformers 5.x; support both.
        get_dim = getattr(
            self.model,
            "get_embedding_dimension",
            self.model.get_sentence_embedding_dimension,
        )
        self.dimension = get_dim()
        
        print(f"Model loaded! Dimension: {self.dimension}\n")
    
    def encode(self, texts: List[str], batch_size: int = 32, show_progress: bool = True,
               is_query: bool = False) -> np.ndarray:
        """Generate embeddings for texts"""
        if self.uses_e5_prefixes:
            prefix = "query: " if is_query else "passage: "
            texts = [prefix + t for t in texts]
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=self.uses_e5_prefixes,
        )
        
        return embeddings


def build_embeddings(model: Optional[str] = None) -> LocalEmbeddings:
    """Construct the encoder; defaults to EMBEDDING_MODEL."""
    from utils.llm_client import get_settings

    return LocalEmbeddings(model or get_settings().embedding_model)


class VectorStore:
    """FAISS-based vector store"""

    def __init__(self, store_path: str = "./rag/vector_db"):
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)

        self.index = None
        self.documents = []
        self.embeddings_model = None
        self.provider = None

    def _meta_path(self) -> Path:
        return self.store_path / META_FILENAME

    def _load_meta(self) -> dict:
        """
        Read the provider/dimension this index was built with.

        Indexes built before meta.json existed are 384-dim MiniLM, so that is
        the fallback - it keeps existing stores loading without a rebuild.
        """
        path = self._meta_path()
        if not path.exists():
            return {"provider": "local", "dimension": 384, "model": "all-MiniLM-L6-v2"}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_meta(self) -> None:
        meta = {
            "provider": self.provider,
            "dimension": int(self.index.d),
            "model": getattr(self.embeddings_model, "model_name", "all-MiniLM-L6-v2"),
            "vectors": int(self.index.ntotal),
        }
        with open(self._meta_path(), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def create_from_documents(self, documents: List[Document]) -> None:
        """
        Create vector store from documents

        Args:
            documents: List of chunked documents
        """
        import faiss

        print("\nGenerating Embeddings")
        print("="*60)
        print(f"Processing {len(documents)} document chunks")
        print("="*60)
        print()

        self.provider = "local"
        self.embeddings_model = build_embeddings()

        # Extract texts
        texts = [doc.page_content for doc in documents]
        
        print(f"Generating embeddings (this may take 5-10 minutes)...")
        print()
        
        # Generate embeddings
        embeddings_array = self.embeddings_model.encode(
            texts,
            batch_size=32,
            show_progress=True
        )
        
        print(f"\nGenerated {len(embeddings_array)} embeddings")
        print(f"Embedding dimension: {embeddings_array.shape[1]}")
        
        # Create FAISS index
        dimension = embeddings_array.shape[1]
        
        # Use L2 distance for similarity
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings_array.astype('float32'))
        
        self.documents = documents
        
        print(f"FAISS index created with {self.index.ntotal} vectors\n")
        
        # Save to disk
        self.save()
    
    def save(self) -> None:
        """Save vector store to disk"""
        import faiss
        
        print("Saving vector store to disk...")
        
        # Save FAISS index
        index_path = self.store_path / "index.faiss"
        faiss.write_index(self.index, str(index_path))
        
        # Save documents
        docs_path = self.store_path / "documents.pkl"
        with open(docs_path, 'wb') as f:
            pickle.dump(self.documents, f)
        
        # Record which provider built this index so load() can pick the
        # matching encoder instead of trusting the current env var.
        self._write_meta()

        print(f"Saved to {self.store_path}")
        print(f"- index.faiss ({os.path.getsize(index_path) / 1024:.1f} KB)")
        print(f"- documents.pkl ({os.path.getsize(docs_path) / 1024:.1f} KB)")
        print(f"- meta.json (provider={self.provider}, dim={self.index.d})")
        print()
    
    def load(self) -> None:
        """Load vector store from disk"""
        import faiss
        
        index_path = self.store_path / "index.faiss"
        docs_path = self.store_path / "documents.pkl"
        
        if not index_path.exists() or not docs_path.exists():
            raise FileNotFoundError(f"Vector store not found at {self.store_path}")
        
        print(f"Loading vector store from {self.store_path}...")

        # Load FAISS index
        self.index = faiss.read_index(str(index_path))

        # Load documents
        with open(docs_path, 'rb') as f:
            self.documents = pickle.load(f)

        # The index dictates the encoder, not the env var
        meta = self._load_meta()
        self.provider = meta.get("provider", "local")
        indexed_dim = int(self.index.d)

        if int(meta.get("dimension", indexed_dim)) != indexed_dim:
            raise ValueError(
                f"{META_FILENAME} says dimension {meta.get('dimension')} but "
                f"index.faiss is {indexed_dim}. Rebuild with: uv run python -m rag.reindex"
            )

        if self.provider != "local":
            raise ValueError(
                f"This index was built with '{self.provider}' embeddings, which are no "
                f"longer supported. Rebuild with: uv run python -m rag.reindex"
            )

        # Queries must be encoded by the model that built the index, whatever
        # EMBEDDING_MODEL says now.
        self.embeddings_model = build_embeddings(meta.get("model"))

        if self.embeddings_model.dimension != indexed_dim:
            raise ValueError(
                f"Encoder produces {self.embeddings_model.dimension} dims but the "
                f"index is {indexed_dim}. Rebuild with: uv run python -m rag.reindex"
            )

        print(f"Loaded {self.index.ntotal} vectors and {len(self.documents)} documents\n")
    
    def vector_search(self, query: str, k: int = 3) -> List[int]:
        """Indices into self.documents of the k nearest chunks, best first."""
        if self.index is None:
            raise ValueError("Vector store not initialized. Call load() or create_from_documents() first.")

        if self.embeddings_model is None:
            self.embeddings_model = build_embeddings()

        query_embedding = self.embeddings_model.encode([query], show_progress=False,
                                                       is_query=True)
        distances, indices = self.index.search(query_embedding.astype('float32'), k)
        return [int(i) for i in indices[0] if 0 <= i < len(self.documents)]

    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        """Search for similar documents"""
        return [self.documents[i] for i in self.vector_search(query, k)]


def generate_embeddings():
    """
    Main function to generate embeddings (RUN ONCE!)
    """
    print("\n" + "="*60)
    print("  STEP 4: Generate Embeddings with LOCAL Model (FREE!)")
    print("="*60)
    print()
    print("Using sentence-transformers (all-MiniLM-L6-v2)")
    print("Cost: $0.00 (100% local, no API calls)")
    print("Time: ~5-10 minutes (one-time)")
    print()
    
    response = input("Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled")
        return False
    
    print()
    
    # Load documents
    print("Step 1: Loading documents...")
    loader = DocumentLoader()
    docs = loader.load_all()
    
    if len(docs) == 0:
        print("No documents found!")
        return False
    
    # Chunk documents
    print("Step 2: Chunking documents...")
    chunker = TextChunker(chunk_size=800, chunk_overlap=150)
    chunks = chunker.chunk_documents(docs)
    
    print(f"Ready to embed {len(chunks)} chunks\n")
    
    # Create vector store
    print("Step 3: Generating embeddings...")
    vector_store = VectorStore()
    
    try:
        vector_store.create_from_documents(chunks)
        
        print("="*60)
        print("EMBEDDINGS GENERATED AND SAVED!")
        print("="*60)
        print()
        print("IMPORTANT: Never run this again unless documents change!")
        print("All future queries will use the saved vector_db/")
        print()
        
        # Test search
        print("Testing vector search...")
        test_query = "What is Ordinance 8119?"
        results = vector_store.similarity_search(test_query, k=2)
        
        print(f"\nQuery: '{test_query}'")
        print(f"Found {len(results)} results:\n")
        
        for i, doc in enumerate(results, 1):
            print(f"{i}. {doc.metadata['source']}")
            print(f"   Ordinance: {doc.metadata.get('ordinance_number', 'N/A')}")
            print(f"   Preview: {doc.page_content[:150]}...\n")
        
        return True
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = generate_embeddings()
    
    if success:
        print("="*60)
        print("Success!")
        print("="*60)
    else:
        print("="*60)
        print("Fix the issues above before continuing")
        print("="*60)
