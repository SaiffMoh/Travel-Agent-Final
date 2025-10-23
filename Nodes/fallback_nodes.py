"""
Modified nodes with fallback support
Place these in a new file: Nodes/fallback_nodes.py
"""

from Models.TravelSearchState import TravelSearchState
import requests
import json
from datetime import datetime, timedelta
import copy
import os

# Import fallback services
try:
    from database_fallback import DatabaseFallbackService, FallbackDataGenerator
    FALLBACK_AVAILABLE = True
    db_service = DatabaseFallbackService()
    fallback_gen = FallbackDataGenerator()
except ImportError:
    FALLBACK_AVAILABLE = False
    print("⚠️ Fallback service not available - will rely on Amadeus API only")

# Environment variable to enable/disable fallback
USE_FALLBACK = os.getenv("USE_FALLBACK", "true").lower() == "true"


def get_flight_offers_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """
    Get flight offers with fallback support
    Tries Amadeus API first, falls back to database if API fails
    """
    
    # Extract parameters
    origin = state.get("origin_location_code")
    destination = state.get("destination_location_code")
    departure_date = state.get("normalized_departure_date")
    cabin = state.get("normalized_cabin", "ECONOMY")
    duration = state.get("duration")
    
    print(f"\n=== FLIGHT SEARCH (WITH FALLBACK) ===")
    print(f"Route: {origin} → {destination}")
    print(f"Date: {departure_date}, Duration: {duration}, Cabin: {cabin}")
    print(f"Fallback enabled: {USE_FALLBACK and FALLBACK_AVAILABLE}")
    
    # Try Amadeus API first
    api_success = False
    
    try:
        base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {
            "Authorization": f"Bearer {state['access_token']}",
            "Content-Type": "application/json"
        }
        
        base_body = state.get("body", {})
        start_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
        
        # Try to get flights for 7 days from API
        all_flights_found = True
        
        for day_offset in range(7):
            query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            body = copy.deepcopy(base_body)
            
            if body.get("originDestinations"):
                body["originDestinations"][0]["departureDateTimeRange"]["date"] = query_date
                
                if len(body["originDestinations"]) > 1 and duration:
                    return_date = (start_date + timedelta(days=day_offset + int(duration))).strftime("%Y-%m-%d")
                    body["originDestinations"][1]["departureDateTimeRange"]["date"] = return_date
            
            if "searchCriteria" not in body:
                body["searchCriteria"] = {}
            body["searchCriteria"]["maxFlightOffers"] = 3
            
            try:
                resp = requests.post(base_url, headers=headers, json=body, timeout=30)
                
                if resp.status_code == 200:
                    data = resp.json()
                    flights = data.get("data", [])
                    
                    if flights:
                        for f in flights:
                            f["_search_date"] = query_date
                            f["_day_number"] = day_offset + 1
                            f["_from_api"] = True
                        
                        state[f"flight_offers_day_{day_offset + 1}"] = flights
                        
                        # Extract hotel dates
                        if flights:
                            checkin, checkout = extract_hotel_dates_from_flight(
                                flights[0], duration, day_offset + 1
                            )
                            if checkin and checkout:
                                state[f"checkin_date_day_{day_offset + 1}"] = checkin
                                state[f"checkout_date_day_{day_offset + 1}"] = checkout
                        
                        print(f"✓ API: Day {day_offset + 1} - {len(flights)} flights")
                    else:
                        all_flights_found = False
                        print(f"✗ API: Day {day_offset + 1} - No flights")
                else:
                    all_flights_found = False
                    print(f"✗ API: Day {day_offset + 1} - Error {resp.status_code}")
                
            except Exception as e:
                all_flights_found = False
                print(f"✗ API: Day {day_offset + 1} - Exception: {e}")
        
        if all_flights_found:
            api_success = True
            print("✓ API search completed successfully")
        
    except Exception as e:
        print(f"✗ API search failed: {e}")
    
    # Fallback to database if API failed and fallback is enabled
    if not api_success and USE_FALLBACK and FALLBACK_AVAILABLE:
        print("\n🔄 Falling back to database...")
        
        try:
            db_flights = db_service.get_flight_offers(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                cabin_class=cabin,
                duration=duration
            )
            
            if db_flights:
                # Organize by day
                flights_by_day = {}
                for flight in db_flights:
                    day_num = flight.get("_day_number", 1)
                    if day_num not in flights_by_day:
                        flights_by_day[day_num] = []
                    flights_by_day[day_num].append(flight)
                
                # Store in state
                for day in range(1, 8):
                    day_flights = flights_by_day.get(day, [])
                    state[f"flight_offers_day_{day}"] = day_flights
                    
                    if day_flights:
                        # Extract hotel dates from first flight
                        checkin, checkout = extract_hotel_dates_from_flight(
                            day_flights[0], duration, day
                        )
                        if checkin and checkout:
                            state[f"checkin_date_day_{day}"] = checkin
                            state[f"checkout_date_day_{day}"] = checkout
                
                print(f"✓ Database: Retrieved {len(db_flights)} flights")
            
            # If still no flights, generate dummy data
            elif USE_FALLBACK:
                print("🔄 Generating fallback data...")
                
                start_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
                
                for day_offset in range(7):
                    query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                    
                    # Generate 3 flight offers
                    flights = []
                    for _ in range(3):
                        flight = fallback_gen.generate_flight_offer(
                            origin=origin,
                            destination=destination,
                            departure_date=query_date,
                            cabin=cabin,
                            duration=duration or 5
                        )
                        flight["_search_date"] = query_date
                        flight["_day_number"] = day_offset + 1
                        flights.append(flight)
                    
                    state[f"flight_offers_day_{day_offset + 1}"] = flights
                    
                    # Set hotel dates
                    checkin, checkout = extract_hotel_dates_from_flight(
                        flights[0], duration, day_offset + 1
                    )
                    if checkin and checkout:
                        state[f"checkin_date_day_{day_offset + 1}"] = checkin
                        state[f"checkout_date_day_{day_offset + 1}"] = checkout
                
                print("✓ Generated fallback flight data")
        
        except Exception as e:
            print(f"✗ Fallback failed: {e}")
    
    # Compile all results
    all_results = []
    for i in range(1, 8):
        day_key = f"flight_offers_day_{i}"
        if day_key in state:
            all_results.extend(state[day_key])
    
    state["result"] = {"data": all_results}
    print(f"\nTotal flights available: {len(all_results)}")
    
    return state


