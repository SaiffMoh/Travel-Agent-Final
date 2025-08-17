from Models.TravelSearchState import TravelSearchState
from datetime import datetime
from typing import Dict, List, Any, Optional

def create_packages(state: TravelSearchState) -> TravelSearchState:
    """Create 3 travel packages by matching flight offers with their corresponding hotel offers."""
    
    # Get flight offers for each day
    flight_day_1 = state.get("flight_offers_day_1", [])
    flight_day_2 = state.get("flight_offers_day_2", [])  
    flight_day_3 = state.get("flight_offers_day_3", [])
    
    # Get hotel offers for each duration
    hotel_duration_1 = state.get("hotel_offers_duration_1", [])
    hotel_duration_2 = state.get("hotel_offers_duration_2", [])
    hotel_duration_3 = state.get("hotel_offers_duration_3", [])
    
    # Get hotel dates for reference
    checkin_dates = state.get("checkin_date", [])
    checkout_dates = state.get("checkout_date", [])
    
    packages = []
    
    # Create Package 1: Day 1 flights + Duration 1 hotels
    package_1 = create_single_package(
        package_id=1,
        flights=flight_day_1,
        hotels=hotel_duration_1,
        checkin_date=checkin_dates[0] if checkin_dates else None,
        checkout_date=checkout_dates[0] if checkout_dates else None
    )
    if package_1:
        packages.append(package_1)
    
    # Create Package 2: Day 2 flights + Duration 2 hotels
    package_2 = create_single_package(
        package_id=2,
        flights=flight_day_2,
        hotels=hotel_duration_2,
        checkin_date=checkin_dates[1] if len(checkin_dates) > 1 else (checkin_dates[0] if checkin_dates else None),
        checkout_date=checkout_dates[1] if len(checkout_dates) > 1 else (checkout_dates[0] if checkout_dates else None)
    )
    if package_2:
        packages.append(package_2)
    
    # Create Package 3: Day 3 flights + Duration 3 hotels
    package_3 = create_single_package(
        package_id=3,
        flights=flight_day_3,
        hotels=hotel_duration_3,
        checkin_date=checkin_dates[2] if len(checkin_dates) > 2 else (checkin_dates[0] if checkin_dates else None),
        checkout_date=checkout_dates[2] if len(checkout_dates) > 2 else (checkout_dates[0] if checkout_dates else None)
    )
    if package_3:
        packages.append(package_3)
    
    # Save packages to state
    state["travel_packages"] = packages
    state["current_node"] = "create_packages"
    
    try:
        print(f"create_packages: built {len(packages)} packages")
        for pkg in packages:
            pricing = pkg.get("pricing", {}) if isinstance(pkg, dict) else {}
            print(f"package {pkg.get('package_id')}: total_min_price={pricing.get('total_min_price')} {pricing.get('currency')}")
    except Exception as e:
        print(f"create_packages: error while printing packages debug info: {e}")
    
    return state

