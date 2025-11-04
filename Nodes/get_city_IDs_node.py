from Models.TravelSearchState import TravelSearchState
import requests
from Nodes.get_access_token_node import get_access_token_node


def get_city_IDs_node(state: TravelSearchState) -> TravelSearchState:
    """Get city IDs using Amadeus API for hotel search.
    
    Works for both:
    - Flights + hotels (uses destination from flights)
    - Hotels-only (uses destination_location_code directly)
    """

    url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    
    # Get destination code - works for both hotels-only and flights+hotels
    destination_code = state.get("destination_location_code", "")
    request_type = state.get("request_type", "packages")
    
    if not destination_code:
        print("ERROR: No destination_location_code found for hotel search")
        state["hotel_id"] = []
        return state
    
    print(f"Fetching hotel IDs for destination: {destination_code} (request_type: {request_type})")
    
    params = {
        "cityCode": destination_code
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=100)
        if response.status_code == 401:
            # Token expired, get a new one
            print("Access token expired, refreshing...")
            state = get_access_token_node(state)  # Refresh token
            headers["Authorization"] = f"Bearer {state['access_token']}"
            response = requests.get(url, headers=headers, params=params, timeout=100)
        
        response.raise_for_status()
        data = response.json()

        hotels_data = data.get("data", [])
        print(f"Found {len(hotels_data)} hotels from Amadeus API for {destination_code}")

        hotel_ids = []
        for hotel in hotels_data:
            hotel_id = hotel.get("hotelId")
            if hotel_id:
                hotel_ids.append(hotel_id)
        
        hotel_ids = hotel_ids[:20]  # limit to first 20
        state["hotel_id"] = hotel_ids
        print(f"Selected {len(hotel_ids)} hotel IDs for search")
        
    except Exception as e:
        print(f"Error getting hotel IDs: {e}")
        state["followup_question"] = "Sorry, I had trouble finding hotels in your city. Please try again later."
        state["hotel_id"] = []

    return state