def get_city_IDs_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """Get city IDs with fallback support"""
    
    city_code = state.get("destination_location_code", "")
    print(f"\n=== GETTING HOTEL IDs FOR {city_code} ===")
    
    # Try API first
    try:
        url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        headers = {
            "Authorization": f"Bearer {state['access_token']}",
            "Content-Type": "application/json"
        }
        params = {"cityCode": city_code}
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            hotels_data = data.get("data", [])
            hotel_ids = [h.get("hotelId") for h in hotels_data if h.get("hotelId")][:20]
            
            if hotel_ids:
                state["hotel_id"] = hotel_ids
                print(f"✓ API: Found {len(hotel_ids)} hotels")
                return state
        
        print(f"✗ API failed with status {response.status_code}")
    
    except Exception as e:
        print(f"✗ API error: {e}")
    
    # Fallback to database
    if USE_FALLBACK and FALLBACK_AVAILABLE:
        print("🔄 Falling back to database...")
        
        try:
            hotel_ids = db_service.get_hotel_ids(city_code)
            
            if hotel_ids:
                state["hotel_id"] = hotel_ids
                print(f"✓ Database: Found {len(hotel_ids)} hotels")
            else:
                # Generate dummy hotel IDs
                state["hotel_id"] = [f"FALLBACK{i:05d}" for i in range(1, 21)]
                print("✓ Generated fallback hotel IDs")
        
        except Exception as e:
            print(f"✗ Fallback failed: {e}")
            state["hotel_id"] = []
    else:
        state["hotel_id"] = []
    
    return state


