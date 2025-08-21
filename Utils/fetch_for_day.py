import requests

def fetch_for_day(day_info, access_token):
        base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
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
