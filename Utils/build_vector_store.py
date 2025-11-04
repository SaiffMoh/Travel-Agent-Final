from typing import List, Dict
from pathlib import Path
from dataclasses import dataclass
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
import arabic_reshaper
from bidi.algorithm import get_display
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
import os
import json
import re
from difflib import SequenceMatcher
import numpy as np

load_dotenv('.env')

@dataclass
class VisaRAGConfig:
    """Configuration for the Visa RAG system"""
    pdf_directory: str = "data/visa_pdfs"
    chunk_size: int = 1500
    chunk_overlap: int = 300
    embeddings_model: str = "multi-qa-mpnet-base-dot-v1"
    base_vector_store_path: str = "data/visa_vector_stores"
    country_mapping_file: str = "data/country_mapping.json"

def extract_country_from_filename(pdf_file: Path) -> str:
    """Extract and normalize country name from PDF filename"""
    country_raw = pdf_file.stem.replace("_", " ").replace("-", " ")
    country_cleaned = re.sub(r'\b(visa|requirements?|info|information)\b', '', country_raw, flags=re.IGNORECASE)
    country_cleaned = country_cleaned.strip()
    country_name = " ".join(word.capitalize() for word in country_cleaned.split())
    return country_name if country_name else pdf_file.stem.title()

def assess_text_quality(text: str) -> Dict[str, any]:
    """Assess the quality of extracted text from PDF"""
    if not text or len(text.strip()) < 10:
        return {"quality": "poor", "reason": "too_short", "confidence": 0.0}
    
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    latin_chars = sum(1 for c in text if c.isalpha() and c < '\u0600')
    total_chars = len([c for c in text if c.isalpha()])
    
    if total_chars == 0:
        return {"quality": "poor", "reason": "no_text", "confidence": 0.0}
    
    corruption_indicators = [
        len(re.findall(r'[^\w\s\u0600-\u06FF.,!?()-]', text)),
        len(re.findall(r'\s{3,}', text)),
        len(re.findall(r'[A-Z]{5,}', text)),
        text.count('ﻭ') + text.count('ﺔ') > len(text) * 0.3
    ]
    
    corruption_score = sum(1 for indicator in corruption_indicators if indicator)
    
    if corruption_score >= 3:
        quality = "poor"
        confidence = 0.2
    elif corruption_score >= 2:
        quality = "medium"
        confidence = 0.6
    else:
        quality = "good"
        confidence = 0.9
    
    if arabic_chars > 0 and latin_chars > 0:
        mixed_ratio = min(arabic_chars, latin_chars) / max(arabic_chars, latin_chars)
        if mixed_ratio > 0.3:
            confidence *= 0.7
    
    return {
        "quality": quality,
        "confidence": confidence,
        "arabic_ratio": arabic_chars / total_chars if total_chars > 0 else 0,
        "latin_ratio": latin_chars / total_chars if total_chars > 0 else 0,
        "corruption_score": corruption_score,
        "total_length": len(text)
    }

def clean_extracted_text(text: str) -> str:
    """Clean and normalize extracted text"""
    if not text:
        return text
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove Arabic diacritics
    text = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', text)
    # Fix spaced letters
    text = re.sub(r'([a-zA-Z])\s+([a-zA-Z])\s+([a-zA-Z])', r'\1\2\3', text)
    
    # Remove very short lines and lines with only symbols
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if len(line) > 3 and not re.match(r'^[^\w\s]*$', line):
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines).strip()

def reassemble_fragments(text: str, similarity_threshold: float = 0.6) -> str:
    """Reassemble OCR fragments in mixed-language text."""
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 5]
    
    reassembled = []
    i = 0
    while i < len(lines):
        current = lines[i]
        j = i + 1
        while j < len(lines):
            similarity = SequenceMatcher(None, current.lower(), lines[j].lower()).ratio()
            if similarity > similarity_threshold and any(keyword in lines[j].lower() for keyword in ['photo', 'passport', 'invitation', 'bank', 'applicant', 'letter', 'statement']):
                current += ' ' + lines[j]
                j += 1
            else:
                break
        reassembled.append(current)
        i = j
    
    return re.sub(r'\s+', ' ', ' '.join(reassembled))

