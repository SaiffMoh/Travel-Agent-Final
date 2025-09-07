import os
from typing import Dict, Any, List
from amadeus import Client, ResponseError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def flight_search_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Node function to search flights with Amadeus.
    Expects state to contain: origin, destination, departure_date
    """
    client = Client(
        client_id=os.getenv("AMADEUS_CLIENT_ID"),
        client_secret=os.getenv("AMADEUS_CLIENT_SECRET"),
          # use "test" if your keys are test keys
    )

    origin = state.get("origin")
    destination = state.get("destination")
    departure_date = state.get("departure_date")

    try:
        response = client.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=departure_date,
            adults=1,
            max=5
        )

        flight_options = []
        for offer in response.data[:5]:  # limit to first 5
            itinerary = offer["itineraries"][0]
            segments = itinerary["segments"]

            flight_options.append({
                "from": segments[0]["departure"]["iataCode"],
                "to": segments[-1]["arrival"]["iataCode"],
                "departure": segments[0]["departure"]["at"],
                "arrival": segments[-1]["arrival"]["at"],
                "airline": segments[0].get("carrierCode"),
                "flight_number": segments[0].get("number"),
                "price": offer["price"]["total"],
                "currency": offer["price"]["currency"]
            })

        return {
            "flight_options": flight_options,
            "error": None
        }

    except ResponseError as e:
        return {
            "flight_options": [],
            "error": f"Amadeus API error: {e}"
        }
    except Exception as e:
        return {
            "flight_options": [],
            "error": f"Unexpected error: {e}"
        }


def format_flight_options(flight_options: List[Dict[str, Any]]) -> str:
    """Convert structured flight data into a human-readable string."""
    if not flight_options:
        return "No flights found for the given search."

    lines = ["Here are some flight options:\n"]
    for i, option in enumerate(flight_options, 1):
        lines.append(
            f"{i}. {option['airline']} {option['flight_number']} "
            f"from {option['from']} at {option['departure']} "
            f"to {option['to']} at {option['arrival']} "
            f"→ {option['price']} {option['currency']}"
        )
    return "\n".join(lines)


# 🔹 Test the node + formatter
if __name__ == "__main__":
    state = {
        "origin": "LAX",
        "destination": "SFO",
        "departure_date": "2025-09-15"
    }

    result = flight_search_node(state)
    if result["error"]:
        print("Error:", result["error"])
    else:
        print(format_flight_options(result["flight_options"]))
