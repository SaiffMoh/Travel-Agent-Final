from langgraph.graph import StateGraph, END
from Models.TravelSearchState import TravelSearchState
from Nodes import (
    llm_conversation_node,
    analyze_conversation_node,
    normalize_info_node,
    get_city_IDs_node,
    get_access_token_node,
    get_flight_offers_node,
    get_hotel_offers_node,
    create_packages,
    format_body_node,
    summarize_packages,
    toHTML
)
from Utils.decisions import check_info_complete

def create_travel_graph():
    graph = StateGraph(TravelSearchState)

    # Nodes
    graph.add_node("llm_conversation", llm_conversation_node)
    graph.add_node("analyze_conversation", analyze_conversation_node)
    graph.add_node("normalize_info", normalize_info_node)
    graph.add_node("get_city_ids", get_city_IDs_node)
    graph.add_node("get_access_token", get_access_token_node)
    graph.add_node("get_flight_offers", get_flight_offers_node)
    graph.add_node("get_hotel_offers", get_hotel_offers_node)
    graph.add_node("create_packages", create_packages)
    graph.add_node("format_body", format_body_node)
    graph.add_node("summarize_packages", summarize_packages)
    graph.add_node("to_html", toHTML)

    # Flow
    graph.add_edge("llm_conversation", "analyze_conversation")
    graph.add_conditional_edges(
        "analyze_conversation",
        check_info_complete,
        {
            "flights": "normalize_info",
            "hotels": "normalize_info",
            "packages": "normalize_info",
            "selection_request": "selection", 
            "ask_followup": END
        }
    )
    graph.add_edge("normalize_info", "get_city_ids")
    graph.add_edge("get_city_ids", "get_access_token")

    # Data fetch
    graph.add_edge("get_access_token", "get_flight_offers")
    graph.add_edge("get_access_token", "get_hotel_offers")
    graph.add_edge("get_access_token", "create_packages")

    # Format
    graph.add_edge("get_flight_offers", "format_body")
    graph.add_edge("get_hotel_offers", "format_body")
    graph.add_edge("create_packages", "summarize_packages")
    graph.add_edge("summarize_packages", "format_body")

    # Output
    graph.add_edge("format_body", "to_html")
    graph.add_edge("to_html", END)

    # Entry point
    graph.set_entry_point("llm_conversation")

    return graph
