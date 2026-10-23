"""
Text Chunking Strategy for RAG
Splits documents into smaller chunks for embedding
"""
from typing import List
from rag.document_loader import Document


class TextChunker:
    """Split documents into chunks for embedding"""
    
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        """
        Initialize chunker
        
        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks to preserve context
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks"""
        chunked_docs = []
        
        print(f"Chunking {len(documents)} documents")
        print(f"Chunk size: {self.chunk_size} chars")
        print(f"Overlap: {self.chunk_overlap} chars\n")
        
        for doc in documents:
            chunks = self._split_text(doc.page_content)
            
            for i, chunk_text in enumerate(chunks):
                chunk_doc = Document(
                    page_content=chunk_text,
                    metadata={
                        **doc.metadata,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "chunk_size": len(chunk_text)
                    }
                )
                chunked_docs.append(chunk_doc)
        
        print(f"Created {len(chunked_docs)} chunks from {len(documents)} documents\n")

        return chunked_docs

    @staticmethod
    def dedupe(chunks: List[Document]) -> List[Document]:
        """
        Drop chunks whose text already appeared.

        Manila_Ordinance_8331.json and 8341.json are byte-identical, so every
        matching passage used to fill two of the five retrieval slots.
        """
        seen = set()
        unique = []
        for chunk in chunks:
            key = " ".join(chunk.page_content.lower().split())
            if key in seen:
                continue
            seen.add(key)
            unique.append(chunk)
        if len(unique) < len(chunks):
            print(f"Dropped {len(chunks) - len(unique)} duplicate chunks\n")
        return unique
    
    def _split_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap"""
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Get chunk
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary if possible
            if end < len(text):
                # Look for sentence endings in last 100 chars
                last_period = chunk.rfind('. ')
                last_newline = chunk.rfind('\n')
                
                break_point = max(last_period, last_newline)
                
                if break_point > self.chunk_size - 200:  # Only if it's not too far back
                    chunk = chunk[:break_point + 1]
                    end = start + len(chunk)
            
            chunks.append(chunk.strip())
            
            # Move start position with overlap
            start = end - self.chunk_overlap
            
            # Avoid infinite loop
            if start <= 0 or start >= len(text):
                break
        
        return chunks


if __name__ == "__main__":
    # Test the chunker
    from rag.document_loader import DocumentLoader
    
    loader = DocumentLoader()
    docs = loader.load_all()
    
    chunker = TextChunker(chunk_size=800, chunk_overlap=150)
    chunks = chunker.chunk_documents(docs)
    
    print("\n" + "="*60)
    print("Sample Chunks:")
    print("="*60)
    
    for i, chunk in enumerate(chunks[:5], 1):
        print(f"\n{i}. {chunk.metadata['source']} (chunk {chunk.metadata['chunk_index']+1}/{chunk.metadata['total_chunks']})")
        print(f"Size: {chunk.metadata['chunk_size']} chars")
        print(f"Content: {chunk.page_content[:150]}...")
