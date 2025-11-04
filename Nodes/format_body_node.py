from datetime import datetime, timedelta
from Models.TravelSearchState import TravelSearchState

def format_body_node(state: TravelSearchState) -> TravelSearchState:
    """Format the request body for Amadeus API based on trip_type (round_trip or one_way)"""

    def format_flight_offers_body(origin_location_code, destination_location_code, 
                                   departure_date, cabin="ECONOMY", duration=None, trip_type="round_trip"):
        """
        Format flight offers body for Amadeus API.
        
        Args:
            origin_location_code: Origin airport code
            destination_location_code: Destination airport code
            departure_date: Departure date (YYYY-MM-DD)
            cabin: Cabin class
            duration: Number of days for round trip (only used if trip_type is round_trip)
            trip_type: "round_trip" or "one_way"
        """
        # Build outbound leg (always present)
        origin_destinations = [{
            "id": "1",
            "originLocationCode": origin_location_code,
            "destinationLocationCode": destination_location_code,
            "departureDateTimeRange": {
                "date": departure_date,
                "time": "10:00:00"
            }
        }]
        
        # Add return leg ONLY if trip_type is round_trip
        if trip_type == "round_trip" and duration is not None:
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
            return_date = (dep_date + timedelta(days=int(duration))).strftime("%Y-%m-%d")
            origin_destinations.append({
                "id": "2",
                "originLocationCode": destination_location_code,
                "destinationLocationCode": origin_location_code,
                "departureDateTimeRange": {
                    "date": return_date,
                    "time": "10:00:00"
                }
            })
        
        # Build the complete request body
        return {
            "currencyCode": "EGP",
            "originDestinations": origin_destinations,
            "travelers": [{"id": "1", "travelerType": "ADULT"}],
            "sources": ["GDS"],
            "searchCriteria": {
                "maxFlightOffers": 1,
                "flightFilters": {
                    "cabinRestrictions": [{
                        "cabin": cabin,
                        "coverage": "MOST_SEGMENTS",
                        "originDestinationIds": [od["id"] for od in origin_destinations]
                    }]
                }
            }
        }

    # Get trip_type from state (default to round_trip if not specified)
    trip_type = state.get("trip_type", "round_trip")
    
    # Format the request body
    state["body"] = format_flight_offers_body(
        origin_location_code=state.get("origin_location_code"),
        destination_location_code=state.get("destination_location_code"),
        departure_date=state.get("normalized_departure_date"),
        cabin=state.get("normalized_cabin", "ECONOMY"),
        duration=state.get("duration"),
        trip_type=trip_type
    )
    
    # Log for debugging
    print(
        f"format_body_node: trip_type={trip_type}, origin={state.get('origin_location_code')}, "
        f"dest={state.get('destination_location_code')}, depart={state.get('normalized_departure_date')}, "
        f"cabin={state.get('normalized_cabin')}, duration={state.get('duration')}"
    )

    state["current_node"] = "format_body"
    return state