def get_hotel_offers_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """Get hotel offers with fallback support, including company hotels."""
    url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
    headers = {
        "Authorization": f"Bearer {state['access_token']}",
        "Content-Type": "application/json"
    }

    hotel_ids = state.get("hotel_id", [])
    city_code = state.get("city_code", "").lower() or state.get("destination_location_code", "").lower()

    print(f"\n=== GETTING HOTEL OFFERS FOR {city_code} ===")

    # Process each day
    for day in range(1, 8):
        checkin = state.get(f"checkin_date_day_{day}")
        checkout = state.get(f"checkout_date_day_{day}")

        if not checkin or not checkout:
            state[f"hotel_offers_duration_{day}"] = []
            continue

        print(f"\nDay {day}: {checkin} → {checkout}")

        api_success = False

        # Try API first
        if hotel_ids:
            try:
                params = {
                    "hotelIds": ",".join(hotel_ids[:10]),
                    "checkInDate": checkin,
                    "checkOutDate": checkout
                }

                response = requests.get(url, headers=headers, params=params, timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    hotels = data.get("data", [])

                    if hotels:
                        # Process hotels
                        processed = process_hotel_offers(hotels, source="amadeus_api")
                        state[f"hotel_offers_duration_{day}"] = processed
                        api_success = True
                        print(f"  ✓ API: {len(hotels)} hotels")
                else:
                    print(f"  ✗ API error {response.status_code}")

            except Exception as e:
                print(f"  ✗ API exception: {e}")

        # Fallback to database
        if not api_success and USE_FALLBACK and FALLBACK_AVAILABLE:
            print(f"  🔄 Falling back to database...")

            try:
                db_hotels = db_service.get_hotel_offers(
                    city_code=city_code.upper(),
                    checkin_date=checkin,
                    checkout_date=checkout
                )

                if db_hotels:
                    processed = process_hotel_offers(db_hotels, source="database")
                    state[f"hotel_offers_duration_{day}"] = processed
                    print(f"  ✓ Database: {len(db_hotels)} hotels")
                else:
                    # Generate dummy hotels
                    dummy_hotels = []
                    hotel_names = [
                        f"Hotel {city_code.upper()} {i}" for i in range(1, 6)
                    ]

                    for name in hotel_names:
                        hotel = fallback_gen.generate_hotel_offer(name, checkin, checkout)
                        dummy_hotels.append(hotel)

                    processed = process_hotel_offers(dummy_hotels, source="generated")
                    state[f"hotel_offers_duration_{day}"] = processed
                    print(f"  ✓ Generated {len(dummy_hotels)} fallback hotels")

            except Exception as e:
                print(f"  ✗ Fallback failed: {e}")
                state[f"hotel_offers_duration_{day}"] = []

        elif not api_success:
            state[f"hotel_offers_duration_{day}"] = []

        # Add company hotels for this day
        company_hotels = state.get("company_hotels", {})
        if company_hotels:
            for country, cities in company_hotels.items():
                if city_code in cities:
                    city_hotels = cities[city_code]
                    for hotel in city_hotels:
                        if checkin and checkout and hotel["rate_per_night"]:
                            try:
                                checkin_dt = pd.to_datetime(checkin)
                                checkout_dt = pd.to_datetime(checkout)
                                nights = (checkout_dt - checkin_dt).days
                                total_price = float(hotel["rate_per_night"]) * nights
                            except Exception:
                                total_price = float(hotel["rate_per_night"])

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
                                "contacts": hotel["contacts"],
                                "notes": hotel["notes"]
                            }],
                            "source": "company_excel"
                        }
                        # Add to the day's offers
                        current_offers = state.get(f"hotel_offers_duration_{day}", [])
                        current_offers.append(company_hotel)
                        state[f"hotel_offers_duration_{day}"] = current_offers

    state["hotel_offers"] = state.get("hotel_offers_duration_1", [])
    return state



def process_hotel_offers(hotel_offers, source="amadeus_api"):
    """Process hotel offers - same as original but with source tagging"""
    from collections import defaultdict
    
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


def extract_hotel_dates_from_flight(flight_offer, duration, day_number):
    """Extract hotel dates from flight - same as original"""
    try:
        itineraries = flight_offer.get("itineraries", [])
        if not itineraries:
            return None, None
        
        outbound_segments = itineraries[0].get("segments", [])
        if not outbound_segments:
            return None, None
        
        final_outbound_segment = outbound_segments[-1]
        outbound_arrival_iso = final_outbound_segment.get("arrival", {}).get("at")
        if not outbound_arrival_iso:
            return None, None
        
        checkin_datetime = datetime.fromisoformat(outbound_arrival_iso.replace("Z", "+00:00"))
        checkin_date = checkin_datetime.date().strftime("%Y-%m-%d")
        
        checkout_date = None
        
        if len(itineraries) > 1:
            return_segments = itineraries[1].get("segments", [])
            if return_segments:
                first_return_segment = return_segments[0]
                return_departure_iso = first_return_segment.get("departure", {}).get("at")
                if return_departure_iso:
                    checkout_datetime = datetime.fromisoformat(return_departure_iso.replace("Z", "+00:00"))
                    checkout_date = checkout_datetime.date().strftime("%Y-%m-%d")
        
        if not checkout_date and duration:
            checkout_date = (checkin_datetime.date() + timedelta(days=int(duration))).strftime("%Y-%m-%d")
        
        return checkin_date, checkout_date
    
    except Exception as e:
        print(f"Error extracting hotel dates: {e}")
        return None, None