# Utils/state_reset.py - State management utilities

from Models.TravelSearchState import TravelSearchState

def reset_travel_state_for_new_search(state: TravelSearchState) -> TravelSearchState:
    """Reset travel-related state while preserving conversation history"""
    print("Resetting travel state for new search...")
    
    # Reset travel search state
    travel_reset_fields = [
        "departure_date", "return_date", "duration", "origin", "destination", 
        "cabin_class", "trip_type", "origin_location_code", "destination_location_code",
        "normalized_departure_date", "normalized_return_date", "normalized_cabin",
        "normalized_trip_type", "info_complete", "travel_search_completed",
        "followup_question", "request_type", "followup_count"
    ]
    
    for field in travel_reset_fields:
        if field in state:
            if field == "trip_type":
                state[field] = "round trip"
            elif field in ["info_complete", "travel_search_completed"]:
                state[field] = False
            elif field == "followup_count":
                state[field] = 0
            elif field == "request_type":
                state[field] = "flights"
            else:
                state[field] = None
    
    # Reset all flight offers
    for i in range(1, 8):
        if f"flight_offers_day_{i}" in state:
            state[f"flight_offers_day_{i}"] = None
    
    # Reset hotel offers
    for i in range(1, 8):
        for field_type in ["checkin_date", "checkout_date", "hotel_offers_duration"]:
            field_name = f"{field_type}_{i}" if field_type != "hotel_offers_duration" else f"hotel_offers_duration_{i}"
            if field_name in state:
                state[field_name] = None
    
    # Reset package data
    package_reset_fields = [
        "hotel_ids", "hotel_id", "city_code", "currency", "room_quantity", "adult",
        "hotel_offers", "travel_packages", "company_hotels_path", "company_hotels",
        "body", "access_token", "package_summary", "travel_packages_html",
        "selected_offer", "package_results", "formatted_results"
    ]
    
    for field in package_reset_fields:
        if field in state:
            state[field] = None if field not in ["travel_packages"] else []
    
    # Set flags for new search
    state["needs_followup"] = True
    state["info_complete"] = False
    state["travel_search_completed"] = False
    
    return state