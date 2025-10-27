from Models.TravelSearchState import TravelSearchState
from Utils.watson_config import llm_generic, ModelType
import json
import logging
from Prompts.summary_prompt import build_compact_summary_prompt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_duration(duration_str):
    """
    Parse ISO 8601 duration string (e.g., 'PT5H30M') to readable format.
    Returns: '5h 30m' or None
    """
    if not duration_str:
        return None
    
    try:
        # Remove 'PT' prefix
        duration_str = duration_str.replace('PT', '')
        
        # Extract hours and minutes
        hours = 0
        minutes = 0
        
        hours_match = re.search(r'(\d+)H', duration_str)
        if hours_match:
            hours = int(hours_match.group(1))
        
        minutes_match = re.search(r'(\d+)M', duration_str)
        if minutes_match:
            minutes = int(minutes_match.group(1))
        
        # Build readable string
        if hours and minutes:
            return f"{hours}h {minutes}m"
        elif hours:
            return f"{hours}h"
        elif minutes:
            return f"{minutes}m"
        else:
            return None
    
    except Exception:
        return None

def summarize_packages(state: TravelSearchState) -> TravelSearchState:
    """Generate LLM summary and recommendation for travel packages."""
    travel_packages = state.get("travel_packages", [])

    if not travel_packages or len(travel_packages) == 0:
        state["package_summary"] = "No travel packages found for your search. Please try different dates or destinations."
        return state

    try:
        # Create compressed summaries instead of passing full objects
        compressed_packages = []
        for pkg in travel_packages[:7]:  # Limit to 7 packages
            compressed = compress_package_for_summary(pkg)
            compressed_packages.append(compressed)
        
        # Build a concise prompt
        llm_prompt = build_compact_summary_prompt(compressed_packages)
        
        logger.info(f"Watsonx summary prompt length: {len(llm_prompt)} chars")
        logger.info(f"Watsonx summary prompt preview: {llm_prompt[:500]}...")
        
        # Use generic model with controlled token limits
        response = llm_generic.generate(
            prompt=llm_prompt,
            model_type=ModelType.GENERIC,
            params={
                'max_tokens': 1024,  # Reasonable limit for summary
                'temperature': 0.3
            }
        )
        
        state["package_summary"] = response["results"][0]["generated_text"].strip()
        logger.info(f"Watsonx summary response: {state['package_summary']}")
        
    except Exception as e:
        logger.error(f"Error summarizing packages: {e}")
        fallback_summary = create_fallback_summary(travel_packages)
        state["package_summary"] = fallback_summary

    state["current_node"] = "summarize_packages_node"
    return state


def compress_package_for_summary(package):
    """
    Extract only essential information from a package for LLM summary.
    This drastically reduces prompt size while keeping key details.
    """
    if not package:
        return None
    
    # Extract flight info (only first flight offer)
    flight_info = None
    flight_offers = package.get("flight_offers", [])
    if flight_offers:
        first_flight = flight_offers[0]
        summary = first_flight.get("summary", {})
        
        # Get outbound info
        outbound = summary.get("outbound", {})
        outbound_dep = outbound.get("departure", {})
        outbound_arr = outbound.get("arrival", {})
        
        # Get return info
        return_info = summary.get("return", {})
        return_dep = return_info.get("departure", {})
        return_arr = return_info.get("arrival", {})
        
        # Parse durations (convert ISO 8601 duration to readable format)
        outbound_duration = parse_duration(outbound.get("duration", ""))
        return_duration = parse_duration(return_info.get("duration", "")) if return_info else None
        
        flight_info = {
            "price": first_flight.get("price", 0),
            "currency": first_flight.get("currency", "EGP"),
            "outbound": {
                "from": outbound_dep.get("airport", ""),
                "to": outbound_arr.get("airport", ""),
                "departure_time": outbound_dep.get("time", "")[:16],  # Just date+time
                "arrival_time": outbound_arr.get("time", "")[:16],
                "duration": outbound_duration,
                "stops": outbound.get("stops", 0)
            },
            "return": {
                "from": return_dep.get("airport", ""),
                "to": return_arr.get("airport", ""),
                "departure_time": return_dep.get("time", "")[:16],
                "arrival_time": return_arr.get("time", "")[:16],
                "duration": return_duration,
                "stops": return_info.get("stops", 0)
            } if return_info else None,
            "alternatives": len(flight_offers)  # Number of flight options
        }
    
    # Extract hotel info (summary only)
    hotels = package.get("hotels", {})
    hotel_info = {
        "total_available": hotels.get("available_count", 0),
        "min_price": hotels.get("min_price", 0),
        "currency": hotels.get("currency", "N/A"),
        "api_hotels_count": hotels.get("api_hotels", {}).get("available_count", 0),
        "company_hotels_count": hotels.get("company_hotels", {}).get("available_count", 0)
    }
    
    # Extract dates
    travel_dates = package.get("travel_dates", {})
    
    return {
        "package_id": package.get("package_id"),
        "search_date": package.get("search_date"),
        "checkin": travel_dates.get("checkin"),
        "checkout": travel_dates.get("checkout"),
        "nights": travel_dates.get("duration_nights"),
        "flight": flight_info,
        "hotels": hotel_info
    }

def create_fallback_summary(packages):
    """Create a basic summary if LLM fails."""
    if not packages:
        return "No travel packages available."

    package_count = len(packages)
    
    # Find cheapest package by flight price (since currencies differ)
    cheapest_package = min(
        packages, 
        key=lambda x: x.get("pricing", {}).get("flight_price", float('inf'))
    )
    
    flight_price = cheapest_package.get("pricing", {}).get("flight_price", 0)
    flight_curr = cheapest_package.get("pricing", {}).get("flight_currency", "EGP")
    
    hotel_price = cheapest_package.get("hotels", {}).get("min_price", 0)
    hotel_curr = cheapest_package.get("hotels", {}).get("currency", "N/A")
    
    nights = cheapest_package.get("travel_dates", {}).get("duration_nights", 0)

    summary = f"""Great! I found {package_count} travel package{'s' if package_count != 1 else ''} for your {nights}-night trip.

The most affordable option starts from {flight_price:,.0f} {flight_curr} for flights and {hotel_price:,.0f} {hotel_curr} for hotels.

Each package offers multiple flight options and various hotel choices at different price points. I recommend comparing the departure times and hotel locations to find what works best for you. Check the details below to select your preferred combination!"""
    
    return summary