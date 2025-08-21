from Models.TravelSearchState import TravelSearchState
import requests
from datetime import datetime
from Nodes.get_access_token_node import get_access_token_node


def get_city_IDs_node(state: TravelSearchState) -> TravelSearchState:
    """Get city IDs using Amadeus API for hotel search based on flight results."""

    url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    
    city_code = state.get("destination_location_code", "")
    if not city_code:
        print("Error: No destination city code found in state")
        state["hotel_id"] = []
        return state
        
    params = {
        "cityCode": city_code
    }
    
    print(f"DEBUG: Getting hotel IDs for city code: {city_code}")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=100)
        
        print(f"DEBUG: Hotel search response status: {response.status_code}")
        
        if response.status_code == 401:
            # Token expired, get a new one
            print("DEBUG: Token expired, refreshing...")
            state = get_access_token_node(state)  # Refresh token
            headers["Authorization"] = f"Bearer {state['access_token']}"
            response = requests.get(url, headers=headers, params=params, timeout=100)
            print(f"DEBUG: Hotel search response status after token refresh: {response.status_code}")
            
        if response.status_code == 400:
            print(f"DEBUG: 400 error in hotel search: {response.text}")
            
        response.raise_for_status()
        data = response.json()

        hotels_data = data.get("data", [])
        print(f"DEBUG: Found {len(hotels_data)} hotels in response")

        hotel_ids = []
        for hotel in hotels_data:
            hotel_id = hotel.get("hotelId")
            if hotel_id:
                hotel_ids.append(hotel_id)
        hotel_ids = hotel_ids[:20]  # limit to first 20
        
        print(f"DEBUG: Extracted {len(hotel_ids)} hotel IDs")
        if hotel_ids:
            print(f"DEBUG: Sample hotel IDs: {hotel_ids[:3]}")
        
        # Ensure hotel IDs are properly stored in state with multiple keys for redundancy
        # Only update if we actually have hotel IDs to avoid overwriting with empty lists
        if hotel_ids:
            state["hotel_id"] = hotel_ids.copy()  # Use copy to avoid reference issues
            state["hotel_ids"] = hotel_ids.copy()  # Alternative key for redundancy
            state["destination_hotel_ids"] = hotel_ids.copy()  # Another backup key
            
            # Force state persistence by setting a flag
            state["hotel_ids_retrieved"] = True
            state["hotel_retrieval_timestamp"] = str(datetime.now())
            
            print(f"SUCCESS: {len(hotel_ids)} hotel IDs stored in state with multiple keys")
        else:
            print("WARNING: No hotel IDs found for the destination")
            # Don't overwrite existing hotel IDs with empty lists
            if not any([state.get("hotel_id"), state.get("hotel_ids"), state.get("destination_hotel_ids")]):
                state["hotel_id"] = []
                state["hotel_ids"] = []
                state["destination_hotel_ids"] = []
        
        # Verify the hotel IDs were stored correctly
        stored_ids = state.get("hotel_id", [])
        print(f"DEBUG: Verified stored hotel IDs count: {len(stored_ids)}")
        print(f"DEBUG: State after storing hotel IDs: hotel_id={len(state.get('hotel_id', []))}, hotel_ids={len(state.get('hotel_ids', []))}, destination_hotel_ids={len(state.get('destination_hotel_ids', []))}")
            
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error getting hotel IDs: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response body: {e.response.text}")
        state["followup_question"] = "Sorry, I had trouble finding hotels in your city. Please try again later."
        # Don't overwrite existing hotel IDs in case of error - preserve any previously retrieved IDs
        if not any([state.get("hotel_id"), state.get("hotel_ids"), state.get("destination_hotel_ids")]):
            state["hotel_id"] = []
            state["hotel_ids"] = []
            state["destination_hotel_ids"] = []
    except Exception as e:
        print(f"Error getting hotel IDs: {e}")
        state["followup_question"] = "Sorry, I had trouble finding hotels in your city. Please try again later."
        # Don't overwrite existing hotel IDs in case of error - preserve any previously retrieved IDs
        if not any([state.get("hotel_id"), state.get("hotel_ids"), state.get("destination_hotel_ids")]):
            state["hotel_id"] = []
            state["hotel_ids"] = []
            state["destination_hotel_ids"] = []

    # Final verification before returning state
    final_hotel_ids = state.get("hotel_id", [])
    print(f"DEBUG: Final check - returning state with {len(final_hotel_ids)} hotel IDs")
    
    return state
