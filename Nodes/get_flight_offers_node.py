from Models.TravelSearchState import TravelSearchState
import requests
import json
from datetime import datetime, timedelta

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
    print(f"\n=== FLIGHT SEARCH DEBUG ===")
    print(f"Base departure date: {start_date}")
    print(f"Trip duration: {state.get('duration', 1)} nights")
    print(f"Base body keys: {list(base_body.keys()) if base_body else 'Empty body!'}")

    if base_body:
        print(f"Currency: {base_body.get('currencyCode')}")
        print(f"Sources: {base_body.get('sources')}")
        print(f"Origin destinations: {len(base_body.get('originDestinations', []))}")
        for i, dest in enumerate(base_body.get('originDestinations', [])):
            print(f"  Destination {i+1}: {dest.get('originLocationCode')} → {dest.get('destinationLocationCode')}")
            print(f"    Original date: {dest.get('departureDateTimeRange', {}).get('date')}")
            print(f"    Original time: {dest.get('departureDateTimeRange', {}).get('time')}")

        print(f"Travelers: {base_body.get('travelers')}")
        print(f"Search criteria: {base_body.get('searchCriteria')}")
    else:
        print("ERROR: No base body found! This will cause all flights to fail.")

    # Prepare requests for 3 consecutive days
    bodies = []
    for day_offset in range(0, 3):
        query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        body = dict(base_body)  # Copy the formatted body
        print(f"Preparing search for day {day_offset + 1}: {query_date}")

        if body.get("originDestinations"):
            # Update departure date
            body["originDestinations"][0]["departureDateTimeRange"]["date"] = query_date
            print(f"  Set outbound departure: {query_date}")

            # Update return date if round trip
            if len(body["originDestinations"]) > 1 and state.get("duration"):
                dep_date_dt = datetime.strptime(query_date, "%Y-%m-%d")
                return_date = (dep_date_dt + timedelta(days=int(state.get("duration", 0)))).strftime("%Y-%m-%d")
                body["originDestinations"][1]["departureDateTimeRange"]["date"] = return_date
                print(f"  Set return departure: {return_date}")
        else:
            print(f"  WARNING: No originDestinations in body!")
            print(f"  Body structure: {body}")

        # Set max offers to 1 for cheapest option
        body.setdefault("searchCriteria", {}).setdefault("maxFlightOffers", 1)
        bodies.append((day_offset + 1, query_date, body))

    # Sequential search across 3 days
    for day_number, search_date, body in bodies:
        print(f"\n--- SEARCHING DAY {day_number} ({search_date}) ---")
        print(f"Request URL: {base_url}")
        print(f"Request body keys: {list(body.keys())}")
        print(f"Request body originDestinations: {body.get('originDestinations')}")

        try:
            print(f"Making API request for day {day_number}...")
            resp = requests.post(base_url, headers=headers, json=body, timeout=100)
            print(f"Response status: {resp.status_code}")

            if resp.status_code != 200:
                print(f"API Error Response: {resp.text}")
                resp.raise_for_status()

            data = resp.json()
            print(f"Response data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            flights = data.get("data", []) or []
            print(f"Found {len(flights)} flight offers for day {day_number}")

            # Check for API errors or warnings
            if "errors" in data:
                print(f"API Errors: {data['errors']}")
            if "warnings" in data:
                print(f"API Warnings: {data['warnings']}")

            # Add metadata to flights
            for f in flights:
                f["_search_date"] = search_date
                f["_day_number"] = day_number

            # Debug each flight offer
            if flights:
                for i, flight in enumerate(flights):
                    print(f"\n  Flight {i+1} for day {day_number}:")
                    debug_flight_offer(flight)
            else:
                print(f"  No flights found for day {day_number} - checking if this is an API issue")
                print(f"  Full response: {data}")

            # Save flight offers by day
            if day_number == 1:
                state["flight_offers_day_1"] = flights
            elif day_number == 2:
                state["flight_offers_day_2"] = flights
            elif day_number == 3:
                state["flight_offers_day_3"] = flights

            # Extract hotel dates from flight offers for this specific day
            if flights:
                flight = flights[0]  # Use first (cheapest) flight
                print(f"\n=== EXTRACTING HOTEL DATES FOR DAY {day_number} ===")
                print(f"Flight search date: {flight.get('_search_date')}")

                checkin_date, checkout_date = extract_hotel_dates_from_flight(
                    flight,
                    state.get("duration", 1),
                    day_number
                )

                if checkin_date and checkout_date:
                    state[f"checkin_date_day_{day_number}"] = checkin_date
                    state[f"checkout_date_day_{day_number}"] = checkout_date
                    print(f"✓ Day {day_number} hotel dates: CHECK-IN {checkin_date} → CHECK-OUT {checkout_date}")
                else:
                    print(f"✗ Day {day_number}: Failed to extract hotel dates")
            else:
                print(f"✗ Day {day_number}: No flights found")
                print(f"  Results for day {day_number}: {flights}")

        except requests.exceptions.RequestException as exc:
            print(f"Network error getting flight offers for day {day_number} ({search_date}): {exc}")
        except Exception as exc:
            print(f"Unexpected error getting flight offers for day {day_number} ({search_date}): {exc}")
            import traceback
            traceback.print_exc()

    # Additional debugging for empty results
    for day in [1, 2, 3]:
        day_flights = state.get(f"flight_offers_day_{day}", [])
        checkin_key = f"checkin_date_day_{day}"
        checkout_key = f"checkout_date_day_{day}"
        if day_flights and checkin_key not in state:
            print(f"Day {day} has flights but dates not extracted!")
            print(f"Sample flight structure: {list(day_flights[0].keys()) if day_flights else 'No flights'}")

    # Final debug summary
    print(f"\n=== FINAL HOTEL DATES SUMMARY ===")
    for day in [1, 2, 3]:
        checkin_key = f"checkin_date_day_{day}"
        checkout_key = f"checkout_date_day_{day}"
        if checkin_key in state and checkout_key in state:
            print(f"Package {day}: {state[checkin_key]} → {state[checkout_key]}")
        else:
            print(f"Package {day}: No hotel dates extracted!")

    # Keep legacy format for compatibility (all flights combined)
    all_results = []
    for day_key in ["flight_offers_day_1", "flight_offers_day_2", "flight_offers_day_3"]:
        if state.get(day_key):
            all_results.extend(state[day_key])
    state["result"] = {"data": all_results}

    print(f"\nTotal flights found across all days: {len(all_results)}")

    return state

def debug_flight_offer(flight_offer):
    """Debug print flight offer details"""
    try:
        print(f"    Flight ID: {flight_offer.get('id', 'N/A')}")
        print(f"    Search date: {flight_offer.get('_search_date', 'N/A')}")
        print(f"    Day number: {flight_offer.get('_day_number', 'N/A')}")

        itineraries = flight_offer.get("itineraries", [])
        print(f"    Itineraries: {len(itineraries)}")

        for i, itinerary in enumerate(itineraries):
            direction = "OUTBOUND" if i == 0 else "RETURN"
            segments = itinerary.get("segments", [])
            print(f"    {direction}: {len(segments)} segments")

            for j, segment in enumerate(segments):
                departure = segment.get("departure", {})
                arrival = segment.get("arrival", {})
                print(f"      Segment {j+1}: {departure.get('iataCode')} → {arrival.get('iataCode')}")
                print(f"        Depart: {departure.get('at', 'N/A')}")
                print(f"        Arrive: {arrival.get('at', 'N/A')}")

    except Exception as e:
        print(f"    Error debugging flight: {e}")

def extract_hotel_dates_from_flight(flight_offer, duration, day_number):
    """Extract hotel check-in (outbound final arrival) and check-out (return departure) dates.

    Args:
        flight_offer: Flight offer data
        duration: Trip duration in nights
        day_number: Which day this flight corresponds to (1, 2, or 3)

    Returns:
        tuple: (checkin_date, checkout_date) as strings in YYYY-MM-DD format
    """
    try:
        print(f"  Processing flight for day {day_number}")
        print(f"  Flight search date: {flight_offer.get('_search_date')}")

        itineraries = flight_offer.get("itineraries", [])
        if not itineraries:
            print(f"  ✗ No itineraries found")
            return None, None
        # --- Outbound Final Arrival (Check-in date) ---
        outbound_segments = itineraries[0].get("segments", [])
        if not outbound_segments:
            print(f"  ✗ No outbound segments found")
            return None, None

        print(f"  Outbound journey has {len(outbound_segments)} segments:")

        # Debug all segments
        for i, segment in enumerate(outbound_segments):
            dep = segment.get("departure", {})
            arr = segment.get("arrival", {})
            print(f"    Segment {i+1}: {dep.get('iataCode')} → {arr.get('iataCode')}")
            print(f"      Depart: {dep.get('at')}")
            print(f"      Arrive: {arr.get('at')}")

        # Use the LAST segment for final destination arrival (this is where user lands)
        final_outbound_segment = outbound_segments[-1]
        outbound_arrival_iso = final_outbound_segment.get("arrival", {}).get("at")
        if not outbound_arrival_iso:
            print(f"  ✗ No arrival time found in final segment")
            return None, None

        print(f"  → Final destination arrival: {outbound_arrival_iso}")

        # Parse arrival datetime and extract date for hotel check-in
        checkin_datetime = datetime.fromisoformat(outbound_arrival_iso.replace("Z", "+00:00"))
        checkin_date = checkin_datetime.date().strftime("%Y-%m-%d")
        print(f"  → Check-in date (arrival date): {checkin_date}")
        # --- Check-out date calculation ---
        checkout_date = None

        # For round trip: use return flight departure date
        if len(itineraries) > 1:
            print(f"  Round trip detected - extracting return departure")
            return_segments = itineraries[1].get("segments", [])
            if return_segments:
                print(f"  Return journey has {len(return_segments)} segments:")

                # Debug return segments
                for i, segment in enumerate(return_segments):
                    dep = segment.get("departure", {})
                    arr = segment.get("arrival", {})
                    print(f"    Return Segment {i+1}: {dep.get('iataCode')} → {arr.get('iataCode')}")
                    print(f"      Depart: {dep.get('at')}")
                    print(f"      Arrive: {arr.get('at')}")

                # Use FIRST segment of return trip (departure FROM destination)
                first_return_segment = return_segments[0]
                return_departure_iso = first_return_segment.get("departure", {}).get("at")
                if return_departure_iso:
                    checkout_datetime = datetime.fromisoformat(return_departure_iso.replace("Z", "+00:00"))
                    checkout_date = checkout_datetime.date().strftime("%Y-%m-%d")
                    print(f"  → Return departure: {return_departure_iso}")
                    print(f"  → Check-out date (departure date): {checkout_date}")
        else:
            print(f"  One-way trip detected")
        # Fallback: if no return flight or couldn't parse, use duration from check-in
        if not checkout_date:
            checkout_date = (checkin_datetime.date() + timedelta(days=int(duration))).strftime("%Y-%m-%d")
            print(f"  → Using fallback check-out date (check-in + {duration} nights): {checkout_date}")
        # Validation
        if checkin_date == checkout_date:
            print(f"  ⚠️ WARNING: Check-in and check-out dates are the same!")

        print(f"  ✓ Final hotel dates: {checkin_date} → {checkout_date}")
        return checkin_date, checkout_date
    except Exception as e:
        print(f"  ✗ Error extracting hotel dates: {e}")
        import traceback
        traceback.print_exc()
        return None, None
