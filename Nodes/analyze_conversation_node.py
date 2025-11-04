from datetime import datetime, date
from Models.TravelSearchState import TravelSearchState

def analyze_conversation_node(state: TravelSearchState) -> TravelSearchState:
    """Validate the information extracted by the LLM conversation node based on request_type and trip_type."""

    # Determine which fields are still missing or invalid
    missing_fields = []

    # Validate departure date (ALWAYS REQUIRED)
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

    # Validate origin and destination (ALWAYS REQUIRED)
    if not state.get("origin"):
        missing_fields.append("origin")
    if not state.get("destination"):
        missing_fields.append("destination")

    # Get request type and trip type
    request_type = state.get("request_type", "packages")
    trip_type = state.get("trip_type", "round_trip")

    # CONDITIONAL VALIDATION BASED ON REQUEST TYPE AND TRIP TYPE
    
    # Duration validation
    if request_type == "hotels":
        # Hotels ALWAYS need duration (number of nights)
        if state.get("duration") is None:
            missing_fields.append("duration")
    elif request_type in ["flights", "packages"]:
        if trip_type == "round_trip":
            # Round trip needs duration (days until return)
            if state.get("duration") is None:
                missing_fields.append("duration")
        elif trip_type == "one_way":
            # One-way does NOT need duration - set to None if present
            state["duration"] = None
    
    # Cabin class validation (only for flights/packages)
    if request_type in ["flights", "packages"]:
        if not state.get("cabin_class"):
            missing_fields.append("cabin_class")
    elif request_type == "hotels":
        # Hotels don't need cabin class
        state["cabin_class"] = None

    # Build required fields list dynamically based on request_type and trip_type
    required_fields = ["departure_date", "origin", "destination"]
    
    if request_type == "hotels":
        required_fields.extend(["duration"])
    elif request_type in ["flights", "packages"]:
        required_fields.append("cabin_class")
        if trip_type == "round_trip":
            required_fields.append("duration")
    
    # Check if all required fields are present
    core_complete = all(field not in missing_fields for field in required_fields)

    if not core_complete:
        state["info_complete"] = False
        state["needs_followup"] = True

        # Generate a single, specific follow-up question if not already provided by LLM
        if not state.get("followup_question"):
            question = None
            if "origin" in missing_fields:
                question = "Which city are you departing from?"
            elif "destination" in missing_fields:
                question = "Which city would you like to go to?"
            elif "departure_date" in missing_fields:
                question = "What is your departure date? (YYYY-MM-DD)"
            elif "duration" in missing_fields:
                if request_type == "hotels":
                    question = "How many nights will you be staying?"
                else:  # round trip flights/packages
                    question = "How many days will your trip last?"
            elif "cabin_class" in missing_fields:
                question = "Which cabin class do you prefer (economy, business, or first)?"

            state["followup_question"] = question or "Could you provide more details about your travel?"
    else:
        state["info_complete"] = True
        state["needs_followup"] = False
        state["followup_question"] = None
        # Ensure request_type is set
        state["request_type"] = request_type
        state["trip_type"] = trip_type

    state["current_node"] = "analyze_conversation"
    return state