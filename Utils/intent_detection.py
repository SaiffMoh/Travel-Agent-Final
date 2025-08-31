from Models.TravelSearchState import TravelSearchState
from langchain_openai import ChatOpenAI
import os

def detect_user_intent(state: TravelSearchState) -> str:
    """Enhanced intent detection to handle multiple flows seamlessly"""
    if state.get("invoice_uploaded", False):
        print("Intent: Invoice upload detected")
        return "invoice_extraction"

    user_message = state.get("current_message") or state.get("user_message", "")
    
    if not user_message:
        print("Intent: No message provided, defaulting to general conversation")
        return "general_conversation"
    
    has_travel_context = (
        state.get("origin") or 
        state.get("destination") or 
        state.get("departure_date") or
        not state.get("travel_search_completed", True)
    )
    
    message_lower = user_message.lower().strip()
    
    if has_travel_context:
        has_numbers = any(char.isdigit() for char in message_lower)
        travel_completion_patterns = [
            "day", "week", "month",
            "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "january", "february", "march", "april", "may", "june", 
            "july", "august", "september", "october", "november", "december",
            "economy", "business", "first", "eco", "biz"
        ]
        
        if has_numbers or any(pattern in message_lower for pattern in travel_completion_patterns):
            print(f"Intent: Travel context detected with completion pattern in '{user_message}'")
            return "travel_search"
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
    
    intent_prompt = f"""
    Analyze this user message and determine their intent. Consider the conversation context.
    
    User message: "{user_message}"
    
    Previous travel search completed: {state.get("travel_search_completed", False)}
    Current destination: {state.get("destination", "None")}
    Has existing travel context: {has_travel_context}
    
    Classify the intent as ONE of these:
    1. "travel_search" - User wants to search for flights/hotels/travel packages OR providing travel details
    2. "visa_inquiry" - User is asking about visa requirements for a specific country
    3. "general_conversation" - Other questions, greetings, or general chat
    
    IMPORTANT CONTEXT RULE:
    - If has_travel_context=True and user provides ANY travel-related info (dates, numbers, cities, cabin class), classify as "travel_search"
    - Numbers, dates, or single words when travel context exists should be "travel_search"
    
    Travel search indicators include:
    - Mentioning cities, countries, or airports for travel
    - Dates for departure/return
    - Words like "flight", "hotel", "travel", "book", "search", "find"
    - "I want to go to...", "I need flights to...", "from [city] to [city]"
    - Providing missing travel details when prompted
    - Numbers when asked about duration
    
    Visa inquiry indicators include:
    - Words like "visa", "requirements", "documents", "embassy"
    - "Do I need a visa for...", "What documents do I need for..."
    
    Respond with just one word: travel_search, visa_inquiry, or general_conversation
    """
    
    try:
        response = llm.invoke(intent_prompt)
        intent = response.content.strip().lower()
        print(f"Detected intent: {intent} for message: '{user_message}'")
        
        if intent == "travel_search":
            return "travel_search"
        elif intent == "visa_inquiry":
            return "visa_inquiry" 
        else:
            return "general_conversation"
            
    except Exception as e:
        print(f"Error in intent detection: {e}")
        visa_keywords = ["visa", "requirements", "documents", "embassy", "entry", "permit"]
        travel_keywords = ["flight", "hotel", "travel", "book", "search", "find", "go to", "trip", "from", "to"]
        
        message_lower = user_message.lower()
        
        if has_travel_context and (
            any(keyword in message_lower for keyword in travel_keywords) or
            any(char.isdigit() for char in message_lower) or
            len(message_lower.split()) <= 3
        ):
            return "travel_search"
        elif any(keyword in message_lower for keyword in visa_keywords):
            return "visa_inquiry"
        elif any(keyword in message_lower for keyword in travel_keywords):
            return "travel_search"
        else:
            return "general_conversation"