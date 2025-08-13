from Models import TravelSearchState
from datetime import datetime
from typing import Dict, List, Any

def create_packages(state: TravelSearchState) -> TravelSearchState:
    """Create travel packages by combining available flight and hotel data."""
    
    # Since this runs in parallel with API calls, we need to wait/check for data
    # or work with whatever data is available in the state
    
    flight_offers_by_date = state.get("flight_offers_by_date", {})
    flight_offers = state.get("flight_offers", [])
    hotel_offers_by_dates = state.get("hotel_offers_by_dates", {})
    hotel_offers = state.get("hotel_offers", [])
    
    # If we have the enhanced data, use it
    if flight_offers_by_date and hotel_offers_by_dates:
        return create_packages_from_enhanced_data(state, flight_offers_by_date, hotel_offers_by_dates)
    
    # Otherwise, work with basic flight and hotel data
    elif flight_offers and hotel_offers:
        return create_packages_from_basic_data(state, flight_offers, hotel_offers)
    
    else:
        # No data available yet, return empty packages
        print("No flight or hotel data available for package creation")
        state["travel_packages"] = []
        return state


def create_packages_from_basic_data(state: TravelSearchState,
                                   flight_offers: list,
                                   hotel_offers: list) -> TravelSearchState:
    """Create packages from basic flight and hotel data when enhanced data isn't available."""
    
    packages = []
    
    # Create packages by pairing each flight with hotel options
    for flight in flight_offers[:3]:  # Limit to top 3 flights
        # Extract hotel dates for this flight
        flight_checkin, flight_checkout = extract_hotel_dates_from_flight(flight)
        
        if not flight_checkin or not flight_checkout:
            continue
        
        # Calculate duration
        checkin_dt = datetime.strptime(flight_checkin, "%Y-%m-%d")
        checkout_dt = datetime.strptime(flight_checkout, "%Y-%m-%d")
        duration_nights = (checkout_dt - checkin_dt).days
        
        # Process available hotels
        available_hotels = []
        min_hotel_price = float('inf')
        
        for hotel in hotel_offers:
            if hotel.get("available", True) and hotel.get("offers"):
                processed_hotel = {
                    "hotel": hotel.get("hotel", {}),
                    "available": True,
                    "best_offers": []
                }
                
                # Find cheapest offer
                offers = hotel.get("offers", [])
                if offers:
                    cheapest = min(offers, key=lambda x: float(x.get("price", {}).get("total", float('inf'))))
                    price = float(cheapest.get("price", {}).get("total", 0))
                    
                    processed_hotel["best_offers"].append({
                        "room_type": cheapest.get("room", {}).get("type", "STANDARD"),
                        "offer": cheapest
                    })
                    
                    if price < min_hotel_price:
                        min_hotel_price = price
                
                available_hotels.append(processed_hotel)
        
        # Create package
        flight_price = float(flight.get("price", {}).get("total", 0))
        if min_hotel_price == float('inf'):
            min_hotel_price = 0
            
        package = {
            "package_id": f"basic_{flight_checkin}_{flight_checkout}",
            "search_date": flight.get("_search_date", "unknown"),
            "travel_dates": {
                "checkin": flight_checkin,
                "checkout": flight_checkout,
                "duration_nights": duration_nights
            },
            "flight": {
                "offer": flight,
                "price": flight_price,
                "currency": flight.get("price", {}).get("currency", "EGP"),
                "itinerary_summary": get_flight_summary(flight)
            },
            "hotels": {
                "available_count": len(available_hotels),
                "top_options": available_hotels[:5],
                "min_price": min_hotel_price,
                "currency": "EGP"
            },
            "total_price": flight_price + min_hotel_price,
            "currency": flight.get("price", {}).get("currency", "EGP"),
            "package_summary": f"{duration_nights} nights, {len(available_hotels)} hotels available"
        }
        
        packages.append(package)
    
    # Sort and limit to top 3
    packages.sort(key=lambda x: x["total_price"])
    state["travel_packages"] = packages[:3]
    return state


def create_packages_from_enhanced_data(state: TravelSearchState, 
                                     flight_offers_by_date: dict, 
                                     hotel_offers_by_dates: dict) -> TravelSearchState:
    """Create packages from enhanced flight and hotel data."""
    
    checkin_dates = state.get("checkin_date", [])
    checkout_dates = state.get("checkout_date", [])
    
    if not flight_offers_by_date or not hotel_offers_by_dates:
        print("Missing enhanced flight or hotel data")
        state["travel_packages"] = []
        return state
    
    packages = []
    
    # Match flights with their corresponding hotel date ranges
    for search_date, flights in flight_offers_by_date.items():
        for flight in flights:
            # Extract the hotel dates for this specific flight
            flight_checkin, flight_checkout = extract_hotel_dates_from_flight(flight)
            
            if not flight_checkin or not flight_checkout:
                continue
                
            # Find matching hotel offers for these dates
            date_key = f"{flight_checkin}_{flight_checkout}"
            matching_hotels = hotel_offers_by_dates.get(date_key, [])
            
            if not matching_hotels:
                continue
            
            # Create package
            package = create_travel_package(
                flight=flight,
                hotels=matching_hotels,
                search_date=search_date,
                checkin_date=flight_checkin,
                checkout_date=flight_checkout
            )
            
            if package:
                packages.append(package)
    
    # Sort packages by total price and select top 3
    packages.sort(key=lambda x: x["total_price"])
    state["travel_packages"] = packages[:3]
    
    return state


