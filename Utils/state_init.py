from typing import Dict, Any

def initialize_state_from_thread(
    thread_id: str,
    conversation_history: list,
    current_message: str
) -> Dict[str, Any]:
    """
    Initialize TravelSearchState for flights, hotels, and packages.
    """
    return {
        "thread_id": thread_id,
        "conversation": conversation_history,
        "current_message": current_message,
        "current_node": "llm_conversation",
        "node_trace": [],

        "needs_followup": True,
        "info_complete": False,

        "request_type": None,  # flights / hotels / packages

        # Common search params
        "origin": None,
        "destination": None,
        "departure_date": None,
        "return_date": None,
        "cabin_class": None,
        "duration": None,

        # Hotels
        "city_code": None,
        "checkin_date": None,
        "checkout_date": None,

        # Results
        "formatted_results": None,
        "selected_offer": None,

        # Package-specific
        "package_results": None
    }
