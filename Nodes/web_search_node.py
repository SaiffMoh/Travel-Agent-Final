import os
import logging
import re
from typing import Dict, Any, List, Tuple, Optional
from openai import OpenAI
from dotenv import load_dotenv
import html
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

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
    Remove ALL tracking parameters (UTM, fbclid, gclid, etc.) from URLs.
    
    Args:
        url: The URL to clean
        
    Returns:
        Cleaned URL without tracking parameters
    """
    try:
        parsed = urlparse(url)
        
        if not parsed.query:
            return url
        
        # Parse query parameters
        params = parse_qs(parsed.query)
        
        # List of tracking parameters to remove
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'msclkid', 'mc_cid', 'mc_eid',
            '_ga', '_gl', 'ref', 'referrer', 'source',
            'zanpid', 'irclickid', 'irgwc', 'ranMID', 'ranEAID',
            'srsltid', 'sa', 'ved', 'uact'  # Google search params
        }
        
        # Filter out tracking parameters
        clean_params = {k: v for k, v in params.items() if k.lower() not in tracking_params}
        
        # Reconstruct query string
        clean_query = urlencode(clean_params, doseq=True) if clean_params else ''
        
        # Rebuild URL
        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            clean_query,
            parsed.fragment
        ))
        
        return clean_url
        
    except Exception as e:
        logger.warning(f"Error cleaning URL {url}: {e}")
        return url


def extract_tables(text: str) -> Tuple[List[str], str]:
    """
    Extract markdown-style tables from text.
    
    Args:
        text: Text that may contain tables
        
    Returns:
        Tuple of (list of table HTML strings, text with tables removed)
    """
    tables = []
    
    # Pattern for markdown tables
    table_pattern = r'(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n)+)'
    
    def table_replacer(match):
        table_text = match.group(1)
        table_html = convert_markdown_table_to_html(table_text)
        tables.append(table_html)
        return f"__TABLE_{len(tables)-1}__"
    
    # Replace tables with placeholders
    text_without_tables = re.sub(table_pattern, table_replacer, text)
    
    return tables, text_without_tables


def convert_markdown_table_to_html(table_text: str) -> str:
    """
    Convert markdown table to HTML table with professional styling.
    
    Args:
        table_text: Markdown table text
        
    Returns:
        HTML table string
    """
    lines = [line.strip() for line in table_text.strip().split('\n') if line.strip()]
    
    if len(lines) < 3:
        return table_text  # Not a valid table
    
    # Parse header
    headers = [cell.strip() for cell in lines[0].split('|') if cell.strip()]
    
    # Skip separator line (line 1)
    
    # Parse rows
    rows = []
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.split('|') if cell.strip()]
        if cells:
            rows.append(cells)
    
    # Build HTML
    html_parts = ['<div class="table-container"><table class="data-table">']
    
    # Header
    html_parts.append('<thead><tr>')
    for header in headers:
        html_parts.append(f'<th>{html.escape(header)}</th>')
    html_parts.append('</tr></thead>')
    
    # Body
    html_parts.append('<tbody>')
    for row in rows:
        html_parts.append('<tr>')
        for cell in row:
            html_parts.append(f'<td>{html.escape(cell)}</td>')
        html_parts.append('</tr>')
    html_parts.append('</tbody>')
    
    html_parts.append('</table></div>')
    
    return ''.join(html_parts)


def extract_structured_content(text: str) -> Dict[str, Any]:
    """
    Parse web search results to detect structure (paragraphs, lists, citations, tables).
    
    Args:
        text: Raw search result text
        
    Returns:
        Dictionary with structured content types
    """
    # First extract tables
    tables, text_without_tables = extract_tables(text)
    
    structure = {
        "has_numbered_list": bool(re.search(r'^\d+\.\s+', text_without_tables, re.MULTILINE)),
        "has_bullet_list": bool(re.search(r'^[•\-\*]\s+', text_without_tables, re.MULTILINE)),
        "has_citations": bool(re.search(r'\[\d+\]|\(\d+\)', text_without_tables)),
        "has_tables": len(tables) > 0,
        "tables": tables,
        "paragraphs": [],
        "sections": []
    }
    
    # Split into paragraphs
    paragraphs = [p.strip() for p in text_without_tables.split('\n\n') if p.strip()]
    structure["paragraphs"] = paragraphs
    
    # Detect sections (lines that look like headers)
    for para in paragraphs:
        lines = para.split('\n')
        if lines and len(lines[0]) < 100:
            # Check if it looks like a header (short, no ending punctuation except :)
            if not re.search(r'[.!?]$', lines[0]) or lines[0].endswith(':'):
                # Check if it's bold (contains ** or __)
                if '**' in lines[0] or '__' in lines[0]:
                    structure["sections"].append(lines[0])
                # Or if it's ALL CAPS
                elif lines[0].isupper() and len(lines[0]) > 3:
                    structure["sections"].append(lines[0])
                # Or if next line is content
                elif len(lines) > 1:
                    structure["sections"].append(lines[0])
    
    return structure


def format_paragraph(para: str) -> str:
    """
    Format a paragraph with proper HTML, handling lists, inline formatting, and links.
    
    Args:
        para: Paragraph text
        
    Returns:
        HTML-formatted paragraph
    """
    lines = para.split('\n')
    
    # Check if this is a numbered list
    if re.match(r'^\d+[\.\)]\s+', lines[0]):
        list_items = []
        for line in lines:
            # Remove list markers
            clean_line = re.sub(r'^\d+[\.\)]\s+', '', line)
            if clean_line:
                # Apply inline formatting
                formatted_line = apply_inline_formatting(clean_line)
                formatted_line = make_links_clickable(formatted_line)
                list_items.append(f'<li>{formatted_line}</li>')
        
        return f'<ol style="list-style: decimal; margin: 0 0 16px 24px; padding: 0;">{"".join(list_items)}</ol>'
    
    # Check if this is a bullet list
    elif re.match(r'^[•\-\*]\s+', lines[0]):
        list_items = []
        for line in lines:
            # Remove list markers
            clean_line = re.sub(r'^[•\-\*]\s+', '', line)
            if clean_line:
                # Apply inline formatting
                formatted_line = apply_inline_formatting(clean_line)
                formatted_line = make_links_clickable(formatted_line)
                list_items.append(f'<li>{formatted_line}</li>')
        
        return f'<ul style="list-style: disc; margin: 0 0 16px 24px; padding: 0;">{"".join(list_items)}</ul>'
    
    # Regular paragraph
    # Apply inline formatting
    formatted_para = apply_inline_formatting(para)
    
    # Make links clickable
    formatted_para = make_links_clickable(formatted_para)
    
    return f'<p style="margin: 0 0 16px 0; line-height: 1.8; color: #333;">{formatted_para}</p>'


def apply_inline_formatting(text: str) -> str:
    """
    Apply inline formatting (bold, italic, code) to text.
    
    Args:
        text: Plain text
        
    Returns:
        Text with HTML formatting
    """
    # Escape HTML first
    text = html.escape(text)
    
    # Bold with ** or __
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    
    # Italic with * or _
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<em>\1</em>', text)
    
    # Code with `
    text = re.sub(r'`(.+?)`', r'<code style="background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace;">\1</code>', text)
    
    return text


def make_links_clickable(text: str) -> str:
    """
    Convert URLs in text to clickable links, removing all tracking parameters.
    
    Args:
        text: Text containing URLs
        
    Returns:
        HTML with clickable links
    """
    def replace_url(match):
        url = match.group(0)
        
        # Clean UTM and tracking params
        clean = clean_url(url)
        
        # Extract domain for display
        try:
            domain = urlparse(clean).netloc
            if domain.startswith('www.'):
                domain = domain[4:]
        except:
            domain = clean
        
        # Truncate display text if URL is very long
        if len(clean) > 60:
            display_text = f"{domain}/..."
        else:
            display_text = clean
        
        return f'<a href="{clean}" target="_blank" rel="noopener noreferrer" style="color: #000; text-decoration: underline; word-break: break-word;">{html.escape(display_text)}</a>'
    
    # Match URLs
    url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
    return url_pattern.sub(replace_url, text)


def restore_tables(text: str, tables: List[str]) -> str:
    """
    Restore table placeholders with actual table HTML.
    
    Args:
        text: Text with table placeholders
        tables: List of table HTML strings
        
    Returns:
        Text with tables restored
    """
    for i, table_html in enumerate(tables):
        text = text.replace(f"__TABLE_{i}__", table_html)
    
    return text


def generate_search_result_html(query: str, result: str) -> str:
    """
    Generate professional, structured HTML for web search results.
    
    Args:
        query: The search query
        result: Raw search result text
        
    Returns:
        HTML-formatted search results
    """
    structure = extract_structured_content(result)
    
    html_parts = [
        """
        <style>
            .search-container {
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
            }
            .section-header {
                border-bottom: 2px solid #000;
                padding-bottom: 12px;
                margin-bottom: 24px;
            }
            .section-title {
                font-size: 24px;
                font-weight: 600;
                margin: 0;
                letter-spacing: -0.5px;
            }
            .section-subtitle {
                font-size: 14px;
                margin: 4px 0 0 0;
                opacity: 0.7;
            }
            .search-content {
                border: 1px solid #ddd;
                padding: 20px;
                margin-bottom: 16px;
                background: #fff;
            }
            .content-section {
                margin-bottom: 24px;
            }
            .content-section:last-child {
                margin-bottom: 0;
            }
            .subsection-title {
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin: 0 0 12px 0;
                padding-bottom: 8px;
                border-bottom: 1px solid #ddd;
            }
            .search-content p {
                line-height: 1.8;
                color: #333;
                margin: 0 0 16px 0;
            }
            .search-content ul, .search-content ol {
                margin: 0 0 16px 24px;
                padding: 0;
            }
            .search-content li {
                line-height: 1.8;
                margin-bottom: 8px;
                color: #333;
            }
            .search-content a {
                color: #000;
                text-decoration: underline;
                word-break: break-word;
            }
            .table-container {
                overflow-x: auto;
                margin: 16px 0;
            }
            .data-table {
                width: 100%;
                border-collapse: collapse;
                border: 1px solid #ddd;
            }
            .data-table th {
                background: #fafafa;
                padding: 12px;
                text-align: left;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                border-bottom: 1px solid #ddd;
            }
            .data-table td {
                padding: 12px;
                border-bottom: 1px solid #eee;
                vertical-align: top;
                font-size: 14px;
            }
            .data-table tr:last-child td {
                border-bottom: none;
            }
            .notice-box {
                border: 1px solid #ddd;
                padding: 20px;
                text-align: center;
                background: #fafafa;
                margin-top: 16px;
            }
            .notice-box p {
                margin: 0;
                font-size: 13px;
                line-height: 1.6;
            }
        </style>
        """,
        '<div class="search-container">',
        '<div class="section-header">',
        '<h1 class="section-title">Web Search Results</h1>',
        f'<p class="section-subtitle">{html.escape(query)}</p>',
        '</div>',
        '<div class="search-content">'
    ]
    
    # Process content based on structure
    if structure["paragraphs"]:
        current_section = None
        for i, para in enumerate(structure["paragraphs"]):
            # Check if this is a section header
            if para in structure["sections"] and len(para) < 100:
                # Close previous section if exists
                if current_section is not None:
                    html_parts.append('</div>')
                
                # Start new section
                clean_header = para.replace('**', '').replace('__', '')
                html_parts.append('<div class="content-section">')
                html_parts.append(f'<h2 class="subsection-title">{html.escape(clean_header)}</h2>')
                current_section = clean_header
            else:
                # If no section started yet, start one
                if current_section is None:
                    html_parts.append('<div class="content-section">')
                    current_section = "Results"
                
                # Format as paragraph or list
                formatted = format_paragraph(para)
                html_parts.append(formatted)
        
        # Close last section
        if current_section is not None:
            html_parts.append('</div>')
    else:
        # Fallback: simple formatting
        formatted_result = apply_inline_formatting(result)
        formatted_result = formatted_result.replace('\n\n', '</p><p style="margin: 0 0 16px 0; line-height: 1.8; color: #333;">')
        formatted_result = formatted_result.replace('\n', '<br>')
        formatted_result = make_links_clickable(formatted_result)
        html_parts.append(f'<p style="margin: 0 0 16px 0; line-height: 1.8; color: #333;">{formatted_result}</p>')
    
    # Restore tables
    if structure["has_tables"]:
        html_content = ''.join(html_parts)
        html_content = restore_tables(html_content, structure["tables"])
        html_parts = [html_content]
    
    # Close search content
    html_parts.append('</div>')
    
    # Add notice section
    html_parts.extend([
        '<div class="notice-box">',
        '<p>',
        'I can also help you find flights, hotels, visa requirements, and complete travel packages.<br>',
        'Just ask me about your travel plans.',
        '</p>',
        '</div>',
        '</div>'
    ])
    
    return '\n'.join(html_parts)


def generate_error_html(error_message: str) -> str:
    """
    Generate professional HTML for displaying error messages.
    
    Args:
        error_message: The error message to display
        
    Returns:
        HTML-formatted error string
    """
    escaped_error = html.escape(error_message)
    
    html_content = f"""
    <style>
        .error-container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        }}
        .error-box {{
            border: 2px solid #000;
            padding: 32px;
            text-align: center;
            background: #fafafa;
        }}
        .error-icon {{
            font-size: 48px;
            margin-bottom: 16px;
        }}
        .error-title {{
            font-size: 20px;
            font-weight: 600;
            margin: 0 0 12px 0;
        }}
        .error-message {{
            margin: 0 0 20px 0;
            font-size: 14px;
            line-height: 1.6;
        }}
        .error-suggestions {{
            border-top: 1px solid #ddd;
            padding-top: 20px;
            margin-top: 20px;
        }}
        .error-suggestions p {{
            margin: 0 0 8px 0;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }}
        .error-suggestions ul {{
            list-style: none;
            padding: 0;
            margin: 12px 0 0 0;
            text-align: left;
        }}
        .error-suggestions li {{
            padding: 8px 0;
            border-bottom: 1px solid #eee;
            font-size: 13px;
        }}
        .error-suggestions li:last-child {{
            border-bottom: none;
        }}
    </style>
    <div class="error-container">
        <div class="error-box">
            <div class="error-icon">✗</div>
            <h3 class="error-title">Search Error</h3>
            <p class="error-message">{escaped_error}</p>
            <div class="error-suggestions">
                <p>Suggestions:</p>
                <ul>
                    <li>Try rephrasing your search query</li>
                    <li>Check your internet connection</li>
                    <li>Use more specific search terms</li>
                    <li>Ask me about flights, hotels, or visa requirements instead</li>
                </ul>
            </div>
        </div>
    </div>
    """
    
    return html_content