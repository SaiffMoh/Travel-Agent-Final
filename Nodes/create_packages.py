from Models.TravelSearchState import TravelSearchState
from datetime import datetime
from typing import Dict, List, Any

def create_packages(state: TravelSearchState) -> TravelSearchState:
    """Create 3 travel packages and identify the optimal (benchmark) package.
    
    Supports:
    - Full packages (flights + hotels)
    - Hotels-only packages (no flights)
    - One-way flight packages (no return leg)
    """

    # Get 3 days of flight and hotel data
    flights_by_day = [state.get(f"flight_offers_day_{i}", []) for i in range(1, 4)]
    hotels_by_duration = [state.get(f"hotel_offers_duration_{i}", []) for i in range(1, 4)]

    packages = []

    for day in range(1, 4):
        package = create_single_package(
            package_id=day,
            flights=flights_by_day[day-1],
            hotels=hotels_by_duration[day-1],
            checkin_date=state.get(f"checkin_date_day_{day}"),
            checkout_date=state.get(f"checkout_date_day_{day}"),
            request_type=state.get("request_type", "packages"),
            trip_type=state.get("trip_type", "round_trip")
        )
        if package:
            packages.append(package)

    # ============================================================================
    # IDENTIFY OPTIMAL PACKAGE (BENCHMARK)
    # ============================================================================
    if packages:
        optimal_package = identify_optimal_package(packages)
        
        # Mark the optimal package
        for pkg in packages:
            pkg["is_optimal"] = (pkg["package_id"] == optimal_package["package_id"])
            
            # Calculate savings compared to optimal
            if not pkg["is_optimal"]:
                pkg["savings_vs_optimal"] = calculate_savings(pkg, optimal_package)
            else:
                pkg["savings_vs_optimal"] = None

    state["travel_packages"] = packages
    return state


