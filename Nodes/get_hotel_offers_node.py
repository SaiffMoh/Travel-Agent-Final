from Models.TravelSearchState import TravelSearchState
import requests
from collections import defaultdict
import time
import pandas as pd

def get_hotel_offers_node(state: TravelSearchState) -> TravelSearchState:
    """Get hotel offers for 3 durations sequentially using extracted dates, and include company hotels.
    
    Works for:
    - Full packages (flights + hotels)
    - Hotels-only requests
    """
    url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }
    hotel_ids = state.get("hotel_id", [])
    city_code = state.get("city_code", "").lower() or state.get("destination_location_code", "").lower()
    request_type = state.get("request_type", "packages")
    
    print(f"\n=== HOTEL SEARCH (request_type: {request_type}) ===")
    print(f"City code: {city_code}")
    print(f"Amadeus hotel IDs: {len(hotel_ids)}")
    print(f"Company hotels available: {bool(state.get('company_hotels'))}")
    
    # If we have neither Amadeus hotels nor company hotels, return empty
    if not hotel_ids and not state.get("company_hotels"):
        print("WARNING: No hotel sources available (neither Amadeus nor company hotels)")
        for day in range(1, 4):  # Changed from 8 to 4 to match your 3-day search
            state[f"hotel_offers_duration_{day}"] = []
        return state

    # Prepare hotel search for 3 days (matching your flight search)
    duration_requests = []
    for day in range(1, 4):  # Changed from 8 to 4
        checkin_key = f"checkin_date_day_{day}"
        checkout_key = f"checkout_date_day_{day}"
        checkin = state.get(checkin_key)
        checkout = state.get(checkout_key)
        
        if checkin and checkout:
            duration_requests.append({
                "duration_number": day,
                "checkin": checkin,
                "checkout": checkout
            })
            print(f"Day {day}: {checkin} → {checkout}")
        else:
            print(f"WARNING: Missing dates for day {day}")

    def fetch_hotels_for_duration(duration_info):
        """Fetch hotel offers for a specific duration and add company hotels."""
        duration_num = duration_info["duration_number"]
        checkin = duration_info["checkin"]
        checkout = duration_info["checkout"]
        combined_offers = []

        # Fetch from Amadeus API
        if hotel_ids and checkin and checkout:
            params = {
                "hotelIds": ",".join(hotel_ids),
                "checkInDate": checkin,
                "checkOutDate": checkout
            }
            print(f"  → Searching Amadeus for {len(hotel_ids)} hotels...")
            try:
                response = requests.get(url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                hotel_offers = data.get("data", [])
                processed_offers = process_hotel_offers(hotel_offers, source="amadeus_api")
                combined_offers.extend(processed_offers)
                print(f"  ✓ Found {len(processed_offers)} Amadeus hotels")
            except requests.exceptions.HTTPError as e:
                print(f"  ✗ Amadeus API error: {e}")
                if response.status_code == 429:
                    print("  ⏳ Rate limited, retrying...")
                    time.sleep(2)
                    try:
                        response = requests.get(url, headers=headers, params=params, timeout=10)
                        response.raise_for_status()
                        data = response.json()
                        hotel_offers = data.get("data", [])
                        processed_offers = process_hotel_offers(hotel_offers, source="amadeus_api")
                        combined_offers.extend(processed_offers)
                        print(f"  ✓ Found {len(processed_offers)} Amadeus hotels (retry)")
                    except Exception as retry_err:
                        print(f"  ✗ Retry failed: {retry_err}")
            except Exception as e:
                print(f"  ✗ Unexpected error: {e}")
        else:
            if not hotel_ids:
                print(f"  ⚠ No Amadeus hotel IDs - skipping API search")

        # Fetch from company hotels
        company_hotels = state.get("company_hotels", {})
        company_hotels_added = 0
        
        if company_hotels:
            print(f"  → Searching company hotels for city code: {city_code}")
            for country, cities in company_hotels.items():
                if city_code in cities:
                    city_hotels = cities[city_code]
                    print(f"  ✓ Found {len(city_hotels)} company hotels in {country}")
                    
                    for hotel in city_hotels:
                        if checkin and checkout and hotel.get("rate_per_night"):
                            try:
                                checkin_dt = pd.to_datetime(checkin)
                                checkout_dt = pd.to_datetime(checkout)
                                nights = (checkout_dt - checkin_dt).days
                                total_price = float(hotel["rate_per_night"]) * nights
                            except Exception as e:
                                print(f"  ⚠ Error calculating price for {hotel.get('hotel_name')}: {e}")
                                total_price = float(hotel["rate_per_night"])
                        else:
                            total_price = float(hotel.get("rate_per_night", 0))

                        company_hotel = {
                            "hotel": {"name": hotel["hotel_name"]},
                            "available": True,
                            "best_offers": [{
                                "room_type": "Standard",
                                "offer": {
                                    "price": {"total": total_price, "currency": hotel["currency"]},
                                    "checkInDate": checkin,
                                    "checkOutDate": checkout
                                },
                                "currency": hotel["currency"],
                                "contacts": hotel.get("contacts", ""),
                                "notes": hotel.get("notes", "")
                            }],
                            "source": "company_excel"
                        }
                        combined_offers.append(company_hotel)
                        company_hotels_added += 1
                    
                    print(f"  ✓ Added {company_hotels_added} company hotels")
                    break  # Only process first matching city
            
            if company_hotels_added == 0:
                print(f"  ⚠ No company hotels found for city code: {city_code}")
        else:
            print(f"  ⚠ No company hotels data available")
        
        print(f"  📊 Total offers for day {duration_num}: {len(combined_offers)}")
        return duration_num, combined_offers

    def process_hotel_offers(hotel_offers, source="amadeus_api"):
        """Process hotel offers to find cheapest offer by room type for each hotel."""
        processed = []
        for hotel in hotel_offers:
            hotel_info = {
                "hotel": hotel.get("hotel", {}),
                "available": hotel.get("available", True),
                "best_offers": [],
                "source": source
            }
            if not hotel_info["available"]:
                processed.append(hotel_info)
                continue
            offers = hotel.get("offers", [])
            if not offers:
                processed.append(hotel_info)
                continue

            offers_by_room_type = defaultdict(list)
            for offer in offers:
                room_info = offer.get("room", {})
                room_type = room_info.get("type", "UNKNOWN")
                offers_by_room_type[room_type].append(offer)

            for room_type, room_offers in offers_by_room_type.items():
                cheapest_offer = min(room_offers, key=lambda x: float(x.get("price", {}).get("total", float('inf'))))
                currency = cheapest_offer.get("price", {}).get("currency", "")
                hotel_info["best_offers"].append({
                    "room_type": room_type,
                    "offer": cheapest_offer,
                    "currency": currency
                })

            hotel_info["best_offers"].sort(key=lambda x: float(x["offer"].get("price", {}).get("total", float('inf'))))
            processed.append(hotel_info)

        processed.sort(key=lambda x: (
            float(x["best_offers"][0]["offer"].get("price", {}).get("total", float('inf')))
            if x["best_offers"] else float('inf')
        ))
        return processed

    # Execute searches for all durations
    for duration_info in duration_requests:
        duration_number, offers = fetch_hotels_for_duration(duration_info)
        state[f"hotel_offers_duration_{duration_number}"] = offers
        time.sleep(0.5)  # Small delay to avoid rate limits

    # Set the first day's offers as default
    state["hotel_offers"] = state.get("hotel_offers_duration_1", [])
    
    print(f"\n✓ Hotel search completed")
    print(f"Total packages created: {len(duration_requests)}")
    
    return state