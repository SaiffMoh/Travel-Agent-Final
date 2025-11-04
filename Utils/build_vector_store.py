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
    chunk_size: int = 800  # Reduced for better granularity
    chunk_overlap: int = 200  # Increased overlap for context
    # CHANGED: Better multilingual model
    embeddings_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    base_vector_store_path: str = "data/visa_vector_stores"
    country_mapping_file: str = "data/country_mapping.json"

def extract_country_from_filename(pdf_file: Path) -> str:
    """Extract and normalize country name from PDF filename"""
    country_raw = pdf_file.stem.replace("_", " ").replace("-", " ")
    country_cleaned = re.sub(r'\b(visa|requirements?|info|information)\b', '', country_raw, flags=re.IGNORECASE)
    country_cleaned = country_cleaned.strip()
    country_name = " ".join(word.capitalize() for word in country_cleaned.split())
    return country_name if country_name else pdf_file.stem.title()

def detect_language_robust(text: str) -> str:
    """Robust language detection for mixed Arabic/English text"""
    if not text or len(text.strip()) < 10:
        return "unknown"
    
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    latin_chars = sum(1 for c in text if c.isalpha() and c < '\u0600')
    total_chars = arabic_chars + latin_chars
    
    if total_chars == 0:
        return "unknown"
    
    arabic_ratio = arabic_chars / total_chars
    
    if arabic_ratio > 0.7:
        return "arabic"
    elif arabic_ratio > 0.3:
        return "mixed"  # Both languages present
    else:
        return "english"

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
        len(re.findall(r'[^\w\s\u0600-\u06FF.,!?()-:/]', text)),
        len(re.findall(r'\s{3,}', text)),
        len(re.findall(r'[A-Z]{5,}', text)),
        text.count('ﻭ') + text.count('ﺔ') > len(text) * 0.3
    ]
    
    corruption_score = sum(1 for indicator in corruption_indicators if indicator > 10)
    
    if corruption_score >= 3:
        quality = "poor"
        confidence = 0.3
    elif corruption_score >= 2:
        quality = "medium"
        confidence = 0.6
    else:
        quality = "good"
        confidence = 0.9
    
    if arabic_chars > 0 and latin_chars > 0:
        mixed_ratio = min(arabic_chars, latin_chars) / max(arabic_chars, latin_chars)
        if mixed_ratio > 0.2:
            confidence *= 0.85  # Slightly penalize but don't discard mixed content
    
    return {
        "quality": quality,
        "confidence": confidence,
        "arabic_ratio": arabic_chars / total_chars if total_chars > 0 else 0,
        "latin_ratio": latin_chars / total_chars if total_chars > 0 else 0,
        "corruption_score": corruption_score,
        "total_length": len(text),
        "is_mixed": arabic_chars > 0 and latin_chars > 0
    }

def clean_extracted_text(text: str) -> str:
    """Clean and normalize extracted text"""
    if not text:
        return text
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove Arabic diacritics but keep base letters
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    # Keep tatweel for certain cases
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

def split_bilingual_content(text: str) -> Dict[str, str]:
    """Attempt to separate Arabic and English content"""
    lines = text.split('\n')
    
    arabic_lines = []
    english_lines = []
    
    for line in lines:
        lang = detect_language_robust(line)
        if lang == "arabic":
            arabic_lines.append(line)
        elif lang == "english":
            english_lines.append(line)
        elif lang == "mixed":
            # For mixed lines, add to both
            arabic_lines.append(line)
            english_lines.append(line)
    
    return {
        "arabic": "\n".join(arabic_lines),
        "english": "\n".join(english_lines),
        "combined": text
    }

