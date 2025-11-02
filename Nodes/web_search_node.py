import os
import logging
import re
from typing import Dict, Any, List, Tuple
from openai import OpenAI
from dotenv import load_dotenv
import html

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


def clean_url(url: str) -> str:
    """
    Remove OpenAI UTM parameters and other tracking parameters from URLs.
    
    Args:
        url: The URL to clean
        
    Returns:
        Cleaned URL without UTM parameters
    """
    # Remove utm_source=chatgpt.com and similar OpenAI tracking parameters
    url = re.sub(r'[?&]utm_source=chatgpt\.com', '', url)
    url = re.sub(r'[?&]utm_medium=[^&]*', '', url)
    url = re.sub(r'[?&]utm_campaign=[^&]*', '', url)
    url = re.sub(r'[?&]utm_content=[^&]*', '', url)
    url = re.sub(r'[?&]utm_term=[^&]*', '', url)
    
    # Clean up any trailing ? or & after removing parameters
    url = re.sub(r'[?&]$', '', url)
    
    # If we removed all parameters, clean up the separator
    url = re.sub(r'\?&', '?', url)
    
    return url


def extract_structured_content(text: str) -> Dict[str, Any]:
    """
    Parse web search results to detect structure (paragraphs, lists, citations).
    
    Args:
        text: Raw search result text
        
    Returns:
        Dictionary with structured content types
    """
    structure = {
        "has_numbered_list": bool(re.search(r'^\d+\.\s+', text, re.MULTILINE)),
        "has_bullet_list": bool(re.search(r'^[•\-\*]\s+', text, re.MULTILINE)),
        "has_citations": bool(re.search(r'\[\d+\]|\(\d+\)', text)),
        "paragraphs": [],
        "sections": []
    }
    
    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    structure["paragraphs"] = paragraphs
    
    # Detect sections (lines that look like headers)
    for para in paragraphs:
        lines = para.split('\n')
        if lines and len(lines[0]) < 100 and not lines[0].endswith(('.', '!', '?', ':')):
            structure["sections"].append(lines[0])
    
    return structure


def format_paragraph(para: str) -> str:
    """
    Format a paragraph with proper HTML, handling lists and inline formatting.
    
    Args:
        para: Paragraph text
        
    Returns:
        HTML-formatted paragraph
    """
    lines = para.split('\n')
    
    # Check if this is a list
    if re.match(r'^[\d•\-\*]+[\.\)]\s+', lines[0]):
        # It's a list
        list_items = []
        list_type = 'ol' if re.match(r'^\d+[\.\)]\s+', lines[0]) else 'ul'
        
        for line in lines:
            # Remove list markers
            clean_line = re.sub(r'^[\d•\-\*]+[\.\)]\s+', '', line)
            if clean_line:
                list_items.append(f'<li class="mb-2">{html.escape(clean_line)}</li>')
        
        list_class = 'list-decimal' if list_type == 'ol' else 'list-disc'
        return f'<{list_type} class="{list_class} ml-6 space-y-2">{"".join(list_items)}</{list_type}>'
    
    # Regular paragraph
    escaped_para = html.escape(para)
    
    # Make bold text (if present with ** or __)
    escaped_para = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped_para)
    escaped_para = re.sub(r'__(.+?)__', r'<strong>\1</strong>', escaped_para)
    
    # Make italic text
    escaped_para = re.sub(r'\*(.+?)\*', r'<em>\1</em>', escaped_para)
    escaped_para = re.sub(r'_(.+?)_', r'<em>\1</em>', escaped_para)
    
    return f'<p class="mb-4 leading-relaxed">{escaped_para}</p>'


def make_links_clickable(text: str) -> str:
    """
    Convert URLs in text to clickable links, removing OpenAI UTM parameters.
    
    Args:
        text: Text containing URLs
        
    Returns:
        HTML with clickable links
    """
    def replace_url(match):
        url = match.group(0)
        clean = clean_url(url)
        # Truncate display text if URL is very long
        display_text = clean if len(clean) <= 60 else clean[:57] + '...'
        return f'<a href="{clean}" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-800 underline break-words">{html.escape(display_text)}</a>'
    
    url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
    return url_pattern.sub(replace_url, text)


def generate_search_result_html(query: str, result: str) -> str:
    """
    Generate structured HTML for web search results with intelligent formatting.
    
    Args:
        query: The search query
        result: Raw search result text
        
    Returns:
        HTML-formatted search results
    """
    structure = extract_structured_content(result)
    
    html_parts = [
        '<div class="web-search-results max-w-4xl mx-auto">',
        '<div class="search-content space-y-4">'
    ]
    
    # Process content based on structure
    if structure["paragraphs"]:
        for i, para in enumerate(structure["paragraphs"]):
            # Check if this looks like a section header
            if para in structure["sections"] and len(para) < 100:
                html_parts.append(
                    f'<h3 class="text-lg font-semibold text-gray-900 mt-6 mb-3">{html.escape(para)}</h3>'
                )
            else:
                # Format as paragraph or list
                formatted = format_paragraph(para)
                # Make links clickable
                formatted = make_links_clickable(formatted)
                html_parts.append(formatted)
    else:
        # Fallback: simple formatting
        escaped_result = html.escape(result)
        formatted_result = escaped_result.replace('\n\n', '</p><p class="mb-4 leading-relaxed">')
        formatted_result = formatted_result.replace('\n', '<br>')
        formatted_result = make_links_clickable(formatted_result)
        html_parts.append(f'<p class="mb-4 leading-relaxed">{formatted_result}</p>')
    
    html_parts.extend([
        '</div>',
        '</div>'
    ])
    
    return '\n'.join(html_parts)


def generate_error_html(error_message: str) -> str:
    """
    Generate HTML for displaying error messages.
    
    Args:
        error_message: The error message to display
        
    Returns:
        HTML-formatted error string
    """
    escaped_error = html.escape(error_message)
    
    html_content = f"""
    <div class="web-search-error max-w-2xl mx-auto p-6 bg-red-50 border border-red-200 rounded-lg shadow-sm">
        <div class="flex items-start gap-3">
            <svg class="w-6 h-6 text-red-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <div class="flex-1">
                <h3 class="text-lg font-semibold text-red-800 mb-2">Search Error</h3>
                <p class="text-red-700 mb-3">{escaped_error}</p>
                <p class="text-sm text-gray-700">Please try again with a different query or contact support if the problem persists.</p>
            </div>
        </div>
    </div>
    """
    
    return html_content