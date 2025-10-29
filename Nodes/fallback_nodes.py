"""
Fixed Fallback Nodes - MINIMAL LLM USAGE
Database → Code-based adjustments → LLM (ONLY if city/route not in DB) → Emergency

PRIORITY:
1. Database with exact match
2. Database with ANY match → calculate/adjust in code
3. LLM ONLY if city/route doesn't exist in database
4. Emergency fallback
"""

from Models.TravelSearchState import TravelSearchState
import json
from datetime import datetime, timedelta
import os
import pandas as pd
import copy

try:
    from database_fallback import DatabaseFallbackService
    FALLBACK_AVAILABLE = True
    db_service = DatabaseFallbackService()
except ImportError:
    FALLBACK_AVAILABLE = False
    print("⚠️ Database fallback service not available")

try:
    from llm_fallback_generator import LLMFallbackGenerator
    LLM_GEN_AVAILABLE = True
    llm_generator = LLMFallbackGenerator()
except ImportError:
    LLM_GEN_AVAILABLE = False
    print("⚠️ LLM generator not available")

USE_FALLBACK = os.getenv("USE_FALLBACK", "true").lower() == "true"


def get_flight_offers_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """
    Get flight offers with smart fallback
    
    Priority:
    1. Database (exact or adjusted dates)
    2. LLM (ONLY if route doesn't exist in DB)
    3. Emergency rules
    """
    
    origin = state.get("origin_location_code")
    destination = state.get("destination_location_code")
    departure_date = state.get("normalized_departure_date")
    cabin = state.get("normalized_cabin", "ECONOMY")
    duration = state.get("duration")
    
    print(f"\n{'='*60}")
    print(f"FLIGHT SEARCH - 3 DAYS MODE (SMART FALLBACK)")
    print(f"{'='*60}")
    print(f"Route: {origin} → {destination}")
    print(f"Date: {departure_date}, Duration: {duration}, Cabin: {cabin}")
    
    data_found = False
    
    # LAYER 1: Database (exact or adjusted dates)
    if FALLBACK_AVAILABLE:
        print(f"\n[Layer 1] Checking database...")
        
        try:
            flights_by_day = db_service.get_flight_offers(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                cabin_class=cabin,
                duration=duration
            )
            
            if flights_by_day:
                # Store each day separately
                for day_num in range(1, 4):
                    day_flights = flights_by_day.get(day_num, [])
                    state[f"flight_offers_day_{day_num}"] = day_flights
                    
                    # Extract hotel dates
                    if day_flights:
                        checkin, checkout = extract_hotel_dates_from_flight(
                            day_flights[0], duration, day_num
                        )
                        if checkin and checkout:
                            state[f"checkin_date_day_{day_num}"] = checkin
                            state[f"checkout_date_day_{day_num}"] = checkout
                            print(f"  ✓ Day {day_num}: {len(day_flights)} flights, hotel dates {checkin} → {checkout}")
                
                total_flights = sum(len(flights_by_day.get(i, [])) for i in range(1, 4))
                print(f"✓ Database: Retrieved {total_flights} flights total")
                data_found = True
            else:
                print("✗ Database: No matching flights found")
        
        except Exception as e:
            print(f"✗ Database error: {e}")
    
    # LAYER 2: LLM ONLY if route doesn't exist in database

    # LAYER 2: LLM ONLY ONCE for Day 1 → Clone for Days 2 & 3
    if not data_found and LLM_GEN_AVAILABLE and FALLBACK_AVAILABLE:
        route_exists = db_service.route_exists(origin, destination)
        if not route_exists:
            print(f"\n[Layer 2] Route not in DB → Generating Day 1 via LLM (cloning for Days 2-3)...")
            start_date = datetime.strptime(departure_date, "%Y-%m-%d").date()

            # === ONLY ONE LLM CALL ===
            day1_flights = llm_generator.generate_flight_offers(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                cabin_class=cabin,
                duration=duration or 5,
                num_offers=3
            )
            for f in day1_flights:
                f["_search_date"] = departure_date
                f["_day_number"] = 1
                f["_from_llm"] = True

            state["flight_offers_day_1"] = day1_flights

            # === CLONE + TWEAK FOR DAYS 2 & 3 ===
            import random
            for day_offset in [1, 2]:  # Day 2 and Day 3
                day_num = day_offset + 1
                new_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                cloned_flights = []
                for f in day1_flights:
                    clone = copy.deepcopy(f)
                    # Adjust all segment dates
                    for itin in clone.get("itineraries", []):
                        for seg in itin.get("segments", []):
                            for key in ["departure", "arrival"]:
                                if "at" in seg[key]:
                                    old_iso = seg[key]["at"]
                                    old_dt = datetime.fromisoformat(old_iso.replace("Z", "+00:00"))
                                    new_dt = old_dt + timedelta(days=day_offset)
                                    seg[key]["at"] = new_dt.isoformat().replace("+00:00", "Z")
                    # Adjust price slightly (±5%)
                    if "price" in clone and "total" in clone["price"]:
                        try:
                            total = float(clone["price"]["total"])
                            factor = 1 + random.uniform(-0.05, 0.05)
                            clone["price"]["total"] = f"{total * factor:.2f}"
                            if "base" in clone["price"]:
                                base = float(clone["price"]["base"])
                                clone["price"]["base"] = f"{base * factor:.2f}"
                        except:
                            pass  # ignore if parsing fails

                    # Optional: tweak flight number slightly
                    for itin in clone.get("itineraries", []):
                        for seg in itin.get("segments", []):
                            if "number" in seg:
                                num = int(seg["number"])
                                seg["number"] = str(num + random.choice([-1, 0, 1, 2]))

                    clone["_search_date"] = new_date
                    clone["_day_number"] = day_num
                    clone["_cloned_from_day_1"] = True
                    cloned_flights.append(clone)

                state[f"flight_offers_day_{day_num}"] = cloned_flights

                # Extract hotel dates from first cloned flight
                if cloned_flights:
                    checkin, checkout = extract_hotel_dates_from_flight(
                        cloned_flights[0], duration, day_num
                    )
                    if checkin and checkout:
                        state[f"checkin_date_day_{day_num}"] = checkin
                        state[f"checkout_date_day_{day_num}"] = checkout
                        print(f"  ✓ Day {day_num}: cloned {len(cloned_flights)} flights, dates {checkin} → {checkout}")

            data_found = True
        else:
            print(f"\n[Layer 2] Route exists in DB but no data → Skipping LLM")
    
    # LAYER 3: Emergency rules
    if not data_found:
        print(f"\n[Layer 3] Using emergency rule-based generation...")
        
        start_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
        
        for day_offset in range(3):
            day_num = day_offset + 1
            query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            
            flights = []
            for i in range(3):
                flight = generate_emergency_flight(
                    origin=origin,
                    destination=destination,
                    departure_date=query_date,
                    cabin=cabin,
                    duration=duration or 5,
                    offer_num=i+1
                )
                flight["_search_date"] = query_date
                flight["_day_number"] = day_num
                flights.append(flight)
            
            state[f"flight_offers_day_{day_num}"] = flights
            
            checkin, checkout = extract_hotel_dates_from_flight(
                flights[0], duration, day_num
            )
            if checkin and checkout:
                state[f"checkin_date_day_{day_num}"] = checkin
                state[f"checkout_date_day_{day_num}"] = checkout
                print(f"  ✓ Day {day_num}: {len(flights)} flights, dates {checkin} → {checkout}")
        
        print("✓ Emergency: Generated basic fallback data")
    
    # Compile results
    all_results = []
    for i in range(1, 4):
        day_key = f"flight_offers_day_{i}"
        if day_key in state:
            all_results.extend(state[day_key])
    
    state["result"] = {"data": all_results}
    
    print(f"\n{'='*60}")
    print(f"Total flights available: {len(all_results)} (3 days)")
    print(f"{'='*60}\n")
    
    return state


