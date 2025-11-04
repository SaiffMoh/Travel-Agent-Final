        
from typing import Optional, List, Dict
from pathlib import Path
from langchain_community.vectorstores import FAISS
from sentence_transformers import SentenceTransformer
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from Models.TravelSearchState import TravelSearchState
from Utils.watson_config import llm
from dotenv import load_dotenv
import json
import re
import logging
from difflib import get_close_matches

load_dotenv('.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VisaRAGConfig:
    """Configuration for the Visa RAG system"""
    top_k: int = 8  # Increased for better coverage
    embeddings_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    base_vector_store_path: str = "data/visa_vector_stores"
    country_mapping_file: str = "data/country_mapping.json"
    llm_model: str = "llama-3.3-70b-instruct"

class CountrySpecificVisaRAG:
    """Enhanced RAG system with metadata filtering and bilingual support"""
    
    def __init__(self, config: VisaRAGConfig):
        self.config = config
        self.embeddings = HuggingFaceEmbeddings(
            model_name=config.embeddings_model,
            model_kwargs={'device': 'cpu'}
        )
        self.country_mapping = self._load_country_mapping()
        self._loaded_stores = {}
    
    def _load_country_mapping(self) -> Dict:
        """Load the country mapping file"""
        mapping_file = Path(self.config.country_mapping_file)
        
        if not mapping_file.exists():
            logger.error(f"Country mapping file not found at {mapping_file}")
            return {}
        
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            logger.info(f"Loaded mapping for {len(mapping)} countries")
            return mapping
        except Exception as e:
            logger.error(f"Error loading country mapping: {e}")
            return {}
    
    def normalize_country_name(self, country_name: str) -> str:
        """Normalize country name to match our storage format"""
        if not country_name:
            return ""
        return country_name.lower().replace(" ", "_").replace("-", "_")
    
    def find_best_country_match(self, query_country: str) -> Optional[str]:
        """Find the best matching country from available options"""
        if not query_country or not self.country_mapping:
            return None
        
        normalized_query = self.normalize_country_name(query_country)
        
        # Direct match
        if normalized_query in self.country_mapping:
            return normalized_query
        
        # Fuzzy match on keys
        country_keys = list(self.country_mapping.keys())
        matches = get_close_matches(normalized_query, country_keys, n=1, cutoff=0.6)
        
        if matches:
            return matches[0]
        
        # Match on display names
        display_names = {info['display_name'].lower(): key for key, info in self.country_mapping.items()}
        matches = get_close_matches(query_country.lower(), list(display_names.keys()), n=1, cutoff=0.6)
        
        if matches:
            return display_names[matches[0]]
        
        # Partial match
        for key, info in self.country_mapping.items():
            if normalized_query in key or normalized_query in info['display_name'].lower():
                return key
            if query_country.lower() in info['display_name'].lower():
                return key
        
        return None
    
    def load_country_vector_store(self, country_key: str) -> Optional[FAISS]:
        """Load vector store for a specific country"""
        if country_key in self._loaded_stores:
            logger.info(f"Using cached vector store for {country_key}")
            return self._loaded_stores[country_key]
        
        if country_key not in self.country_mapping:
            logger.warning(f"Country {country_key} not found in mapping")
            return None
        
        store_path = Path(self.country_mapping[country_key]['store_path'])
        
        if not store_path.exists():
            logger.error(f"Vector store path does not exist: {store_path}")
            return None
        
        try:
            logger.info(f"Loading vector store for {country_key} from {store_path}")
            vector_store = FAISS.load_local(
                str(store_path),
                self.embeddings,
                allow_dangerous_deserialization=True
            )
            self._loaded_stores[country_key] = vector_store
            logger.info(f"Successfully loaded vector store for {country_key}")
            return vector_store
        except Exception as e:
            logger.error(f"Error loading vector store for {country_key}: {e}")
            return None
    
    def retrieve_documents_with_filtering(self, query: str, country_key: str, 
                                         preferred_language: Optional[str] = None) -> List[Document]:
        """Retrieve relevant documents with optional language filtering"""
        vector_store = self.load_country_vector_store(country_key)
        
        if not vector_store:
            logger.warning(f"Could not load vector store for {country_key}")
            return []
        
        try:
            # Get more documents initially for filtering
            initial_k = self.config.top_k * 2
            docs = vector_store.similarity_search(query, k=initial_k)
            
            if not docs:
                logger.warning(f"No documents retrieved for query: {query}")
                return []
            
            # Filter by language preference if specified
            if preferred_language:
                filtered_docs = [
                    doc for doc in docs 
                    if doc.metadata.get('language') == preferred_language 
                    or doc.metadata.get('language') == 'mixed'
                ]
                if filtered_docs:
                    docs = filtered_docs[:self.config.top_k]
                    logger.info(f"Filtered to {len(docs)} {preferred_language} documents")
            
            # Sort by quality score
            docs_with_scores = [
                (doc, doc.metadata.get('quality_confidence', 0.5))
                for doc in docs
            ]
            docs_with_scores.sort(key=lambda x: x[1], reverse=True)
            docs = [doc for doc, _ in docs_with_scores[:self.config.top_k]]
            
            logger.info(f"Retrieved {len(docs)} documents for {country_key}")
            return docs
            
        except Exception as e:
            logger.error(f"Error retrieving documents for {country_key}: {e}")
            return []

    def answer_query(self, query: str, target_country: Optional[str] = None) -> tuple[str, List[Document]]:
        """Generate answer using country-specific vector store. Returns (answer, source_docs)"""
        country_key = None
        
        if target_country:
            country_key = self.find_best_country_match(target_country)
        
        if not country_key:
            country_key = self.extract_country_from_query(query)
        
        if not country_key:
            available_countries = [info['display_name'] for info in self.country_mapping.values()]
            return (f"""I couldn't determine which country you're asking about for visa requirements. 

Available countries: {', '.join(sorted(available_countries[:15]))}{'...' if len(available_countries) > 15 else ''}

Please specify a country name in your question.""", [])
        
        country_info = self.country_mapping[country_key]
        country_display = country_info['display_name']
        
        logger.info(f"Processing visa query for {country_display}")
        
        # Detect query language for better retrieval
        query_lang = self._detect_query_language(query)
        documents = self.retrieve_documents_with_filtering(query, country_key, preferred_language=query_lang)
        
        if not documents:
            return (f"""I found the country ({country_display}) but couldn't retrieve specific visa requirement documents.

Please try rephrasing your question or ask about visa requirements for {country_display} in general.""", [])
        
        # Separate Arabic and English content
        arabic_docs = [d for d in documents if d.metadata.get('language') in ['arabic', 'mixed']]
        english_docs = [d for d in documents if d.metadata.get('language') in ['english', 'mixed']]
        
        # Build context with language separation
        context_parts = []
        
        if english_docs:
            context_parts.append("=== ENGLISH VERSION ===")
            for doc in english_docs[:4]:
                context_parts.append(f"[Page {doc.metadata.get('page', 'N/A')}]\n{doc.page_content}")
        
        if arabic_docs:
            context_parts.append("\n=== ARABIC VERSION (عربي) ===")
            for doc in arabic_docs[:4]:
                context_parts.append(f"[صفحة {doc.metadata.get('page', 'N/A')}]\n{doc.page_content}")
        
        doc_contents = "\n\n".join(context_parts)[:15000]  # Limit total length
        
        prompt_template = f"""<|SYSTEM|>You are a visa requirements expert fluent in English and Arabic.

CRITICAL INSTRUCTIONS:
- Base your answer STRICTLY on the provided documents for {country_display}
- The documents contain BOTH English and Arabic versions - use BOTH to provide complete information
- If English and Arabic versions differ, mention BOTH perspectives
- Present information in a clear, structured format
- List ALL requirements mentioned (documents, photos, fees, processing time, etc.)
- If information is unclear or contradictory between languages, explicitly state this
- Do NOT add external knowledge or assumptions

Query: {query}
Target Country: {country_display}
Documents Available: {len(documents)} (English: {len(english_docs)}, Arabic: {len(arabic_docs)})

DOCUMENTS:
{doc_contents}

Provide a comprehensive, well-structured response covering:
1. **Required Documents** - List all documents needed
2. **Application Process** - Steps to apply
3. **Fees & Processing Time** - If mentioned
4. **Important Notes** - Any special conditions or restrictions
5. **Language Differences** - Note any differences between English/Arabic versions

Format using clear sections with bullet points.
End with: "Need more help? I can also assist with flight and hotel bookings!"
<|USER|>Provide comprehensive visa requirements based on the documents.<|END|>"""
        
        logger.info(f"Generating response for {country_display} with {len(documents)} documents")
        
        try:
            response = llm.generate(prompt=prompt_template)
            raw_answer = response["results"][0]["generated_text"].strip()
            visa_answer = raw_answer.split('<|')[0].strip()
            
            logger.info(f"Successfully generated response for {country_display}")
            return visa_answer, documents
        except Exception as e:
            logger.error(f"Error generating response for {country_display}: {e}")
            return (f"""I encountered an error while processing visa requirements for {country_display}: {str(e)}

Need more help? I can also assist with flight and hotel bookings!""", documents)

    def _detect_query_language(self, query: str) -> Optional[str]:
        """Detect if query is in English or Arabic"""
        arabic_chars = sum(1 for c in query if '\u0600' <= c <= '\u06FF')
        latin_chars = sum(1 for c in query if c.isalpha() and c < '\u0600')
        
        if arabic_chars > latin_chars:
            return "arabic"
        elif latin_chars > 0:
            return "english"
        return None

    def extract_country_from_query(self, query: str) -> Optional[str]:
        """Extract country from query text"""
        query_lower = query.lower()
        for country_key, country_info in self.country_mapping.items():
            if country_info['display_name'].lower() in query_lower:
                return country_key
        return None

def enhanced_get_country(user_message: str, destination: Optional[str]) -> Optional[str]:
    """Enhanced country detection using available country mapping"""
    config = VisaRAGConfig()
    mapping_file = Path(config.country_mapping_file)
    
    available_countries = []
    if mapping_file.exists():
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                country_mapping = json.load(f)
            available_countries = [info['display_name'] for info in country_mapping.values()]
        except Exception as e:
            logger.error(f"Error loading countries for LLM context: {e}")
    
    countries_context = f"Available countries in our system: {', '.join(sorted(available_countries))}" if available_countries else "No country list available"
    dest_str = destination if destination else "None"
    
    prompt = f"""<|SYSTEM|>From the user message: '{user_message}'

Extract the country inquired about for visas or travel requirements.

{countries_context}

If none specified, infer from destination: '{dest_str}'.

Match to available countries. Return closest match.

Reply with ONLY the country name or 'None' - no extra text.
<|USER|>Return ONLY country name or 'None'.<|END|>"""
    
    logger.info(f"Enhanced country detection for: {user_message[:100]}...")
    try:
        response = llm.generate(prompt=prompt)
        raw_country = response["results"][0]["generated_text"].strip()
        country = raw_country.split('<|')[0].strip().split('\n')[0].strip()
        country = re.sub(r'^(assistant|user|system).*', '', country, flags=re.IGNORECASE).strip()
        
        if country and country.lower() != 'none':
            if available_countries:
                for avail_country in available_countries:
                    if country.lower() in avail_country.lower() or avail_country.lower() in country.lower():
                        logger.info(f"LLM detected and validated country: {avail_country}")
                        return avail_country
                logger.warning(f"LLM returned '{country}' but it doesn't match available countries")
                return None
            logger.info(f"LLM detected country: {country}")
            return country
        
        logger.info("LLM could not detect a valid country")
        return None
    except Exception as e:
        logger.error(f"Error in enhanced country detection: {e}")
        return None

def visa_rag_node(state: TravelSearchState) -> TravelSearchState:
    """Enhanced visa RAG node with professional HTML output"""
    config = VisaRAGConfig()
    rag = CountrySpecificVisaRAG(config)
    
    user_message = state.get("current_message") or state.get("user_message", "")
    destination = state.get("destination")
    
    country = state.get("detected_visa_country")
    if not country:
        country = enhanced_get_country(user_message, destination)
        logger.info(f"Enhanced country detection result: {country}")
    else:
        logger.info(f"Using router-detected country: {country}")
    
    if not country:
        available_countries = [info['display_name'] for info in rag.country_mapping.values()]
        state["visa_info_html"] = generate_country_selection_html(available_countries)
        return state
    
    logger.info(f"Processing visa query for country: {country}")
    
    query = f"What are the visa requirements for {country}?"
    visa_answer, source_docs = rag.answer_query(query, country)
    
    visa_html = generate_visa_info_html(country, visa_answer, source_docs)
    
    state["visa_info_html"] = visa_html
    return state

def generate_country_selection_html(available_countries: List[str]) -> str:
    """Generate professional HTML for country selection"""
    countries_list = ', '.join(sorted(available_countries[:20]))
    if len(available_countries) > 20:
        countries_list += f" and {len(available_countries) - 20} more"
    
    return f"""
    <style>
        .visa-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
        }}
        .section-header {{
            border-bottom: 2px solid #000;
            padding-bottom: 12px;
            margin-bottom: 24px;
        }}
        .section-title {{
            font-size: 24px;
            font-weight: 600;
            margin: 0;
            letter-spacing: -0.5px;
        }}
        .section-subtitle {{
            font-size: 14px;
            margin: 4px 0 0 0;
            opacity: 0.7;
        }}
        .info-box {{
            border: 1px solid #ddd;
            padding: 16px;
            margin-bottom: 24px;
            background: #fafafa;
        }}
        .info-box p {{
            margin: 0;
            font-size: 14px;
        }}
        .countries-list {{
            border: 1px solid #ddd;
            padding: 20px;
            margin-bottom: 16px;
            background: #fff;
        }}
        .countries-list p {{
            margin: 0 0 12px 0;
            font-size: 14px;
            line-height: 1.8;
        }}
    </style>
    <div class="visa-container">
        <div class="section-header">
            <h1 class="section-title">Visa Requirements Assistant</h1>
            <p class="section-subtitle">Specify which country you're asking about</p>
        </div>
        
        <div class="info-box">
            <p><strong>How to ask:</strong> "What are the visa requirements for [Country]?" or "Do I need a visa for [Country]?"</p>
        </div>
        
        <div class="countries-list">
            <p><strong>Available countries:</strong></p>
            <p>{countries_list}</p>
        </div>
        
        <div class="info-box">
            <p>I can also help with flight bookings, hotel search, and complete travel packages.</p>
        </div>
    </div>
    """

def generate_visa_info_html(country: str, visa_answer: str, source_docs: List[Document]) -> str:
    """Generate professional HTML for visa requirements"""
    
    # Extract sections from the answer
    sections = parse_visa_sections(visa_answer)
    
    # Count sources
    arabic_sources = sum(1 for d in source_docs if d.metadata.get('language') in ['arabic', 'mixed'])
    english_sources = sum(1 for d in source_docs if d.metadata.get('language') in ['english', 'mixed'])
    
    return f"""
    <style>
        .visa-container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
        }}
        .section-header {{
            border-bottom: 2px solid #000;
            padding-bottom: 12px;
            margin-bottom: 24px;
        }}
        .section-title {{
            font-size: 24px;
            font-weight: 600;
            margin: 0;
            letter-spacing: -0.5px;
        }}
        .section-subtitle {{
            font-size: 14px;
            margin: 4px 0 0 0;
            opacity: 0.7;
        }}
        .info-card {{
            border: 1px solid #ddd;
            padding: 20px;
            margin-bottom: 16px;
        }}
        .card-title {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 0 16px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #ddd;
        }}
        .card-content {{
            font-size: 14px;
            line-height: 1.8;
            color: #333;
        }}
        .card-content ul {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .card-content li {{
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .card-content li:last-child {{
            border-bottom: none;
        }}
        .card-content p {{
            margin: 0 0 12px 0;
        }}
        .sources-info {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            opacity: 0.6;
            padding: 8px 0;
        }}
        .notice-box {{
            border: 1px solid #ddd;
            padding: 20px;
            text-align: center;
            background: #fafafa;
            margin-top: 16px;
        }}
        .notice-box p {{
            margin: 0;
            font-size: 13px;
            line-height: 1.6;
        }}
    </style>
    <div class="visa-container">
        <div class="section-header">
            <h1 class="section-title">Visa Requirements for {country}</h1>
            <p class="section-subtitle">Based on official sources</p>
            <div class="sources-info">{len(source_docs)} sources ({english_sources} English, {arabic_sources} Arabic)</div>
        </div>
        
        {format_visa_sections_html(sections)}
        
        <div class="notice-box">
            <p>
                I can help you find the best flights, hotels, and travel packages to {country}.<br>
                Just tell me where you're traveling from and when you'd like to go.
            </p>
        </div>
    </div>
    """

def parse_visa_sections(visa_answer: str) -> Dict[str, str]:
    """Parse visa answer into structured sections without repetition"""
    
    # Stop at the closing message
    stop_phrases = [
        "Need more help?",
        "I can also assist",
        "Just tell me where"
    ]
    
    for phrase in stop_phrases:
        if phrase in visa_answer:
            visa_answer = visa_answer.split(phrase)[0]
    
    sections = {}
    current_section = None
    current_content = []
    
    lines = visa_answer.split('\n')
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
        
        # Check if this line is a section header
        # Pattern 1: ## Section Name
        markdown_header = re.match(r'^##\s+(.+)$', line)
        # Pattern 2: **Section Name** or **Section Name:**
        bold_header = re.match(r'^\*\*([^*]+)\*\*:?\s*$', line)
        # Pattern 3: Numbered section like "1. Section Name" at start
        numbered_header = re.match(r'^\d+\.\s+\*\*([^*]+)\*\*', line)
        
        if markdown_header or bold_header or numbered_header:
            # Save previous section if exists
            if current_section and current_content:
                sections[current_section] = '\n'.join(current_content).strip()
            
            # Start new section
            if markdown_header:
                current_section = markdown_header.group(1).strip()
            elif bold_header:
                current_section = bold_header.group(1).strip()
            else:
                current_section = numbered_header.group(1).strip()
            
            current_content = []
        else:
            # Add line to current section content
            if current_section:
                current_content.append(line)
    
    # Save the last section
    if current_section and current_content:
        sections[current_section] = '\n'.join(current_content).strip()
    
    # If no sections were parsed, return the whole answer as one section
    if not sections and visa_answer.strip():
        sections["Information"] = visa_answer.strip()
    
    logger.info(f"Parsed {len(sections)} sections: {list(sections.keys())}")
    
    return sections

def format_visa_sections_html(sections: Dict[str, str]) -> str:
    """Format visa sections as professional HTML"""
    html_parts = []
    
    for title, content in sections.items():
        # Convert content to formatted HTML
        formatted_content = format_content_to_html(content)
        
        html_parts.append(f"""
        <div class="info-card">
            <h2 class="card-title">{title}</h2>
            <div class="card-content">
                {formatted_content}
            </div>
        </div>
        """)
    
    return "".join(html_parts)

def format_content_to_html(content: str) -> str:
    """Convert plain text content to formatted HTML"""
    if not content:
        return "<p>No information available.</p>"
    
    # Split into lines
    lines = content.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            continue
        
        # Check if it's a list item
        if re.match(r'^[\-\*\•]\s', line) or re.match(r'^\d+[\.\)]\s', line):
            if not in_list:
                formatted_lines.append('<ul>')
                in_list = True
            # Remove bullet/number and add as list item
            item_text = re.sub(r'^[\-\*\•\d]+[\.\)]*\s*', '', line)
            formatted_lines.append(f'<li>{item_text}</li>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            # Bold any text that looks like a header or important
            if re.match(r'^[A-Z][^:]{3,30}:$', line):
                formatted_lines.append(f'<p><strong>{line}</strong></p>')
            else:
                formatted_lines.append(f'<p>{line}</p>')
    
    if in_list:
        formatted_lines.append('</ul>')
    
    return '\n'.join(formatted_lines)

def check_system_status():
    """Check the status of the visa RAG system"""
    config = VisaRAGConfig()
    rag = CountrySpecificVisaRAG(config)
    
    print(f"🔍 System Status Check")
    print(f"Embedding Model: {config.embeddings_model}")
    print(f"Countries available: {len(rag.country_mapping)}")
    print(f"Base vector store path: {config.base_vector_store_path}")
    print(f"Country mapping file: {config.country_mapping_file}")
    
    for key, info in list(rag.country_mapping.items())[:5]:
        store_path = Path(info['store_path'])
        status = "✅" if store_path.exists() else "❌"
        arabic = info.get('arabic_chunks', 0)
        english = info.get('english_chunks', 0)
        print(f"  {status} {info['display_name']}: {info['chunk_count']} chunks ({arabic} AR, {english} EN)")
    
    if len(rag.country_mapping) > 5:
        print(f"  ... and {len(rag.country_mapping) - 5} more countries")
    
    return rag.country_mapping

if __name__ == "__main__":
    check_system_status()