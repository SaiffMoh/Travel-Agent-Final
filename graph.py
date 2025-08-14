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
from Nodes.summarize_packages import summarize_packages
from Nodes.toHTML import toHTML
from Utils.decisions import check_info_complete

def create_travel_graph():
    graph = StateGraph(TravelSearchState)

    # Nodes
    graph.add_node("llm_conversation", llm_conversation_node)
    graph.add_node("analyze_conversation", analyze_conversation_node)
    graph.add_node("normalize_info", normalize_info_node)
    graph.add_node("format_body", format_body_node)
    graph.add_node("get_access_token", get_access_token_node)
    graph.add_node("get_flight_offers", get_flight_offers_node)
    graph.add_node("get_city_ids", get_city_IDs_node)
    graph.add_node("get_hotel_offers", get_hotel_offers_node)
    graph.add_node("create_packages", create_packages)
    graph.add_node("summarize_packages", summarize_packages)
    graph.add_node("to_html", toHTML)

    # Flow according to your sequence
    graph.add_edge("llm_conversation", "analyze_conversation")
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
    graph.add_edge("normalize_info", "format_body")
    graph.add_edge("format_body", "get_access_token")
    graph.add_edge("get_access_token", "get_flight_offers")
    graph.add_edge("get_flight_offers", "get_city_ids")
    graph.add_edge("get_city_ids", "get_hotel_offers")
    graph.add_edge("get_hotel_offers", "create_packages")
    graph.add_edge("create_packages", "summarize_packages")
    graph.add_edge("summarize_packages", "to_html")
    graph.add_edge("to_html", END)

    # Entry point
    graph.set_entry_point("llm_conversation")

    return graph
