from Models import TravelSearchState
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

def get_hotel_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get hotel offers for multiple date ranges in parallel using Amadeus API."""
    
    url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    
    hotel_ids = state.get("hotel_id", [])
    checkin_dates = state.get("checkin_date", [])
    checkout_dates = state.get("checkout_date", [])
    
    if not hotel_ids or not checkin_dates or not checkout_dates:
        print("Missing hotel IDs or dates for hotel search")
        state["hotel_offers_by_dates"] = {}
        return state
    
    # Create unique date range combinations
    unique_date_ranges = []
    date_range_set = set()
    
    for checkin, checkout in zip(checkin_dates, checkout_dates):
        date_key = f"{checkin}_{checkout}"
        if date_key not in date_range_set:
            date_range_set.add(date_key)
            unique_date_ranges.append({
                "checkin": checkin,
                "checkout": checkout,
                "key": date_key
            })
    
    def fetch_hotels_for_dates(date_range):
        """Fetch hotel offers for a specific date range."""
        params = {
            "hotelIds": ",".join(hotel_ids),
            "checkInDate": date_range["checkin"],
            "checkOutDate": date_range["checkout"],
            "currencyCode": "EGP"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=100)
            response.raise_for_status()
            data = response.json()
            hotel_offers = data.get("data", [])
            
            # Find cheapest offer by room type for each hotel
            processed_offers = process_hotel_offers(hotel_offers)
            
            return date_range["key"], processed_offers
            
        except Exception as e:
            print(f"Error getting hotel offers for {date_range['checkin']} to {date_range['checkout']}: {e}")
            return date_range["key"], []
    
    # Parallel hotel search across all unique date ranges
    hotel_offers_by_dates = {}
    
    with ThreadPoolExecutor(max_workers=len(unique_date_ranges)) as executor:
        futures = [executor.submit(fetch_hotels_for_dates, date_range) for date_range in unique_date_ranges]
        
        for fut in as_completed(futures):
            date_key, offers = fut.result()
            hotel_offers_by_dates[date_key] = offers
    
    state["hotel_offers_by_dates"] = hotel_offers_by_dates
    state["unique_date_ranges"] = unique_date_ranges
    
    # Keep legacy format for compatibility - use first date range result
    if hotel_offers_by_dates:
        first_key = list(hotel_offers_by_dates.keys())[0]
        state["hotel_offers"] = hotel_offers_by_dates[first_key]
    else:
        state["hotel_offers"] = []
    
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