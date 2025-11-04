from Models.TravelSearchState import TravelSearchState
import requests
import json
from datetime import datetime, timedelta
import copy

def get_flight_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get flight offers from Amadeus API for 3 consecutive days and extract hotel dates.
    
    SKIPS flight search if request_type is 'hotels' (hotels-only request).
    """
    
    # NEW: Check if this is a hotels-only request
    request_type = state.get("request_type", "packages")
    if request_type == "hotels":
        print("\n=== HOTELS-ONLY REQUEST ===")
        print("Skipping flight search, setting up hotel dates only")
        
        # Set empty flight results for all days
        for i in range(1, 4):
            state[f"flight_offers_day_{i}"] = []
        
        # For hotels-only, use departure date as checkin for 3 consecutive days
        start_date_str = state.get("normalized_departure_date")
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        duration = state.get("duration", 1)
        
        print(f"Base checkin date: {start_date}")
        print(f"Duration: {duration} nights")
        
        for day_offset in range(0, 3):
            checkin_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            checkout_date = (start_date + timedelta(days=day_offset + duration)).strftime("%Y-%m-%d")
            
            day_number = day_offset + 1
            state[f"checkin_date_day_{day_number}"] = checkin_date
            state[f"checkout_date_day_{day_number}"] = checkout_date
            
            print(f"Day {day_number}: CHECK-IN {checkin_date} → CHECK-OUT {checkout_date}")
        
        state["result"] = {"data": []}
        return state
    
    # EXISTING CODE: Flight search for flights/packages requests
    base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }

    base_body = state.get("body", {})
    start_date_str = state.get("normalized_departure_date")
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    trip_type = state.get("trip_type", "round_trip")
    
    print(f"\n=== FLIGHT SEARCH DEBUG (3 DAYS) ===")
    print(f"Base departure date: {start_date}")
    print(f"Trip type: {trip_type}")
    if trip_type == "round_trip":
        print(f"Trip duration: {state.get('duration', 1)} nights")
    else:
        print("One-way trip (no return)")

    # Prepare requests for 3 consecutive days
    bodies = []
    for day_offset in range(0, 3):
        query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        body = copy.deepcopy(base_body)
        print(f"Preparing search for day {day_offset + 1}: {query_date}")

        if body.get("originDestinations"):
            body["originDestinations"][0]["departureDateTimeRange"]["date"] = query_date

            # Update return date only if round trip
            if len(body["originDestinations"]) > 1 and trip_type == "round_trip" and state.get("duration"):
                dep_date_dt = datetime.strptime(query_date, "%Y-%m-%d")
                return_date = (dep_date_dt + timedelta(days=int(state.get("duration", 0)))).strftime("%Y-%m-%d")
                body["originDestinations"][1]["departureDateTimeRange"]["date"] = return_date

        if "searchCriteria" not in body:
            body["searchCriteria"] = {}
        body["searchCriteria"]["maxFlightOffers"] = 1
        bodies.append((day_offset + 1, query_date, body))

    # Sequential search across 3 days
    for day_number, search_date, body in bodies:
        print(f"\n--- SEARCHING DAY {day_number} ({search_date}) ---")

        try:
            resp = requests.post(base_url, headers=headers, json=body, timeout=100)
            
            if resp.status_code != 200:
                print(f"API Error Response: {resp.text}")
                resp.raise_for_status()

            data = resp.json()
            flights = data.get("data", []) or []
            print(f"Found {len(flights)} flight offers for day {day_number}")

            for f in flights:
                f["_search_date"] = search_date
                f["_day_number"] = day_number

            state[f"flight_offers_day_{day_number}"] = flights

            if flights:
                flight = flights[0]
                
                # NEW: For one-way flights, use a default hotel duration
                hotel_duration = state.get("duration")
                if trip_type == "one_way" and hotel_duration is None:
                    hotel_duration = 3  # Default to 3 nights for one-way flights
                    print(f"One-way flight detected - using default hotel duration of {hotel_duration} nights")
                
                checkin_date, checkout_date = extract_hotel_dates_from_flight(
                    flight,
                    hotel_duration,
                    day_number,
                    trip_type
                )

                if checkin_date and checkout_date:
                    state[f"checkin_date_day_{day_number}"] = checkin_date
                    state[f"checkout_date_day_{day_number}"] = checkout_date
                    print(f"✓ Day {day_number} hotel dates: CHECK-IN {checkin_date} → CHECK-OUT {checkout_date}")
                else:
                    print(f"✗ Failed to extract hotel dates for day {day_number}")

        except requests.exceptions.RequestException as exc:
            print(f"Network error getting flight offers for day {day_number}: {exc}")
        except Exception as exc:
            print(f"Unexpected error getting flight offers for day {day_number}: {exc}")

    # Keep legacy format for compatibility
    all_results = []
    for i in range(1, 4):
        day_key = f"flight_offers_day_{i}"
        if day_key in state:
            all_results.extend(state[day_key])
    state["result"] = {"data": all_results}

    print(f"\nTotal flights found across all days: {len(all_results)}")
    return state


def extract_hotel_dates_from_flight(flight_offer, duration, day_number, trip_type="round_trip"):
    """Extract hotel check-in and check-out dates from flight offer.
    
    Args:
        flight_offer: Flight offer data
        duration: Trip duration in days (can be None for one-way, will use 3 as default)
        day_number: Day number for this search
        trip_type: "round_trip" or "one_way"
    """
    try:
        # Handle None duration (shouldn't happen after fix above, but defensive)
        if duration is None:
            print(f"WARNING: Duration is None in extract_hotel_dates_from_flight, using default 3 nights")
            duration = 3
        
        itineraries = flight_offer.get("itineraries", [])
        if not itineraries:
            print(f"No itineraries found in flight offer")
            return None, None

        outbound_segments = itineraries[0].get("segments", [])
        if not outbound_segments:
            print(f"No outbound segments found")
            return None, None

        final_outbound_segment = outbound_segments[-1]
        outbound_arrival_iso = final_outbound_segment.get("arrival", {}).get("at")
        if not outbound_arrival_iso:
            print(f"No arrival time found in outbound segment")
            return None, None

        checkin_datetime = datetime.fromisoformat(outbound_arrival_iso.replace("Z", "+00:00"))
        checkin_date = checkin_datetime.date().strftime("%Y-%m-%d")

        checkout_date = None
        
        # For round trip, use return flight departure as checkout
        if trip_type == "round_trip" and len(itineraries) > 1:
            return_segments = itineraries[1].get("segments", [])
            if return_segments:
                first_return_segment = return_segments[0]
                return_departure_iso = first_return_segment.get("departure", {}).get("at")
                if return_departure_iso:
                    checkout_datetime = datetime.fromisoformat(return_departure_iso.replace("Z", "+00:00"))
                    checkout_date = checkout_datetime.date().strftime("%Y-%m-%d")
                    print(f"Round trip: Using return flight departure as checkout")

        # Fallback: use duration to calculate checkout (works for both one-way and round trip)
        if not checkout_date:
            # Convert duration to int, with safety check
            try:
                duration_days = int(duration)
            except (TypeError, ValueError):
                print(f"Invalid duration value: {duration}, using 3 days")
                duration_days = 3
            
            checkout_date = (checkin_datetime.date() + timedelta(days=duration_days)).strftime("%Y-%m-%d")
            print(f"Using duration-based checkout: {duration_days} days from arrival")

        return checkin_date, checkout_date
        
    except Exception as e:
        print(f"Error extracting hotel dates: {e}")
        import traceback
        traceback.print_exc()
        return None, None