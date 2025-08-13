from langgraph.graph import StateGraph, END
from models import FlightSearchState,HotelSearchState, TravelSearchState
from typing import Dict, Any
from Models.TravelSearchState import TravelSearchState
import re

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
graph = StateGraph(TravelSearchState)
# Conversation
graph.add_node("llm_conversation", llm_conversation_node)
graph.add_node("analyze_conversation", analyze_conversation_node)
graph.add_node("normalize_info", normalize_info_node)
graph.add_node("get_city_ids", get_city_IDs_node)
graph.add_node("get_access_token", get_access_token_node)

# Fetching data
graph.add_node("get_flight_offers", get_flight_offers_node)
graph.add_node("get_hotel_offers", get_hotel_offers_node)
graph.add_node("create_packages", create_packages)

# Formatting
graph.add_node("format_body", format_body_node)
graph.add_node("summarize_packages", summarize_packages)
graph.add_node("to_html", toHTML)

# Flow
graph.add_edge("llm_conversation", "analyze_conversation")
graph.add_edge("analyze_conversation", "normalize_info")
graph.add_edge("normalize_info", "get_city_ids")
graph.add_edge("get_city_ids", "get_access_token")

# Branching logic for different searches
graph.add_edge("get_access_token", "get_flight_offers")
graph.add_edge("get_access_token", "get_hotel_offers")
graph.add_edge("get_access_token", "create_packages")

graph.add_edge("get_flight_offers", "format_body")
graph.add_edge("get_hotel_offers", "format_body")
graph.add_edge("create_packages", "summarize_packages")
graph.add_edge("summarize_packages", "format_body")

graph.add_edge("format_body", "to_html")
graph.add_edge("to_html", END)

if __name__ == "__main__":
    app = graph.compile()
    app.run()