def identify_optimal_package(packages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Identify the optimal package based on:
    1. Lowest total price (flight + min hotel)
    2. Best convenience (direct flights preferred)
    3. Hotel availability
    
    Returns the package that offers best overall value.
    """
    
    scored_packages = []
    
    for pkg in packages:
        score = 0
        
        # Price score (lower is better)
        flight_price = pkg.get("pricing", {}).get("flight_price", 0)
        hotel_price = pkg.get("hotels", {}).get("min_price", 0)
        
        # Normalize prices to comparable range (0-100 scale)
        # Using inverse so lower price = higher score
        price_score = 100 - min((flight_price / 1000), 100)  # Adjust denominator based on typical prices
        
        # Convenience score (direct flights = bonus)
        flight_offer = pkg.get("flight_offer")
        if flight_offer:
            summary = flight_offer.get("summary", {})
            
            outbound_stops = summary.get("outbound", {}).get("stops", 0)
            return_stops = summary.get("return", {}).get("stops", 0) if summary.get("return") else 0
            
            # Direct flights get bonus points
            if outbound_stops == 0:
                score += 20
            if return_stops == 0:
                score += 20
        
        # Hotel availability score
        available_hotels = pkg.get("hotels", {}).get("available_count", 0)
        hotel_score = min(available_hotels * 2, 20)  # Cap at 20 points
        
        # Total score
        total_score = price_score + score + hotel_score
        
        scored_packages.append({
            "package": pkg,
            "score": total_score,
            "flight_price": flight_price,
            "hotel_price": hotel_price,
            "total_price": flight_price + hotel_price
        })
    
    # Sort by total price first (primary factor), then by score
    scored_packages.sort(key=lambda x: (x["total_price"], -x["score"]))
    
    return scored_packages[0]["package"]


def calculate_savings(current_package: Dict[str, Any], optimal_package: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate how much MORE the current package costs vs optimal package.
    Returns savings breakdown (negative = you pay more).
    """
    
    current_flight = current_package.get("pricing", {}).get("flight_price", 0)
    optimal_flight = optimal_package.get("pricing", {}).get("flight_price", 0)
    
    current_hotel = current_package.get("hotels", {}).get("min_price", 0)
    optimal_hotel = optimal_package.get("hotels", {}).get("min_price", 0)
    
    flight_diff = current_flight - optimal_flight
    hotel_diff = current_hotel - optimal_hotel
    total_diff = flight_diff + hotel_diff
    
    return {
        "flight_difference": flight_diff,
        "hotel_difference": hotel_diff,
        "total_difference": total_diff,
        "flight_currency": current_package.get("pricing", {}).get("flight_currency", "EGP"),
        "hotel_currency": current_package.get("hotels", {}).get("currency", "N/A"),
        "is_more_expensive": total_diff > 0,
        "percentage_more": (total_diff / (optimal_flight + optimal_hotel) * 100) if (optimal_flight + optimal_hotel) > 0 else 0
    }


def create_single_package(package_id: int, flights: List[Dict[str, Any]], hotels: List[Dict[str, Any]],
                         checkin_date: str, checkout_date: str, request_type: str = "packages",
                         trip_type: str = "round_trip") -> Dict[str, Any]:
    """Create a single travel package from flight and hotel data.
    
    Handles:
    - Hotels-only requests (no flights)
    - One-way flights (no return leg)
    - Round trip packages (full flight + hotel)
    
    Args:
        package_id: Package identifier
        flights: List of flight offers (empty for hotels-only)
        hotels: List of hotel offers
        checkin_date: Hotel check-in date
        checkout_date: Hotel check-out date
        request_type: "flights", "hotels", or "packages"
        trip_type: "one_way" or "round_trip"
    """

    # ============================================================================
    # HOTELS-ONLY PACKAGE (NO FLIGHTS)
    # ============================================================================
    if request_type == "hotels" or (not flights and checkin_date and checkout_date):
        try:
            checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d") if checkin_date else None
            checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d") if checkout_date else None
            duration_nights = (checkout_dt - checkin_dt).days if checkin_dt and checkout_dt else 0

            # Process hotels
            api_hotels, company_hotels, total_hotels, available_hotels, min_hotel_price, hotel_currency = process_hotels(hotels)

            package = {
                "package_id": package_id,
                "search_date": checkin_date,
                "request_type": "hotels",
                "travel_dates": {
                    "checkin": checkin_date,
                    "checkout": checkout_date,
                    "duration_nights": duration_nights
                },
                "flight_offer": None,  # No flights for hotels-only
                "hotels": {
                    "api_hotels": api_hotels,
                    "company_hotels": company_hotels,
                    "total_found": total_hotels,
                    "available_count": len(available_hotels),
                    "min_price": min_hotel_price,
                    "currency": hotel_currency
                },
                "pricing": {
                    "flight_price": 0,
                    "flight_currency": "N/A",
                    "min_hotel_price": min_hotel_price,
                    "hotel_currency": hotel_currency,
                    "note": "Hotels-only package (no flights)"
                },
                "package_summary": f"Package {package_id}: {duration_nights} nights (hotels only), "
                                  f"{len(available_hotels)} hotels available from {min_hotel_price:,.2f} {hotel_currency}",
                "is_optimal": False,
                "savings_vs_optimal": None
            }

            return package

        except Exception as e:
            print(f"Error creating hotels-only package: {e}")
            return None

    # ============================================================================
    # FLIGHT + HOTEL PACKAGES (ONE-WAY OR ROUND TRIP)
    # ============================================================================
    if not flights or not checkin_date or not checkout_date:
        return None

    try:
        # Get flight data
        flight = flights[0] if flights else {}
        flight_price = float(flight.get("price", {}).get("total", 0)) if flight else 0
        flight_currency = flight.get("price", {}).get("currency", "EGP") if flight else "EGP"
        search_date = flight.get("_search_date", "unknown") if flight else "unknown"

        # Calculate duration
        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d") if checkin_date else None
        checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d") if checkout_date else None
        duration_nights = (checkout_dt - checkin_dt).days if checkin_dt and checkout_dt else 0

        # Process hotels
        api_hotels, company_hotels, total_hotels, available_hotels, min_hotel_price, hotel_currency = process_hotels(hotels)

        # Create flight offer object
        flight_offer = {
            "offer": flight,
            "price": float(flight.get("price", {}).get("total", 0)),
            "currency": flight.get("price", {}).get("currency", "EGP"),
            "summary": get_flight_summary(flight, trip_type)
        }

        # Determine package type label
        if trip_type == "one_way":
            trip_label = "one-way"
        else:
            trip_label = "round trip"

        package = {
            "package_id": package_id,
            "search_date": search_date,
            "request_type": request_type,
            "trip_type": trip_type,
            "travel_dates": {
                "checkin": checkin_date,
                "checkout": checkout_date,
                "duration_nights": duration_nights
            },
            "flight_offer": flight_offer,
            "hotels": {
                "api_hotels": api_hotels,
                "company_hotels": company_hotels,
                "total_found": total_hotels,
                "available_count": len(available_hotels),
                "min_price": min_hotel_price,
                "currency": hotel_currency
            },
            "pricing": {
                "flight_price": flight_price,
                "flight_currency": flight_currency,
                "min_hotel_price": min_hotel_price,
                "hotel_currency": hotel_currency,
                "note": "Prices in different currencies - not combined"
            },
            "package_summary": f"Package {package_id}: {duration_nights} nights ({trip_label}), "
                              f"flight price {flight_price:,.2f} {flight_currency}, "
                              f"{len(available_hotels)} hotels available from {min_hotel_price:,.2f} {hotel_currency}",
            "is_optimal": False,
            "savings_vs_optimal": None
        }

        return package

    except Exception as e:
        print(f"Error creating package: {e}")
        return None


def process_hotels(hotels: List[Dict[str, Any]]) -> tuple:
    """Process hotel data and return organized structure.
    
    Returns:
        (api_hotels, company_hotels, total_hotels, available_hotels, min_hotel_price, hotel_currency)
    """
    api_hotels_list = [h for h in hotels if h.get("source") == "amadeus_api"]
    company_hotels_list = [h for h in hotels if h.get("source") == "company_excel"]
    total_hotels = len(hotels)
    available_hotels = [h for h in hotels if h.get("available", True) and h.get("best_offers")]

    def get_hotel_price(hotel):
        try:
            if hotel.get("best_offers") and len(hotel["best_offers"]) > 0:
                return float(hotel["best_offers"][0]["offer"].get("price", {}).get("total", float('inf')))
            return float('inf')
        except Exception:
            return float('inf')

    api_hotels_sorted = sorted(api_hotels_list, key=get_hotel_price)
    company_hotels_sorted = sorted(company_hotels_list, key=get_hotel_price)

    min_hotel_price = 0
    hotel_currency = "N/A"
    if available_hotels:
        cheapest_hotel = min(available_hotels, key=get_hotel_price)
        if cheapest_hotel.get("best_offers"):
            min_hotel_price = float(cheapest_hotel["best_offers"][0]["offer"].get("price", {}).get("total", 0))
            hotel_currency = cheapest_hotel["best_offers"][0].get("currency", "N/A")

    api_hotels = {
        "total_found": len(api_hotels_list),
        "available_count": len([h for h in api_hotels_list if h.get("available", True)]),
        "top_options": api_hotels_sorted[:5],
        "min_price": min([get_hotel_price(h) for h in api_hotels_list] or [0]),
        "currency": hotel_currency if api_hotels_list else "N/A"
    }

    company_hotels = {
        "total_found": len(company_hotels_list),
        "available_count": len([h for h in company_hotels_list if h.get("available", True)]),
        "top_options": company_hotels_sorted[:5],
        "min_price": min([get_hotel_price(h) for h in company_hotels_list] or [0]),
        "currency": hotel_currency if company_hotels_list else "N/A"
    }

    return api_hotels, company_hotels, total_hotels, available_hotels, min_hotel_price, hotel_currency


def get_flight_summary(flight: Dict[str, Any], trip_type: str = "round_trip") -> Dict[str, Any]:
    """Create a summary of flight information with enhanced details.
    
    Args:
        flight: Flight offer data
        trip_type: "one_way" or "round_trip"
    """

    try:
        itineraries = flight.get("itineraries", [])
        if not itineraries:
            return {"error": "No itineraries found"}

        summary = {
            "trip_type": trip_type,
            "numberOfBookableSeats": flight.get("numberOfBookableSeats", 0),
            "outbound": None,
            "return": None
        }

        # OUTBOUND FLIGHT
        outbound = itineraries[0]
        outbound_segments = outbound.get("segments", [])

        if outbound_segments:
            first_segment = outbound_segments[0]
            last_segment = outbound_segments[-1]

            outbound_flight_details = []
            for segment in outbound_segments:
                flight_detail = {
                    "carrierCode": segment.get("carrierCode", ""),
                    "number": segment.get("number", ""),
                    "aircraft": {
                        "code": segment.get("aircraft", {}).get("code", "")
                    },
                    "operating": {
                        "carrierCode": segment.get("operating", {}).get("carrierCode", "")
                    },
                    "departure": {
                        "airport": segment.get("departure", {}).get("iataCode", ""),
                        "time": segment.get("departure", {}).get("at", ""),
                        "terminal": segment.get("departure", {}).get("terminal", "")
                    },
                    "arrival": {
                        "airport": segment.get("arrival", {}).get("iataCode", ""),
                        "time": segment.get("arrival", {}).get("at", ""),
                        "terminal": segment.get("arrival", {}).get("terminal", "")
                    },
                    "duration": segment.get("duration", "")
                }
                outbound_flight_details.append(flight_detail)

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
                "stops": len(outbound_segments) - 1,
                "flight_details": outbound_flight_details
            }

        # RETURN FLIGHT (only for round trip)
        if trip_type == "round_trip" and len(itineraries) > 1:
            return_itinerary = itineraries[1]
            return_segments = return_itinerary.get("segments", [])

            if return_segments:
                first_return = return_segments[0]
                last_return = return_segments[-1]

                return_flight_details = []
                for segment in return_segments:
                    flight_detail = {
                        "carrierCode": segment.get("carrierCode", ""),
                        "number": segment.get("number", ""),
                        "aircraft": {
                            "code": segment.get("aircraft", {}).get("code", "")
                        },
                        "operating": {
                            "carrierCode": segment.get("operating", {}).get("carrierCode", "")
                        },
                        "departure": {
                            "airport": segment.get("departure", {}).get("iataCode", ""),
                            "time": segment.get("departure", {}).get("at", ""),
                            "terminal": segment.get("departure", {}).get("terminal", "")
                        },
                        "arrival": {
                            "airport": segment.get("arrival", {}).get("iataCode", ""),
                            "time": segment.get("arrival", {}).get("at", ""),
                            "terminal": segment.get("arrival", {}).get("terminal", "")
                        },
                        "duration": segment.get("duration", "")
                    }
                    return_flight_details.append(flight_detail)

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
                    "stops": len(return_segments) - 1,
                    "flight_details": return_flight_details
                }

        return summary

    except Exception as e:
        print(f"Error creating flight summary: {e}")
        return {"error": "Failed to create summary"}