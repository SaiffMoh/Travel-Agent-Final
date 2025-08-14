from datetime import datetime, date
from Models.TravelSearchState import TravelSearchState

def analyze_conversation_node(state: TravelSearchState) -> TravelSearchState:
    """Validate the information extracted by the LLM conversation node and craft targeted follow-up."""

    # Determine which fields are still missing or invalid
    missing_fields = []

    # Validate departure date
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
    else:
        missing_fields.append("departure_date")

    # Validate origin and destination
    if not state.get("origin"):
        missing_fields.append("origin")
    if not state.get("destination"):
        missing_fields.append("destination")

    # Duration and cabin_class are required to proceed to packages flow
    if state.get("duration") is None:
        missing_fields.append("duration")
    if not state.get("cabin_class"):
        missing_fields.append("cabin_class")

    # Decide completion: require all 5 fields
    required_fields = ["departure_date", "origin", "destination", "duration", "cabin_class"]
    core_complete = all(field not in missing_fields for field in required_fields)

    if not core_complete:
        state["info_complete"] = False
        state["needs_followup"] = True

        # Generate a single, specific follow-up question if not already provided by LLM
        if not state.get("followup_question"):
            question = None
            if "origin" in missing_fields:
                question = "Which city are you flying from?"
            elif "destination" in missing_fields:
                question = "Which city would you like to fly to?"
            elif "departure_date" in missing_fields:
                question = "What is your departure date? (YYYY-MM-DD)"
            elif "duration" in missing_fields:
                question = "How many days will you stay (trip duration)?"
            elif "cabin_class" in missing_fields:
                question = "Which cabin class do you prefer (economy, business, or first)?"

            state["followup_question"] = question or "Could you share your origin, destination, departure date, duration (days), and preferred cabin class?"
    else:
        state["info_complete"] = True
        state["needs_followup"] = False
        state["followup_question"] = None
        # Default request type to flights so the graph can proceed
        state.setdefault("request_type", "flights")

    state["current_node"] = "analyze_conversation"
    return state