def create_single_package(package_id: int, flights: List[Dict[str, Any]], hotels: List[Dict[str, Any]], 
                         checkin_date: str, checkout_date: str) -> Optional[Dict[str, Any]]:
    """Create a single travel package from flight and hotel data - enhanced version."""
    
    print(f"DEBUG: Creating package {package_id} - flights: {len(flights) if flights else 0}, hotels: {len(hotels) if hotels else 0}")
    print(f"DEBUG: Package {package_id} dates - checkin: {checkin_date}, checkout: {checkout_date}")
    
    # Enhanced validation
    if not flights:
        print(f"No flights available for package {package_id}")
        return None
        
    if not checkin_date or not checkout_date:
        print(f"Missing dates for package {package_id}")
        return None
    
    try:
        # Use the first (cheapest) flight
        flight = flights[0]
        
        # Extract flight information with better error handling
        flight_price_data = flight.get("price", {})
        flight_price = float(flight_price_data.get("total", 0))
        flight_currency = flight_price_data.get("currency", "EGP")
        search_date = flight.get("_search_date", "unknown")
        
        # Calculate trip duration with validation
        try:
            checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
            checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d") 
            duration_nights = (checkout_dt - checkin_dt).days
            
            if duration_nights <= 0:
                print(f"Invalid duration for package {package_id}: {duration_nights} nights")
                return None
                
        except ValueError as e:
            print(f"Date parsing error for package {package_id}: {e}")
            return None
        
        # Process hotel data with enhanced logic
        available_hotels = []
        if hotels:
            available_hotels = [h for h in hotels 
                             if h.get("available", True) and 
                                h.get("best_offers") and 
                                len(h.get("best_offers", [])) > 0]
        
        total_hotels = len(hotels) if hotels else 0
        
        # Find minimum hotel price and best hotel details
        min_hotel_price_per_night = 0
        best_hotel_details = {}
        
        if available_hotels and available_hotels[0].get("best_offers"):
            # Get the cheapest offer from the best hotel
            best_offers = available_hotels[0]["best_offers"]
            cheapest_offer = min(best_offers, key=lambda x: x.get("offer", {}).get("price", {}).get("total", float('inf')))
            
            min_hotel_price_per_night = float(cheapest_offer.get("offer", {}).get("price", {}).get("total", 0))
            
            # Extract detailed hotel information
            hotel_info = cheapest_offer.get("hotel", {})
            offer_info = cheapest_offer.get("offer", {})
            
            best_hotel_details = {
                "name": hotel_info.get("name", "N/A"),
                "location": hotel_info.get("location", "N/A"),
                "price_per_night": min_hotel_price_per_night,
                "currency": offer_info.get("price", {}).get("currency", "EGP"),
                "room_type": offer_info.get("room", {}).get("type", "Standard Room"),
                "rating": hotel_info.get("rating", 0),
                "amenities": hotel_info.get("amenities", [])
            }
        
        # Calculate total hotel cost for the stay
        total_hotel_cost = min_hotel_price_per_night * duration_nights
        
        # Get enhanced flight summary for HTML rendering
        flight_summary = get_flight_summary_for_html(flight)
        
        # Create comprehensive package structure
        package = {
            "package_id": package_id,
            "search_date": search_date,
            "travel_dates": {
                "checkin": checkin_date,
                "checkout": checkout_date,
                "duration_nights": duration_nights,
                "checkin_formatted": checkin_dt.strftime("%B %d, %Y"),
                "checkout_formatted": checkout_dt.strftime("%B %d, %Y")
            },
            "flight": {
                "price": flight_price,
                "currency": flight_currency,
                "summary": flight_summary,
                "raw_data": flight  # Keep original flight data for reference
            },
            "hotels": {
                "total_found": total_hotels,
                "available_count": len(available_hotels),
                "min_price_per_night": min_hotel_price_per_night,
                "total_cost": total_hotel_cost,
                "currency": "EGP",
                "best_hotel": best_hotel_details,
                "best_offers": available_hotels[:5] if available_hotels else [],  # Top 5 for variety
                "raw_data": hotels  # Keep original hotel data
            },
            "pricing": {
                "flight_price": flight_price,
                "hotel_total_cost": total_hotel_cost,
                "total_min_price": flight_price + total_hotel_cost,
                "currency": flight_currency,
                "price_per_person": flight_price + total_hotel_cost,  # Assuming single occupancy
                "breakdown": {
                    "flight": f"{flight_price} {flight_currency}",
                    "hotel": f"{total_hotel_cost} {flight_currency} ({duration_nights} nights × {min_hotel_price_per_night})",
                    "total": f"{flight_price + total_hotel_cost} {flight_currency}"
                }
            },
            "package_summary": f"Package {package_id}: {duration_nights} nights, {len(available_hotels)} hotels available from {min_hotel_price_per_night} EGP/night",
            "created_at": datetime.now().isoformat(),
            "is_valid": True
        }
        
        return package
        
    except Exception as e:
        print(f"Error creating package {package_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_flight_summary_for_html(flight: Dict[str, Any]) -> Dict[str, Any]:
    """Create a simplified flight summary specifically for HTML rendering - enhanced version."""
    
    try:
        itineraries = flight.get("itineraries", [])
        if not itineraries:
            return get_empty_flight_summary()
        
        summary = {
            "trip_type": "round_trip" if len(itineraries) > 1 else "one_way",
            "outbound": None,
            "return": None
        }
        
        # Process outbound flight with enhanced data extraction
        outbound = itineraries[0]
        outbound_segments = outbound.get("segments", [])
        
        if outbound_segments:
            first_segment = outbound_segments[0]
            last_segment = outbound_segments[-1]
            
            # Extract comprehensive departure info
            departure_info = first_segment.get("departure", {})
            arrival_info = last_segment.get("arrival", {})
            
            # Calculate total flight duration
            total_duration = outbound.get("duration", "")
            
            summary["outbound"] = {
                "departure": {
                    "airport": departure_info.get("iataCode", "N/A"),
                    "airport_name": departure_info.get("name", ""),
                    "time": departure_info.get("at", ""),
                    "terminal": departure_info.get("terminal", ""),
                    "city": departure_info.get("city", "")
                },
                "arrival": {
                    "airport": arrival_info.get("iataCode", "N/A"),
                    "airport_name": arrival_info.get("name", ""),
                    "time": arrival_info.get("at", ""),
                    "terminal": arrival_info.get("terminal", ""),
                    "city": arrival_info.get("city", "")
                },
                "duration": total_duration,
                "duration_formatted": format_flight_duration(total_duration),
                "stops": len(outbound_segments) - 1,
                "airline": first_segment.get("carrierCode", ""),
                "airline_name": first_segment.get("carrier", {}).get("name", ""),
                "flight_number": first_segment.get("number", ""),
                "aircraft": first_segment.get("aircraft", {}).get("code", ""),
                "segments_count": len(outbound_segments)
            }
        else:
            summary["outbound"] = get_empty_flight_leg()
        
        # Process return flight if exists
        if len(itineraries) > 1:
            return_itinerary = itineraries[1]
            return_segments = return_itinerary.get("segments", [])
            
            if return_segments:
                first_return = return_segments[0]
                last_return = return_segments[-1]
                
                return_departure = first_return.get("departure", {})
                return_arrival = last_return.get("arrival", {})
                
                summary["return"] = {
                    "departure": {
                        "airport": return_departure.get("iataCode", "N/A"),
                        "airport_name": return_departure.get("name", ""),
                        "time": return_departure.get("at", ""),
                        "terminal": return_departure.get("terminal", ""),
                        "city": return_departure.get("city", "")
                    },
                    "arrival": {
                        "airport": return_arrival.get("iataCode", "N/A"),
                        "airport_name": return_arrival.get("name", ""),
                        "time": return_arrival.get("at", ""),
                        "terminal": return_arrival.get("terminal", ""),
                        "city": return_arrival.get("city", "")
                    },
                    "duration": return_itinerary.get("duration", ""),
                    "duration_formatted": format_flight_duration(return_itinerary.get("duration", "")),
                    "stops": len(return_segments) - 1,
                    "airline": first_return.get("carrierCode", ""),
                    "airline_name": first_return.get("carrier", {}).get("name", ""),
                    "flight_number": first_return.get("number", ""),
                    "aircraft": first_return.get("aircraft", {}).get("code", "")
                }
        
        return summary
        
    except Exception as e:
        print(f"Error creating flight summary for HTML: {e}")
        return get_empty_flight_summary()


def get_empty_flight_summary() -> Dict[str, Any]:
    """Return a safe fallback flight summary structure."""
    return {
        "outbound": get_empty_flight_leg(),
        "error": "Could not parse flight data"
    }


def get_empty_flight_leg() -> Dict[str, Any]:
    """Return empty flight leg structure."""
    return {
        "departure": {"airport": "N/A", "time": "", "terminal": ""},
        "arrival": {"airport": "N/A", "time": "", "terminal": ""},
        "stops": 0,
        "duration": "",
        "airline": "",
        "flight_number": ""
    }


def format_flight_duration(duration_str: str) -> str:
    """Convert PT2H15M to readable format like '2h 15m'."""
    if not duration_str or not duration_str.startswith('PT'):
        return duration_str
    
    import re
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', duration_str)
    if match:
        hours = int(match.group(1) or '0')
        minutes = int(match.group(2) or '0')
        
        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h"
        elif minutes > 0:
            return f"{minutes}m"
        else:
            return "0m"
    
    return duration_str


# Keep the original get_flight_summary function for backward compatibility
def get_flight_summary(flight: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary of flight information (original version for compatibility)."""
    
    try:
        itineraries = flight.get("itineraries", [])
        if not itineraries:
            return {"error": "No itineraries found"}
        
        summary = {
            "trip_type": "round_trip" if len(itineraries) > 1 else "one_way",
            "outbound": None,
            "return": None
        }
        
        # Outbound flight info
        outbound = itineraries[0]
        outbound_segments = outbound.get("segments", [])
        
        if outbound_segments:
            first_segment = outbound_segments[0]
            last_segment = outbound_segments[-1]
            
            summary["outbound"] = {
                "departure": {
                    "airport": first_segment.get("departure", {}).get("iataCode", ""),
                    "time": first_segment.get("departure", {}).get("at", ""),
                    "terminal": first_segment.get("departure", {}).get("terminal", "")
                },
                "arrival": {
                    "airport": last_segment.get("arrival", {}).get("iataCode", ""),
                    "time": last_segment.get("arrival", {}).get("at", ""),
                    "terminal": last_segment.get("arrival", {}).get("terminal", "")
                },
                "duration": outbound.get("duration", ""),
                "stops": len(outbound_segments) - 1
            }
        
        # Return flight info (if exists)
        if len(itineraries) > 1:
            return_itinerary = itineraries[1]
            return_segments = return_itinerary.get("segments", [])
            
            if return_segments:
                first_return = return_segments[0]
                last_return = return_segments[-1]
                
                summary["return"] = {
                    "departure": {
                        "airport": first_return.get("departure", {}).get("iataCode", ""),
                        "time": first_return.get("departure", {}).get("at", ""),
                        "terminal": first_return.get("departure", {}).get("terminal", "")
                    },
                    "arrival": {
                        "airport": last_return.get("arrival", {}).get("iataCode", ""),
                        "time": last_return.get("arrival", {}).get("at", ""),
                        "terminal": last_return.get("arrival", {}).get("terminal", "")
                    },
                    "duration": return_itinerary.get("duration", ""),
                    "stops": len(return_segments) - 1
                }
        
        return summary
        
    except Exception as e:
        print(f"Error creating flight summary: {e}")
        return {"error": f"Failed to create summary: {str(e)}"}