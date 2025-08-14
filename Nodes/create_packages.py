from Models.TravelSearchState import TravelSearchState
from datetime import datetime
from typing import Dict, List, Any

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
    try:
        print(f"create_packages: built {len(packages)} packages")
        for pkg in packages:
            pricing = pkg.get("pricing", {}) if isinstance(pkg, dict) else {}
            print(
                f"package {pkg.get('package_id')}: total_min_price={pricing.get('total_min_price')} {pricing.get('currency')}"
            )
    except Exception as _:
        print("create_packages: error while printing packages debug info")
    
    return state


def create_single_package(package_id: int, flights: List[Dict[str, Any]], hotels: List[Dict[str, Any]], 
                         checkin_date: str, checkout_date: str) -> Dict[str, Any]:
    """Create a single travel package from flight and hotel data."""
    
    if not flights or not checkin_date or not checkout_date:
        print(f"Insufficient data for package {package_id}")
        return None
    
    try:
        # Use the first (cheapest) flight
        flight = flights[0]
        
        # Extract flight information
        flight_price = float(flight.get("price", {}).get("total", 0))
        flight_currency = flight.get("price", {}).get("currency", "EGP")
        search_date = flight.get("_search_date", "unknown")
        
        # Calculate trip duration
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d")
        checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d") 
        duration_nights = (checkout_dt - checkin_dt).days
        
        # Process hotel data
        available_hotels = [h for h in hotels if h.get("available", True) and h.get("best_offers")]
        total_hotels = len(hotels)
        
        # Find minimum hotel price
        min_hotel_price = 0
        if available_hotels and available_hotels[0].get("best_offers"):
            min_hotel_price = float(available_hotels[0]["best_offers"][0]["offer"].get("price", {}).get("total", 0))
        
        # Get flight summary
        flight_summary = get_flight_summary(flight)
        
        package = {
            "package_id": package_id,
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
                "summary": flight_summary
            },
            "hotels": {
                "total_found": total_hotels,
                "available_count": len(available_hotels),
                "top_options": available_hotels[:5],  # Top 5 cheapest
                "min_price": min_hotel_price,
                "currency": "EGP"
            },
            "pricing": {
                "flight_price": flight_price,
                "min_hotel_price": min_hotel_price, 
                "total_min_price": flight_price + min_hotel_price,
                "currency": flight_currency
            },
            "package_summary": f"Package {package_id}: {duration_nights} nights, {len(available_hotels)} hotels available from {min_hotel_price} EGP"
        }
        
        return package
        
    except Exception as e:
        print(f"Error creating package {package_id}: {e}")
        return None


def get_flight_summary(flight: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary of flight information."""
    
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