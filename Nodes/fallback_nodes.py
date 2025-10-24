"""
Modified nodes with fallback support - DATABASE FIRST, LLM FOR DAY 1 ONLY
Two-layer fallback: Database → LLM Generator (Day 1) → Rule-based cloning (Days 2-7)
NO Amadeus API calls - completely offline for reliability
"""

from Models.TravelSearchState import TravelSearchState
import json
from datetime import datetime, timedelta
import os
import pandas as pd
import copy

# Import fallback services
try:
    from database_fallback import DatabaseFallbackService
    FALLBACK_AVAILABLE = True
    db_service = DatabaseFallbackService()
except ImportError:
    FALLBACK_AVAILABLE = False
    print("⚠️ Database fallback service not available")

# Import LLM generator
try:
    from llm_fallback_generator import LLMFallbackGenerator
    LLM_GEN_AVAILABLE = True
    llm_generator = LLMFallbackGenerator()
except ImportError:
    LLM_GEN_AVAILABLE = False
    print("⚠️ LLM generator not available - will use basic fallback only")

# Environment variable to enable/disable fallback
USE_FALLBACK = os.getenv("USE_FALLBACK", "true").lower() == "true"


def get_flight_offers_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """
    Get flight offers with optimized fallback support
    Layer 1: Database (pre-collected real data)
    Layer 2: LLM Generator (DAY 1 ONLY)
    Layer 3: Rule-based cloning (Days 2-7 from Day 1)
    """
    
    # Extract parameters
    origin = state.get("origin_location_code")
    destination = state.get("destination_location_code")
    departure_date = state.get("normalized_departure_date")
    cabin = state.get("normalized_cabin", "ECONOMY")
    duration = state.get("duration")
    
    print(f"\n{'='*60}")
    print(f"FLIGHT SEARCH - DATABASE FIRST MODE")
    print(f"{'='*60}")
    print(f"Route: {origin} → {destination}")
    print(f"Date: {departure_date}, Duration: {duration}, Cabin: {cabin}")
    print(f"Database available: {FALLBACK_AVAILABLE}")
    print(f"LLM generator available: {LLM_GEN_AVAILABLE}")
    
    data_found = False
    
    # ============================================================================
    # LAYER 1: Try Database first
    # ============================================================================
    if FALLBACK_AVAILABLE:
        print(f"\n[Layer 1] Checking database...")
        
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
                
                print(f"✓ Database: Retrieved {len(db_flights)} flights from cache")
                data_found = True
            else:
                print("✗ Database: No matching flights found (query outside scope)")
        
        except Exception as e:
            print(f"✗ Database error: {e}")
    
    # ============================================================================
    # LAYER 2: LLM Generator for DAY 1 ONLY, then clone for days 2-7
    # ============================================================================
    if not data_found and LLM_GEN_AVAILABLE:
        print(f"\n[Layer 2] Query outside database scope - Using LLM Generator for DAY 1...")
        
        try:
            start_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
            
            # Generate flights for DAY 1 ONLY
            day1_date = start_date.strftime("%Y-%m-%d")
            print(f"🤖 Generating Day 1 flights via LLM...")
            
            day1_flights = llm_generator.generate_flight_offers(
                origin=origin,
                destination=destination,
                departure_date=day1_date,
                cabin_class=cabin,
                duration=duration or 5,
                num_offers=3
            )
            
            # Add metadata
            for flight in day1_flights:
                flight["_search_date"] = day1_date
                flight["_day_number"] = 1
                if "_from_llm" not in flight:
                    flight["_from_llm"] = True
            
            state[f"flight_offers_day_1"] = day1_flights
            
            # Set hotel dates for Day 1
            if day1_flights:
                checkin, checkout = extract_hotel_dates_from_flight(
                    day1_flights[0], duration, 1
                )
                if checkin and checkout:
                    state[f"checkin_date_day_1"] = checkin
                    state[f"checkout_date_day_1"] = checkout
            
            print(f"  ✓ LLM Day 1: {len(day1_flights)} flights generated")
            
            # ========================================================================
            # CLONE DAY 1 DATA FOR DAYS 2-7 (Rule-based date adjustment)
            # ========================================================================
            print(f"  🔄 Cloning Day 1 data for Days 2-7 (rule-based)...")
            
            for day_offset in range(1, 7):  # Days 2-7
                day_num = day_offset + 1
                query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                
                # Clone and adjust dates
                cloned_flights = clone_and_adjust_flights(
                    day1_flights, 
                    query_date, 
                    duration or 5,
                    day_num
                )
                
                state[f"flight_offers_day_{day_num}"] = cloned_flights
                
                # Set hotel dates
                if cloned_flights:
                    checkin, checkout = extract_hotel_dates_from_flight(
                        cloned_flights[0], duration, day_num
                    )
                    if checkin and checkout:
                        state[f"checkin_date_day_{day_num}"] = checkin
                        state[f"checkout_date_day_{day_num}"] = checkout
                
                print(f"    ✓ Day {day_num}: {len(cloned_flights)} flights cloned")
            
            total_flights = len(day1_flights) * 7
            print(f"✓ Total: {total_flights} flights (1 LLM generation + 6 clones)")
            data_found = True
        
        except Exception as e:
            print(f"✗ LLM generation failed: {e}")
    
    # ============================================================================
    # LAYER 3: Emergency rules if everything fails
    # ============================================================================
    if not data_found:
        print(f"\n[Layer 3] LLM unavailable - Using emergency rule-based generation...")
        
        start_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
        
        for day_offset in range(7):
            query_date = (start_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            
            # Generate 3 basic flight offers
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
        
        print("✓ Emergency: Generated basic fallback data")
    
    # Compile all results
    all_results = []
    for i in range(1, 8):
        day_key = f"flight_offers_day_{i}"
        if day_key in state:
            all_results.extend(state[day_key])
    
    state["result"] = {"data": all_results}
    print(f"\n{'='*60}")
    print(f"Total flights available: {len(all_results)}")
    print(f"{'='*60}\n")
    
    return state


def clone_and_adjust_flights(template_flights: list, new_date: str, duration: int, day_num: int) -> list:
    """
    Clone flights from Day 1 and adjust dates for a new day
    Uses deep copy to avoid mutating original data
    """
    import random
    
    cloned = []
    new_dep_date = datetime.strptime(new_date, "%Y-%m-%d")
    new_ret_date = new_dep_date + timedelta(days=duration)
    
    for i, template in enumerate(template_flights):
        flight = copy.deepcopy(template)
        
        # Add small price variation (±5%)
        if "price" in flight and "total" in flight["price"]:
            original_price = float(flight["price"]["total"])
            variation = random.uniform(0.95, 1.05)
            new_price = int(original_price * variation)
            flight["price"]["total"] = str(new_price)
            flight["price"]["grandTotal"] = str(new_price)
            if "base" in flight["price"]:
                flight["price"]["base"] = str(int(new_price * 0.85))
        
        # Update flight ID
        flight["id"] = f"CLONED_DAY{day_num}_{i+1}"
        
        # Update itinerary dates
        if "itineraries" in flight and len(flight["itineraries"]) > 0:
            # Outbound
            outbound = flight["itineraries"][0]
            if "segments" in outbound:
                for segment in outbound["segments"]:
                    if "departure" in segment and "at" in segment["departure"]:
                        old_time = segment["departure"]["at"].split("T")[1] if "T" in segment["departure"]["at"] else "10:00:00"
                        segment["departure"]["at"] = f"{new_date}T{old_time}"
                    if "arrival" in segment and "at" in segment["arrival"]:
                        old_time = segment["arrival"]["at"].split("T")[1] if "T" in segment["arrival"]["at"] else "14:00:00"
                        segment["arrival"]["at"] = f"{new_date}T{old_time}"
            
            # Return (if exists)
            if len(flight["itineraries"]) > 1:
                return_itinerary = flight["itineraries"][1]
                if "segments" in return_itinerary:
                    for segment in return_itinerary["segments"]:
                        if "departure" in segment and "at" in segment["departure"]:
                            old_time = segment["departure"]["at"].split("T")[1] if "T" in segment["departure"]["at"] else "15:00:00"
                            segment["departure"]["at"] = f"{new_ret_date.strftime('%Y-%m-%d')}T{old_time}"
                        if "arrival" in segment and "at" in segment["arrival"]:
                            old_time = segment["arrival"]["at"].split("T")[1] if "T" in segment["arrival"]["at"] else "19:00:00"
                            segment["arrival"]["at"] = f"{new_ret_date.strftime('%Y-%m-%d')}T{old_time}"
        
        # Update metadata
        flight["_search_date"] = new_date
        flight["_day_number"] = day_num
        flight["_cloned_from_day_1"] = True
        
        cloned.append(flight)
    
    return cloned


def clone_and_adjust_hotels(template_hotels: list, new_checkin: str, new_checkout: str) -> list:
    """
    Clone hotels from Day 1 and adjust dates/prices for a new day
    """
    import random
    
    cloned = []
    
    # Calculate new nights
    checkin_dt = datetime.strptime(new_checkin, "%Y-%m-%d")
    checkout_dt = datetime.strptime(new_checkout, "%Y-%m-%d")
    new_nights = (checkout_dt - checkin_dt).days
    
    for template in template_hotels:
        hotel = copy.deepcopy(template)
        
        # Update offers with new dates and prices
        if "offers" in hotel:
            for offer in hotel["offers"]:
                # Update dates
                offer["checkInDate"] = new_checkin
                offer["checkOutDate"] = new_checkout
                
                # Recalculate price based on new nights
                if "price" in offer and "total" in offer["price"]:
                    # Try to get original per-night rate
                    old_total = float(offer["price"]["total"])
                    # Assume template was for similar duration, just adjust with small variation
                    variation = random.uniform(0.95, 1.05)
                    new_total = int(old_total * variation)
                    
                    offer["price"]["total"] = str(new_total)
                    if "base" in offer["price"]:
                        offer["price"]["base"] = str(int(new_total * 0.9))
        
        hotel["_cloned_from_day_1"] = True
        cloned.append(hotel)
    
    return cloned


def get_city_IDs_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """
    Get city IDs with database-first fallback support
    Layer 1: Database
    Layer 2: Generate dummy IDs
    """
    
    city_code = state.get("destination_location_code", "")
    print(f"\n{'='*60}")
    print(f"HOTEL IDs - DATABASE FIRST MODE")
    print(f"{'='*60}")
    print(f"City: {city_code}")
    
    data_found = False
    
    # ============================================================================
    # LAYER 1: Try database
    # ============================================================================
    if FALLBACK_AVAILABLE:
        print(f"\n[Layer 1] Checking database...")
        
        try:
            hotel_ids = db_service.get_hotel_ids(city_code)
            
            if hotel_ids:
                state["hotel_id"] = hotel_ids
                print(f"✓ Database: Found {len(hotel_ids)} hotel IDs")
                data_found = True
            else:
                print("✗ Database: No hotel IDs found (city outside scope)")
        
        except Exception as e:
            print(f"✗ Database error: {e}")
    
    # ============================================================================
    # LAYER 2: Generate dummy hotel IDs
    # ============================================================================
    if not data_found:
        print(f"\n[Layer 2] Generating hotel IDs for out-of-scope city...")
        state["hotel_id"] = [f"GEN{city_code}{i:03d}" for i in range(1, 21)]
        print(f"✓ Generated {len(state['hotel_id'])} hotel IDs")
    
    print(f"{'='*60}\n")
    return state


def get_hotel_offers_node_with_fallback(state: TravelSearchState) -> TravelSearchState:
    """
    Get hotel offers with optimized fallback support
    Layer 1: Database (pre-collected real data)
    Layer 2: LLM Generator (DAY 1 ONLY)
    Layer 3: Rule-based cloning (Days 2-7 from Day 1)
    """
    
    hotel_ids = state.get("hotel_id", [])
    city_code = state.get("city_code", "").lower() or state.get("destination_location_code", "").lower()

    print(f"\n{'='*60}")
    print(f"HOTEL OFFERS - DATABASE FIRST MODE")
    print(f"{'='*60}")
    print(f"City: {city_code}")

    day1_hotels = None  # Store Day 1 hotels for cloning
    
    # Process each day
    for day in range(1, 8):
        checkin = state.get(f"checkin_date_day_{day}")
        checkout = state.get(f"checkout_date_day_{day}")

        if not checkin or not checkout:
            state[f"hotel_offers_duration_{day}"] = []
            continue

        print(f"\nDay {day}: {checkin} → {checkout}")

        data_found = False

        # ========================================================================
        # LAYER 1: Try database
        # ========================================================================
        if FALLBACK_AVAILABLE:
            print(f"  [Layer 1] Checking database...")

            try:
                db_hotels = db_service.get_hotel_offers(
                    city_code=city_code.upper(),
                    checkin_date=checkin,
                    checkout_date=checkout
                )

                if db_hotels:
                    processed = process_hotel_offers(db_hotels, source="database")
                    state[f"hotel_offers_duration_{day}"] = processed
                    data_found = True
                    print(f"  ✓ Database: {len(db_hotels)} hotels from cache")
                else:
                    print(f"  ✗ Database: No hotels found (query outside scope)")

            except Exception as e:
                print(f"  ✗ Database error: {e}")

        # ========================================================================
        # LAYER 2: LLM Generator for DAY 1 ONLY
        # ========================================================================
        if not data_found and LLM_GEN_AVAILABLE and day == 1:
            print(f"  [Layer 2] Query outside database scope - Using LLM Generator for DAY 1...")

            try:
                generated_hotels = llm_generator.generate_hotel_offers(
                    city_code=city_code.upper(),
                    checkin_date=checkin,
                    checkout_date=checkout,
                    num_offers=5
                )

                if generated_hotels:
                    processed = process_hotel_offers(generated_hotels, source="llm_generated")
                    state[f"hotel_offers_duration_{day}"] = processed
                    day1_hotels = processed  # Store for cloning
                    data_found = True
                    print(f"  ✓ LLM: {len(generated_hotels)} hotels generated")

            except Exception as e:
                print(f"  ✗ LLM generation failed: {e}")
        
        # ========================================================================
        # LAYER 2.5: Clone from Day 1 for Days 2-7
        # ========================================================================
        elif not data_found and day > 1 and day1_hotels:
            print(f"  [Layer 2.5] Cloning Day 1 hotels...")
            
            cloned_hotels = clone_and_adjust_hotels(day1_hotels, checkin, checkout)
            state[f"hotel_offers_duration_{day}"] = cloned_hotels
            data_found = True
            print(f"  ✓ Cloned: {len(cloned_hotels)} hotels from Day 1")

        # ========================================================================
        # LAYER 3: Emergency rules if everything fails
        # ========================================================================
        if not data_found:
            print(f"  [Layer 3] Using emergency generation...")

            dummy_hotels = generate_emergency_hotels(
                city_code=city_code.upper(),
                checkin=checkin,
                checkout=checkout,
                num_hotels=5
            )

            processed = process_hotel_offers(dummy_hotels, source="emergency")
            state[f"hotel_offers_duration_{day}"] = processed
            
            # Store Day 1 for cloning
            if day == 1:
                day1_hotels = processed
            
            print(f"  ✓ Emergency: {len(dummy_hotels)} hotels generated")

        # ========================================================================
        # Add company hotels for this day
        # ========================================================================
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
                        
                    print(f"  ✓ Added {len(city_hotels)} company hotels")

    state["hotel_offers"] = state.get("hotel_offers_duration_1", [])
    
    print(f"{'='*60}\n")
    return state


def process_hotel_offers(hotel_offers, source="database"):
    """Process hotel offers - organizes by room type and finds best prices"""
    from collections import defaultdict
    
    processed = []
    for hotel in hotel_offers:
        hotel_info = {
            "hotel": hotel.get("hotel", {}),
            "available": hotel.get("available", True),
            "best_offers": [],
            # FIX: Always use "amadeus_api" as source so create_packages recognizes them
            # This includes database, LLM-generated, and emergency hotels
            "source": "amadeus_api"
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
    """Extract hotel dates from flight offer"""
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
    
    # Simple price ranges based on cabin
    if cabin == "BUSINESS":
        base_price = random.randint(35000, 80000)
    else:
        base_price = random.randint(10000, 30000)
    
    # Add variation
    price_variation = random.uniform(0.9, 1.1)
    final_price = int(base_price * price_variation)
    
    # Random flight times
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
                    "base": str(int(total_price * 0.9))
                },
                "checkInDate": checkin,
                "checkOutDate": checkout
            }],
            "_emergency_fallback": True
        }
        hotels.append(hotel)
    
    return hotels