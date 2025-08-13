from Models import TravelSearchState
import requests
from Nodes import get_access_token_node


def get_city_IDs_node(state: TravelSearchState) -> TravelSearchState:
    """Get city IDs using Amadeus API for hotel search based on flight results."""

    url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    params = {
        "cityCode": state.get("destination_location_code", "")
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=100)
        if response.status_code == 401:
            # Token expired, get a new one
            state = get_access_token_node(state)  # Refresh token
            headers["Authorization"] = f"Bearer {state['access_token']}"
            response = requests.get(url, headers=headers, params=params, timeout=100)
        response.raise_for_status()
        data = response.json()

        hotels_data = data.get("data", [])

        hotel_ids = []
        for hotel in hotels_data:
            hotel_id = hotel.get("hotelId")
            if hotel_id:
                hotel_ids.append(hotel_id)
        hotel_ids = hotel_ids[:20]  # limit to first 20
        state["hotel_id"] = hotel_ids
    except Exception as e:
        print(f"Error getting hotel IDs: {e}")
        state["followup_question"] = "Sorry, I had trouble finding hotels in your city. Please try again later."
        state["hotel_id"] = []

    return state
