from datetime import datetime, timedelta
from Models.TravelSearchState import TravelSearchState

def build_input_extraction_prompt(state: TravelSearchState) -> str:
    """Build context-aware prompt for input extraction that handles seamless conversation flow"""
    
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    current_month = current_date.month
    current_day = current_date.day
    current_year = current_date.year
    tomorrow_str = (current_date + timedelta(days=1)).strftime("%Y-%m-%d")
    
    conversation_text = "".join(f"{m['role']}: {m['content']}\n" for m in state.get("conversation", []))
    user_text = state.get("current_message", "")
    travel_completed = state.get("travel_search_completed", False)
    
    # Build current state context
    current_state_info = ""
    if state.get("departure_date"):
        current_state_info += f"Current departure date: {state['departure_date']}\n"
    if state.get("origin"):
        current_state_info += f"Current origin: {state['origin']}\n"
    if state.get("destination"):
        current_state_info += f"Current destination: {state['destination']}\n"
    if state.get("cabin_class"):
        current_state_info += f"Current cabin class: {state['cabin_class']}\n"
    if state.get("duration"):
        current_state_info += f"Current duration: {state['duration']} days\n"
    if state.get("request_type"):
        current_state_info += f"Current request type: {state['request_type']}\n"
    if state.get("trip_type"):
        current_state_info += f"Current trip type: {state['trip_type']}\n"

    return f"""
You are an expert travel assistant helping users book flights, hotels, or complete travel packages. Today's date is {current_date_str}.

CONVERSATION SO FAR:
{conversation_text}

USER'S LATEST MESSAGE: "{user_text}"

CURRENT CONTEXT:
- Previous travel search status: {"completed" if travel_completed else "in progress"}
- Current travel information:
{current_state_info if current_state_info else "No current travel information"}

YOUR TASKS:
1. Determine if this is a NEW travel search request or continuation of existing search
2. Extract/update travel information intelligently
3. Detect what the user wants: flights only, hotels only, or full package
4. Detect if they want one-way or round trip (for flights/packages)
5. Handle seamless transitions between different requests

CRITICAL DETECTION RULES:
- If user mentions NEW destinations that differ from current destination → treat as NEW search
- If user says "I want to go to [different place]" → NEW search
- If previous search was completed AND user mentions travel → NEW search
- If user provides additional details for SAME destination → update existing info
- If user asks about visas or non-travel topics → extract any travel info mentioned but focus on their query

NEW SEARCH DETECTION (ENHANCED):
- Previous search completed AND user mentions any travel = NEW search
- Different destination from current state = NEW search  
- User says "now I want to..." or "I also want to..." = NEW search
- User provides origin+destination combo that differs from current = NEW search

REQUEST TYPE DETECTION (NEW):
- If user says "just hotels", "only hotels", "hotel only" → request_type = "hotels"
- If user says "just flights", "only flights", "flight only" → request_type = "flights"
- If user wants complete travel with both flights and hotels → request_type = "packages"
- If user doesn't specify → default to "packages"

TRIP TYPE DETECTION (NEW - FOR FLIGHTS/PACKAGES ONLY):
- If user says "one way", "one-way", "no return", "single trip" → trip_type = "one_way"
- If user says "round trip", "return flight", "there and back" → trip_type = "round_trip"
- If user doesn't specify → default to "round_trip"
- NOTE: trip_type only applies to flights and packages, NOT hotels-only requests

DATE PARSING RULES (CRITICAL):
- If user says "august 20th" or "Aug 20" → convert to "2025-08-20" 
- If year omitted: use {current_year}, UNLESS month is before {current_month}, then use {current_year + 1}
- If month and year omitted: use current month/year, UNLESS day is before {current_day}, then next month
- If next month would be January, increment year too
- Always output dates as YYYY-MM-DD
- "tomorrow" = "{tomorrow_str}"

LOCATION PARSING:
- Convert casual names: "NYC" → "New York", "LA" → "Los Angeles"
- Accept abbreviations and full names

CABIN CLASS PARSING (FOR FLIGHTS/PACKAGES ONLY):
- "eco" → "economy", "biz" → "business", "first" → "first class"
- If not specified → return null (do not assume)
- NOTE: cabin_class only applies when request_type is "flights" or "packages"

DURATION PARSING:
- Numbers like "5", "5 days", "one week" → convert to number of days
- For hotels: duration = number of nights staying
- For round trip flights/packages: duration = number of days until return
- For one-way flights: duration = null (not needed)
- Default to 7 if not specified and request needs it

REQUIRED INFORMATION LOGIC (CRITICAL):

For request_type = "hotels":
- Required: departure_date (checkin date), origin, destination, duration (nights)
- NOT required: cabin_class, trip_type

For request_type = "flights" with trip_type = "one_way":
- Required: departure_date, origin, destination, cabin_class
- NOT required: duration, trip_type stays as "one_way"

For request_type = "flights" with trip_type = "round_trip":
- Required: departure_date, origin, destination, cabin_class, duration
- trip_type = "round_trip"

For request_type = "packages" with trip_type = "one_way":
- Required: departure_date, origin, destination, cabin_class
- NOT required: duration, trip_type stays as "one_way"

For request_type = "packages" with trip_type = "round_trip":
- Required: departure_date, origin, destination, cabin_class, duration
- trip_type = "round_trip"

COMPLETION LOGIC (CRITICAL):
- ALL required fields (based on request_type and trip_type above) must be present to mark info_complete=true
- If user provides just a number (like "5") when we're asking for duration, treat as duration in days
- Set needs_followup=false and followup_question=null when complete

FOLLOWUP QUESTION RULES:
- For NEW searches: Ask for missing info efficiently 
- For continuing searches: Ask for ONE missing piece only
- Be smart about what to ask based on request_type and trip_type
- Examples:
  - For hotels: "How many nights will you be staying?"
  - For one-way: "Which cabin class do you prefer?"
  - For round trip: "How many days until you return?"
- Always ask natural, conversational questions

RESPONSE FORMAT (STRICT JSON ONLY, no prose, no backticks):
{{
    "departure_date": "YYYY-MM-DD or null",
    "origin": "City Name or null", 
    "destination": "City Name or null",
    "cabin_class": "economy/business/first class or null (null for hotels-only)",
    "duration": number_or_null,
    "request_type": "flights/hotels/packages",
    "trip_type": "round_trip/one_way (only relevant for flights/packages)",
    "followup_question": "Ask for missing info OR null if complete",
    "needs_followup": true_or_false,
    "info_complete": true_or_false,
    "is_new_search": true_or_false
}}

COMPLETION EXAMPLES:
- Hotels request with all info → {{"request_type": "hotels", "info_complete": true, "needs_followup": false, "followup_question": null}}
- One-way flight with all info (no duration) → {{"request_type": "flights", "trip_type": "one_way", "info_complete": true, "needs_followup": false}}
- Round trip package missing duration → {{"request_type": "packages", "trip_type": "round_trip", "info_complete": false, "needs_followup": true, "followup_question": "How many days will your trip last?"}}

BE SMART: When all required info (based on request_type and trip_type) is present, immediately mark as complete. Don't ask unnecessary confirmation questions.
"""