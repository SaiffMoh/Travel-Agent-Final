from Models import TravelSearchState
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_flight_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get flight offers from Amadeus API for a 3-day window in parallel and extract hotel dates."""

    base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    start_date_str = state.get("normalized_departure_date")
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()

    # Search 3-day window: departure date + 2 days
    bodies = []
    for day_offset in range(0, 3):
        query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        body = dict(state["body"]) if state.get("body") else {}

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
        bodies.append((query_date, body))

    def fetch_for_day(day_body_tuple):
        day, body = day_body_tuple
        try:
            resp = requests.post(base_url, headers=headers, json=body, timeout=100)
            resp.raise_for_status()
            data = resp.json()
            flights = data.get("data", []) or []
            
            # Add search date metadata
            for f in flights:
                f["_search_date"] = day
            
            return day, flights
        except Exception as exc:
            print(f"Error getting flight offers for {day}: {exc}")
            return day, []

    # Parallel search across 3 days
    flight_offers_by_date = {}
    checkin_dates = []
    checkout_dates = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetch_for_day, b) for b in bodies]
        for fut in as_completed(futures):
            search_date, flights = fut.result()
            flight_offers_by_date[search_date] = flights
            
            # Extract hotel dates from flight segments
            for flight in flights:
                checkin_date, checkout_date = extract_hotel_dates_from_flight(flight)
                if checkin_date and checkout_date:
                    checkin_dates.append(checkin_date)
                    checkout_dates.append(checkout_date)

    # Update state - store both formats
    state["flight_offers_by_date"] = flight_offers_by_date
    state["checkin_date"] = checkin_dates
    state["checkout_date"] = checkout_dates
    
    # Keep legacy format for compatibility AND set flight_offers for create_packages
    all_results = []
    for flights in flight_offers_by_date.values():
        all_results.extend(flights)
    state["result"] = {"data": all_results}
    state["flight_offers"] = all_results  # For create_packages node to use
    
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