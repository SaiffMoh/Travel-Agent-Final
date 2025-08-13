import re
from Models.TravelSearchState import TravelSearchState

def check_info_complete(state: TravelSearchState) -> str:
    """
    Decide what to do after analyze_conversation.
    Branches into flights, hotels, or packages if enough info.
    """
    try:
        # If user typed a number → selection request
        msg = str(state.get("current_message", ""))
        if re.search(r"\b\d+\b", msg) and state.get("formatted_results"):
            return "selection_request"
    except Exception:
        pass

    if state.get("info_complete", False):
        req_type = state.get("request_type")
        if req_type == "flights":
            return "flights"
        elif req_type == "hotels":
            return "hotels"
        elif req_type == "packages":
            return "packages"

    return "ask_followup"


def check_selection_complete(state: TravelSearchState) -> str:
    """
    If after selecting a flight we have enough info for hotel search, continue.
    """
    if state.get("city_code") and state.get("checkin_date") and state.get("checkout_date"):
        return "continue_hotel_search"
    return "ask_followup"
