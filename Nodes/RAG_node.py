import os
from typing import Dict, List, Any, Optional
from pathlib import Path
from dataclasses import dataclass

from langchain_community.document_loaders import PyPDFLoader  # Reverted to PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.schema import Document
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
import arabic_reshaper
from bidi.algorithm import get_display
from langdetect import detect

@dataclass
class VisaRAGConfig:
    """Configuration for the Visa RAG system"""
    pdf_directory: str = "/Users/mazinsaleh/Desktop/Travel-Agent-Final/visa_pdfs"
    chunk_size: int = 1000
    chunk_overlap: int = 300
    top_k: int = 5
    embeddings_model: str = "text-embedding-ada-002"
    vector_store_path: str = "./visa_vector_store"
    llm_model: str = "gpt-4o-mini"

class VisaRAGSystem:
    """RAG System for visa requirements with LLM generation"""
    
    def __init__(self, config: VisaRAGConfig):
        self.config = config
        self.embeddings = OpenAIEmbeddings(model=config.embeddings_model)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", " ", ""]
        )
        self.llm = ChatOpenAI(model=config.llm_model, temperature=0.0)
        self.vector_store = None
        self._load_or_create_vector_store()
    
    def _load_or_create_vector_store(self):
        """Load existing vector store or create new one"""
        vector_store_path = Path(self.config.vector_store_path)
        
        if vector_store_path.exists():
            print("Loading existing vector store...")
            self.vector_store = FAISS.load_local(
                str(vector_store_path), 
                self.embeddings,
                allow_dangerous_deserialization=True
            )
        else:
            print("Creating new vector store...")
            self._create_vector_store()
    
    def _create_vector_store(self):
        """Create vector store from PDF documents"""
        documents = self._load_all_pdfs()
        
        if not documents:
            raise ValueError("No documents found to create vector store")
        
        chunks = self.text_splitter.split_documents(documents)
        self.vector_store = FAISS.from_documents(chunks, self.embeddings)
        os.makedirs(self.config.vector_store_path, exist_ok=True)
        self.vector_store.save_local(self.config.vector_store_path)
        print(f"Created vector store with {len(chunks)} chunks from {len(documents)} documents")
    
    def _load_all_pdfs(self) -> List[Document]:
        """Load all PDF files from the specified directory with preprocessing"""
        documents = []
        pdf_dir = Path(self.config.pdf_directory)
        print("hiiiii", pdf_dir)
        
        if not pdf_dir.exists():
            print(f"Warning: PDF directory {pdf_dir} does not exist")
            return documents
        
        pdf_files = list(pdf_dir.glob("*.pdf"))
        print(pdf_files, "heyyyyyy")
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
    
    def extract_country_from_query(self, query: str) -> Optional[str]:
        """Extract country name from user query"""
        query_lower = query.lower()
        
        if self.vector_store:
            all_docs = self.vector_store.docstore._dict.values()
            countries = set()
            for doc in all_docs:
                if hasattr(doc, 'metadata') and 'country' in doc.metadata:
                    countries.add(doc.metadata['country'].lower())
            
            for country in countries:
                if country in query_lower:
                    return country.title()
        
        return None
    
    def retrieve_documents(self, query: str, country_filter: Optional[str] = None) -> List[Document]:
        """Retrieve relevant documents based on query"""
        if not self.vector_store:
            return []
        
        docs = self.vector_store.similarity_search(query, k=self.config.top_k)
        
        if country_filter:
            filtered_docs = []
            for doc in docs:
                doc_country = doc.metadata.get('country', '').lower()
                if country_filter.lower() in doc_country or doc_country in country_filter.lower():
                    filtered_docs.append(doc)
            docs = filtered_docs
        
        return docs
    
    def answer_query(self, query: str) -> str:
        """Single-node processing: Extract country, retrieve docs, and generate answer with LLM"""
        country = self.extract_country_from_query(query)
        documents = self.retrieve_documents(query, country)
        
        if not documents:
            return f"I couldn't find specific visa requirements for {country or 'the requested country'}. Please check if the country name is correct or if we have information available."
        
        doc_contents = "\n\n".join([
            f"Document from {doc.metadata.get('country', 'Unknown')} (Language: {doc.metadata.get('language', 'Unknown')}, Page {doc.metadata.get('page', 'N/A')}):\n{doc.page_content}"
            for doc in documents
        ])
        doc_contents = doc_contents[:10000]
        
        prompt_template = PromptTemplate.from_template(
            """You are a visa requirements expert. Based ONLY on the following documents extracted from official PDF sources, 
            answer the user's query about visa requirements. Do not add external knowledge. If the documents don't cover the query, say so.
            If text is in Arabic, translate key parts to English in your summary.

            Query: {query}
            Country (if detected): {country}
            Date Check: {date_check}

            Documents:
            {doc_contents}
            
            Provide a clear, comprehensive answer in Markdown format, including:
            - Key requirements (e.g., documents needed)
            - Application process
            - Any notes or caveats
            """
        )
        
        chain = prompt_template | self.llm
        response = chain.invoke({
            "query": query,
            "country": country or "Not specified",
            "date_check": documents[0].metadata.get("date_check", "No date found"),
            "doc_contents": doc_contents
        })
        
        return response.content

def main():
    # Set up API key (replace with your actual key)
    os.environ["OPENAI_API_KEY"] = "OPENAI_API_KEY"  # Replace with valid key
    
    config = VisaRAGConfig()
    rag_system = VisaRAGSystem(config)
    
    queries = [
        "What are the visa requirements for Angola?",
        "I need to know the documents required for Angola visa",
        "متطلبات التأشيرة لأنغولا",  # Arabic query
    ]
    
    for query in queries:
        print(f"\n{'='*50}")
        print(f"Query: {query}")
        print(f"{'='*50}")
        
        answer = rag_system.answer_query(query)
        print(f"\nAnswer:\n{answer}")

if __name__ == "__main__":
    main()