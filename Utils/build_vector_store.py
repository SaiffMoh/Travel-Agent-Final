from typing import List
from pathlib import Path
from dataclasses import dataclass
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
import arabic_reshaper
from bidi.algorithm import get_display
from langdetect import detect
from dotenv import load_dotenv
import os

load_dotenv('.env')

@dataclass
class VisaRAGConfig:
    """Configuration for the Visa RAG system"""
    pdf_directory: str = "data/visa_pdfs"
    chunk_size: int = 1000
    chunk_overlap: int = 300
    embeddings_model: str = "text-embedding-ada-002"
    vector_store_path: str = "data/visa_vector_store"

def load_all_pdfs(config: VisaRAGConfig) -> List[Document]:
    """Load all PDF files from the specified directory with preprocessing"""
    documents = []
    pdf_dir = Path(config.pdf_directory)
    
    if not pdf_dir.exists():
        print(f"Warning: PDF directory {pdf_dir} does not exist")
        return documents
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    for pdf_file in pdf_files:
        try:
            country_name = pdf_file.stem.replace("_", " ").title()
            loader = PyPDFLoader(str(pdf_file))
            docs = loader.load()
            
            for doc in docs:
                # Preprocess Arabic text
                if any(c >= '\u0600' and c <= '\u06FF' for c in doc.page_content):
                    reshaped = arabic_reshaper.reshape(doc.page_content)
                    doc.page_content = get_display(reshaped)
                # Detect language and add to metadata
                lang = detect(doc.page_content)
                doc.metadata.update({
                    "country": country_name,
                    "source_file": str(pdf_file),
                    "doc_type": "visa_requirements",
                    "language": lang
                })
                # Simple date check (placeholder; enhance with regex for real dates)
                doc.metadata["date_check"] = "No date found" if "date" not in doc.page_content.lower() else "Date present"
            
            documents.extend(docs)
            print(f"Loaded {len(docs)} pages from {pdf_file}")
            
        except Exception as e:
            print(f"Error loading {pdf_file}: {e}")
    
    return documents

def create_vector_store():
    config = VisaRAGConfig()
    embeddings = OpenAIEmbeddings(model=config.embeddings_model)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    
    documents = load_all_pdfs(config)
    
    if not documents:
        raise ValueError("No documents found to create vector store")
    
    chunks = text_splitter.split_documents(documents)
    vector_store = FAISS.from_documents(chunks, embeddings)
    os.makedirs(config.vector_store_path, exist_ok=True)
    vector_store.save_local(config.vector_store_path)
    print(f"Created vector store with {len(chunks)} chunks from {len(documents)} documents")

if __name__ == "__main__":
    create_vector_store()