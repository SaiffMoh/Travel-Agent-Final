from Models import TravelSearchState
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_flight_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get flight offers from Amadeus API for a 3-day window in parallel."""

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

        body.setdefault("searchCriteria", {}).setdefault("maxFlightOffers", 3)
        bodies.append((query_date, body))
    all_results = []
    def fetch_for_day(day_body_tuple):
        day, body = day_body_tuple
        try:
            resp = requests.post(base_url, headers=headers, json=body, timeout=100)
            resp.raise_for_status()
            data = resp.json()
            flights = data.get("data", []) or []
            for f in flights[:5]:
                f["_search_date"] = day
            return flights[:5]
        except Exception as exc:
            print(f"Error getting flight offers for {day}: {exc}")
            return []
    # Parallel search across 3 days
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetch_for_day, b) for b in bodies]
        for fut in as_completed(futures):
            all_results.extend(fut.result())
    state["result"] = {"data": all_results}
    return state