from Models.TravelSearchState import TravelSearchState
from Utils.state_reset import reset_travel_state_for_new_search
from Utils.intent_detection import detect_user_intent
from Nodes.visa_rag_node import enhanced_get_country
from Utils.watson_config import llm
import os

def should_proceed_to_search(state: TravelSearchState) -> str:
    """Check if we have enough info to proceed with travel search"""
    has_origin = state.get("origin") is not None
    has_destination = state.get("destination") is not None  
    has_departure_date = state.get("departure_date") is not None
    has_duration = state.get("duration") is not None
    has_cabin_class = state.get("cabin_class") is not None
    
    info_complete = state.get("info_complete", False)
    
    print(f"Info check - Origin: {has_origin}, Destination: {has_destination}, Date: {has_departure_date}, Duration: {has_duration}, Cabin: {has_cabin_class}, LLM says complete: {info_complete}")
    
    if has_origin and has_destination and has_departure_date and has_duration and has_cabin_class and info_complete:
        return "search_ready"
    else:
        return "need_more_info"

def detect_visa_inquiry(state: TravelSearchState) -> tuple[bool, str | None]:
    """
    Detect if the user is asking about visa requirements.
    Returns: (is_visa_inquiry, detected_country)
    """
    user_message = state.get("current_message") or state.get("user_message", "")
    destination = state.get("destination")
    
    # Check for visa-related keywords
    visa_keywords = ["visa", "entry requirements", "travel requirements", "do i need", 
                     "requirements for", "documents needed", "travel documents"]
    
    message_lower = user_message.lower()
    contains_visa_keyword = any(keyword in message_lower for keyword in visa_keywords)
    
    if contains_visa_keyword:
        country = enhanced_get_country(user_message, destination)
        return True, country
    
    return False, None

def smart_router(state: TravelSearchState) -> str:
    """
    Enhanced smart routing with visa RAG check for all flows.
    Priority order:
    1. Visa inquiries (highest priority - can be asked anytime)
    2. Invoice extraction
    3. Travel search
    4. General conversation
    """
    
    # FIRST: Check for visa inquiry (can interrupt any flow)
    is_visa_inquiry, detected_country = detect_visa_inquiry(state)
    if is_visa_inquiry:
        if detected_country:
            print(f"Router: Visa inquiry detected for country - {detected_country}")
            state["detected_visa_country"] = detected_country
        else:
            print("Router: Visa inquiry detected without clear country - routing to visa_rag for country selection")
        return "visa_rag"
    
    # SECOND: Check primary intent
    intent = detect_user_intent(state)
    print(f"Router: Detected primary intent - {intent}")
    
    if intent == "invoice_extraction":
        print("Router: Routing to invoice_extraction node")
        return "invoice_extraction"
    
    if intent == "travel_search":
        is_new_search = state.get("is_new_search", False)
        if is_new_search:
            print("New search detected in router - resetting travel state")
            reset_travel_state_for_new_search(state)
            return "need_more_info"
        
        search_status = should_proceed_to_search(state)
        if search_status == "search_ready":
            print("Router: All required info complete - proceeding to travel flow")
            state["needs_followup"] = False
            state["followup_question"] = None
            return "travel_flow"
        
        if state.get("needs_followup") and state.get("followup_question"):
            print(f"Router: Info incomplete, showing followup question - {state.get('followup_question')}")
            return "need_more_info"
        
        return "need_more_info"
    
    # Default to general conversation
    if state.get("needs_followup") and state.get("followup_question"):
        print(f"Router: General conversation with followup - {state.get('followup_question')}")
        return "need_more_info"
    
    print("Router: Defaulting to general conversation")
    return "general_conversation"