def enhanced_load_pdf_for_country(pdf_file: Path, country_name: str) -> List[Document]:
    """Enhanced PDF loading with language separation and quality assessment"""
    documents = []
    
    try:
        loader = PyPDFLoader(str(pdf_file))
        docs = loader.load()
        
        print(f"Processing {len(docs)} pages from {pdf_file.name}...")
        
        for page_num, doc in enumerate(docs, 1):
            quality_info = assess_text_quality(doc.page_content)
            original_content = doc.page_content
            cleaned_content = clean_extracted_text(original_content)
            
            # Split bilingual content
            lang_split = split_bilingual_content(cleaned_content)
            detected_lang = detect_language_robust(cleaned_content)
            
            # If mixed content, create separate documents for each language
            if quality_info['is_mixed'] and len(lang_split['arabic']) > 50 and len(lang_split['english']) > 50:
                # Arabic version
                if lang_split['arabic']:
                    arabic_doc = Document(
                        page_content=lang_split['arabic'],
                        metadata={
                            "country": country_name,
                            "country_normalized": country_name.lower().replace(" ", "_"),
                            "source_file": str(pdf_file),
                            "page": page_num,
                            "doc_type": "visa_requirements",
                            "language": "arabic",
                            "content_type": "arabic_only",
                            "text_quality": quality_info['quality'],
                            "quality_confidence": quality_info['confidence'],
                            "file_size": pdf_file.stat().st_size if pdf_file.exists() else 0
                        }
                    )
                    documents.append(arabic_doc)
                
                # English version
                if lang_split['english']:
                    english_doc = Document(
                        page_content=lang_split['english'],
                        metadata={
                            "country": country_name,
                            "country_normalized": country_name.lower().replace(" ", "_"),
                            "source_file": str(pdf_file),
                            "page": page_num,
                            "doc_type": "visa_requirements",
                            "language": "english",
                            "content_type": "english_only",
                            "text_quality": quality_info['quality'],
                            "quality_confidence": quality_info['confidence'],
                            "file_size": pdf_file.stat().st_size if pdf_file.exists() else 0
                        }
                    )
                    documents.append(english_doc)
            else:
                # Single language or not worth splitting
                doc.page_content = cleaned_content
                doc.metadata.update({
                    "country": country_name,
                    "country_normalized": country_name.lower().replace(" ", "_"),
                    "source_file": str(pdf_file),
                    "page": page_num,
                    "doc_type": "visa_requirements",
                    "language": detected_lang,
                    "content_type": "mixed" if detected_lang == "mixed" else detected_lang,
                    "text_quality": quality_info['quality'],
                    "quality_confidence": quality_info['confidence'],
                    "arabic_ratio": quality_info['arabic_ratio'],
                    "latin_ratio": quality_info['latin_ratio'],
                    "original_length": len(original_content),
                    "cleaned_length": len(cleaned_content),
                    "file_size": pdf_file.stat().st_size if pdf_file.exists() else 0
                })
                
                if quality_info['quality'] == 'poor':
                    doc.page_content = f"[WARNING: Poor text extraction quality]\n\n{doc.page_content}"
                elif quality_info['quality'] == 'medium':
                    doc.page_content = f"[NOTE: Text may contain extraction errors]\n\n{doc.page_content}"
                
                documents.append(doc)
        
        avg_quality = sum(assess_text_quality(doc.page_content)['confidence'] for doc in documents) / len(documents) if documents else 0
        print(f"✓ Loaded {len(documents)} document chunks from {pdf_file.name} (avg quality: {avg_quality:.2f})")
        
    except Exception as e:
        print(f"✗ Error loading {pdf_file}: {e}")
    
    return documents

def create_country_vector_stores():
    """Create separate vector stores for each country with metadata filtering support"""
    config = VisaRAGConfig()
    
    # Use multilingual embeddings
    embeddings = HuggingFaceEmbeddings(
        model_name=config.embeddings_model,
        model_kwargs={'device': 'cpu'}
    )
    
    # Custom splitter for better handling of bilingual content
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=["\n\n", "\n", ". ", "• ", " ", ""],
        length_function=len
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
    print(f"Using embedding model: {config.embeddings_model}")
    
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
            
            # Count chunks by language
            arabic_chunks = sum(1 for c in chunks if c.metadata.get('language') in ['arabic', 'mixed'])
            english_chunks = sum(1 for c in chunks if c.metadata.get('language') in ['english', 'mixed'])
            
            print(f"  Created {len(chunks)} chunks ({arabic_chunks} Arabic, {english_chunks} English)")
            
            # Create FAISS vector store
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
                "page_count": len(documents),
                "arabic_chunks": arabic_chunks,
                "english_chunks": english_chunks,
                "embedding_model": config.embeddings_model
            }
            
            successful_countries.append(country_name)
            print(f"✅ Successfully created vector store for {country_name}")
            print(f"  📁 Stored at: {country_store_path}")
            
        except Exception as e:
            print(f"❌ Failed to process {pdf_file}: {e}")
            import traceback
            traceback.print_exc()
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
        arabic = info.get('arabic_chunks', 0)
        english = info.get('english_chunks', 0)
        print(f"  {status} {info['display_name']} ({info['chunk_count']} chunks: {arabic} AR, {english} EN)")
    
    return country_mapping

if __name__ == "__main__":
    print("🚀 Creating country-specific vector stores with multilingual support...")
    mapping = create_country_vector_stores()
    print("\n📋 Listing available countries...")
    list_available_countries()