from Models.TravelSearchState import TravelSearchState
from Utils.state_reset import reset_travel_state_for_new_search
from Utils.intent_detection import detect_user_intent
from Nodes.visa_rag_node import get_country
from Utils.watson_config import llm  # Import Watson LLM instead of OpenAI
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

def smart_router(state: TravelSearchState) -> str:
    """Smart routing function that can handle multiple flows seamlessly"""
    intent = detect_user_intent(state)
    
    print(f"Router: Detected intent - {intent}")
    
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
        
    elif intent == "visa_inquiry":
        user_message = state.get("current_message") or state.get("user_message", "")
        destination = state.get("destination")
        
        # Fixed: Remove the llm parameter since get_country only takes 2 arguments
        country = get_country(user_message, destination)
        if country:
            print(f"Router: Visa inquiry for country - {country}")
            return "visa_rag"
        else:
            print("Router: Visa inquiry without clear country - defaulting to general conversation")
            return "general_conversation"
    else:
        if state.get("needs_followup") and state.get("followup_question"):
            print(f"Router: General conversation with followup - {state.get('followup_question')}")
            return "need_more_info"
        print("Router: Defaulting to general conversation")
        return "general_conversation"