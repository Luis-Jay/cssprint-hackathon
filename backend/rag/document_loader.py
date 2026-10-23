"""
RAG Document Loader
Loads PDFs, JSONs, and TXT files from rag_documents/
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass


# Which permit stage each source speaks for, matched against the lowercased
# filename. First match wins; anything unmatched covers every stage.
SOURCE_AGENCIES = (
    ("bir", "bir"),
    ("dti", "dti"),
    # Despite its name, this file holds the text of Ordinance 8341.
    ("manila_ordinance_8331.json", "zoning"),
    ("8119", "zoning"),
    ("8341", "zoning"),          # amends the 8119 zoning ordinance
    ("8331", "mayors_permit"),   # 2013 Omnibus Revenue Code: business tax and fees
    ("revenue", "mayors_permit"),
    ("bpls", "mayors_permit"),
    ("citizens-charter-handbook-bop", "mayors_permit"),
    ("citizens_charter_2021", "mayors_permit"),
    ("online_permit_access", "mayors_permit"),
)


def source_agency(filename: str) -> str:
    """The agency a source file belongs to, or "general"."""
    name = (filename or "").lower()
    for marker, agency in SOURCE_AGENCIES:
        if marker in name:
            return agency
    return "general"


@dataclass
class Document:
    """Document with content and metadata"""
    page_content: str
    metadata: Dict[str, Any]
    
    def __repr__(self):
        content_preview = self.page_content[:100] + "..." if len(self.page_content) > 100 else self.page_content
        return f"Document(content='{content_preview}', metadata={self.metadata})"


class DocumentLoader:
    """Load documents from various file formats"""
    
    def __init__(self, base_path: str = "./rag_documents"):
        self.base_path = Path(base_path)
        
    def load_all(self) -> List[Document]:
        """Load all documents from rag_documents directory"""
        documents = []
        
        print("Loading documents from:", self.base_path)
        
        # Load PDFs
        pdf_docs = self.load_pdfs()
        print(f"Loaded {len(pdf_docs)} PDF documents")
        documents.extend(pdf_docs)
        
        # Load JSONs
        json_docs = self.load_jsons()
        print(f"Loaded {len(json_docs)} JSON documents")
        documents.extend(json_docs)
        
        # Load TXTs
        txt_docs = self.load_txts()
        print(f"Loaded {len(txt_docs)} TXT documents")
        documents.extend(txt_docs)
        
        for doc in documents:
            doc.metadata["agency"] = source_agency(doc.metadata["source"])

        print(f"\nTotal: {len(documents)} documents loaded\n")

        return documents
    
    def load_pdfs(self) -> List[Document]:
        """Load all PDF files"""
        from pypdf import PdfReader
        
        pdf_dir = self.base_path / "PDF FILES"
        if not pdf_dir.exists():
            print(f"PDF directory not found: {pdf_dir}")
            return []
        
        documents = []
        
        for pdf_file in pdf_dir.glob("*.pdf"):
            try:
                reader = PdfReader(str(pdf_file))
                
                # Extract text from all pages
                full_text = ""
                for page_num, page in enumerate(reader.pages, start=1):
                    text = page.extract_text()
                    if text.strip():
                        full_text += f"\n\n--- Page {page_num} ---\n\n{text}"
                
                if full_text.strip():
                    # Extract ordinance number if present
                    ordinance_num = self._extract_ordinance_number(pdf_file.name)
                    
                    doc = Document(
                        page_content=full_text.strip(),
                        metadata={
                            "source": str(pdf_file.name),
                            "file_path": str(pdf_file),
                            "document_type": "pdf",
                            "ordinance_number": ordinance_num,
                            "num_pages": len(reader.pages)
                        }
                    )
                    documents.append(doc)
                    
            except Exception as e:
                print(f"Error loading {pdf_file.name}: {e}")
        
        return documents
    
    def load_jsons(self) -> List[Document]:
        """Load all JSON files"""
        json_dir = self.base_path / "JSON FILES"
        if not json_dir.exists():
            print(f"JSON directory not found: {json_dir}")
            return []
        
        documents = []
        
        for json_file in json_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Convert JSON to readable text
                text = self._json_to_text(data, json_file.name)
                
                if text.strip():
                    doc = Document(
                        page_content=text.strip(),
                        metadata={
                            "source": str(json_file.name),
                            "file_path": str(json_file),
                            "document_type": "json",
                            "ordinance_number": self._extract_ordinance_number(json_file.name)
                        }
                    )
                    documents.append(doc)
                    
            except Exception as e:
                print(f"Error loading {json_file.name}: {e}")
        
        return documents
    
    def load_txts(self) -> List[Document]:
        """Load all TXT files"""
        txt_dir = self.base_path / "TXT FILES"
        if not txt_dir.exists():
            print(f"TXT directory not found: {txt_dir}")
            return []
        
        documents = []
        
        for txt_file in txt_dir.glob("*.txt"):
            try:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    text = f.read()
                
                if text.strip():
                    doc = Document(
                        page_content=text.strip(),
                        metadata={
                            "source": str(txt_file.name),
                            "file_path": str(txt_file),
                            "document_type": "txt",
                            "ordinance_number": self._extract_ordinance_number(txt_file.name)
                        }
                    )
                    documents.append(doc)
                    
            except Exception as e:
                print(f"Error loading {txt_file.name}: {e}")
        
        return documents
    
    def _json_to_text(self, data: Any, filename: str) -> str:
        """Convert JSON data to readable text format"""
        
        def format_dict(d: dict, indent: int = 0) -> str:
            lines = []
            prefix = "  " * indent
            
            for key, value in d.items():
                if isinstance(value, dict):
                    lines.append(f"{prefix}{key}:")
                    lines.append(format_dict(value, indent + 1))
                elif isinstance(value, list):
                    lines.append(f"{prefix}{key}:")
                    for item in value:
                        if isinstance(item, dict):
                            lines.append(format_dict(item, indent + 1))
                        else:
                            lines.append(f"{prefix}  - {item}")
                else:
                    lines.append(f"{prefix}{key}: {value}")
            
            return "\n".join(lines)
        
        header = f"=== {filename} ===\n\n"
        
        if isinstance(data, dict):
            return header + format_dict(data)
        elif isinstance(data, list):
            content = "\n\n".join([format_dict(item) if isinstance(item, dict) else str(item) for item in data])
            return header + content
        else:
            return header + str(data)
    
    def _extract_ordinance_number(self, filename: str) -> str:
        """Extract ordinance number from filename"""
        import re
        
        # Match patterns like "8119", "8331", "Ordinance_8341", etc.
        patterns = [
            r'Ordinance[_\s-]*(\d{4,})',
            r'ordinance[_\s-]*(\d{4,})',
            r'ORDINANCE[_\s-]*(\d{4,})',
            r'(\d{4,})',
        ]
        
        filename_lower = filename.lower()
        
        for pattern in patterns:
            match = re.search(pattern, filename_lower, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return "unknown"


if __name__ == "__main__":
    # Test the loader
    loader = DocumentLoader()
    docs = loader.load_all()
    
    print("\n" + "="*60)
    print("Sample Documents:")
    print("="*60)
    
    for i, doc in enumerate(docs[:3], 1):
        print(f"\n{i}. {doc.metadata['source']}")
        print(f"Type: {doc.metadata['document_type']}")
        print(f"Ordinance: {doc.metadata.get('ordinance_number', 'N/A')}")
        print(f"Content length: {len(doc.page_content)} chars")
        print(f"Preview: {doc.page_content[:200]}...")