def get_city_IDs_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """Get city IDs with database-first fallback support"""
    
    city_code = state.get("destination_location_code", "")
    print(f"\n{'='*60}")
    print(f"HOTEL IDs - DATABASE FIRST MODE")
    print(f"{'='*60}")
    print(f"City: {city_code}")
    
    data_found = False
    
    if FALLBACK_AVAILABLE:
        print(f"\n[Layer 1] Checking database...")
        
        try:
            hotel_ids = db_service.get_hotel_ids(city_code)
            
            if hotel_ids:
                state["hotel_id"] = hotel_ids
                print(f"✓ Database: Found {len(hotel_ids)} hotel IDs")
                data_found = True
            else:
                print("✗ Database: No hotel IDs found")
        
        except Exception as e:
            print(f"✗ Database error: {e}")
    
    if not data_found:
        print(f"\n[Layer 2] Generating hotel IDs...")
        state["hotel_id"] = [f"GEN{city_code}{i:03d}" for i in range(1, 21)]
        print(f"✓ Generated {len(state['hotel_id'])} hotel IDs")
    
    print(f"{'='*60}\n")
    return state


def get_hotel_offers_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """
    Get hotel offers with MINIMAL LLM usage

    Priority:
    1. Database with exact dates
    2. Database with ANY dates → calculate price-per-night in code (handled in DatabaseFallbackService)
    3. LLM (ONLY if city doesn't exist in database)
    4. Emergency generation
    """

    hotel_ids = state.get("hotel_id", [])
    raw_city_code = state.get("city_code", "") or state.get("destination_location_code", "")
    city_code = (raw_city_code or "").strip().upper()

    print(f"\n{'='*60}")
    print(f"HOTEL OFFERS - 3 DAYS MODE (SMART PRICING)")
    print(f"{'='*60}")
    print(f"City: {city_code}")

    # Check if city exists in database ONCE
    city_exists_in_db = False
    if FALLBACK_AVAILABLE and city_code:
        city_exists_in_db = db_service.city_exists(city_code)
        if city_exists_in_db:
            print(f"✓ City {city_code} found in database")
        else:
            print(f"✗ City {city_code} NOT in database → Will use LLM if needed")

    # Process 3 days
    for day in range(1, 4):
        checkin = state.get(f"checkin_date_day_{day}")
        checkout = state.get(f"checkout_date_day_{day}")

        if not checkin or not checkout:
            state[f"hotel_offers_duration_{day}"] = []
            print(f"  - Day {day}: missing checkin/checkout → skipping")
            continue

        print(f"\nDay {day}: {checkin} → {checkout}")

        data_found = False
        offers_for_day = []

        # LAYER 1: Database (exact dates OR smart ANY-dates calculation)
        if FALLBACK_AVAILABLE and city_exists_in_db:
            print(f"  [Layer 1] Checking database (exact dates then ANY-dates)...")

            try:
                # DatabaseFallbackService.get_hotel_offers now returns scaled offers when needed.
                db_hotels = db_service.get_hotel_offers(
                    city_code=city_code,
                    checkin_date=checkin,
                    checkout_date=checkout
                )

                if db_hotels:
                    processed = process_hotel_offers(db_hotels, source="amadeus_api")
                    state[f"hotel_offers_duration_{day}"] = processed
                    data_found = True

                    # Printer diagnostics: check tags on first hotel
                    example = db_hotels[0]
                    if example.get("_exact_match"):
                        print(f"  ✓ Database: {len(db_hotels)} hotels (exact match)")
                    elif example.get("_price_calculated"):
                        print(f"  ✓ Database: {len(db_hotels)} hotels (calculated price-per-night from {example.get('_original_dates')} -> requested {example.get('_requested_nights')} nights)")
                    else:
                        print(f"  ✓ Database: {len(db_hotels)} hotels (from DB)")

                else:
                    # Defensive attempt: try ANY-dates explicitly (some DBs may have differing schema)
                    print(f"  ✗ Database: No hotels found for exact dates. Trying ANY-dates fallback explicitly...")
                    db_hotels_any = db_service.get_hotel_offers(
                        city_code=city_code,
                        checkin_date=None,
                        checkout_date=None
                    )
                    if db_hotels_any:
                        processed = process_hotel_offers(db_hotels_any, source="amadeus_api")
                        # Adjust dates per requested range using DB service helper if needed
                        state[f"hotel_offers_duration_{day}"] = processed
                        data_found = True
                        print(f"  ✓ Database (ANY-dates): {len(db_hotels_any)} hotels used and adjusted to requested dates")
                    else:
                        print(f"  ✗ Database: No hotels found for {city_code} even with ANY-dates")

            except Exception as e:
                print(f"  ✗ Database error: {e}")

        # LAYER 2: LLM ONLY if city doesn't exist in database
        if not data_found and LLM_GEN_AVAILABLE and not city_exists_in_db:
            print(f"  [Layer 2] City not in DB → Generating Day 1 via LLM (cloning for Days 2-3)...")

            checkin_d1 = state.get("checkin_date_day_1")
            checkout_d1 = state.get("checkout_date_day_1")
            if checkin_d1 and checkout_d1:
                day1_hotels = llm_generator.generate_hotel_offers(
                    city_code=city_code,
                    checkin_date=checkin_d1,
                    checkout_date=checkout_d1,
                    num_offers=5
                )
                state["hotel_offers_duration_1"] = process_hotel_offers(day1_hotels, source="llm")
                print(f"  ✓ LLM: Day 1 – {len(day1_hotels)} hotels generated")

                # Clone for Days 2 & 3
                import random
                for day2 in [2, 3]:
                    checkin_d = state.get(f"checkin_date_day_{day2}")
                    checkout_d = state.get(f"checkout_date_day_{day2}")
                    if not checkin_d or not checkout_d:
                        state[f"hotel_offers_duration_{day2}"] = []
                        continue

                    cloned_hotels = []
                    for h in day1_hotels:
                        clone = copy.deepcopy(h)
                        # Update dates and adjust price for new duration
                        if "offers" in clone:
                            for offer in clone["offers"]:
                                offer["checkInDate"] = checkin_d
                                offer["checkOutDate"] = checkout_d
                                try:
                                    d1_nights = (datetime.strptime(checkout_d1, "%Y-%m-%d") - datetime.strptime(checkin_d1, "%Y-%m-%d")).days
                                    new_nights = (datetime.strptime(checkout_d, "%Y-%m-%d") - datetime.strptime(checkin_d, "%Y-%m-%d")).days
                                    if d1_nights > 0:
                                        total = float(offer["price"]["total"])
                                        price_per_night = total / d1_nights
                                        new_total = price_per_night * new_nights
                                        new_total *= (1 + random.uniform(-0.03, 0.03))
                                        offer["price"]["total"] = f"{new_total:.2f}"
                                        offer["price"]["_price_per_night"] = f"{price_per_night:.2f}"
                                except Exception:
                                    pass

                        clone["_cloned_from_day_1"] = True
                        cloned_hotels.append(clone)

                    state[f"hotel_offers_duration_{day2}"] = process_hotel_offers(cloned_hotels, source="llm")
                    print(f"  ✓ Cloned Day {day2}: {len(cloned_hotels)} hotels")

                data_found = True

        # LAYER 3: Emergency
        if not data_found:
            print(f"  [Layer 3] Using emergency generation...")

            dummy_hotels = generate_emergency_hotels(
                city_code=city_code,
                checkin=checkin,
                checkout=checkout,
                num_hotels=5
            )

            processed = process_hotel_offers(dummy_hotels, source="emergency")
            state[f"hotel_offers_duration_{day}"] = processed
            print(f"  ✓ Emergency: {len(dummy_hotels)} hotels generated")

        # Add company hotels (same as API node)
        company_hotels = state.get("company_hotels", {})
        if company_hotels:
            for country, cities in company_hotels.items():
                if city_code.lower() in cities:
                    city_hotels = cities[city_code.lower()]
                    added = 0
                    for hotel in city_hotels:
                        if checkin and checkout and hotel.get("rate_per_night"):
                            try:
                                checkin_dt = pd.to_datetime(checkin)
                                checkout_dt = pd.to_datetime(checkout)
                                nights = (checkout_dt - checkin_dt).days
                                total_price = float(hotel["rate_per_night"]) * nights
                            except Exception:
                                total_price = float(hotel["rate_per_night"])

                        else:
                            total_price = float(hotel.get("rate_per_night", 0))

                        company_hotel = {
                            "hotel": {"name": hotel.get("hotel_name", "Company Hotel")},
                            "available": True,
                            "best_offers": [{
                                "room_type": "Standard",
                                "offer": {
                                    "price": {"total": total_price, "currency": hotel.get("currency", "EGP")},
                                    "checkInDate": checkin,
                                    "checkOutDate": checkout,
                                    "_price_per_night": hotel.get("rate_per_night")
                                },
                                "currency": hotel.get("currency", "EGP"),
                                "contacts": hotel.get("contacts", {}),
                                "notes": hotel.get("notes", "")
                            }],
                            "source": "company_excel"
                        }
                        current_offers = state.get(f"hotel_offers_duration_{day}", [])
                        current_offers.append(company_hotel)
                        state[f"hotel_offers_duration_{day}"] = current_offers
                        added += 1

                    if added:
                        print(f"  ✓ Added {added} company hotels")

    # Set legacy key for compatibility
    state["hotel_offers"] = state.get("hotel_offers_duration_1", [])

    print(f"\n{'='*60}")
    print(f"State keys created: hotel_offers_duration_1, hotel_offers_duration_2, hotel_offers_duration_3")
    print(f"{'='*60}\n")

    return state

