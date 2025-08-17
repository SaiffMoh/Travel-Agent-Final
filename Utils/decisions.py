import re
from Models.TravelSearchState import TravelSearchState

def check_info_complete(state: TravelSearchState) -> str:
    """
    Decide what to do after analyze_conversation.
    Branches into flights, hotels, or packages if enough info.
    """
    print(f"DEBUG check_info_complete: info_complete={state.get('info_complete')}, request_type={state.get('request_type')}")
    print(f"DEBUG check_info_complete: needs_followup={state.get('needs_followup')}, followup_question={state.get('followup_question')}")
    
    try:
        # If user typed a number → selection request
        msg = str(state.get("current_message", ""))
        if re.search(r"\b\d+\b", msg) and state.get("formatted_results"):
            print("DEBUG: Routing to selection_request")
            return "selection_request"
    except Exception:
        pass

    # Check if information is complete
    if state.get("info_complete", False):
<<<<<<< HEAD
        req_type = state.get("request_type", "flights")  # Default to flights
        print(f"DEBUG: Info complete, routing to {req_type}")
=======
        req_type = state.get("request_type") or "flights"
>>>>>>> 6af8097fe9825879df8bfa14c52dbb89ce68716d
        if req_type == "flights":
            return "flights"
        elif req_type == "hotels":
            return "hotels"
        elif req_type == "packages":
            return "packages"
        else:
            # Default to flights if request_type is not recognized
            return "flights"

    print("DEBUG: Info incomplete, routing to ask_followup")
    return "ask_followup"

