from Models.TravelSearchState import TravelSearchState
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
    
    hotel_ids = state.get("hotel_id", [])
    checkin_dates = state.get("checkin_date", [])
    checkout_dates = state.get("checkout_date", [])
    
    if not hotel_ids:
        print("No hotel IDs available for hotel search")
        state["hotel_offers_duration_1"] = []
        state["hotel_offers_duration_2"] = []
        state["hotel_offers_duration_3"] = []
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
    
    # Parallel hotel search across 3 durations
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetch_hotels_for_duration, duration_info) for duration_info in duration_requests]
        
        for fut in as_completed(futures):
            duration_number, offers = fut.result()
            
            # Save hotel offers by duration
            if duration_number == 1:
                state["hotel_offers_duration_1"] = offers
            elif duration_number == 2:
                state["hotel_offers_duration_2"] = offers
            elif duration_number == 3:
                state["hotel_offers_duration_3"] = offers
    
    # Keep legacy format for compatibility (use first duration)
    state["hotel_offers"] = state.get("hotel_offers_duration_1", [])
    
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