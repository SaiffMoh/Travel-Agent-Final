from datetime import datetime, date
from Models.TravelSearchState import TravelSearchState

def analyze_conversation_node(state: TravelSearchState) -> TravelSearchState:
    """Validate the information extracted by the LLM conversation node."""

    required_fields = ["departure_date", "origin", "destination", "cabin_class", "duration"]
    missing_fields = [f for f in required_fields if not state.get(f)]

    departure_date = state.get("departure_date")
    if departure_date:
        try:
            parsed_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
            if parsed_date < datetime.now().date():
                missing_fields.append("departure_date")
                state["departure_date"] = None
        except ValueError:
            missing_fields.append("departure_date")
            state["departure_date"] = None

    if missing_fields:
        state["info_complete"] = False
        state["needs_followup"] = True
        if not state.get("followup_question"):
            state["followup_question"] = "I still need some information to search for flights. Could you help me with the missing details?"
    else:
        state["info_complete"] = True
        state["needs_followup"] = False
        state["followup_question"] = None

    state["current_node"] = "analyze_conversation"
    return state
