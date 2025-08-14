from Models import TravelSearchState
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

def get_hotel_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get hotel offers for 3 durations in parallel using extracted flight dates."""
    
    url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    
    # Get hotel IDs with comprehensive debugging and redundancy - try all possible keys
    hotel_id_keys = ["hotel_id", "hotel_ids", "destination_hotel_ids"]
    hotel_ids = None
    
    print(f"DEBUG: Checking multiple hotel ID keys:")
    for key in hotel_id_keys:
        key_value = state.get(key, [])
        key_len = len(key_value) if key_value else 0
        print(f"  - {key}: {key_len}")
        if key_value and not hotel_ids:  # Use first non-empty list found
            hotel_ids = key_value
            print(f"DEBUG: Using hotel IDs from key: {key}")
    
    print(f"  - hotel_ids_retrieved flag: {state.get('hotel_ids_retrieved', False)}")
    
    checkin_dates = state.get("checkin_date", [])
    checkout_dates = state.get("checkout_date", [])
    
    print(f"DEBUG: Hotel search - hotel_ids: {len(hotel_ids) if hotel_ids else 0}")
    print(f"DEBUG: Hotel search - checkin_dates: {len(checkin_dates) if checkin_dates else 0}")
    print(f"DEBUG: Hotel search - checkout_dates: {len(checkout_dates) if checkout_dates else 0}")
    
    # Debug: Print first few hotel IDs if available
    if hotel_ids:
        print(f"DEBUG: First 3 hotel IDs: {hotel_ids[:3]}")
        print(f"DEBUG: Hotel IDs type: {type(hotel_ids)}")
    else:
        print("DEBUG: hotel_ids is empty or None")
        print(f"DEBUG: State keys containing 'hotel': {[k for k in state.keys() if 'hotel' in k.lower()]}")
        for key in hotel_id_keys:
            print(f"DEBUG: Raw {key} value: {repr(state.get(key))}")
    
    # Try to recover hotel IDs if they're missing
    if not hotel_ids:
        print("ERROR: No hotel IDs available for hotel search")
        print(f"DEBUG: Checking state for hotel_id key: {state.get('hotel_id', 'KEY_NOT_FOUND')}")
        
        # Check if we need to call get_city_IDs_node again
        destination_code = state.get("destination_location_code")
        if destination_code and state.get('access_token'):
            print(f"DEBUG: Attempting to recover hotel IDs for destination: {destination_code}")
            
            # Import and call get_city_IDs_node to recover hotel IDs
            from Nodes.get_city_IDs_node import get_city_IDs_node
            print("DEBUG: Calling get_city_IDs_node to recover hotel IDs")
            state = get_city_IDs_node(state)
            
            # Re-check hotel IDs after recovery attempt with redundancy
            hotel_ids = None
            for key in hotel_id_keys:
                key_value = state.get(key, [])
                if key_value and not hotel_ids:  # Use first non-empty list found
                    hotel_ids = key_value
                    print(f"DEBUG: After recovery, using hotel IDs from key: {key}")
                    break
            
            print(f"DEBUG: After recovery attempt - hotel_ids: {len(hotel_ids) if hotel_ids else 0}")
            print(f"DEBUG: Recovery result - hotel_id: {len(state.get('hotel_id', []))}, hotel_ids: {len(state.get('hotel_ids', []))}, destination_hotel_ids: {len(state.get('destination_hotel_ids', []))}")
            
            if hotel_ids:
                print(f"SUCCESS: Recovered {len(hotel_ids)} hotel IDs")
                # Continue with hotel search
            else:
                print("FAILED: Could not recover hotel IDs")
        
        # If still no hotel IDs, set up fallback
        if not hotel_ids:
            fallback_checkin = state.get("normalized_departure_date")
            fallback_checkout = None
            if fallback_checkin and state.get("duration"):
                from datetime import datetime, timedelta
                checkin_dt = datetime.strptime(fallback_checkin, "%Y-%m-%d")
                checkout_dt = checkin_dt + timedelta(days=int(state.get("duration", 1)))
                fallback_checkout = checkout_dt.strftime("%Y-%m-%d")
                
            state["hotel_offers_duration_1"] = []
            state["hotel_offers_duration_2"] = []
            state["hotel_offers_duration_3"] = []
            
            # Store fallback dates for potential use
            if fallback_checkin and fallback_checkout:
                state["checkin_date"] = [fallback_checkin]
                state["checkout_date"] = [fallback_checkout]
                print(f"DEBUG: Set fallback hotel dates: {fallback_checkin} to {fallback_checkout}")
            
            print("WARNING: Continuing without hotel search due to missing hotel IDs")
            return state
    
    if not checkin_dates or not checkout_dates or len(checkin_dates) != len(checkout_dates):
        print("Missing or mismatched hotel dates")
        state["hotel_offers_duration_1"] = []
        state["hotel_offers_duration_2"] = []
        state["hotel_offers_duration_3"] = []
        return state

    # Prepare requests for up to 3 durations
    duration_requests = []
    for i in range(min(3, len(checkin_dates))):
        duration_requests.append({
            "duration_number": i + 1,
            "checkin": checkin_dates[i],
            "checkout": checkout_dates[i]
        })
    
    # Fill remaining slots if we have less than 3
    while len(duration_requests) < 3:
        # Use the last available date range
        if duration_requests:
            last_request = duration_requests[-1]
            duration_requests.append({
                "duration_number": len(duration_requests) + 1,
                "checkin": last_request["checkin"], 
                "checkout": last_request["checkout"]
            })
        else:
            # No dates available, use empty
            duration_requests.append({
                "duration_number": len(duration_requests) + 1,
                "checkin": None,
                "checkout": None
            })

    def fetch_hotels_for_duration(duration_info):
        """Fetch hotel offers for a specific duration."""
        duration_num = duration_info["duration_number"]
        checkin = duration_info["checkin"]
        checkout = duration_info["checkout"]
        
        if not checkin or not checkout:
            return duration_num, []
            
        params = {
            "hotelIds": ",".join(hotel_ids),
            "checkInDate": checkin,
            "checkOutDate": checkout,
            "currencyCode": "EGP"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=100)
            response.raise_for_status()
            data = response.json()
            hotel_offers = data.get("data", [])
            
            # Process hotel offers to find cheapest by room type
            processed_offers = process_hotel_offers(hotel_offers)
            
            return duration_num, processed_offers
            
        except Exception as e:
            print(f"Error getting hotel offers for duration {duration_num} ({checkin} to {checkout}): {e}")
            return duration_num, []
    
    # Sequential hotel search to avoid rate limiting (instead of parallel)
    print("DEBUG: Using sequential hotel requests to avoid rate limiting")
    
    for duration_info in duration_requests:
        duration_number, offers = fetch_hotels_for_duration(duration_info)
        
        # Save hotel offers by duration
        if duration_number == 1:
            state["hotel_offers_duration_1"] = offers
        elif duration_number == 2:
            state["hotel_offers_duration_2"] = offers
        elif duration_number == 3:
            state["hotel_offers_duration_3"] = offers
        
        # Add delay between requests to avoid rate limiting
        import time
        if duration_info != duration_requests[-1]:  # Don't delay after last request
            print("DEBUG: Adding 2-second delay between hotel requests")
            time.sleep(2)  # 2 second delay between hotel requests
    
    # Keep legacy format for compatibility (use first duration)
    state["hotel_offers"] = state.get("hotel_offers_duration_1", [])
    
    # Debug final hotel offers
    total_offers_1 = len(state.get("hotel_offers_duration_1", []))
    total_offers_2 = len(state.get("hotel_offers_duration_2", []))
    total_offers_3 = len(state.get("hotel_offers_duration_3", []))
    print(f"DEBUG: Final hotel offers - Duration 1: {total_offers_1}, Duration 2: {total_offers_2}, Duration 3: {total_offers_3}")
    
    return state


def process_hotel_offers(hotel_offers):
    """Process hotel offers to find cheapest offer by room type for each hotel."""
    processed = []
    
    for hotel in hotel_offers:
        hotel_info = {
            "hotel": hotel.get("hotel", {}),
            "available": hotel.get("available", True),
            "best_offers": []
        }
        
        if not hotel_info["available"]:
            processed.append(hotel_info)
            continue
            
        offers = hotel.get("offers", [])
        if not offers:
            processed.append(hotel_info)
            continue
        
        # Group offers by room type
        offers_by_room_type = defaultdict(list)
        
        for offer in offers:
            room_info = offer.get("room", {})
            room_type = room_info.get("type", "UNKNOWN")
            offers_by_room_type[room_type].append(offer)
        
        # Find cheapest offer for each room type
        for room_type, room_offers in offers_by_room_type.items():
            cheapest_offer = min(room_offers, key=lambda x: float(x.get("price", {}).get("total", float('inf'))))
            hotel_info["best_offers"].append({
                "room_type": room_type,
                "offer": cheapest_offer
            })
        
        # Sort by price (cheapest first)
        hotel_info["best_offers"].sort(key=lambda x: float(x["offer"].get("price", {}).get("total", float('inf'))))
        
        processed.append(hotel_info)
    
    # Sort hotels by their cheapest offer
    processed.sort(key=lambda x: (
        float(x["best_offers"][0]["offer"].get("price", {}).get("total", float('inf'))) 
        if x["best_offers"] else float('inf')
    ))
    
    return processed