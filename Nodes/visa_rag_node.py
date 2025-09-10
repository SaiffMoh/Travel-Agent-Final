from typing import Optional, List
from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from Models.TravelSearchState import TravelSearchState
from Utils.watson_config import llm
from dotenv import load_dotenv
import arabic_reshaper
from bidi.algorithm import get_display
import os
import re
import logging

load_dotenv('.env')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VisaRAGConfig:
    """Configuration for the Visa RAG system"""
    top_k: int = 5
    embeddings_model: str = "text-embedding-ada-002"
    vector_store_path: str = "data/visa_vector_store"
    llm_model: str = "llama-3.3-70b-instruct"

class VisaRAGRetriever:
    """Retrieval and generation part of RAG (no embedding creation)"""
    
    def __init__(self, config: VisaRAGConfig):
        self.config = config
        self.embeddings = OpenAIEmbeddings(model=config.embeddings_model)
        self.vector_store = self._load_vector_store()
    
    def _load_vector_store(self):
        """Load existing vector store (assumes it's pre-built)"""
        vector_store_path = Path(self.config.vector_store_path)
        
        if not vector_store_path.exists():
            raise ValueError(f"Vector store not found at {vector_store_path}. Run build_vector_store.py first.")
        
        logger.info("Loading existing vector store...")
        return FAISS.load_local(
            str(vector_store_path), 
            self.embeddings,
            allow_dangerous_deserialization=True
        )
    
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
        """Retrieve docs and generate answer with Watsonx LLM"""
        country = self.extract_country_from_query(query)
        documents = self.retrieve_documents(query, country)
        
        if not documents:
            return f"I couldn't find specific visa requirements for {country or 'the requested country'}. Please check if the country name is correct or if we have information available.\n\nIs there anything else you'd like to know about travel or visa requirements?"
        
        doc_contents = "\n\n".join([
            f"Document from {doc.metadata.get('country', 'Unknown')} (Language: {doc.metadata.get('language', 'Unknown')}, Page {doc.metadata.get('page', 'N/A')}):\n{doc.page_content}"
            for doc in documents
        ])
        doc_contents = doc_contents[:10000]
        
        prompt_template = f"""<|SYSTEM|>You are a visa requirements expert. Based ONLY on the following documents extracted from official PDF sources, 
answer the user's query about visa requirements. Do not add external knowledge. If the documents don't cover the query, say so.
If text is in Arabic, translate key parts to English in your summary.

Query: {query}
Country (if detected): {country or 'Not specified'}
Date Check: {documents[0].metadata.get('date_check', 'No date found')}

Documents:
{doc_contents}

Provide a clear, comprehensive answer in Markdown format, including:
- Key requirements (e.g., documents needed)
- Application process
- Any notes or caveats

End your response with: "Is there anything else you'd like to know about travel or visa requirements?"
<|USER|>Return the response in Markdown format as specified.<|END|>"""
        
        logger.info(f"Watsonx visa prompt: {prompt_template[:500]}...")
        try:
            response = llm.generate(prompt=prompt_template)
            raw_answer = response["results"][0]["generated_text"].strip()
            # Clean the response - remove any trailing tokens like <|END|>
            visa_answer = raw_answer.split('<|')[0].strip()
            logger.info(f"Watsonx visa response: {visa_answer[:500]}...")
            return visa_answer
        except Exception as e:
            logger.error(f"Error in Watsonx visa query: {e}")
            return f"I couldn't process the visa requirements for {country or 'the requested country'} due to an error: {str(e)}. Please try again.\n\nIs there anything else you'd like to know about travel or visa requirements?"

def get_country(user_message: str, destination: Optional[str]) -> Optional[str]:
    """Determine country with a single Watsonx LLM call: extract from message or infer from destination"""
    dest_str = destination if destination else "None"
    prompt = f"""<|SYSTEM|>From the user message: '{user_message}'

Extract the country they are inquiring about for visas or travel requirements.

If none is specified in the message, then infer the country from the destination: '{dest_str}' (if destination is 'None', use 'None').

If no country can be determined, reply with 'None'

Reply with just the country name or 'None' in plain text
<|USER|>Return the country name or 'None' as plain text.<|END|>"""
    
    logger.info(f"Watsonx country prompt: {prompt[:500]}...")
    try:
        response = llm.generate(prompt=prompt)
        raw_country = response["results"][0]["generated_text"].strip()
        # Clean the response - remove any trailing tokens like <|END|>
        country = raw_country.split('<|')[0].strip()
        logger.info(f"Watsonx country response: {country}")
        return country if country != 'None' and country.lower() != 'none' else None
    except Exception as e:
        logger.error(f"Error getting country: {e}")
        return None

def visa_rag_node(state: TravelSearchState) -> TravelSearchState:
    """Enhanced visa RAG node that doesn't get stuck and encourages continued conversation"""
    config = VisaRAGConfig()
    rag = VisaRAGRetriever(config)
    
    user_message = state.get("current_message") or state.get("user_message", "")
    destination = state.get("destination")
    
    country = get_country(user_message, destination)
    
    if not country:
        logger.info("No country could be determined, providing general visa guidance.")
        state["visa_info_html"] = """
        <div class="visa-section">
            <h3>Visa Information</h3>
            <p>I'd be happy to help you with visa requirements! Please specify which country you're asking about.</p>
            <p>You can also ask me about flights, hotels, or start a new travel search anytime.</p>
        </div>
        """
        return state
    
    logger.info(f"Determined country: {country}")
    
    query = f"What are the visa requirements for {country}?"
    visa_answer = rag.answer_query(query)
    
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
    """Convert basic markdown to HTML"""
    html = markdown_text
    
    html = html.replace('### ', '<h4>').replace('\n### ', '</h4>\n<h4>')
    html = html.replace('## ', '<h3>').replace('\n## ', '</h3>\n<h3>')
    html = html.replace('# ', '<h2>').replace('\n# ', '</h2>\n<h2>')
    
    html = html.replace('**', '<strong>').replace('**', '</strong>')
    
    lines = html.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if line.startswith('- ') or line.startswith('* '):
            if not in_list:
                formatted_lines.append('<ul>')
                in_list = True
            formatted_lines.append(f'<li>{line[2:]}</li>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            if line:
                formatted_lines.append(f'<p>{line}</p>')
    
    if in_list:
        formatted_lines.append('</ul>')
    
    return '\n'.join(formatted_lines)