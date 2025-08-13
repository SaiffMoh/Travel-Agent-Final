from typing import Dict, Any, List
from Utils.getLLM import get_llm
from Prompts.summary_prompt import summary_prompt
from langchain.schema import HumanMessage

def summarize_hotels_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate LLM summary and recommendation for hotel offers."""
    try:
        (state.setdefault("node_trace", [])).append("summarize_hotels")
    except Exception:
        pass

    formatted_offers = state.get("formatted_hotel_offers", {}).get("all", [])
    cheapest_per_category = state.get("formatted_hotel_offers", {}).get("cheapest_per_category", {})

    if not formatted_offers:
        state["summary"] = "No hotel options found for your search."
        return state

    try:
        # Use OpenAI's ChatCompletion API
        summary_response = get_llm().invoke([HumanMessage(content=summary_prompt)])
        state["summary"] = summary_response.content
        print("Generated summary:", summary_response.content)
    except Exception as e:
        print(f"Error generating summary: {e}")
        import traceback
        traceback.print_exc()
        state["summary"] = (
            "Great! I found several hotel options for your trip. "
            "Here are the best choices based on price and convenience. "
            "Check cancellation policies before booking."
        )

    state["current_node"] = "summarize_hotels_node"
    return state