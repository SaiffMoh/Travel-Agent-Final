from langgraph.graph import StateGraph, END
from Models.TravelSearchState import TravelSearchState
from Nodes.analyze_conversation_node import analyze_conversation_node
from Nodes.create_packages import create_packages
from Nodes.format_body_node import format_body_node
from Nodes.get_access_token_node import get_access_token_node
from Nodes.get_city_IDs_node import get_city_IDs_node
from Nodes.get_flight_offers_node import get_flight_offers_node
from Nodes.get_hotel_offers_node import get_hotel_offers_node
from Nodes.llm_conversation_node import llm_conversation_node
from Nodes.normalize_info_node import normalize_info_node
from Nodes.parse_company_hotels_node import parse_company_hotels_node
from Nodes.summarize_packages import summarize_packages
from Nodes.toHTML import toHTML
from Nodes.visa_rag_node import visa_rag_node
from Nodes.general_conversation_node import general_conversation_node
from Nodes.invoice_extraction_node import invoice_extraction_node
from Utils.decisions import check_info_complete
from Utils.routing import smart_router

def create_travel_graph():
    graph = StateGraph(TravelSearchState)

    # Add all nodes
    graph.add_node("llm_conversation", llm_conversation_node)
    graph.add_node("general_conversation", general_conversation_node)
    graph.add_node("analyze_conversation", analyze_conversation_node)
    graph.add_node("normalize_info", normalize_info_node)
    graph.add_node("parse_company_hotels", parse_company_hotels_node)
    graph.add_node("format_body", format_body_node)
    graph.add_node("get_access_token", get_access_token_node)
    graph.add_node("get_flight_offers", get_flight_offers_node)
    graph.add_node("get_city_ids", get_city_IDs_node)
    graph.add_node("get_hotel_offers", get_hotel_offers_node)
    graph.add_node("create_packages", create_packages)
    graph.add_node("summarize_packages", summarize_packages)
    graph.add_node("to_html", toHTML)
    graph.add_node("visa_rag", visa_rag_node)
    graph.add_node("invoice_extraction", invoice_extraction_node)

    # Entry point and main routing
    graph.set_entry_point("llm_conversation")
    
    graph.add_conditional_edges(
        "llm_conversation",
        smart_router,
        {
            "travel_flow": "analyze_conversation",
            "visa_rag": "visa_rag",
            "general_conversation": "general_conversation",
            "invoice_extraction": "invoice_extraction",
            "need_more_info": END
        }
    )
    
    # End points for non-travel flows
    graph.add_edge("visa_rag", END)
    graph.add_edge("general_conversation", END)
    graph.add_edge("invoice_extraction", END)
    
    # Travel flow
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

    return graph