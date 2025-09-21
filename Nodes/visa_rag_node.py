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
from rank_bm25 import BM25Okapi

load_dotenv('.env')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VisaRAGConfig:
    """Configuration for the Visa RAG system"""
    top_k: int = 5
    embeddings_model: str = "multi-qa-mpnet-base-dot-v1"  # Multilingual model
    base_vector_store_path: str = "data/visa_vector_stores"
    country_mapping_file: str = "data/country_mapping.json"
    llm_model: str = "llama-3.3-70b-instruct"

class CountrySpecificVisaRAG:
    """Enhanced RAG system that loads country-specific vector stores on demand with hybrid retrieval"""
    
    def __init__(self, config: VisaRAGConfig):
        self.config = config
        # Use HuggingFaceEmbeddings for LangChain compatibility
        self.embeddings = HuggingFaceEmbeddings(
            model_name=config.embeddings_model,
            model_kwargs={'device': 'cpu'}
        )
        # Keep SentenceTransformer for encoding if needed
        self.sentence_transformer = SentenceTransformer(config.embeddings_model)
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
            # Use the HuggingFaceEmbeddings object instead of SentenceTransformer
            vector_store = FAISS.load_local(
                str(store_path),
                self.embeddings,  # This is now HuggingFaceEmbeddings
                allow_dangerous_deserialization=True
            )
            self._loaded_stores[country_key] = vector_store
            logger.info(f"Successfully loaded vector store for {country_key}")
            return vector_store
        except Exception as e:
            logger.error(f"Error loading vector store for {country_key}: {e}")
            return None
    
    def retrieve_documents(self, query: str, country_key: str) -> List[Document]:
        """Retrieve relevant documents using dense retrieval with fallback BM25"""
        vector_store = self.load_country_vector_store(country_key)
        
        if not vector_store:
            logger.warning(f"Could not load vector store for {country_key}")
            return []
        
        try:
            # Perform dense retrieval using FAISS
            docs = vector_store.similarity_search(query, k=self.config.top_k)
            
            if not docs:
                logger.warning(f"No documents retrieved for query: {query}")
                return []
            
            # Optional: Recompute BM25 scores for re-ranking
            try:
                tokenized_query = query.lower().split()
                doc_texts = [doc.page_content for doc in docs]
                tokenized_corpus = [text.lower().split() for text in doc_texts]
                
                if tokenized_corpus and all(tokenized_corpus):
                    bm25 = BM25Okapi(tokenized_corpus)
                    bm25_scores = bm25.get_scores(tokenized_query)
                    
                    # Combine documents with scores and re-rank
                    doc_score_pairs = list(zip(docs, bm25_scores))
                    doc_score_pairs.sort(key=lambda x: x[1], reverse=True)
                    docs = [doc for doc, _ in doc_score_pairs[:self.config.top_k]]
                    
                    logger.info(f"Re-ranked documents using BM25 scores")
            except Exception as bm25_error:
                logger.warning(f"BM25 re-ranking failed, using original order: {bm25_error}")
            
            logger.info(f"Retrieved {len(docs)} documents for {country_key}")
            return docs
            
        except Exception as e:
            logger.error(f"Error retrieving documents for {country_key}: {e}")
            return []

    def answer_query(self, query: str, target_country: Optional[str] = None) -> str:
        """Generate answer using country-specific vector store"""
        country_key = None
        
        if target_country:
            country_key = self.find_best_country_match(target_country)
        
        if not country_key:
            country_key = self.extract_country_from_query(query)
        
        if not country_key:
            available_countries = [info['display_name'] for info in self.country_mapping.values()]
            return f"""I couldn't determine which country you're asking about for visa requirements. 

Available countries: {', '.join(sorted(available_countries[:10]))}{'...' if len(available_countries) > 10 else ''}

Please specify a country name in your question.

Is there anything else you'd like to know about travel or visa requirements?"""
        
        country_info = self.country_mapping[country_key]
        country_display = country_info['display_name']
        
        logger.info(f"Processing visa query for {country_display}")
        documents = self.retrieve_documents(query, country_key)
        
        if not documents:
            return f"""I found the country ({country_display}) but couldn't retrieve specific visa requirement documents. This might be due to:
- The vector store for {country_display} might not be properly loaded
- No relevant information found for your specific query

Please try rephrasing your question or ask about visa requirements for {country_display} in general.

Is there anything else you'd like to know about travel or visa requirements?"""
        
        # Process documents for the prompt
        doc_contents = "\n\n".join([
            f"Document from {doc.metadata.get('country', 'Unknown')} "
            f"(Language: {doc.metadata.get('language', 'Unknown')}, "
            f"Page {doc.metadata.get('page', 'N/A')}):\n{doc.page_content}"
            for doc in documents
        ])
        doc_contents = doc_contents[:10000]  # Limit content length
        
        prompt_template = f"""<|SYSTEM|>You are a visa requirements expert fluent in English and Arabic. You MUST base your answer STRICTLY AND ONLY on the following documents extracted from official PDF sources for {country_display}. 

CRITICAL INSTRUCTIONS:
- Do NOT add any external knowledge about visa requirements
- Do NOT mention requirements not explicitly stated in the documents
- If information is unclear due to OCR errors or mixed languages, state this clearly
- If documents lack specific information (e.g., fees, processing times), say 'Not mentioned in the provided documents'
- Translate any Arabic text accurately, marking uncertain translations with '[Uncertain]'
- Acknowledge any corrupted or unclear text

Query: {query}
Target Country: {country_display}
Documents Available: {len(documents)} relevant documents

Documents (may contain OCR errors or mixed languages):
{doc_contents}

Based ONLY on the above documents, provide a response that:
1. Lists ONLY the requirements explicitly mentioned
2. Clearly notes missing, unclear, or corrupted information
3. Acknowledges text extraction or language issues
4. Avoids inventing or assuming standard requirements

Format response clearly without adding unmentioned details.

End with: 'Is there anything else you'd like to know about travel or visa requirements?'
<|USER|>Provide response based strictly on document content.<|END|>"""
        
        logger.info(f"Generating response for {country_display} with {len(documents)} documents")
        
        try:
            response = llm.generate(prompt=prompt_template)
            raw_answer = response["results"][0]["generated_text"].strip()
            visa_answer = raw_answer.split('<|')[0].strip()
            
            logger.info(f"Successfully generated response for {country_display}")
            return visa_answer
        except Exception as e:
            logger.error(f"Error generating response for {country_display}: {e}")
            return f"""I encountered an error while processing visa requirements for {country_display}: {str(e)}

Is there anything else you'd like to know about travel or visa requirements?"""

    def extract_country_from_query(self, query: str) -> Optional[str]:
        """Extract country from query text"""
        # Simple extraction - look for country names in the query
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

