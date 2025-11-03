"""
Dynamic Graph Configuration with Booking Flow
Routes to fallback nodes when USE_FALLBACK=true, otherwise uses original nodes
Visa RAG is accessible from all conversation flows
Booking node handles package selection and document verification
"""

from langgraph.graph import StateGraph, END
from Models.TravelSearchState import TravelSearchState
from Utils.decisions import check_info_complete
from Utils.routing import smart_router
import os
from dotenv import load_dotenv

load_dotenv()

# Check environment variable
USE_FALLBACK = os.getenv("USE_FALLBACK", "false").lower() == "true"

# Import base nodes (always needed)
from Nodes.analyze_conversation_node import analyze_conversation_node
from Nodes.create_packages import create_packages
from Nodes.format_body_node import format_body_node
from Nodes.get_access_token_node import get_access_token_node
from Nodes.llm_conversation_node import llm_conversation_node
from Nodes.normalize_info_node import normalize_info_node
from Nodes.parse_company_hotels_node import parse_company_hotels_node
from Nodes.summarize_packages import summarize_packages
from Nodes.toHTML import toHTML
from Nodes.visa_rag_node import visa_rag_node
from Nodes.general_conversation_node import general_conversation_node
from Nodes.invoice_extraction_node import invoice_extraction_node
from Nodes.booking_node import booking_node  # NEW

# Conditionally import nodes based on USE_FALLBACK
if USE_FALLBACK:
    print("🔄 Fallback mode ENABLED - Using fallback nodes with database support")
    from Nodes.fallback_nodes import (
        get_flight_offers_node_with_fallback as get_flight_offers_node,
        get_city_IDs_node_with_fallback as get_city_IDs_node,
        get_hotel_offers_node_with_fallback as get_hotel_offers_node
    )
else:
    print("🌐 Fallback mode DISABLED - Using original API-only nodes")
    from Nodes.get_flight_offers_node import get_flight_offers_node
    from Nodes.get_city_IDs_node import get_city_IDs_node
    from Nodes.get_hotel_offers_node import get_hotel_offers_node


def create_travel_graph():
    """
    Create the travel agent graph with booking flow support.
    
    Flow additions:
    - Booking node accessible from main router
    - Booking verifies passport and visa uploads
    - Can route back to booking after document uploads
    """
    graph = StateGraph(TravelSearchState)

    # Add all nodes
    graph.add_node("llm_conversation", llm_conversation_node)
    graph.add_node("general_conversation", general_conversation_node)
    graph.add_node("analyze_conversation", analyze_conversation_node)
    graph.add_node("normalize_info", normalize_info_node)
    graph.add_node("parse_company_hotels", parse_company_hotels_node)
    graph.add_node("format_body", format_body_node)
    graph.add_node("get_access_token", get_access_token_node)
    graph.add_node("create_packages", create_packages)
    graph.add_node("summarize_packages", summarize_packages)
    graph.add_node("to_html", toHTML)
    graph.add_node("visa_rag", visa_rag_node)
    graph.add_node("invoice_extraction", invoice_extraction_node)
    graph.add_node("booking", booking_node)  # NEW
    
    # Add the dynamically selected nodes
    graph.add_node("get_flight_offers", get_flight_offers_node)
    graph.add_node("get_city_ids", get_city_IDs_node)
    graph.add_node("get_hotel_offers", get_hotel_offers_node)

    # Entry point and main routing
    graph.set_entry_point("llm_conversation")
    
    # Main router with booking as a new destination
    graph.add_conditional_edges(
        "llm_conversation",
        smart_router,
        {
            "travel_flow": "analyze_conversation",
            "visa_rag": "visa_rag",
            "general_conversation": "general_conversation",
            "invoice_extraction": "invoice_extraction",
            "booking": "booking",  # NEW
            "need_more_info": END
        }
    )
    
    # End points for non-travel flows
    graph.add_edge("visa_rag", END)
    graph.add_edge("general_conversation", END)
    graph.add_edge("invoice_extraction", END)
    graph.add_edge("booking", END)  # NEW - Booking ends here
    
    # Travel flow (unchanged)
    graph.add_conditional_edges(
        "analyze_conversation",
        check_info_complete,
        {
            "flights": "normalize_info",
            "hotels": "normalize_info",
            "packages": "normalize_info",
            "selection_request": "normalize_info",
            "ask_followup": END
        }
    )
    
    # Main travel search pipeline
    graph.add_edge("normalize_info", "parse_company_hotels")
    graph.add_edge("parse_company_hotels", "format_body")
    graph.add_edge("format_body", "get_access_token")
    graph.add_edge("get_access_token", "get_flight_offers")
    graph.add_edge("get_flight_offers", "get_city_ids")
    graph.add_edge("get_city_ids", "get_hotel_offers")
    graph.add_edge("get_hotel_offers", "create_packages")
    graph.add_edge("create_packages", "summarize_packages")
    graph.add_edge("summarize_packages", "to_html")
    graph.add_edge("to_html", END)

    # Log the mode
    mode = "FALLBACK (with database)" if USE_FALLBACK else "ORIGINAL (API-only)"
    print(f"✅ Travel graph created in {mode} mode")
    print(f"🔍 Visa RAG is universally accessible across all flows")
    print(f"📦 Booking flow integrated with document verification")
    
    return graph


def get_graph_mode():
    """Returns the current graph mode configuration"""
    return {
        "use_fallback": USE_FALLBACK,
        "mode": "fallback" if USE_FALLBACK else "original",
        "description": "Database fallback enabled" if USE_FALLBACK else "API-only mode",
        "visa_rag_enabled": True,
        "booking_flow_enabled": True  # NEW
    }


if __name__ == "__main__":
    print("\n" + "="*60)
    print("GRAPH CONFIGURATION TEST")
    print("="*60)
    
    mode_info = get_graph_mode()
    print(f"\nCurrent Mode: {mode_info['mode'].upper()}")
    print(f"USE_FALLBACK: {mode_info['use_fallback']}")
    print(f"Description: {mode_info['description']}")
    print(f"Visa RAG Universal Access: {mode_info['visa_rag_enabled']}")
    print(f"Booking Flow: {mode_info['booking_flow_enabled']}")
    
    print("\n" + "="*60)
    print("Creating graph...")
    graph = create_travel_graph()
    print("✅ Graph creation successful!")
    print("="*60)