def enhanced_load_pdf_for_country(pdf_file: Path, country_name: str) -> List[Document]:
    """Enhanced PDF loading with quality assessment and fragment reassembly"""
    documents = []
    
    try:
        loader = PyPDFLoader(str(pdf_file))
        docs = loader.load()
        
        for doc in docs:
            quality_info = assess_text_quality(doc.page_content)
            original_content = doc.page_content
            cleaned_content = clean_extracted_text(original_content)
            cleaned_content = reassemble_fragments(cleaned_content)
            
            if quality_info['arabic_ratio'] > 0.1:
                try:
                    reshaped = arabic_reshaper.reshape(cleaned_content)
                    cleaned_content = get_display(reshaped)
                except Exception as e:
                    print(f"Warning: Arabic processing failed for {pdf_file}: {e}")
            
            try:
                lang = detect(cleaned_content)
            except:
                lang = "mixed" if quality_info['arabic_ratio'] > 0.1 and quality_info['latin_ratio'] > 0.1 else "unknown"
            
            doc.page_content = cleaned_content
            doc.metadata.update({
                "country": country_name,
                "country_normalized": country_name.lower().replace(" ", "_"),
                "source_file": str(pdf_file),
                "doc_type": "visa_requirements",
                "language": lang,
                "text_quality": quality_info['quality'],
                "quality_confidence": quality_info['confidence'],
                "arabic_ratio": quality_info['arabic_ratio'],
                "latin_ratio": quality_info['latin_ratio'],
                "original_length": len(original_content),
                "cleaned_length": len(cleaned_content),
                "file_size": pdf_file.stat().st_size if pdf_file.exists() else 0
            })
            
            if quality_info['quality'] == 'poor':
                doc.page_content = f"[WARNING: Poor text extraction quality - content may be unreliable]\n\n{doc.page_content}"
            elif quality_info['quality'] == 'medium':
                doc.page_content = f"[NOTE: Text extraction may contain some errors]\n\n{doc.page_content}"
        
        documents.extend(docs)
        avg_quality = sum(assess_text_quality(doc.page_content)['confidence'] for doc in docs) / len(docs) if docs else 0
        print(f"✓ Loaded {len(docs)} pages from {pdf_file} for {country_name} (avg quality: {avg_quality:.2f})")
        
    except Exception as e:
        print(f"✗ Error loading {pdf_file}: {e}")
    
    return documents

