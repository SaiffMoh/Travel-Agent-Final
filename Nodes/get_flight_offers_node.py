from Models import TravelSearchState
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_flight_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get flight offers from Amadeus API for 3 consecutive days and extract hotel dates."""

    base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    
    # Use the body from format_body_node
    base_body = state.get("body", {})
    start_date_str = state.get("normalized_departure_date")
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

    # Prepare requests for 3 consecutive days
    bodies = []
    for day_offset in range(0, 3):
        query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        body = dict(base_body)  # Copy the formatted body

        if body.get("originDestinations"):
            # Update departure date
            body["originDestinations"][0]["departureDateTimeRange"]["date"] = query_date

            # Update return date if round trip
            if len(body["originDestinations"]) > 1 and state.get("duration"):
                dep_date_dt = datetime.strptime(query_date, "%Y-%m-%d")
                return_date = (dep_date_dt + timedelta(days=int(state.get("duration", 0)))).strftime("%Y-%m-%d")
                body["originDestinations"][1]["departureDateTimeRange"]["date"] = return_date

        # Set max offers to 1 for cheapest option
        body.setdefault("searchCriteria", {}).setdefault("maxFlightOffers", 1)
        bodies.append((day_offset + 1, query_date, body))

    def fetch_for_day(day_info):
        day_number, search_date, body = day_info
        try:
            resp = requests.post(base_url, headers=headers, json=body, timeout=100)
            resp.raise_for_status()
            data = resp.json()
            flights = data.get("data", []) or []
            
            # Add metadata to flights
            for f in flights:
                f["_search_date"] = search_date
                f["_day_number"] = day_number
            
            return day_number, flights
        except Exception as exc:
            print(f"Error getting flight offers for day {day_number} ({search_date}): {exc}")
            return day_number, []

    # Parallel search across 3 days
    checkin_dates = []
    checkout_dates = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetch_for_day, body_info) for body_info in bodies]
        
        for fut in as_completed(futures):
            day_number, flights = fut.result()
            
            # Save flight offers by day
            if day_number == 1:
                state["flight_offers_day_1"] = flights
            elif day_number == 2:
                state["flight_offers_day_2"] = flights
            elif day_number == 3:
                state["flight_offers_day_3"] = flights
            
            # Extract hotel dates from flight offers
            for flight in flights:
                checkin_date, checkout_date = extract_hotel_dates_from_flight(flight)
                if checkin_date and checkout_date:
                    checkin_dates.append(checkin_date)
                    checkout_dates.append(checkout_date)

    # Save extracted hotel dates
    state["checkin_date"] = checkin_dates
    state["checkout_date"] = checkout_dates
    
    # Keep legacy format for compatibility (all flights combined)
    all_results = []
    for day_key in ["flight_offers_day_1", "flight_offers_day_2", "flight_offers_day_3"]:
        if state.get(day_key):
            all_results.extend(state[day_key])
    state["result"] = {"data": all_results}
    
    return state


def extract_hotel_dates_from_flight(flight_offer):
    """Extract check-in and check-out dates from flight segments."""
    try:
        itineraries = flight_offer.get("itineraries", [])
        if not itineraries:
            return None, None
        
        # Extract outbound arrival date (check-in)
        outbound = itineraries[0]  # First itinerary is outbound
        outbound_segments = outbound.get("segments", [])
        if not outbound_segments:
            return None, None
            
        # Get final destination arrival time
        final_outbound_segment = outbound_segments[-1]
        outbound_arrival = final_outbound_segment.get("arrival", {}).get("at")
        
        if not outbound_arrival:
            return None, None
            
        # Parse arrival datetime and get date
        checkin_datetime = datetime.fromisoformat(outbound_arrival.replace('Z', '+00:00'))
        checkin_date = checkin_datetime.strftime("%Y-%m-%d")
        
        # Extract return departure date (check-out) if round trip
        if len(itineraries) > 1:
            return_itinerary = itineraries[1]  # Second itinerary is return
            return_segments = return_itinerary.get("segments", [])
            if return_segments:
                # Get first segment departure time (origin departure)
                first_return_segment = return_segments[0]
                return_departure = first_return_segment.get("departure", {}).get("at")
                
                if return_departure:
                    checkout_datetime = datetime.fromisoformat(return_departure.replace('Z', '+00:00'))
                    checkout_date = checkout_datetime.strftime("%Y-%m-%d")
                    return checkin_date, checkout_date
        
        # For one-way trips, assume 1 night stay
        checkout_datetime = checkin_datetime + timedelta(days=1)
        checkout_date = checkout_datetime.strftime("%Y-%m-%d")
        
        return checkin_date, checkout_date
        
    except Exception as e:
        print(f"Error extracting hotel dates from flight: {e}")
        return None, None