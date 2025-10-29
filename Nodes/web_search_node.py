# Nodes/web_search_node.py
import os
import logging
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

# Initialize OpenAI client for web search
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def web_search_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a web search using OpenAI's web_search tool and return HTML-formatted results.
    
    Args:
        state: Dictionary containing:
            - user_message: The search query from the user
            - thread_id: Conversation thread identifier
            
    Returns:
        Updated state with:
            - web_search_result: Raw text result from web search
            - web_search_html: HTML-formatted result for display
            - web_search_error: Error message if search fails
    """
    try:
        query = state.get("user_message", "").strip()
        
        if not query:
            logger.error("No query provided for web search")
            state["web_search_error"] = "No search query provided"
            state["web_search_html"] = generate_error_html("Please provide a search query.")
            return state
        
        logger.info(f"Executing web search for query: {query}")
        
        # Execute web search using OpenAI Responses API
        response = client.responses.create(
            model="gpt-4o-mini",
            input=query,
            tools=[{"type": "web_search"}]
        )
        
        # Extract text response from output
        search_result = extract_response_text(response)
        
        if not search_result:
            logger.warning("No search results returned")
            state["web_search_error"] = "No results found"
            state["web_search_html"] = generate_error_html("No search results found for your query.")
            return state
        
        logger.info(f"Web search successful, result length: {len(search_result)}")
        
        # Store results in state
        state["web_search_result"] = search_result
        state["web_search_html"] = generate_search_result_html(query, search_result)
        state["web_search_error"] = None
        
        return state
        
    except Exception as e:
        logger.error(f"Web search error: {str(e)}")
        state["web_search_error"] = str(e)
        state["web_search_html"] = generate_error_html(f"Search failed: {str(e)}")
        return state


def extract_response_text(response) -> str:
    """
    Extract text content from OpenAI response object.
    
    Args:
        response: OpenAI API response object
        
    Returns:
        Extracted text string
    """
    try:
        # Try to extract from output array
        if hasattr(response, "output") and len(response.output) >= 2:
            text_output = response.output[1]
            
            if hasattr(text_output, "content") and isinstance(text_output.content, list):
                if len(text_output.content) > 0:
                    first_content = text_output.content[0]
                    if hasattr(first_content, "text"):
                        return first_content.text.strip()
            
            if hasattr(text_output, "text"):
                return text_output.text.strip()
            
            return str(text_output)
        
        # Fallback extraction methods
        if hasattr(response, "output_text"):
            return response.output_text.strip()
        
        if hasattr(response, "text"):
            return response.text.strip()
        
        return "No textual output found in web search response."
        
    except Exception as e:
        logger.error(f"Error extracting response text: {str(e)}")
        return f"Error processing response: {str(e)}"


def generate_search_result_html(query: str, result: str) -> str:
    """
    Generate structured HTML for web search results with clickable links.
    """
    import html
    escaped_result = html.escape(result)
    formatted_result = escaped_result.replace('\n', '<br>')

    # Simple regex to make URLs clickable (basic example)
    def make_links_clickable(text):
        import re
        url_pattern = re.compile(r'(https?://[^\s]+)')
        return url_pattern.sub(r'<a href="\1" target="_blank" class="text-blue-600 hover:underline">\1</a>', text)

    formatted_result = make_links_clickable(formatted_result)

    return f"""
    <div class="web-search-results">
        {formatted_result}
    </div>
    """



def generate_error_html(error_message: str) -> str:
    """
    Generate HTML for displaying error messages.
    
    Args:
        error_message: The error message to display
        
    Returns:
        HTML-formatted error string
    """
    import html
    escaped_error = html.escape(error_message)
    
    html_content = f"""
    <div class="web-search-error p-4 bg-red-50 border border-red-200 rounded-lg">
        <div class="flex items-start gap-3">
            <svg class="w-5 h-5 text-red-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <div>
                <h3 class="text-lg font-semibold text-red-700 mb-1">Search Error</h3>
                <p class="text-red-600">{escaped_error}</p>
                <p class="text-sm text-gray-600 mt-2">Please try again with a different query or contact support if the problem persists.</p>
            </div>
        </div>
    </div>
    """
    
    return html_content