def create_country_vector_stores():
    """Create separate vector stores for each country"""
    config = VisaRAGConfig()
    
    # Use HuggingFaceEmbeddings for LangChain compatibility
    embeddings = HuggingFaceEmbeddings(
        model_name=config.embeddings_model,
        model_kwargs={'device': 'cpu'}
    )
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    pdf_dir = Path(config.pdf_directory)
    base_store_dir = Path(config.base_vector_store_path)
    
    if not pdf_dir.exists():
        raise ValueError(f"PDF directory {pdf_dir} does not exist")
    
    base_store_dir.mkdir(parents=True, exist_ok=True)
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        raise ValueError(f"No PDF files found in {pdf_dir}")
    
    print(f"Found {len(pdf_files)} PDF files to process...")
    
    country_mapping = {}
    successful_countries = []
    failed_countries = []
    
    for pdf_file in pdf_files:
        try:
            country_name = extract_country_from_filename(pdf_file)
            country_key = country_name.lower().replace(" ", "_")
            
            print(f"\n🔄 Processing {country_name} ({pdf_file.name})...")
            
            documents = enhanced_load_pdf_for_country(pdf_file, country_name)
            
            if not documents:
                print(f"⚠️  No documents loaded for {country_name}, skipping...")
                failed_countries.append(country_name)
                continue
            
            # Split documents into chunks
            chunks = text_splitter.split_documents(documents)
            
            if not chunks:
                print(f"⚠️  No chunks created for {country_name}, skipping...")
                failed_countries.append(country_name)
                continue
            
            # Create FAISS vector store from documents
            vector_store = FAISS.from_documents(
                documents=chunks,
                embedding=embeddings
            )
            
            # Save vector store
            country_store_path = base_store_dir / country_key
            country_store_path.mkdir(exist_ok=True)
            vector_store.save_local(str(country_store_path))
            
            # Store mapping information
            country_mapping[country_key] = {
                "display_name": country_name,
                "store_path": str(country_store_path),
                "pdf_source": str(pdf_file),
                "chunk_count": len(chunks),
                "page_count": len(documents)
            }
            
            successful_countries.append(country_name)
            print(f"✅ Successfully created vector store for {country_name}")
            print(f"  📁 Stored at: {country_store_path}")
            print(f"  📄 {len(documents)} pages, {len(chunks)} chunks")
            
        except Exception as e:
            print(f"❌ Failed to process {pdf_file}: {e}")
            country_name_var = country_name if 'country_name' in locals() else pdf_file.stem
            failed_countries.append(country_name_var)
    
    # Save country mapping
    mapping_file = Path(config.country_mapping_file)
    mapping_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(country_mapping, f, indent=2, ensure_ascii=False)
    
    print(f"\n🎯 SUMMARY:")
    print(f"✅ Successfully processed: {len(successful_countries)} countries")
    print(f"❌ Failed to process: {len(failed_countries)} countries")
    print(f"📋 Country mapping saved to: {mapping_file}")
    
    if successful_countries:
        print(f"\n🌍 Successfully processed countries:")
        for country in sorted(successful_countries):
            print(f"  • {country}")
    
    if failed_countries:
        print(f"\n⚠️  Failed countries:")
        for country in sorted(failed_countries):
            print(f"  • {country}")
    
    return country_mapping

def list_available_countries():
    """List all available countries with their vector stores"""
    config = VisaRAGConfig()
    mapping_file = Path(config.country_mapping_file)
    
    if not mapping_file.exists():
        print("No country mapping found. Run create_country_vector_stores() first.")
        return {}
    
    with open(mapping_file, 'r', encoding='utf-8') as f:
        country_mapping = json.load(f)
    
    print("📋 Available countries:")
    for key, info in sorted(country_mapping.items()):
        store_exists = Path(info['store_path']).exists()
        status = "✅" if store_exists else "❌"
        print(f"  {status} {info['display_name']} ({info['chunk_count']} chunks, {info['page_count']} pages)")
    
    return country_mapping

def test_vector_store_loading():
    """Test loading vector stores to ensure they work properly"""
    config = VisaRAGConfig()
    mapping_file = Path(config.country_mapping_file)
    
    if not mapping_file.exists():
        print("No country mapping found. Run create_country_vector_stores() first.")
        return
    
    with open(mapping_file, 'r', encoding='utf-8') as f:
        country_mapping = json.load(f)
    
    # Use HuggingFaceEmbeddings for consistency
    embeddings = HuggingFaceEmbeddings(
        model_name=config.embeddings_model,
        model_kwargs={'device': 'cpu'}
    )
    
    print("🧪 Testing vector store loading...")
    
    for country_key, info in list(country_mapping.items())[:3]:  # Test first 3 countries
        try:
            store_path = Path(info['store_path'])
            if not store_path.exists():
                print(f"❌ {info['display_name']}: Store path doesn't exist")
                continue
            
            vector_store = FAISS.load_local(
                str(store_path),
                embeddings,
                allow_dangerous_deserialization=True
            )
            
            # Test a simple search
            test_results = vector_store.similarity_search("visa requirements", k=2)
            print(f"✅ {info['display_name']}: Loaded successfully, found {len(test_results)} test results")
            
        except Exception as e:
            print(f"❌ {info['display_name']}: Error loading - {e}")

if __name__ == "__main__":
    print("🚀 Creating country-specific vector stores...")
    mapping = create_country_vector_stores()
    print("\n📋 Listing available countries...")
    list_available_countries()
    print("\n🧪 Testing vector store loading...")
    test_vector_store_loading()