If none specified, infer from destination: '{dest_str}' (use 'None' if no destination).

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
    """Enhanced visa RAG node with country-specific vector stores"""
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
        countries_list = ', '.join(sorted(available_countries[:15]))
        if len(available_countries) > 15:
            countries_list += f" and {len(available_countries) - 15} more"
        
        logger.info("No country determined, providing available countries list")
        state["visa_info_html"] = f"""
        <div class="visa-section">
            <h3>Visa Information</h3>
            <p>I'd be happy to help you with visa requirements! Please specify which country you're asking about.</p>
            <p><strong>Available countries:</strong> {countries_list}</p>
            <p>You can also ask me about flights, hotels, or start a new travel search anytime.</p>
        </div>
        """
        return state
    
    logger.info(f"Processing visa query for country: {country}")
    
    query = f"What are the visa requirements for {country}?"
    visa_answer = rag.answer_query(query, country)
    
    visa_html = f"""
    <div class="visa-section">
        <h3>Visa Requirements for {country}</h3>
        <div class="visa-content">
            {format_markdown_to_html(visa_answer)}
        </div>
        <div class="travel-help-note">
            <p><strong>Need help with travel planning?</strong> I can also help you search for flights, hotels, 
            and travel packages. Just let me know where you'd like to go!</p>
        </div>
    </div>
    """
    
    state["visa_info_html"] = visa_html
    return state

def format_markdown_to_html(markdown_text: str) -> str:
    """Convert basic markdown to HTML with improved formatting"""
    html = markdown_text
    
    # Headers
    html = re.sub(r'### (.*?)(?=\n|$)', r'<h4>\1</h4>', html)
    html = re.sub(r'## (.*?)(?=\n|$)', r'<h3>\1</h3>', html)
    html = re.sub(r'# (.*?)(?=\n|$)', r'<h2>\1</h2>', html)
    
    # Bold text
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    
    # Process line by line for lists and paragraphs
    lines = html.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            continue
            
        if line.startswith('- ') or line.startswith('* '):
            if not in_list:
                formatted_lines.append('<ul>')
                in_list = True
            formatted_lines.append(f'<li>{line[2:]}</li>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            if not line.startswith('<h'):
                formatted_lines.append(f'<p>{line}</p>')
            else:
                formatted_lines.append(line)
    
    if in_list:
        formatted_lines.append('</ul>')
    
    return '\n'.join(formatted_lines)

def check_system_status():
    """Check the status of the visa RAG system"""
    config = VisaRAGConfig()
    rag = CountrySpecificVisaRAG(config)
    
    print(f"🔍 System Status Check")
    print(f"Countries available: {len(rag.country_mapping)}")
    print(f"Base vector store path: {config.base_vector_store_path}")
    print(f"Country mapping file: {config.country_mapping_file}")
    
    for key, info in list(rag.country_mapping.items())[:5]:
        store_path = Path(info['store_path'])
        status = "✅" if store_path.exists() else "❌"
        print(f"  {status} {info['display_name']}: {info['chunk_count']} chunks")
    
    if len(rag.country_mapping) > 5:
        print(f"  ... and {len(rag.country_mapping) - 5} more countries")
    
    return rag.country_mapping

if __name__ == "__main__":
    check_system_status()