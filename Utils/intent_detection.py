# Utils/intent_detection.py - Intent detection utilities

from Models.TravelSearchState import TravelSearchState
from langchain_openai import ChatOpenAI
import os

def detect_user_intent(state: TravelSearchState) -> str:
    """Enhanced intent detection to handle multiple flows seamlessly"""
    user_message = state.get("current_message") or state.get("user_message", "")
    
    if not user_message:
        return "general_conversation"
    
    # CRITICAL FIX: If we're in an active travel context, assume travel intent
    # This handles cases like "5 days", "tomorrow", "business class" etc.
    has_travel_context = (
        state.get("origin") or 
        state.get("destination") or 
        state.get("departure_date") or
        not state.get("travel_search_completed", True)  # Search not completed yet
    )
    
    message_lower = user_message.lower().strip()
    
    # If we have travel context and user provides travel-related info, it's travel_search
    if has_travel_context:
        # Check if message contains numbers (duration/dates)
        has_numbers = any(char.isdigit() for char in message_lower)
        
        # Check for travel completion patterns
        travel_completion_patterns = [
            # Duration patterns
            "day", "week", "month",
            # Date patterns  
            "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "january", "february", "march", "april", "may", "june", 
            "july", "august", "september", "october", "november", "december",
            # Cabin class patterns
            "economy", "business", "first", "eco", "biz"
        ]
        
        # Check if any pattern matches OR if message contains numbers
        if has_numbers or any(pattern in message_lower for pattern in travel_completion_patterns):
            print(f"Intent: Travel context detected with completion pattern in '{user_message}'")
            return "travel_search"
    
    # Fallback to LLM for complex cases
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
        
        # Map to our routing options
        if intent == "travel_search":
            return "travel_search"
        elif intent == "visa_inquiry":
            return "visa_inquiry" 
        else:
            return "general_conversation"
            
    except Exception as e:
        print(f"Error in intent detection: {e}")
        # Enhanced fallback logic that considers travel context
        visa_keywords = ["visa", "requirements", "documents", "embassy", "entry", "permit"]
        travel_keywords = ["flight", "hotel", "travel", "book", "search", "find", "go to", "trip", "from", "to"]
        
        message_lower = user_message.lower()
        
        # If in travel context, lean toward travel_search
        if has_travel_context and (
            any(keyword in message_lower for keyword in travel_keywords) or
            any(char.isdigit() for char in message_lower) or
            len(message_lower.split()) <= 3  # Short responses likely completing travel info
        ):
            return "travel_search"
        elif any(keyword in message_lower for keyword in visa_keywords):
            return "visa_inquiry"
        elif any(keyword in message_lower for keyword in travel_keywords):
            return "travel_search"
        else:
            return "general_conversation"