def create_travel_package(flight: Dict[str, Any], hotels: List[Dict[str, Any]], 
                         search_date: str, checkin_date: str, checkout_date: str) -> Dict[str, Any]:
    """Create a travel package combining flight and hotel data."""
    
    try:
        # Extract flight information
        flight_price = float(flight.get("price", {}).get("total", 0))
        flight_currency = flight.get("price", {}).get("currency", "EGP")
        
        # Calculate trip duration
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
        checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d")
        duration_nights = (checkout_dt - checkin_dt).days
        
        # Get best hotel options (top 5 cheapest available)
        available_hotels = [h for h in hotels if h.get("available", True) and h.get("best_offers")]
        best_hotels = available_hotels[:5]
        
        # Calculate minimum hotel price for package total
        min_hotel_price = 0
        if best_hotels and best_hotels[0].get("best_offers"):
            min_hotel_price = float(best_hotels[0]["best_offers"][0]["offer"].get("price", {}).get("total", 0))
        
        package = {
            "package_id": f"{search_date}_{checkin_date}_{checkout_date}",
            "search_date": search_date,
            "travel_dates": {
                "checkin": checkin_date,
                "checkout": checkout_date,
                "duration_nights": duration_nights
            },
            "flight": {
                "offer": flight,
                "price": flight_price,
                "currency": flight_currency,
                "itinerary_summary": get_flight_summary(flight)
            },
            "hotels": {
                "available_count": len(available_hotels),
                "top_options": best_hotels,
                "min_price": min_hotel_price,
                "currency": "EGP"
            },
            "total_price": flight_price + min_hotel_price,
            "currency": flight_currency,
            "package_summary": f"{duration_nights} nights, {len(available_hotels)} hotels available"
        }
        
        return package
        
    except Exception as e:
        print(f"Error creating package: {e}")
        return None


def get_flight_summary(flight: Dict[str, Any]) -> Dict[str, Any]:
    """Extract flight summary information."""
    
    try:
        itineraries = flight.get("itineraries", [])
        if not itineraries:
            return {}
        
        outbound = itineraries[0]
        outbound_segments = outbound.get("segments", [])
        
        summary = {
            "outbound": {
                "departure": None,
                "arrival": None,
                "duration": outbound.get("duration", ""),
                "stops": len(outbound_segments) - 1
            }
        }
        
        if outbound_segments:
            first_segment = outbound_segments[0]
            last_segment = outbound_segments[-1]
            
            summary["outbound"]["departure"] = {
                "airport": first_segment.get("departure", {}).get("iataCode", ""),
                "time": first_segment.get("departure", {}).get("at", "")
            }
            
            summary["outbound"]["arrival"] = {
                "airport": last_segment.get("arrival", {}).get("iataCode", ""),
                "time": last_segment.get("arrival", {}).get("at", "")
            }
        
        # Add return flight info if available
        if len(itineraries) > 1:
            return_itinerary = itineraries[1]
            return_segments = return_itinerary.get("segments", [])
            
            summary["return"] = {
                "departure": None,
                "arrival": None,
                "duration": return_itinerary.get("duration", ""),
                "stops": len(return_segments) - 1
            }
            
            if return_segments:
                first_return = return_segments[0]
                last_return = return_segments[-1]
                
                summary["return"]["departure"] = {
                    "airport": first_return.get("departure", {}).get("iataCode", ""),
                    "time": first_return.get("departure", {}).get("at", "")
                }
                
                summary["return"]["arrival"] = {
                    "airport": last_return.get("arrival", {}).get("iataCode", ""),
                    "time": last_return.get("arrival", {}).get("at", "")
                }
        
        return summary
        
    except Exception as e:
        print(f"Error creating flight summary: {e}")
        return {}


def extract_hotel_dates_from_flight(flight_offer):
    """Extract check-in and check-out dates from flight segments."""
    try:
        itineraries = flight_offer.get("itineraries", [])
        if not itineraries:
            return None, None
        
        # Extract outbound arrival date (check-in)
        outbound = itineraries[0]  # First itinerary is outbound
        outbound_segments = outbound.get("segments", [])
        if not outbound_segments:
            return None, None
            
        # Get final destination arrival time
        final_outbound_segment = outbound_segments[-1]
        outbound_arrival = final_outbound_segment.get("arrival", {}).get("at")
        
        if not outbound_arrival:
            return None, None
            
        # Parse arrival datetime and get date
        checkin_datetime = datetime.fromisoformat(outbound_arrival.replace('Z', '+00:00'))
        checkin_date = checkin_datetime.strftime("%Y-%m-%d")
        
        # Extract return departure date (check-out) if round trip
        if len(itineraries) > 1:
            return_itinerary = itineraries[1]  # Second itinerary is return
            return_segments = return_itinerary.get("segments", [])
            if return_segments:
                # Get first segment departure time (origin departure)
                first_return_segment = return_segments[0]
                return_departure = first_return_segment.get("departure", {}).get("at")
                
                if return_departure:
                    checkout_datetime = datetime.fromisoformat(return_departure.replace('Z', '+00:00'))
                    checkout_date = checkout_datetime.strftime("%Y-%m-%d")
                    return checkin_date, checkout_date
        
        # For one-way trips, assume 1 night stay
        from datetime import timedelta
        checkout_datetime = checkin_datetime + timedelta(days=1)
        checkout_date = checkout_datetime.strftime("%Y-%m-%d")
        
        return checkin_date, checkout_date
        
    except Exception as e:
        print(f"Error extracting hotel dates from flight: {e}")
        return None, None