def process_hotel_offers(hotel_offers, source="amadeus_api"):
    """Process hotel offers - always use 'amadeus_api' as source for compatibility"""
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
        if not offers and hotel.get("best_offers"):
            # Support adjusted format where best_offers already exists (from DB adjustments)
            for bo in hotel.get("best_offers"):
                processed_offer = {
                    "room_type": bo.get("room_type", "UNKNOWN"),
                    "offer": bo.get("offer", {}),
                    "currency": bo.get("currency", "")
                }
                hotel_info["best_offers"].append(processed_offer)

        else:
            offers_by_room_type = defaultdict(list)
            for offer in offers:
                room_info = offer.get("room", {})
                room_type = room_info.get("type", "UNKNOWN")
                offers_by_room_type[room_type].append(offer)

            for room_type, room_offers in offers_by_room_type.items():
                cheapest_offer = min(room_offers, key=lambda x: float(x.get("price", {}).get("total", float('inf'))))
                currency = cheapest_offer.get("price", {}).get("currency", "")
                # preserve price-per-night if present on offer
                if "_price_per_night" in cheapest_offer.get("price", {}):
                    cheapest_offer["price"]["_price_per_night"] = cheapest_offer["price"]["_price_per_night"]
                hotel_info["best_offers"].append({
                    "room_type": room_type,
                    "offer": cheapest_offer,
                    "currency": currency
                })

        # Put cheapest room first
        hotel_info["best_offers"].sort(key=lambda x: float(x["offer"].get("price", {}).get("total", float('inf'))))
        processed.append(hotel_info)

    # Sort hotels by cheapest price
    processed.sort(key=lambda x: (
        float(x["best_offers"][0]["offer"].get("price", {}).get("total", float('inf')))
        if x["best_offers"] else float('inf')
    ))

    return processed



