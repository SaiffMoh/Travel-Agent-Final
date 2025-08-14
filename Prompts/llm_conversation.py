from datetime import datetime
from Models.TravelSearchState import TravelSearchState

def build_input_extraction_prompt(state: TravelSearchState):
    """Build the LLM prompt for extracting flight booking information."""
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    current_month = current_date.month
    current_day = current_date.day
    current_year = current_date.year

    conversation_text = "".join(f"{m['role']}: {m['content']}\n" for m in state.get("conversation", []))
    user_text = state.get("current_message", "")

    return f"""
        You are an expert travel assistant helping users book flights. Today's date is {current_date_str}.

        CONVERSATION SO FAR:
        {conversation_text}

        USER'S LATEST MESSAGE: "{user_text}"

        YOUR TASKS:
        1. Extract/update flight information from the entire conversation
        2. Intelligently parse dates and locations 
        3. Ask for ONE missing piece of information OR indicate completion

        DATE PARSING RULES (CRITICAL):
        - If user says "august 20th" or "Aug 20" → convert to "2025-08-20" 
        - If year omitted: use {current_year}, UNLESS month is before {current_month}, then use {current_year + 1}
        - If month and year omitted: use current month/year, UNLESS day is before {current_day}, then next month
        - If next month would be January, increment year too
        - Always output dates as YYYY-MM-DD

        LOCATION PARSING:
        - Convert casual names: "NYC" → "New York", "LA" → "Los Angeles"
        - Accept abbreviations and full names

        CABIN CLASS PARSING:
        - "eco" → "economy", "biz" → "business", "first" → "first class"

        REQUIRED INFORMATION:
        1. departure_date (YYYY-MM-DD format)
        2. origin (city name)
        3. destination (city name) 
        4. cabin_class (economy/business/first class)
        5. duration (number of days for round trip)

        CURRENT STATE:
        - departure_date: {state.get('departure_date', 'Not provided')}
        - origin: {state.get('origin', 'Not provided')}
        - destination: {state.get('destination', 'Not provided')}
        - cabin_class: {state.get('cabin_class', 'Not provided')}
        - duration: {state.get('duration', 'Not provided')}
        - trip_type: {state.get('trip_type', 'round trip')} (always round trip)

        RESPONSE FORMAT (JSON):
        {{
        "departure_date": "YYYY-MM-DD or null",
        "origin": "City Name or null", 
        "destination": "City Name or null",
        "cabin_class": "economy/business/first class or null",
        "duration": number_or_null,
        "followup_question": "Ask for ONE missing piece OR null if complete",
        "needs_followup": true_or_false,
        "info_complete": true_or_false
        }}

        EXAMPLES:
        - User: "I want to fly to Paris on august 20th" → {{"departure_date": "2025-08-20", "destination": "Paris", "followup_question": "Which city are you flying from?"}}
        - User: "from NYC, eco class" → {{"origin": "New York", "cabin_class": "economy", "followup_question": "Which city would you like to fly to?"}}
        - User: "5 days" → {{"duration": 5, "followup_question": "What date would you like to depart?"}}

        BE SMART: If user provides multiple pieces of info at once, extract all of them. Ask natural, conversational questions.
    """
