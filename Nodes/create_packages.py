from Models.TravelSearchState import TravelSearchState
from datetime import datetime
from typing import Dict, List, Any

def create_packages(state: TravelSearchState) -> TravelSearchState:
    """Create 7 travel packages by matching flight offers with their corresponding hotel offers."""

    flights_by_day = [state.get(f"flight_offers_day_{i}", []) for i in range(1, 8)]
    hotels_by_duration = [state.get(f"hotel_offers_duration_{i}", []) for i in range(1, 8)]

    packages = []

    for day in range(1, 8):
        package = create_single_package(
            package_id=day,
            flights=flights_by_day[day-1],
            hotels=hotels_by_duration[day-1],
            checkin_date=state.get(f"checkin_date_day_{day}"),
            checkout_date=state.get(f"checkout_date_day_{day}")
        )
        if package:
            packages.append(package)

    state["travel_packages"] = packages
    return state

def create_single_package(package_id: int, flights: List[Dict[str, Any]], hotels: List[Dict[str, Any]],
                         checkin_date: str, checkout_date: str) -> Dict[str, Any]:
    """Create a single travel package from flight and hotel data."""

    if not flights or not checkin_date or not checkout_date:
        return None

    try:
        flight = flights[0] if flights else {}
        flight_price = float(flight.get("price", {}).get("total", 0)) if flight else 0
        flight_currency = flight.get("price", {}).get("currency", "EGP") if flight else "EGP"
        search_date = flight.get("_search_date", "unknown") if flight else "unknown"

        checkin_dt = datetime.strptime(checkin_date, "%Y-%m-%d") if checkin_date else None
        checkout_dt = datetime.strptime(checkout_date, "%Y-%m-%d") if checkout_date else None
        duration_nights = (checkout_dt - checkin_dt).days if checkin_dt and checkout_dt else 0

        api_hotels = [h for h in hotels if h.get("source") == "amadeus_api"]
        company_hotels = [h for h in hotels if h.get("source") == "company_excel"]
        total_hotels = len(hotels)
        available_hotels = [h for h in hotels if h.get("available", True) and h.get("best_offers")]

        def get_hotel_price(hotel):
            try:
                if hotel.get("best_offers") and len(hotel["best_offers"]) > 0:
                    return float(hotel["best_offers"][0]["offer"].get("price", {}).get("total", float('inf')))
                return float('inf')
            except Exception:
                return float('inf')

        api_hotels_sorted = sorted(api_hotels, key=get_hotel_price)
        company_hotels_sorted = sorted(company_hotels, key=get_hotel_price)

        min_hotel_price = 0
        hotel_currency = flight_currency
        if available_hotels:
            cheapest_hotel = min(available_hotels, key=get_hotel_price)
            if cheapest_hotel.get("best_offers"):
                min_hotel_price = float(cheapest_hotel["best_offers"][0]["offer"].get("price", {}).get("total", 0))
                hotel_currency = cheapest_hotel["best_offers"][0].get("currency", flight_currency)

        flight_offers = [
            {
                "offer": flight,
                "price": float(flight.get("price", {}).get("total", 0)),
                "currency": flight.get("price", {}).get("currency", "EGP"),
                "summary": get_flight_summary(flight)
            } for flight in flights
        ]

        package = {
            "package_id": package_id,
            "search_date": search_date,
            "travel_dates": {
                "checkin": checkin_date,
                "checkout": checkout_date,
                "duration_nights": duration_nights
            },
            "flight_offers": flight_offers,
            "hotels": {
                "api_hotels": {
                    "total_found": len(api_hotels),
                    "available_count": len([h for h in api_hotels if h.get("available", True)]),
                    "top_options": api_hotels_sorted[:5],
                    "min_price": min([get_hotel_price(h) for h in api_hotels] or [0]),
                    "currency": hotel_currency
                },
                "company_hotels": {
                    "total_found": len(company_hotels),
                    "available_count": len([h for h in company_hotels if h.get("available", True)]),
                    "top_options": company_hotels_sorted[:5],
                    "min_price": min([get_hotel_price(h) for h in company_hotels] or [0]),
                    "currency": hotel_currency
                },
                "total_found": total_hotels,
                "available_count": len(available_hotels),
                "min_price": min_hotel_price,
                "currency": hotel_currency
            },
            "pricing": {
                "flight_price": flight_price,
                "min_hotel_price": min_hotel_price,
                "total_min_price": flight_price + min_hotel_price,
                "currency": flight_currency
            },
            "package_summary": f"Package {package_id}: {duration_nights} nights, "
                              f"flight price {flight_price:,.2f} {flight_currency}, "
                              f"{len(available_hotels)} hotels available from {min_hotel_price:,.2f} {hotel_currency}"
        }

        return package

    except Exception:
        return None

def get_flight_summary(flight: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary of flight information with enhanced details."""

    try:
        itineraries = flight.get("itineraries", [])
        if not itineraries:
            return {"error": "No itineraries found"}

        summary = {
            "trip_type": "round_trip" if len(itineraries) > 1 else "one_way",
            "numberOfBookableSeats": flight.get("numberOfBookableSeats", 0),
            "outbound": None,
            "return": None
        }

        outbound = itineraries[0]
        outbound_segments = outbound.get("segments", [])

        if outbound_segments:
            first_segment = outbound_segments[0]
            last_segment = outbound_segments[-1]

            # Extract flight details from segments
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

        if len(itineraries) > 1:
            return_itinerary = itineraries[1]
            return_segments = return_itinerary.get("segments", [])

            if return_segments:
                first_return = return_segments[0]
                last_return = return_segments[-1]

                # Extract return flight details from segments
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

    except Exception:
        return {"error": "Failed to create summary"}