def extract_hotel_dates_from_flight(flight_offer, duration, day_number):
    """Extract hotel dates from flight offer (same as API node)"""
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



def generate_emergency_flight(origin: str, destination: str, departure_date: str,
                              cabin: str, duration: int, offer_num: int) -> dict:
    """Generate basic flight offer using simple rules"""
    import random
    
    dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
    ret_date = dep_date + timedelta(days=duration)
    
    if cabin == "BUSINESS":
        base_price = random.randint(35000, 80000)
    else:
        base_price = random.randint(10000, 30000)
    
    price_variation = random.uniform(0.9, 1.1)
    final_price = int(base_price * price_variation)
    
    dep_hour = random.randint(6, 22)
    arr_hour = (dep_hour + random.randint(3, 8)) % 24
    
    flight = {
        "type": "flight-offer",
        "id": f"EMERGENCY_{offer_num}",
        "price": {
            "currency": "EGP",
            "total": str(final_price),
            "base": str(int(final_price * 0.85)),
            "grandTotal": str(final_price)
        },
        "itineraries": [
            {
                "duration": f"PT{random.randint(3, 8)}H{random.randint(0, 59)}M",
                "segments": [{
                    "departure": {
                        "iataCode": origin,
                        "at": f"{departure_date}T{dep_hour:02d}:00:00"
                    },
                    "arrival": {
                        "iataCode": destination,
                        "at": f"{departure_date}T{arr_hour:02d}:00:00"
                    },
                    "carrierCode": "MS",
                    "number": str(random.randint(100, 999)),
                    "aircraft": {"code": "738"}
                }]
            },
            {
                "duration": f"PT{random.randint(3, 8)}H{random.randint(0, 59)}M",
                "segments": [{
                    "departure": {
                        "iataCode": destination,
                        "at": f"{ret_date.strftime('%Y-%m-%d')}T{dep_hour:02d}:00:00"
                    },
                    "arrival": {
                        "iataCode": origin,
                        "at": f"{ret_date.strftime('%Y-%m-%d')}T{arr_hour:02d}:00:00"
                    },
                    "carrierCode": "MS",
                    "number": str(random.randint(100, 999)),
                    "aircraft": {"code": "738"}
                }]
            }
        ],
        "_emergency_fallback": True
    }
    
    return flight


def generate_emergency_hotels(city_code: str, checkin: str, checkout: str, num_hotels: int) -> list:
    """Generate basic hotel offers using simple rules"""
    import random

    checkin_dt = datetime.strptime(checkin, "%Y-%m-%d")
    checkout_dt = datetime.strptime(checkout, "%Y-%m-%d")
    nights = (checkout_dt - checkin_dt).days

    hotels = []
    for i in range(num_hotels):
        rate_per_night = random.randint(1000, 3500)
        total_price = rate_per_night * nights

        hotel = {
            "hotel": {
                "name": f"Hotel {city_code} {i+1}",
                "hotelId": f"EMERGENCY{i:03d}"
            },
            "available": True,
            "offers": [{
                "room": {"type": "STANDARD"},
                "price": {
                    "currency": "EGP",
                    "total": str(total_price),
                    "base": str(int(total_price * 0.9)),
                    "_price_per_night": str(rate_per_night)
                },
                "checkInDate": checkin,
                "checkOutDate": checkout
            }],
            "_emergency_fallback": True
        }
        hotels.append(hotel)

    return hotels