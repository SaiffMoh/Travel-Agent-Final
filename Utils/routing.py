from Models.TravelSearchState import TravelSearchState
from Utils.state_reset import reset_travel_state_for_new_search
from Utils.intent_detection import detect_user_intent
from Nodes.visa_rag_node import enhanced_get_country
from Utils.watson_config import llm
import os
import re

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


def detect_booking_intent(state: TravelSearchState) -> tuple[bool, int | None]:
    """
    Detect if user wants to book a package or is responding to booking flow.
    Returns: (is_booking, package_id)
    """
    user_message = state.get("current_message") or state.get("user_message", "")
    message_lower = user_message.lower()
    
    # Check if already in booking flow
    booking_in_progress = state.get("booking_in_progress", False)
    
    # Booking keywords
    booking_keywords = ["book", "booking", "reserve", "confirm", "i want package", "select package"]
    
    # Check for explicit booking request
    has_booking_keyword = any(keyword in message_lower for keyword in booking_keywords)
    
    # Extract package number
    package_id = None
    
    # Pattern 1: "book package 2", "package 2", "I want package 1"
    match = re.search(r'package\s*(\d+)', message_lower)
    if match:
        package_id = int(match.group(1))
    
    # Pattern 2: Just a number if in booking context
    elif booking_in_progress:
        match = re.search(r'\b(\d+)\b', message_lower)
        if match:
            potential_id = int(match.group(1))
            # Only accept if it's a reasonable package ID (1-10)
            if 1 <= potential_id <= 10:
                package_id = potential_id
    
    # Determine if this is a booking intent
    is_booking = has_booking_keyword or (booking_in_progress and package_id is not None)
    
    return is_booking, package_id


def detect_document_upload_completion(state: TravelSearchState) -> bool:
    """
    Check if user JUST completed uploading documents while in booking flow.
    This is only True immediately after the upload, not on subsequent messages.
    
    CRITICAL: This should ONLY return True when the current message indicates
    a file upload just happened (not a text message like "package 3").
    """
    booking_in_progress = state.get("booking_in_progress", False)
    
    if not booking_in_progress:
        return False
    
    # Check current message - if it's a normal text message, this is NOT an upload
    current_message = state.get("current_message") or state.get("user_message", "")
    message_lower = current_message.lower()
    
    # If message contains booking/package keywords, it's a selection, not an upload
    if any(keyword in message_lower for keyword in ["package", "book", "select", "choose"]):
        return False
    
    # If message contains a number, it's likely a package selection
    if re.search(r'\b\d+\b', message_lower):
        return False
    
    # Check if documents were recently uploaded AND the message indicates an upload
    passport_uploaded = state.get("passport_uploaded", False)
    visa_uploaded = state.get("visa_uploaded", False)
    
    # Only return True if BOTH are uploaded AND message suggests file upload context
    # (e.g., "Uploaded X passport file(s)" or "Processing uploaded invoice")
    is_upload_context = "uploaded" in message_lower or "processing" in message_lower
    
    return passport_uploaded and visa_uploaded and is_upload_context


def smart_router(state: TravelSearchState) -> str:
    """
    Enhanced smart routing with booking flow support.
    Priority order:
    1. Booking requests (explicit package selection has HIGHEST priority)
    2. Document upload completion (if in booking flow) - route back to booking
    3. Visa inquiries (can interrupt any flow)
    4. Invoice extraction
    5. Travel search
    6. General conversation
    
    NOTE: This router only returns routing decisions.
    State modifications (like setting selected_package_id) must happen in main.py
    before graph invocation, as routers cannot modify state in LangGraph.
    """
    
    # FIRST: Check for booking intent (HIGHEST PRIORITY for package selection)
    is_booking, package_id = detect_booking_intent(state)
    if is_booking:
        print(f"Router: Booking intent detected - Package ID: {package_id}")
        # Note: selected_package_id should be set in main.py before graph invocation
        # Router functions cannot modify state in LangGraph
        return "booking"
    
    # SECOND: Check if we just completed document uploads during booking
    # (This now only triggers on actual uploads, not text messages)
    if detect_document_upload_completion(state):
        print("Router: Document upload completed during booking - returning to booking verification")
        return "booking"
    
    # THIRD: Check for visa inquiry (can interrupt any flow)
    is_visa_inquiry, detected_country = detect_visa_inquiry(state)
    if is_visa_inquiry:
        if detected_country:
            print(f"Router: Visa inquiry detected for country - {detected_country}")
            state["detected_visa_country"] = detected_country
        else:
            print("Router: Visa inquiry detected without clear country - routing to visa_rag for country selection")
        return "visa_rag"
    
    # FOURTH: Check primary intent
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