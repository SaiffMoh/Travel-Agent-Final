# Utils/routing.py - Router and state management utilities

from Models.TravelSearchState import TravelSearchState
from Utils.state_reset import reset_travel_state_for_new_search
from Utils.intent_detection import detect_user_intent
from Nodes.visa_rag_node import get_country
from langchain_openai import ChatOpenAI
import os

def should_proceed_to_search(state: TravelSearchState) -> str:
    """Check if we have enough info to proceed with travel search"""
    # Check ALL required fields
    has_origin = state.get("origin") is not None
    has_destination = state.get("destination") is not None  
    has_departure_date = state.get("departure_date") is not None
    has_duration = state.get("duration") is not None
    has_cabin_class = state.get("cabin_class") is not None
    
    info_complete = state.get("info_complete", False)
    
    print(f"Info check - Origin: {has_origin}, Destination: {has_destination}, Date: {has_departure_date}, Duration: {has_duration}, Cabin: {has_cabin_class}, LLM says complete: {info_complete}")
    
    # All fields must be present AND LLM must confirm completeness
    if has_origin and has_destination and has_departure_date and has_duration and has_cabin_class and info_complete:
        return "search_ready"
    else:
        return "need_more_info"

def smart_router(state: TravelSearchState) -> str:
    """Smart routing function that can handle multiple flows seamlessly"""
    intent = detect_user_intent(state)
    
    if intent == "travel_search":
        # Check if this is a new search and reset if needed
        is_new_search = state.get("is_new_search", False)
        if is_new_search:
            print("New search detected in router - resetting travel state")
            reset_travel_state_for_new_search(state)
            # After reset, we definitely need more info
            return "need_more_info"
        
        # PRIORITY CHECK: If info is complete, proceed to travel flow
        search_status = should_proceed_to_search(state)
        if search_status == "search_ready":
            print("Router: All required info complete - proceeding to travel flow")
            # Clear any residual followup flags since we're proceeding
            state["needs_followup"] = False
            state["followup_question"] = None
            return "travel_flow"
        
        # Only check for followup questions if info is NOT complete
        if state.get("needs_followup") and state.get("followup_question"):
            print(f"Router: Info incomplete, showing followup question - {state.get('followup_question')}")
            return "need_more_info"
        
        return "need_more_info"
        
    elif intent == "visa_inquiry":
        # Check if we can determine a country for visa query
        user_message = state.get("current_message") or state.get("user_message", "")
        destination = state.get("destination")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=os.getenv("OPENAI_API_KEY"))
        
        country = get_country(llm, user_message, destination)
        if country:
            return "visa_rag"
        else:
            return "general_conversation"
    else:
        # For general conversation, only show followup if there's a question
        if state.get("needs_followup") and state.get("followup_question"):
            print(f"Router: General conversation with followup - {state.get('followup_question')}")
            return "need_more_info"
        return "general_conversation"