from datetime import datetime, timedelta
from ..Models import FlightSearchState
from ..Utils import _debug_print

def format_body_node(state: FlightSearchState) -> FlightSearchState:
    """Format the request body for Amadeus API"""
    try:
        (state.setdefault("node_trace", [])).append("format_body")
    except Exception:
        pass

    def format_flight_offers_body(origin_location_code, destination_location_code, departure_date, cabin="ECONOMY", duration=None):
        origin_destinations = [{
            "id": "1",
            "originLocationCode": origin_location_code,
            "destinationLocationCode": destination_location_code,
            "departureDateTimeRange": {
                "date": departure_date,
                "time": "10:00:00"
            }
        }]
        if duration is not None:
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
        return {
            "currencyCode": "EGP",
            "originDestinations": origin_destinations,
            "travelers": [{"id": "1", "travelerType": "ADULT"}],
            "sources": ["GDS"],
            "searchCriteria": {
                "maxFlightOffers": 5,
                "flightFilters": {
                    "cabinRestrictions": [{
                        "cabin": cabin,
                        "coverage": "MOST_SEGMENTS",
                        "originDestinationIds": [od["id"] for od in origin_destinations]
                    }]
                }
            }
        }

    state["body"] = format_flight_offers_body(
        origin_location_code=state.get("origin_location_code"),
        destination_location_code=state.get("destination_location_code"),
        departure_date=state.get("normalized_departure_date"),
        cabin=state.get("normalized_cabin", "ECONOMY"),
        duration=state.get("duration")
    )

    _debug_print("Amadeus request body", state.get("body"))
    state["current_node"] = "format_body"
    return state
