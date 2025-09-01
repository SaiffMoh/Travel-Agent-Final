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

    return f"""
You are an expert travel assistant helping users book flights. Today's date is {current_date_str}.

CONVERSATION SO FAR:
{conversation_text}

USER'S LATEST MESSAGE: "{user_text}"

CURRENT CONTEXT:
- Previous travel search status: {"completed" if travel_completed else "in progress"}
- Current travel information:
{current_state_info if current_state_info else "No current travel information"}

YOUR TASKS:
1. Determine if this is a NEW travel search request or continuation of existing search
2. Extract/update flight information intelligently
3. Handle seamless transitions between different requests

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

CABIN CLASS PARSING:
- "eco" → "economy", "biz" → "business", "first" → "first class"
- If not specified → return null (do not assume)

DURATION PARSING:
- Numbers like "5", "5 days", "one week" → convert to number of days
- Default to 7 if not specified and all other info is complete

REQUIRED INFORMATION FOR COMPLETE SEARCH:
1. departure_date (YYYY-MM-DD format)
2. origin (city name)
3. destination (city name) 
4. cabin_class (economy/business/first class)
5. duration (number of days for round trip)

COMPLETION LOGIC (CRITICAL):
- ALL 5 fields must be present to mark info_complete=true
- If user provides just a number (like "5") when we're asking for duration, treat as duration in days
- If 4 out of 5 fields are present and user gives remaining info, complete immediately
- Set needs_followup=false and followup_question=null when complete

FOLLOWUP QUESTION RULES:
- For NEW searches: Ask for missing info efficiently 
- For continuing searches: Ask for ONE missing piece only
- If it's a new search but user provided some info: "I see you want to go from [origin] to [destination]. What's your departure date and how many days will you stay?"
- Always ask natural, conversational questions

RESPONSE FORMAT (STRICT JSON ONLY, no prose, no backticks):
{{
    "departure_date": "YYYY-MM-DD or null",
    "origin": "City Name or null", 
    "destination": "City Name or null",
    "cabin_class": "economy/business/first class or null",
    "duration": number_or_null,
    "followup_question": "Ask for missing info OR null if complete",
    "needs_followup": true_or_false,
    "info_complete": true_or_false,
    "is_new_search": true_or_false
}}

COMPLETION EXAMPLES:
- If ALL 5 fields present → {{"info_complete": true, "needs_followup": false, "followup_question": null}}
- If 4/5 fields present → {{"info_complete": false, "needs_followup": true, "followup_question": "What's missing?"}}
- User says "5" when asked for duration → {{"duration": 5, "info_complete": true, "needs_followup": false, "followup_question": null}} (if other fields complete)

BE SMART: When all required info is present, immediately mark as complete. Don't ask unnecessary confirmation questions.
"""